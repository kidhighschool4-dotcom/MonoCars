"""Deterministic candidate ranking (§8.9, §12.3).

Absolute quality before relative ranking: a listing must independently be `eligible` and reach
the minimum score. If none does, nothing is selected — being the best of a bad set is not enough.
"""
from __future__ import annotations

from .normalize import stable_hash
from .schemas import Eligibility, RankingResult, ScoredCandidate
from .scoring import RankingPolicy


def rank(scored: list[ScoredCandidate], duplicate_groups: dict[str, str], policy: RankingPolicy = RankingPolicy()) -> RankingResult:
    input_ids = [s.listing_id for s in scored]
    candidate_set_hash = stable_hash(sorted(input_ids), policy.version)

    if not scored:
        return RankingResult(status="empty", selected_listing_id=None, minimum_acceptable_score=policy.minimum_acceptable_score,
                             selected_composite_score=None, members=[], reason_codes=["no_candidates"],
                             candidate_set_hash=candidate_set_hash, policy_version=policy.version)

    # Keep the best-scoring member of each duplicate group only.
    best_per_group: dict[str, ScoredCandidate] = {}
    for s in scored:
        g = duplicate_groups.get(s.listing_id, s.listing_id)
        cur = best_per_group.get(g)
        if cur is None or (s.composite_score, s.listing_id) > (cur.composite_score, cur.listing_id):
            best_per_group[g] = s
    kept = {s.listing_id for s in best_per_group.values()}

    # Stable, deterministic order: score desc, then listing id asc as tie-breaker.
    ordered = sorted(scored, key=lambda s: (-s.composite_score, s.listing_id))
    members: list[dict] = []
    for pos, s in enumerate(ordered):
        codes = list(s.reason_codes)
        qualified = (
            s.listing_id in kept
            and s.eligibility == Eligibility.ELIGIBLE
            and s.composite_score >= policy.minimum_acceptable_score
        )
        if s.listing_id not in kept:
            codes.append("duplicate_group_member")
        elif s.eligibility != Eligibility.ELIGIBLE:
            codes.append(f"not_eligible_{s.eligibility.value}")
        elif s.composite_score < policy.minimum_acceptable_score:
            codes.append("below_minimum_score")
        else:
            codes.append("qualified_above_minimum")
        members.append({
            "listing_id": s.listing_id,
            "input_position": input_ids.index(s.listing_id),
            "rank_position": pos + 1,
            "component_scores": s.component_scores,
            "penalties": s.penalties,
            "composite_score": s.composite_score,
            "eligibility": s.eligibility.value,
            "qualified": qualified,
            "selected": False,
            "reason_codes": codes,
        })

    qualified = [m for m in members if m["qualified"]]
    reasons: list[str] = []
    if not qualified:
        return RankingResult(status="no_qualifying_candidate", selected_listing_id=None,
                             minimum_acceptable_score=policy.minimum_acceptable_score, selected_composite_score=None,
                             members=members, reason_codes=["no_candidate_reached_minimum"],
                             candidate_set_hash=candidate_set_hash, policy_version=policy.version)

    top = qualified[0]
    status = "recommended"
    if len(qualified) > 1 and top["composite_score"] - qualified[1]["composite_score"] <= policy.tie_margin:
        status = "manual_review"
        reasons.append("top_candidates_tied")
    if top["composite_score"] - policy.minimum_acceptable_score <= policy.near_threshold_margin:
        status = "manual_review"
        reasons.append("top_candidate_near_threshold")

    top["selected"] = True
    top["reason_codes"].append("selected")
    return RankingResult(status=status, selected_listing_id=top["listing_id"],
                         minimum_acceptable_score=policy.minimum_acceptable_score,
                         selected_composite_score=top["composite_score"], members=members,
                         reason_codes=reasons or ["selected_above_minimum"],
                         candidate_set_hash=candidate_set_hash, policy_version=policy.version)
