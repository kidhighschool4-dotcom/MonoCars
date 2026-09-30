"""Persistence worker (§8.10): the ONLY code that writes pipeline results to Supabase.

Talks to PostgREST + Storage with the service-role key (server-side only). Every write is either an
idempotent upsert on a stable key or an append; evidence and evaluations are never overwritten.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from .normalize import fold
from .prefilter import KnownListing
from .schemas import ProductBrief, RawListingObservation, ScreenshotEvidence, SearchPlan, SearchProfile, VisionEvaluation
from .settings import Settings
from .state import check_transition


class StoreError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseStore:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        settings.require_supabase()
        self.s = settings
        self.http = client or httpx.Client(timeout=60)
        self._h = {"apikey": settings.service_role_key, "Authorization": f"Bearer {settings.service_role_key}"}

    # ── low level ──
    def _url(self, table: str) -> str:
        return f"{self.s.supabase_url}/rest/v1/{table}"

    def _check(self, r: httpx.Response) -> Any:
        if r.status_code >= 400:
            # never include headers (they carry the key)
            raise StoreError(f"{r.request.method} {r.request.url.path} → {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    def select(self, table: str, params: dict) -> list[dict]:
        return self._check(self.http.get(self._url(table), params=params, headers=self._h))

    def insert(self, table: str, rows: dict | list[dict], *, on_conflict: str | None = None,
               ignore_duplicates: bool = False, merge: bool = False) -> list[dict]:
        prefer = ["return=representation"]
        if on_conflict and ignore_duplicates:
            prefer.append("resolution=ignore-duplicates")
        elif on_conflict and merge:
            prefer.append("resolution=merge-duplicates")
        params = {"on_conflict": on_conflict} if on_conflict else None
        r = self.http.post(self._url(table), params=params, headers={**self._h, "Prefer": ",".join(prefer)},
                           content=json.dumps(rows, default=str))
        return self._check(r) or []

    def update(self, table: str, match: dict, values: dict) -> list[dict]:
        params = {k: f"eq.{v}" for k, v in match.items()}
        r = self.http.patch(self._url(table), params=params, headers={**self._h, "Prefer": "return=representation"},
                            content=json.dumps(values, default=str))
        return self._check(r) or []

    def _one(self, table: str, **eq: Any) -> dict | None:
        rows = self.select(table, {**{k: f"eq.{v}" for k, v in eq.items()}, "limit": "1"})
        return rows[0] if rows else None

    def _get_or_insert(self, table: str, row: dict, conflict: str, **lookup: Any) -> dict:
        created = self.insert(table, row, on_conflict=conflict, ignore_duplicates=True)
        if created:
            return created[0]
        existing = self._one(table, **lookup)
        if not existing:
            raise StoreError(f"could not upsert {table}")
        return existing

    # ── configuration ──
    def upsert_brief(self, b: ProductBrief) -> ProductBrief:
        row = self._get_or_insert("product_briefs", {
            "slug": b.slug, "name": b.name, "summary": b.summary, "target_customer": b.target_customer,
            "positive_signals": b.positive_signals, "hard_rejections": b.hard_rejections,
            "supported_locations": b.supported_locations, "supported_categories": b.supported_categories,
            "version": b.version}, "slug,version", slug=b.slug, version=b.version)
        return b.model_copy(update={"id": row["id"]})

    def upsert_profile(self, p: SearchProfile, brief_id: str) -> SearchProfile:
        row = self._get_or_insert("search_profiles", {
            "product_brief_id": brief_id, "slug": p.slug, "name": p.name, "intent": p.intent,
            "languages": p.languages, "locations": p.locations, "platforms": p.platforms,
            "max_queries_per_run": p.max_queries_per_run, "max_pages_per_query": p.max_pages_per_query,
            "max_listings_per_run": p.max_listings_per_run, "maximum_listing_age_days": p.maximum_listing_age_days,
            "version": p.version, "enabled": p.enabled}, "slug,version", slug=p.slug, version=p.version)
        return p.model_copy(update={"id": row["id"], "enabled": row["enabled"]})

    def save_search_terms(self, profile_id: str, plan: SearchPlan, source: str, approved_by: str | None) -> list[dict]:
        from .normalize import fold

        rows = [{"search_profile_id": profile_id, "text": q.text, "text_normalized": fold(q.text), "language": q.language,
                 "category": q.category, "priority": q.priority, "planner_version": plan.planner_version,
                 "source": source, "approved_by": approved_by, "approved_at": _now() if approved_by else None}
                for q in plan.queries]
        self.insert("search_terms", rows, on_conflict="search_profile_id,text_normalized,planner_version", ignore_duplicates=True)
        return self.approved_terms(profile_id, plan.planner_version)

    def approved_terms(self, profile_id: str, planner_version: str) -> list[dict]:
        return self.select("search_terms", {"search_profile_id": f"eq.{profile_id}", "planner_version": f"eq.{planner_version}",
                                            "approved_at": "not.is.null", "order": "priority.desc,text_normalized.asc"})

    # ── runs ──
    def create_crawl_run(self, profile_id: str, pipeline_version: str) -> dict:
        return self.insert("crawl_runs", {"search_profile_id": profile_id, "pipeline_version": pipeline_version,
                                          "status": "running", "started_at": _now()})[0]

    def finish_crawl_run(self, run_id: str, status: str, counters: dict, failure_summary: str | None = None) -> None:
        self.update("crawl_runs", {"id": run_id}, {**counters, "status": status, "completed_at": _now(),
                                                    "failure_summary": failure_summary})

    def upsert_crawl_query(self, row: dict) -> dict:
        return self._get_or_insert("crawl_queries", row, "idempotency_key", idempotency_key=row["idempotency_key"])

    def update_crawl_query(self, qid: str, values: dict) -> None:
        self.update("crawl_queries", {"id": qid}, values)

    # ── listings ──
    def upsert_listing(self, obs: RawListingObservation, *, canonical_url_hash: str, content_hash: str,
                       price_usd: int | None, location: str | None, category: str | None) -> tuple[dict, bool]:
        """Returns (row, material_change). Existing listings only get last_seen + observed fields refreshed."""
        existing = self._one("listings", canonical_url_hash=canonical_url_hash)
        observed = {
            "title_raw": obs.title_raw, "description_raw": obs.description_raw, "price_text_raw": obs.price_text_raw,
            "location_text_raw": obs.location_text_raw, "seller_display_name": obs.seller_display_name,
            "published_at_observed": obs.published_at_observed, "price_usd": price_usd,
            "location_normalized": location, "category_normalized": category, "adapter_version": obs.adapter_version,
            "content_hash": content_hash, "last_seen_at": _now(), "updated_at": _now(),
        }
        if existing:
            material = existing["content_hash"] != content_hash
            row = self.update("listings", {"id": existing["id"]}, observed)[0]
            return row, material
        row = self.insert("listings", {
            **observed, "source_platform": obs.source_platform, "source_listing_id": obs.source_listing_id,
            "source_url": obs.source_url, "canonical_url": obs.canonical_url, "canonical_url_hash": canonical_url_hash,
            "lifecycle_status": "discovered"}, on_conflict="canonical_url_hash", ignore_duplicates=True)
        if not row:  # lost a race with another worker
            return self._one("listings", canonical_url_hash=canonical_url_hash), False
        return row[0], True

    def add_observation(self, listing_id: str, run_id: str | None, obs: RawListingObservation, content_hash: str) -> None:
        payload = obs.model_dump(mode="json")
        self.insert("listing_observations", {
            "listing_id": listing_id, "crawl_run_id": run_id, "captured_at": obs.captured_at, "adapter_version": obs.adapter_version,
            "content_hash": content_hash, "observation_payload": payload, "page_state": obs.page_state.value,
        }, on_conflict="listing_id,content_hash", ignore_duplicates=True)

    def store_evidence(self, listing: dict, ev: ScreenshotEvidence, kind: str = "listing_container") -> dict:
        """Private bucket upload + immutable asset row. Same checksum → reuse (no duplicate upload)."""
        existing = self._one("listing_assets", listing_id=listing["id"], checksum_sha256=ev.checksum_sha256)
        if existing:
            return existing
        captured = ev.captured_at
        import uuid

        asset_id = str(uuid.uuid4())
        path = f"{listing['source_platform']}/{captured:%Y}/{captured:%m}/{listing['id']}/{kind}-{asset_id}.png"
        r = self.http.post(f"{self.s.supabase_url}/storage/v1/object/{self.s.evidence_bucket}/{path}",
                           headers={**self._h, "Content-Type": ev.mime_type, "x-upsert": "false"}, content=ev.png_bytes)
        self._check(r)
        return self.insert("listing_assets", {
            "id": asset_id, "listing_id": listing["id"], "storage_path": path, "checksum_sha256": ev.checksum_sha256,
            "perceptual_hash": ev.perceptual_hash, "width": ev.width, "height": ev.height, "mime_type": ev.mime_type,
            "captured_at": ev.captured_at, "viewport": ev.viewport, "source_url": ev.source_url,
            "crop_policy_version": ev.crop_policy_version, "visibility": ev.visibility, "asset_kind": kind,
        })[0]

    def save_buyer_comments(self, listing_id: str, run_id: str | None, comments: list, classifier_version: str) -> int:
        if not comments:
            return 0
        rows = [{"listing_id": listing_id, "crawl_run_id": run_id, "comment_hash": c.comment_hash,
                 "text_redacted": c.text_redacted, "signals": c.signals, "language": c.language,
                 "text_normalized": c.text_normalized, "matched_phrases": c.matched_phrases,
                 "classifier_version": classifier_version, "observed_at": _now()} for c in comments]
        return len(self.insert("listing_comments", rows, on_conflict="listing_id,comment_hash", ignore_duplicates=True))

    def download_evidence(self, storage_path: str) -> bytes:
        r = self.http.get(f"{self.s.supabase_url}/storage/v1/object/{self.s.evidence_bucket}/{storage_path}", headers=self._h)
        if r.status_code >= 400:
            raise StoreError(f"evidence download failed: {r.status_code}")
        return r.content

    def latest_observation(self, listing_id: str) -> dict | None:
        rows = self.select("listing_observations", {"listing_id": f"eq.{listing_id}", "order": "captured_at.desc", "limit": "1"})
        return rows[0] if rows else None

    def latest_asset(self, listing_id: str, kind: str = "listing_container") -> dict | None:
        rows = self.select("listing_assets", {"listing_id": f"eq.{listing_id}", "asset_kind": f"eq.{kind}",
                                              "order": "captured_at.desc", "limit": "1"})
        return rows[0] if rows else None

    def known_listings(self, exclude_ids: set[str] | None = None) -> list[KnownListing]:
        """Canonical (non-duplicate) listings with their latest screenshot hash, for dedupe."""
        rows = self.select("listings", {"select": "id,canonical_url_hash,source_platform,source_listing_id,content_hash,title_raw,"
                                        "listing_assets(perceptual_hash,captured_at,asset_kind)", "duplicate_of": "is.null",
                                        "lifecycle_status": "not.in.(duplicate,discovered)"})
        out = []
        for r in rows:
            if exclude_ids and r["id"] in exclude_ids:
                continue
            assets = sorted((a for a in r.get("listing_assets") or [] if a.get("asset_kind", "listing_container") == "listing_container"),
                            key=lambda a: a["captured_at"], reverse=True)
            out.append(KnownListing(r["id"], r["canonical_url_hash"], r["source_platform"], r["source_listing_id"],
                                    r["content_hash"], assets[0]["perceptual_hash"] if assets else None,
                                    fold(r.get("title_raw"))))
        return out

    def listings_in_state(self, states: list[str], ids: list[str] | None = None) -> list[dict]:
        params = {"lifecycle_status": f"in.({','.join(states)})", "order": "first_captured_at.asc"}
        if ids is not None:
            if not ids:
                return []
            params["id"] = f"in.({','.join(ids)})"
        return self.select("listings", params)

    # ── state machine + audit ──
    def transition(self, listing: dict, nxt: str, *, actor: str, reason: str | None = None, job_id: str | None = None,
                   idempotency_key: str | None = None, extra: dict | None = None) -> dict:
        check_transition(listing["lifecycle_status"], nxt)
        values = {"lifecycle_status": nxt, "status_reason": reason, "updated_at": _now(), **(extra or {})}
        rows = self.update("listings", {"id": listing["id"], "lifecycle_status": listing["lifecycle_status"]}, values)
        if not rows:
            raise StoreError(f"listing {listing['id']} changed state concurrently")
        self.event("listing", listing["id"], listing["lifecycle_status"], nxt, actor=actor, reason=reason,
                   job_id=job_id, idempotency_key=idempotency_key)
        return rows[0]

    def event(self, entity_type: str, entity_id: str, prev: str | None, nxt: str, *, actor: str, reason: str | None = None,
              job_id: str | None = None, idempotency_key: str | None = None, metadata: dict | None = None) -> None:
        self.insert("pipeline_events", {"entity_type": entity_type, "entity_id": entity_id, "previous_state": prev,
                                        "next_state": nxt, "actor": actor, "job_id": job_id, "reason": reason,
                                        "idempotency_key": idempotency_key, "metadata": metadata or {}},
                    on_conflict="idempotency_key" if idempotency_key else None, ignore_duplicates=bool(idempotency_key))

    def record_failure(self, job_type: str, entity_id: str | None, idem: str | None, err: Exception, *, retryable: bool,
                       attempt: int, terminal: bool, correlation: dict) -> None:
        self.insert("job_failures", {"job_type": job_type, "entity_id": entity_id, "idempotency_key": idem,
                                     "error_class": type(err).__name__, "error_message": str(err)[:500],
                                     "retryable": retryable, "attempt": attempt, "terminal": terminal,
                                     "correlation": correlation})

    def open_review_task(self, *, idempotency_key: str, reason: str, priority: int, listing_id: str | None = None,
                         vision_evaluation_id: str | None = None, ranking_run_id: str | None = None) -> None:
        self.insert("review_tasks", {"idempotency_key": idempotency_key, "reason": reason, "priority": priority,
                                     "listing_id": listing_id, "vision_evaluation_id": vision_evaluation_id,
                                     "ranking_run_id": ranking_run_id},
                    on_conflict="idempotency_key", ignore_duplicates=True)

    # ── evaluations, scores, rankings ──
    def save_vision_evaluation(self, ev: VisionEvaluation, idempotency_key: str) -> dict:
        o = ev.output
        row = {
            "listing_id": ev.listing_id, "listing_asset_id": ev.listing_asset_id, "idempotency_key": idempotency_key,
            "model_decision": o.decision.value, "decision": ev.decision.value,
            "fit_score_percent": o.fit_score_percent, "evidence_quality_percent": o.evidence_quality_percent,
            "visual_condition_level": o.visual_condition_level, "information_quality_level": o.information_quality_level,
            "apparent_risk_level": o.apparent_risk_level, "hard_rejections_detected": o.hard_rejections_detected,
            "visible_signals": o.visible_signals, "risk_flags": o.risk_flags, "missing_information": o.missing_information,
            "cannot_determine": o.cannot_determine, "short_reason": o.short_reason, "provider": ev.provider,
            "model": ev.model, "prompt_version": ev.prompt_version, "schema_version": ev.schema_version,
            "rubric_version": ev.rubric_version, "product_brief_id": ev.product_brief_id,
            "product_brief_version": ev.product_brief_version, "input_checksum_sha256": ev.input_checksum_sha256,
            "raw_response": ev.raw_response, "latency_ms": ev.latency_ms, "usage": ev.usage,
            "evaluated_at": ev.evaluated_at,
        }
        return self._get_or_insert("vision_evaluations", row, "idempotency_key", idempotency_key=idempotency_key)

    def existing_evaluation(self, idempotency_key: str) -> dict | None:
        return self._one("vision_evaluations", idempotency_key=idempotency_key)

    def latest_evaluation(self, listing_id: str) -> dict | None:
        rows = self.select("vision_evaluations", {"listing_id": f"eq.{listing_id}", "order": "created_at.desc", "limit": "1"})
        return rows[0] if rows else None

    def save_score(self, row: dict) -> dict:
        return self._get_or_insert("listing_scores", row, "vision_evaluation_id,policy_version",
                                   vision_evaluation_id=row["vision_evaluation_id"], policy_version=row["policy_version"])

    def save_ranking(self, run: dict, members: list[dict]) -> tuple[dict, bool]:
        created = self.insert("ranking_runs", run, on_conflict="idempotency_key", ignore_duplicates=True)
        if not created:
            return self._one("ranking_runs", idempotency_key=run["idempotency_key"]), False
        rr = created[0]
        if members:
            self.insert("ranking_members", [{**m, "ranking_run_id": rr["id"]} for m in members])
        return rr, True

    def profile_listing_ids(self, profile_id: str, since_iso: str) -> list[str]:
        """Listings observed by any version of this search profile (same slug) inside the window."""
        me = self._one("search_profiles", id=profile_id)
        versions_ = self.select("search_profiles", {"slug": f"eq.{me['slug']}", "select": "id"}) if me else []
        ids = ",".join(v["id"] for v in versions_) or profile_id
        runs = self.select("crawl_runs", {"search_profile_id": f"in.({ids})", "planned_at": f"gte.{since_iso}", "select": "id"})
        if not runs:
            return []
        obs = self.select("listing_observations", {"crawl_run_id": f"in.({','.join(r['id'] for r in runs)})", "select": "listing_id"})
        return sorted({o["listing_id"] for o in obs})
