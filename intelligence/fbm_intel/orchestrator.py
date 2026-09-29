"""Orchestrator (§8.1): owns the state machine, budgets, retries and persistence order.

It contains no selectors (those live in adapters) and never lets model output drive control flow.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import versions
from .adapters.base import PlatformAdapter, ResultRef
from .browser import BlockedError, open_session
from .normalize import (content_hash, fold, freshness_percent, normalize_location, parse_price_usd, sha256_hex,
                        stable_hash)
from .prefilter import detect_hard_rejections, prefilter
from .ranking import rank
from .schemas import (Decision, Eligibility, ProductBrief, RankingCandidate, RawListingObservation, SearchProfile,
                      VisionModelOutput)
from .scoring import RankingPolicy, ScoringPolicy, score_candidate
from .state import IllegalTransition, S
from .store import SupabaseStore
from .vision import VisionError, VisionProvider, evaluate_screenshot

log = logging.getLogger("fbm_intel")
ACTOR = f"worker:{versions.PIPELINE_VERSION}"


@dataclass
class RunCounters:
    queries_attempted: int = 0
    pages_processed: int = 0
    listings_found: int = 0
    listings_captured: int = 0
    duplicates: int = 0
    prefilter_rejected: int = 0
    blocks: int = 0
    errors: int = 0

    def as_row(self) -> dict:
        return dict(self.__dict__)


@dataclass
class RunReport:
    crawl_run_id: str | None = None
    counters: RunCounters = field(default_factory=RunCounters)
    captured_listing_ids: list[str] = field(default_factory=list)
    evaluated: int = 0
    vision_errors: int = 0
    scored: dict[str, int] = field(default_factory=dict)
    ranking: dict | None = None
    blocked: list[str] = field(default_factory=list)


class Pipeline:
    def __init__(self, store: SupabaseStore, provider: VisionProvider, brief: ProductBrief, profile: SearchProfile,
                 scoring_policy: ScoringPolicy = ScoringPolicy(), ranking_policy: RankingPolicy = RankingPolicy()):
        if not brief.id or not profile.id:
            raise ValueError("brief and profile must be persisted first")
        self.store, self.provider, self.brief, self.profile = store, provider, brief, profile
        self.scoring_policy, self.ranking_policy = scoring_policy, ranking_policy

    # ── 10.2 collection ─────────────────────────────────────────────────────
    def crawl(self, adapter: PlatformAdapter, terms: list[dict], report: RunReport, *, listing_budget: int | None = None) -> None:
        if not self.profile.enabled:
            raise RuntimeError("search profile is disabled")
        access = adapter.validate_access()
        if not access.allowed:
            raise PermissionError(f"{adapter.platform}: {access.reason}")
        budget = min(listing_budget or self.profile.max_listings_per_run, self.profile.max_listings_per_run)
        seen_urls: set[str] = set()
        with open_session(adapter.allowed_hosts, adapter.min_interval_s) as s:
            for term in terms[: self.profile.max_queries_per_run]:
                if len(seen_urls) >= budget:
                    break
                idem = stable_hash(report.crawl_run_id, adapter.platform, term["id"], 1)
                q = self.store.upsert_crawl_query({"crawl_run_id": report.crawl_run_id, "platform": adapter.platform,
                                                   "search_term_id": term["id"], "query_text": term["text"],
                                                   "idempotency_key": idem, "status": "running",
                                                   "started_at": datetime.now(timezone.utc).isoformat()})
                report.counters.queries_attempted += 1
                try:
                    state = adapter.open_search(s, term["text"])
                    if state is None:
                        self.store.update_crawl_query(q["id"], {"status": "skipped"})
                        continue
                    refs: list[ResultRef] = []
                    pages = 0
                    while not state.done and pages < self.profile.max_pages_per_query:
                        refs += adapter.collect_result_refs(s, state)
                        pages += 1
                        state = adapter.advance(s, state)
                    report.counters.pages_processed += pages
                    new_refs = [r for r in refs if r.url not in seen_urls]
                    report.counters.listings_found += len(new_refs)
                    self.store.update_crawl_query(q["id"], {"status": "completed", "pages_processed": pages,
                                                            "results_found": len(refs),
                                                            "completed_at": datetime.now(timezone.utc).isoformat()})
                    for ref in new_refs:
                        if len(seen_urls) >= budget:
                            break
                        seen_urls.add(ref.url)
                        self.capture_one(adapter, s, ref, report)
                except BlockedError as e:
                    # §8.3: stop this platform immediately, never retry automatically
                    report.counters.blocks += 1
                    report.blocked.append(f"{adapter.platform}: {e.status.value}")
                    self.store.update_crawl_query(q["id"], {"status": "blocked", "block_status": e.status.value,
                                                            "completed_at": datetime.now(timezone.utc).isoformat()})
                    log.warning("stopping %s: %s", adapter.platform, e)
                    return
                except Exception as e:  # noqa: BLE001 — record and continue with the next query
                    report.counters.errors += 1
                    self.store.update_crawl_query(q["id"], {"status": "failed", "error": str(e)[:300]})
                    self.store.record_failure("crawl_query", None, idem, e, retryable=True, attempt=1, terminal=False,
                                              correlation={"crawl_run_id": report.crawl_run_id, "query": term["text"]})

    def capture_one(self, adapter: PlatformAdapter, s, ref: ResultRef, report: RunReport) -> str | None:
        """Open listing → observe → focused screenshot → persist listing/observation/asset → prefilter."""
        adapter.open_listing(s, ref)  # BlockedError propagates to stop the platform
        obs = adapter.extract_observation(s, ref)
        evidence = adapter.capture_evidence(s, ref.url) if obs.page_state.value == "ok" else None
        return self.persist_capture(obs, evidence, report)

    def persist_capture(self, obs: RawListingObservation, evidence, report: RunReport) -> str | None:
        url_hash = sha256_hex(obs.canonical_url)
        c_hash = content_hash(obs.title_raw, obs.description_raw, obs.price_text_raw, obs.location_text_raw)
        category = (obs.observation_payload.get("body_type") or None) if isinstance(obs.observation_payload, dict) else None
        listing, material = self.store.upsert_listing(
            obs, canonical_url_hash=url_hash, content_hash=c_hash, price_usd=parse_price_usd(obs.price_text_raw),
            location=normalize_location(obs.location_text_raw), category=fold(category) or None)
        self.store.add_observation(listing["id"], report.crawl_run_id, obs, c_hash)

        cur = listing["lifecycle_status"]
        if cur != S.DISCOVERED.value and not material:
            return listing["id"]  # §10.6: no material change → last_seen only, no re-evaluation
        asset = self.store.store_evidence(listing, evidence) if evidence else None
        try:
            listing = self.store.transition(listing, S.CAPTURED.value, actor=ACTOR,
                                            reason="recaptured_material_change" if cur != S.DISCOVERED.value else None,
                                            idempotency_key=stable_hash("capture", obs.source_platform, obs.canonical_url, c_hash))
        except IllegalTransition:
            # e.g. already approved or mid-evaluation: keep the state, but leave an audit trail of the change
            self.store.event("listing", listing["id"], cur, cur, actor=ACTOR, reason="material_change_not_reprocessed",
                             idempotency_key=stable_hash("material-change", listing["id"], c_hash))
            return listing["id"]
        report.counters.listings_captured += 1
        report.captured_listing_ids.append(listing["id"])

        self._prefilter(listing, obs, asset, url_hash, c_hash, report)
        return listing["id"]

    def _prefilter(self, listing: dict, obs: RawListingObservation, asset: dict | None, url_hash: str, c_hash: str,
                   report: RunReport) -> None:
        known = self.store.known_listings(exclude_ids={listing["id"]})
        result = prefilter(obs, listing_id=listing["id"], canonical_url_hash=url_hash, content_hash=c_hash,
                           perceptual_hash=asset["perceptual_hash"] if asset else None, has_screenshot=asset is not None,
                           brief=self.brief, known=known, max_age_days=self.profile.maximum_listing_age_days)
        if result.outcome == "duplicate":
            report.counters.duplicates += 1
            self.store.transition(listing, S.DUPLICATE.value, actor=ACTOR, reason=",".join(result.reason_codes),
                                  extra={"duplicate_of": result.duplicate_of})
        elif result.outcome == "reject":
            report.counters.prefilter_rejected += 1
            self.store.transition(listing, S.PREFILTER_REJECTED.value, actor=ACTOR, reason=",".join(result.reason_codes))
        else:
            self.store.transition(listing, S.VISION_PENDING.value, actor=ACTOR)

    def reprefilter(self, report: RunReport, states: tuple[str, ...] = (S.PREFILTER_REJECTED.value, S.DUPLICATE.value)) -> int:
        """Re-run the deterministic prefilter under the CURRENT brief/profile versions, using stored evidence.

        Used after a policy change (e.g. a new maximum listing age). No re-crawl, no vision call here.
        """
        n = 0
        for listing in self.store.listings_in_state(list(states)):
            o = self.store.latest_observation(listing["id"])
            if not o:
                continue
            obs = RawListingObservation.model_validate(o["observation_payload"])
            asset = self.store.latest_asset(listing["id"])
            listing = self.store.transition(
                listing, S.CAPTURED.value, actor=ACTOR,
                reason=f"reprefilter:{self.profile.slug}@v{self.profile.version}",
                extra={"duplicate_of": None})
            self._prefilter(listing, obs, asset, listing["canonical_url_hash"], listing["content_hash"], report)
            n += 1
        return n

    # ── 10.3 screenshot evaluation ──────────────────────────────────────────
    def evaluate_pending(self, report: RunReport, listing_ids: list[str] | None = None, max_attempts: int = 2) -> None:
        for listing in self.store.listings_in_state([S.VISION_PENDING.value, S.RETRYABLE_ERROR.value], listing_ids):
            asset = self.store.latest_asset(listing["id"])
            if not asset:
                continue
            idem = stable_hash("vision", asset["checksum_sha256"], versions.VISION_PROMPT_VERSION, versions.RUBRIC_VERSION,
                               self.provider.model, self.brief.id, self.brief.version)
            if listing["lifecycle_status"] == S.RETRYABLE_ERROR.value:
                listing = self.store.transition(listing, S.VISION_PENDING.value, actor=ACTOR, reason="retry")
            listing = self.store.transition(listing, S.VISION_PROCESSING.value, actor=ACTOR)
            existing = self.store.existing_evaluation(idem)
            try:
                if existing:  # idempotent: never pay twice for the same evidence + prompt + rubric + model
                    decision = existing["decision"]
                else:
                    png = self.store.download_evidence(asset["storage_path"])
                    ev = None
                    for attempt in range(1, max_attempts + 1):
                        try:
                            ev = evaluate_screenshot(self.provider, png=png, checksum=asset["checksum_sha256"],
                                                     listing_id=listing["id"], listing_asset_id=asset["id"], brief=self.brief)
                            break
                        except VisionError as e:
                            if not e.retryable or attempt == max_attempts:
                                raise
                    self.store.save_vision_evaluation(ev, idem)
                    decision = ev.decision.value
                    report.evaluated += 1
            except Exception as e:  # noqa: BLE001
                report.vision_errors += 1
                retryable = getattr(e, "retryable", False)
                self.store.record_failure("evaluate_screenshot", listing["id"], idem, e, retryable=retryable,
                                          attempt=max_attempts, terminal=not retryable,
                                          correlation={"listing_id": listing["id"], "asset_id": asset["id"]})
                nxt = S.RETRYABLE_ERROR if retryable else S.TERMINAL_ERROR
                self.store.transition(listing, nxt.value, actor=ACTOR, reason=f"{type(e).__name__}: {str(e)[:120]}")
                if not retryable:  # §14.3: don't silently drop a listing
                    self.store.open_review_task(idempotency_key=stable_hash("review-vision-failure", idem),
                                                reason="vision_evaluation_failed", priority=40, listing_id=listing["id"])
                continue
            state = {"good": S.VISION_GOOD, "review": S.VISION_REVIEW, "reject": S.VISION_REJECTED,
                     "insufficient_evidence": S.INSUFFICIENT_EVIDENCE}[decision]
            self.store.transition(listing, state.value, actor=ACTOR, idempotency_key=stable_hash("vision-done", idem))

    # ── 10.4 eligibility + scoring ──────────────────────────────────────────
    def score_evaluated(self, report: RunReport, listing_ids: list[str] | None = None) -> None:
        states = [S.VISION_GOOD.value, S.VISION_REVIEW.value, S.VISION_REJECTED.value, S.INSUFFICIENT_EVIDENCE.value]
        for listing in self.store.listings_in_state(states, listing_ids):
            ev = self.store.latest_evaluation(listing["id"])
            if not ev:
                continue
            listing = self.store.transition(listing, S.SCORING_PENDING.value, actor=ACTOR)
            cand = self.candidate(listing, ev)
            scored = score_candidate(cand, self.scoring_policy)
            row = self.store.save_score({
                "listing_id": listing["id"], "vision_evaluation_id": ev["id"], "policy_version": self.scoring_policy.version,
                "eligibility": scored.eligibility.value, "reason_codes": scored.reason_codes,
                "component_scores": scored.component_scores, "penalties": scored.penalties,
                "composite_score": scored.composite_score})
            listing = self.store.transition(listing, S.SCORED.value, actor=ACTOR)
            listing = self.store.transition(listing, scored.eligibility.value, actor=ACTOR,
                                            reason=",".join(scored.reason_codes) or None)
            report.scored[scored.eligibility.value] = report.scored.get(scored.eligibility.value, 0) + 1
            if scored.eligibility == Eligibility.MANUAL_REVIEW:
                self.store.open_review_task(idempotency_key=stable_hash("review-eligibility", row["id"]),
                                            reason=",".join(scored.reason_codes) or "manual_review", priority=50,
                                            listing_id=listing["id"], vision_evaluation_id=ev["id"])

    def candidate(self, listing: dict, ev: dict) -> RankingCandidate:
        published = listing.get("published_at_observed")
        published_dt = datetime.fromisoformat(published) if published else None
        text_flags = detect_hard_rejections(listing.get("title_raw"), listing.get("description_raw"))
        return RankingCandidate(
            listing_id=listing["id"],
            eligibility=Eligibility.MANUAL_REVIEW,  # recomputed by score_candidate
            vision_decision=Decision(ev["decision"]),
            fit_score_percent=ev["fit_score_percent"],
            evidence_quality_percent=ev["evidence_quality_percent"],
            information_quality_level=ev["information_quality_level"],
            visual_condition_level=ev["visual_condition_level"],
            apparent_risk_level=ev["apparent_risk_level"],
            freshness_score_percent=freshness_percent(published_dt, self.profile.maximum_listing_age_days),
            hard_rejection_flags=sorted(set(text_flags) | set(ev.get("hard_rejections_detected") or [])),
            missing_information=ev.get("missing_information") or [],
            duplicate_group=listing.get("duplicate_of") or listing["id"],
            price_usd=listing.get("price_usd"),
        )

    # ── 10.5 ranking ────────────────────────────────────────────────────────
    def rank_profile(self, report: RunReport, window_days: int = 30) -> dict:
        since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        ids = self.store.profile_listing_ids(self.profile.id, since)
        listings = self.store.listings_in_state([S.ELIGIBLE.value, S.MANUAL_REVIEW.value, S.RANKED.value,
                                                 S.NOT_SELECTED.value], ids)
        scored = []
        groups: dict[str, str] = {}
        for l in listings:
            ev = self.store.latest_evaluation(l["id"])
            if not ev:
                continue
            sc = score_candidate(self.candidate(l, ev), self.scoring_policy)
            scored.append(sc)
            groups[l["id"]] = l.get("duplicate_of") or l["id"]
        result = rank(scored, groups, self.ranking_policy)
        evidence_versions = sorted((l["id"], l["content_hash"]) for l in listings)
        idem = stable_hash("ranking", result.candidate_set_hash, self.ranking_policy.version, evidence_versions)
        run_row = {
            "search_profile_id": self.profile.id, "idempotency_key": idem, "candidate_set_hash": result.candidate_set_hash,
            "policy_version": result.policy_version, "status": result.status, "selected_listing_id": result.selected_listing_id,
            "minimum_acceptable_score": result.minimum_acceptable_score,
            "selected_composite_score": result.selected_composite_score,
            "component_score_summary": next((m["component_scores"] for m in result.members if m["selected"]), {}),
            "reason_codes": result.reason_codes,
        }
        members = [{"listing_id": m["listing_id"], "input_position": m["input_position"], "rank_position": m["rank_position"],
                    "component_scores": {**m["component_scores"], "penalties": m["penalties"], "eligibility": m["eligibility"]},
                    "composite_score": m["composite_score"], "qualified": m["qualified"], "selected": m["selected"],
                    "reason_codes": m["reason_codes"]} for m in result.members]
        rr, created = self.store.save_ranking(run_row, members)
        if created:
            by_id = {l["id"]: l for l in listings}
            for m in result.members:
                l = by_id[m["listing_id"]]
                if l["lifecycle_status"] in (S.ELIGIBLE.value, S.MANUAL_REVIEW.value, S.NOT_SELECTED.value, S.RANKED.value):
                    self.store.transition(l, S.RANKED.value, actor=ACTOR, reason=f"ranking_run:{rr['id']}",
                                          idempotency_key=stable_hash("ranked", rr["id"], l["id"]))
            if result.selected_listing_id:
                # Human approval is required for every recommendation in this release (§21 #8).
                self.store.open_review_task(idempotency_key=stable_hash("review-recommendation", rr["id"]),
                                            reason=f"recommendation_{result.status}", priority=80,
                                            listing_id=result.selected_listing_id, ranking_run_id=rr["id"])
        report.ranking = {"ranking_run_id": rr["id"], "status": rr["status"], "selected": rr["selected_listing_id"],
                          "score": rr["selected_composite_score"], "candidates": len(members), "new": created}
        return report.ranking


def run_id() -> str:
    return str(uuid.uuid4())


# re-exported for CLI convenience
__all__ = ["Pipeline", "RunReport", "RunCounters", "VisionModelOutput"]
