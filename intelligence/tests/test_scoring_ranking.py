import random

import pytest

from fbm_intel.ranking import rank
from fbm_intel.schemas import Decision, Eligibility, RankingCandidate, VisionModelOutput
from fbm_intel.scoring import RankingPolicy, ScoringPolicy, route_vision_decision, score_candidate

from .conftest import GOOD_OUTPUT


def out(**kw) -> VisionModelOutput:
    return VisionModelOutput.model_validate({**GOOD_OUTPUT, **kw})


class TestVisionRouting:
    def test_good_stays_good(self):
        assert route_vision_decision(out())[0] == Decision.GOOD

    def test_good_below_thresholds_becomes_review(self):
        d, reasons = route_vision_decision(out(fit_score_percent=70))
        assert d == Decision.REVIEW and reasons == ["routed_review_good_below_thresholds"]

    def test_risky_good_becomes_review(self):
        assert route_vision_decision(out(apparent_risk_level=3))[0] == Decision.REVIEW

    def test_low_evidence_is_insufficient(self):
        assert route_vision_decision(out(evidence_quality_percent=40))[0] == Decision.INSUFFICIENT_EVIDENCE

    def test_visible_hard_rejection_forces_reject(self):
        assert route_vision_decision(out(hard_rejections_detected=["Rental only"]))[0] == Decision.REJECT


def cand(lid="a", **kw) -> RankingCandidate:
    base = dict(listing_id=lid, eligibility=Eligibility.MANUAL_REVIEW, vision_decision=Decision.GOOD, fit_score_percent=90,
                evidence_quality_percent=90, information_quality_level=4, visual_condition_level=4,
                apparent_risk_level=1, freshness_score_percent=90, duplicate_group=lid, price_usd=15000)
    base.update(kw)
    return RankingCandidate(**base)


class TestScoring:
    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValueError):
            ScoringPolicy(w_fit=0.9)

    def test_eligible_candidate(self):
        s = score_candidate(cand())
        assert s.eligibility == Eligibility.ELIGIBLE
        assert s.composite_score == pytest.approx(0.4 * 90 + 0.2 * 90 + 0.15 * 75 + 0.1 * 75 + 0.15 * 90)

    def test_hard_rejection_cannot_be_offset(self):
        s = score_candidate(cand(fit_score_percent=100, evidence_quality_percent=100, hard_rejection_flags=["rental_only"]))
        assert s.eligibility == Eligibility.REJECTED and s.composite_score == 0.0
        assert "gate_hard_rejection" in s.reason_codes

    @pytest.mark.parametrize("kw,code", [
        ({"vision_decision": Decision.INSUFFICIENT_EVIDENCE}, "gate_insufficient_evidence"),
        ({"evidence_quality_percent": 55}, "gate_low_evidence_quality"),
        ({"apparent_risk_level": 4}, "gate_critical_risk"),
        ({"vision_decision": Decision.REVIEW}, "gate_vision_review"),
    ])
    def test_gates_route_to_manual_review(self, kw, code):
        s = score_candidate(cand(**kw))
        assert s.eligibility == Eligibility.MANUAL_REVIEW and code in s.reason_codes

    def test_penalties(self):
        s = score_candidate(cand(price_usd=None, apparent_risk_level=3, missing_information=["a", "b", "c"]))
        assert s.penalties == {"risk": 5.0, "missing_price": 5.0, "missing_information": 3.0}
        assert "missing_price" in s.reason_codes


class TestRanking:
    POLICY = RankingPolicy(minimum_acceptable_score=75, near_threshold_margin=3, tie_margin=1)

    def scored(self, *cands):
        return [score_candidate(c) for c in cands]

    def test_selects_best_above_minimum(self):
        r = rank(self.scored(cand("a"), cand("b", fit_score_percent=70)), {}, self.POLICY)
        assert r.status == "recommended" and r.selected_listing_id == "a"
        assert [m["listing_id"] for m in r.members] == ["a", "b"]
        assert all("component_scores" in m and "reason_codes" in m for m in r.members)

    def test_no_winner_when_all_below_minimum(self):
        poor = [cand(x, fit_score_percent=40, evidence_quality_percent=62, freshness_score_percent=10) for x in "abc"]
        r = rank(self.scored(*poor), {}, self.POLICY)
        assert r.status == "no_qualifying_candidate" and r.selected_listing_id is None
        assert all("below_minimum_score" in m["reason_codes"] for m in r.members)

    def test_manual_review_candidates_never_selected(self):
        r = rank(self.scored(cand("a", vision_decision=Decision.REVIEW)), {}, self.POLICY)
        assert r.selected_listing_id is None and r.members[0]["reason_codes"][-1] == "not_eligible_manual_review"

    def test_deterministic_regardless_of_input_order(self):
        cands = [cand(x, fit_score_percent=80 + i) for i, x in enumerate("abcdef")]
        orders = []
        for seed in range(5):
            random.Random(seed).shuffle(cands)
            orders.append([m["listing_id"] for m in rank(self.scored(*cands), {}, self.POLICY).members])
        assert all(o == orders[0] for o in orders)

    def test_exact_tie_breaks_by_id_and_routes_to_review(self):
        r = rank(self.scored(cand("b"), cand("a")), {}, self.POLICY)
        assert r.selected_listing_id == "a" and r.status == "manual_review" and "top_candidates_tied" in r.reason_codes

    def test_near_threshold_routes_to_review(self):
        # composite ≈ 76.5, within 3 of the 75 minimum
        r = rank(self.scored(cand("a", fit_score_percent=80, evidence_quality_percent=78, freshness_score_percent=70)), {}, self.POLICY)
        assert r.selected_listing_id == "a" and r.status == "manual_review" and "top_candidate_near_threshold" in r.reason_codes

    def test_duplicate_group_keeps_single_best(self):
        r = rank(self.scored(cand("a"), cand("b", fit_score_percent=95)), {"a": "g", "b": "g"}, self.POLICY)
        assert r.selected_listing_id == "b"
        assert "duplicate_group_member" in next(m for m in r.members if m["listing_id"] == "a")["reason_codes"]

    def test_empty(self):
        assert rank([], {}, self.POLICY).status == "empty"
