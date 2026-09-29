import pytest

from fbm_intel.state import IllegalTransition, S, check_transition


@pytest.mark.parametrize("a,b", [
    ("discovered", "captured"), ("captured", "vision_pending"), ("captured", "duplicate"),
    ("vision_pending", "vision_processing"), ("vision_processing", "insufficient_evidence"),
    ("insufficient_evidence", "captured"),  # one controlled recapture
    ("vision_good", "scoring_pending"), ("scoring_pending", "scored"), ("scored", "eligible"),
    ("eligible", "ranked"), ("ranked", "approved"), ("manual_review", "rejected"),
    ("vision_processing", "retryable_error"), ("retryable_error", "vision_pending"), ("ranked", "captured"),
])
def test_allowed(a, b):
    assert check_transition(a, b) == S(b)


@pytest.mark.parametrize("a,b", [
    ("discovered", "vision_good"),      # can't skip capture + vision
    ("captured", "eligible"),           # can't skip evaluation and scoring
    ("duplicate", "vision_pending"),    # a duplicate never starts a second vision job
    ("vision_rejected", "eligible"),    # must go through scoring
    ("approved", "ranked"),             # human approval is final (only expiry after)
    ("terminal_error", "vision_pending"),
])
def test_forbidden(a, b):
    with pytest.raises(IllegalTransition):
        check_transition(a, b)


def test_unknown_state_rejected():
    with pytest.raises(ValueError):
        check_transition("made_up", "captured")
