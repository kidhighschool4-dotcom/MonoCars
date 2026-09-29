"""Listing pipeline state machine (architecture §7). Code owns every transition."""
from __future__ import annotations

from enum import Enum


class S(str, Enum):
    DISCOVERED = "discovered"
    CAPTURED = "captured"
    DUPLICATE = "duplicate"
    PREFILTER_REJECTED = "prefilter_rejected"
    VISION_PENDING = "vision_pending"
    VISION_PROCESSING = "vision_processing"
    VISION_GOOD = "vision_good"
    VISION_REVIEW = "vision_review"
    VISION_REJECTED = "vision_rejected"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SCORING_PENDING = "scoring_pending"
    SCORED = "scored"
    ELIGIBLE = "eligible"
    MANUAL_REVIEW = "manual_review"
    REJECTED = "rejected"
    RANKED = "ranked"
    APPROVED = "approved"
    NOT_SELECTED = "not_selected"
    EXPIRED = "expired"
    RETRYABLE_ERROR = "retryable_error"
    TERMINAL_ERROR = "terminal_error"


PROCESSING = {S.DISCOVERED, S.CAPTURED, S.VISION_PENDING, S.VISION_PROCESSING, S.SCORING_PENDING, S.SCORED}

TRANSITIONS: dict[S, set[S]] = {
    S.DISCOVERED: {S.CAPTURED},
    S.CAPTURED: {S.DUPLICATE, S.PREFILTER_REJECTED, S.VISION_PENDING},
    S.VISION_PENDING: {S.VISION_PROCESSING},
    S.VISION_PROCESSING: {S.VISION_GOOD, S.VISION_REVIEW, S.VISION_REJECTED, S.INSUFFICIENT_EVIDENCE},
    S.VISION_GOOD: {S.SCORING_PENDING},
    S.VISION_REVIEW: {S.SCORING_PENDING},
    S.VISION_REJECTED: {S.SCORING_PENDING},
    # one controlled recapture, otherwise straight to scoring (which routes to manual review)
    S.INSUFFICIENT_EVIDENCE: {S.CAPTURED, S.SCORING_PENDING},
    S.SCORING_PENDING: {S.SCORED},
    S.SCORED: {S.ELIGIBLE, S.MANUAL_REVIEW, S.REJECTED},
    S.ELIGIBLE: {S.RANKED},
    S.MANUAL_REVIEW: {S.RANKED, S.APPROVED, S.REJECTED},
    S.RANKED: {S.APPROVED, S.NOT_SELECTED, S.EXPIRED, S.RANKED},
    S.RETRYABLE_ERROR: set(),  # filled below: may resume any processing state
    S.APPROVED: {S.EXPIRED},
    S.NOT_SELECTED: {S.RANKED, S.EXPIRED},
}
for _s in PROCESSING:
    TRANSITIONS.setdefault(_s, set()).update({S.RETRYABLE_ERROR, S.TERMINAL_ERROR})
TRANSITIONS[S.RETRYABLE_ERROR] = set(PROCESSING) | {S.TERMINAL_ERROR}
# A changed listing (recrawl) may re-enter capture from most resting states (§10.6)
for _s in (S.PREFILTER_REJECTED, S.VISION_REJECTED, S.REJECTED, S.RANKED, S.NOT_SELECTED, S.ELIGIBLE,
           S.MANUAL_REVIEW, S.EXPIRED, S.TERMINAL_ERROR, S.DUPLICATE, S.INSUFFICIENT_EVIDENCE):
    TRANSITIONS.setdefault(_s, set()).add(S.CAPTURED)
for _s in S:
    if _s not in (S.EXPIRED,):
        TRANSITIONS.setdefault(_s, set()).add(S.EXPIRED)


class IllegalTransition(Exception):
    pass


def check_transition(current: str | S, nxt: str | S) -> S:
    cur, new = S(current), S(nxt)
    if new not in TRANSITIONS.get(cur, set()):
        raise IllegalTransition(f"{cur.value} -> {new.value} is not allowed")
    return new
