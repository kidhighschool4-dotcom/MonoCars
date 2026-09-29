"""In-memory stand-in for SupabaseStore with the same method contract (used by pipeline tests).

It enforces the same invariants the database does: unique keys, append-only events, state-machine checks.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fbm_intel.prefilter import KnownListing
from fbm_intel.state import check_transition


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self):
        self.t: dict[str, list[dict]] = {k: [] for k in (
            "search_terms", "crawl_runs", "crawl_queries", "listings", "listing_observations", "listing_assets",
            "vision_evaluations", "listing_scores", "ranking_runs", "ranking_members", "review_tasks",
            "pipeline_events", "job_failures")}
        self.blobs: dict[str, bytes] = {}

    def _find(self, table, **eq):
        return next((r for r in self.t[table] if all(r.get(k) == v for k, v in eq.items())), None)

    def _add(self, table, row):
        row = {"id": str(uuid.uuid4()), "created_at": _now(), **row}
        self.t[table].append(row)
        return row

    # config
    def save_search_terms(self, profile_id, plan, source, approved_by):
        for q in plan.queries:
            if not self._find("search_terms", search_profile_id=profile_id, text=q.text, planner_version=plan.planner_version):
                self._add("search_terms", {"search_profile_id": profile_id, "text": q.text, "priority": q.priority,
                                           "planner_version": plan.planner_version, "approved_at": _now() if approved_by else None})
        return [r for r in self.t["search_terms"] if r["approved_at"]]

    # runs
    def create_crawl_run(self, profile_id, pipeline_version):
        return self._add("crawl_runs", {"search_profile_id": profile_id, "planned_at": _now(), "status": "running"})

    def finish_crawl_run(self, run_id, status, counters, failure_summary=None):
        self._find("crawl_runs", id=run_id).update(status=status, **counters)

    def upsert_crawl_query(self, row):
        return self._find("crawl_queries", idempotency_key=row["idempotency_key"]) or self._add("crawl_queries", dict(row))

    def update_crawl_query(self, qid, values):
        self._find("crawl_queries", id=qid).update(values)

    # listings
    def upsert_listing(self, obs, *, canonical_url_hash, content_hash, price_usd, location, category):
        existing = self._find("listings", canonical_url_hash=canonical_url_hash)
        observed = {"title_raw": obs.title_raw, "description_raw": obs.description_raw, "price_usd": price_usd,
                    "published_at_observed": obs.published_at_observed.isoformat() if obs.published_at_observed else None,
                    "content_hash": content_hash, "last_seen_at": _now()}
        if existing:
            material = existing["content_hash"] != content_hash
            existing.update(observed)
            return existing, material
        return self._add("listings", {**observed, "source_platform": obs.source_platform,
                                      "source_listing_id": obs.source_listing_id, "canonical_url_hash": canonical_url_hash,
                                      "lifecycle_status": "discovered", "duplicate_of": None,
                                      "first_captured_at": _now()}), True

    def add_observation(self, listing_id, run_id, obs, content_hash):
        if not self._find("listing_observations", listing_id=listing_id, content_hash=content_hash):
            self._add("listing_observations", {"listing_id": listing_id, "crawl_run_id": run_id, "content_hash": content_hash})

    def store_evidence(self, listing, ev):
        existing = self._find("listing_assets", listing_id=listing["id"], checksum_sha256=ev.checksum_sha256)
        if existing:
            return existing
        path = f"{listing['id']}/{ev.checksum_sha256}.png"
        self.blobs[path] = ev.png_bytes
        return self._add("listing_assets", {"listing_id": listing["id"], "storage_path": path, "captured_at": _now(),
                                            "checksum_sha256": ev.checksum_sha256, "perceptual_hash": ev.perceptual_hash})

    def download_evidence(self, path):
        return self.blobs[path]

    def latest_asset(self, listing_id):
        rows = [a for a in self.t["listing_assets"] if a["listing_id"] == listing_id]
        return rows[-1] if rows else None

    def known_listings(self, exclude_ids=None):
        out = []
        for r in self.t["listings"]:
            if r["duplicate_of"] or r["lifecycle_status"] in ("duplicate", "discovered") or r["id"] in (exclude_ids or set()):
                continue
            a = self.latest_asset(r["id"])
            out.append(KnownListing(r["id"], r["canonical_url_hash"], r["source_platform"], r["source_listing_id"],
                                    r["content_hash"], a["perceptual_hash"] if a else None))
        return out

    def listings_in_state(self, states, ids=None):
        return [r for r in self.t["listings"] if r["lifecycle_status"] in states and (ids is None or r["id"] in ids)]

    # state + audit
    def transition(self, listing, nxt, *, actor, reason=None, job_id=None, idempotency_key=None, extra=None):
        row = self._find("listings", id=listing["id"])
        check_transition(row["lifecycle_status"], nxt)
        self.event("listing", row["id"], row["lifecycle_status"], nxt, actor=actor, reason=reason, idempotency_key=idempotency_key)
        row.update(lifecycle_status=nxt, status_reason=reason, **(extra or {}))
        return row

    def event(self, entity_type, entity_id, prev, nxt, *, actor, reason=None, job_id=None, idempotency_key=None, metadata=None):
        if idempotency_key and self._find("pipeline_events", idempotency_key=idempotency_key):
            return
        self._add("pipeline_events", {"entity_id": entity_id, "previous_state": prev, "next_state": nxt, "actor": actor,
                                      "reason": reason, "idempotency_key": idempotency_key})

    def record_failure(self, job_type, entity_id, idem, err, *, retryable, attempt, terminal, correlation):
        self._add("job_failures", {"job_type": job_type, "error_class": type(err).__name__, "terminal": terminal})

    def open_review_task(self, *, idempotency_key, reason, priority, listing_id=None, vision_evaluation_id=None, ranking_run_id=None):
        if not self._find("review_tasks", idempotency_key=idempotency_key):
            self._add("review_tasks", {"idempotency_key": idempotency_key, "reason": reason, "listing_id": listing_id,
                                       "ranking_run_id": ranking_run_id, "status": "open"})

    # evaluations
    def save_vision_evaluation(self, ev, idempotency_key):
        existing = self._find("vision_evaluations", idempotency_key=idempotency_key)
        if existing:
            return existing
        o = ev.output
        return self._add("vision_evaluations", {
            "listing_id": ev.listing_id, "idempotency_key": idempotency_key, "decision": ev.decision.value,
            "fit_score_percent": o.fit_score_percent, "evidence_quality_percent": o.evidence_quality_percent,
            "information_quality_level": o.information_quality_level, "visual_condition_level": o.visual_condition_level,
            "apparent_risk_level": o.apparent_risk_level, "hard_rejections_detected": o.hard_rejections_detected,
            "missing_information": o.missing_information})

    def existing_evaluation(self, idempotency_key):
        return self._find("vision_evaluations", idempotency_key=idempotency_key)

    def latest_evaluation(self, listing_id):
        rows = [e for e in self.t["vision_evaluations"] if e["listing_id"] == listing_id]
        return rows[-1] if rows else None

    def save_score(self, row):
        return self._find("listing_scores", vision_evaluation_id=row["vision_evaluation_id"], policy_version=row["policy_version"]) \
            or self._add("listing_scores", dict(row))

    def save_ranking(self, run, members):
        existing = self._find("ranking_runs", idempotency_key=run["idempotency_key"])
        if existing:
            return existing, False
        rr = self._add("ranking_runs", dict(run))
        for m in members:
            self._add("ranking_members", {**m, "ranking_run_id": rr["id"]})
        return rr, True

    def profile_listing_ids(self, profile_id, since_iso):
        runs = {r["id"] for r in self.t["crawl_runs"] if r["search_profile_id"] == profile_id}
        return sorted({o["listing_id"] for o in self.t["listing_observations"] if o["crawl_run_id"] in runs})
