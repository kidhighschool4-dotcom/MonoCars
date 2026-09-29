"""Deterministic vision routing, eligibility gates and composite scoring (§8.7, §8.8, §11).

Business weights live here, versioned — never in the model prompt.
A hard rejection can never be offset by good component scores (non-compensating gates).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import versions
from .schemas import Decision, Eligibility, RankingCandidate, ScoredCandidate, VisionModelOutput


@dataclass(frozen=True)
class VisionRoutingPolicy:
    """§11 'Example vision routing'. Thresholds are hypotheses until calibrated on labeled data."""

    insufficient_evidence_below: int = 50
    good_min_fit: int = 80
    good_min_evidence: int = 75
    good_max_risk: int = 2


def route_vision_decision(out: VisionModelOutput, policy: VisionRoutingPolicy = VisionRoutingPolicy()) -> tuple[Decision, list[str]]:
    """Python has the final say on the decision; the model's own label is stored alongside."""
    reasons: list[str] = []
    if out.decision == Decision.REJECT or out.hard_rejections_detected:
        if out.decision != Decision.REJECT:
            reasons.append("routed_reject_hard_rejection_visible")
        return Decision.REJECT, reasons
    if out.decision == Decision.INSUFFICIENT_EVIDENCE or out.evidence_quality_percent < policy.insufficient_evidence_below:
        if out.decision != Decision.INSUFFICIENT_EVIDENCE:
            reasons.append("routed_insufficient_low_evidence")
        return Decision.INSUFFICIENT_EVIDENCE, reasons
    meets_good = (
        out.fit_score_percent >= policy.good_min_fit
        and out.evidence_quality_percent >= policy.good_min_evidence
        and out.apparent_risk_level <= policy.good_max_risk
    )
    if meets_good and out.decision == Decision.GOOD:
        return Decision.GOOD, reasons
    if out.decision == Decision.GOOD and not meets_good:
        reasons.append("routed_review_good_below_thresholds")
    return Decision.REVIEW, reasons


@dataclass(frozen=True)
class ScoringPolicy:
    version: str = versions.ELIGIBILITY_POLICY_VERSION
    minimum_evidence_quality: int = 60
    critical_risk_level: int = 4
    # composite weights (must sum to 1.0)
    w_fit: float = 0.40
    w_evidence: float = 0.20
    w_information: float = 0.15
    w_condition: float = 0.10
    w_freshness: float = 0.15
    # penalties (points subtracted after weighting)
    risk_penalty_per_level_above_2: float = 5.0
    missing_price_penalty: float = 5.0
    missing_info_penalty_each: float = 1.0
    missing_info_penalty_cap: float = 5.0

    def __post_init__(self) -> None:
        total = self.w_fit + self.w_evidence + self.w_information + self.w_condition + self.w_freshness
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"weights must sum to 1.0, got {total}")


def level_to_percent(level: int) -> float:
    """Rubric levels 1..5 → 0..100 (1=0, 3=50, 5=100)."""
    return (level - 1) * 25.0


def score_candidate(c: RankingCandidate, policy: ScoringPolicy = ScoringPolicy()) -> ScoredCandidate:
    reasons: list[str] = []

    # ── Non-compensating gates ──
    if c.hard_rejection_flags or c.vision_decision == Decision.REJECT:
        reasons.append("gate_hard_rejection")
        eligibility = Eligibility.REJECTED
    elif c.vision_decision == Decision.INSUFFICIENT_EVIDENCE:
        reasons.append("gate_insufficient_evidence")
        eligibility = Eligibility.MANUAL_REVIEW
    elif c.evidence_quality_percent < policy.minimum_evidence_quality:
        reasons.append("gate_low_evidence_quality")
        eligibility = Eligibility.MANUAL_REVIEW
    elif c.apparent_risk_level >= policy.critical_risk_level:
        reasons.append("gate_critical_risk")
        eligibility = Eligibility.MANUAL_REVIEW
    elif c.vision_decision == Decision.REVIEW:
        reasons.append("gate_vision_review")
        eligibility = Eligibility.MANUAL_REVIEW
    else:
        eligibility = Eligibility.ELIGIBLE

    # ── Component scores (0..100) ──
    comp = {
        "fit": float(c.fit_score_percent),
        "evidence_quality": float(c.evidence_quality_percent),
        "information_quality": level_to_percent(c.information_quality_level),
        "visual_condition": level_to_percent(c.visual_condition_level),
        "freshness": float(c.freshness_score_percent),
    }
    weighted = (
        policy.w_fit * comp["fit"]
        + policy.w_evidence * comp["evidence_quality"]
        + policy.w_information * comp["information_quality"]
        + policy.w_condition * comp["visual_condition"]
        + policy.w_freshness * comp["freshness"]
    )

    penalties: dict[str, float] = {}
    if c.apparent_risk_level > 2:
        penalties["risk"] = policy.risk_penalty_per_level_above_2 * (c.apparent_risk_level - 2)
    if c.price_usd is None:
        penalties["missing_price"] = policy.missing_price_penalty
        reasons.append("missing_price")
    if c.missing_information:
        penalties["missing_information"] = min(policy.missing_info_penalty_cap, policy.missing_info_penalty_each * len(c.missing_information))

    composite = round(max(0.0, min(100.0, weighted - sum(penalties.values()))), 2)
    if eligibility == Eligibility.REJECTED:
        composite = 0.0  # a hard rejection can never rank

    return ScoredCandidate(
        listing_id=c.listing_id,
        eligibility=eligibility,
        component_scores={k: round(v, 2) for k, v in comp.items()},
        penalties={k: round(v, 2) for k, v in penalties.items()},
        composite_score=composite,
        reason_codes=reasons,
    )


@dataclass
class RankingPolicy:
    version: str = versions.RANKING_POLICY_VERSION
    minimum_acceptable_score: float = 75.0
    near_threshold_margin: float = 3.0
    tie_margin: float = 1.0
    extra: dict = field(default_factory=dict)
