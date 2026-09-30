"""Buyer-intent scoring shared by every platform (Facebook, TikTok, …).

Builds on fbm_intel.comments.classify (phrase rules for Khmer, Romanized Khmer, English, mixed, with negations)
and adds: a 0–100 score, label, primary intent type, language, spam score, human-review flag and a reason.
It scores the COMMENT, never labels the person.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ..comments import classify, load_config, normalize_tokens

SCORER_VERSION = "buyer-intent-score-v1"

# Weight of each signal on its own (a phrase already matched — never an isolated word).
SIGNAL_WEIGHTS = {
    "wants_to_buy": 90,
    "makes_offer": 85,
    "asks_price": 70,
    "asks_contact": 70,
    "asks_delivery": 65,
    "asks_availability": 65,
    "asks_to_see": 65,
    "asks_vehicle_details": 50,
}
STRONG, POSSIBLE = 70, 40  # label thresholds (configurable per run)

# Short whole-comment forms common on TikTok/Facebook ("inbox", "ib", "price?", "location?", "nov te?")
SHORT_FORMS = {
    re.compile(r"^(inbox|ib|pm|dm)\s*[?!.]*$", re.I): "asks_contact",
    re.compile(r"^(price|tlai|domlai)\s*[?？]*$", re.I): "asks_price",
    re.compile(r"^(នៅទេ|នៅអត់|នៅមានទេ)(បង|ចែ|អូន)?\s*[?？]*$"): "asks_availability",
    re.compile(r"^(location|loc|nov na)\s*[?]+$", re.I): "asks_to_see",
    re.compile(r"^(nov te|available)\s*[?]+$", re.I): "asks_availability",
}
EXTRA_PHRASES = {
    "asks_availability": ["មានទៀតអត់", "មានទៀតទេ", "នៅមានអត់", "still have", "any left"],
    "asks_delivery": ["can deliver", "delivery?", "deliver to", "ship to", "ដឹកជញ្ជូន", "ដឹកដល់", "ដឹកទៅ", "deliver ban te"],
}
SPAM_PATTERNS = [
    (re.compile(r"\[link\]|https?://|www\.", re.I), 35, "contains_link"),
    (re.compile(r"\[phone\]"), 20, "contains_phone"),
    (re.compile(r"\b(for sale|we sell|i sell|shop|promotion|promo|discount code|follow me|check my (page|profile|bio))\b", re.I), 40, "advertising"),
    (re.compile(r"(#\w+.*){3,}"), 20, "many_hashtags"),
    (re.compile(r"(.)\1{7,}"), 15, "character_flood"),
    (re.compile(r"(\p{Emoji}.*){8,}" if False else r"([\U0001F300-\U0001FAFF].*){8,}"), 15, "emoji_flood"),
]


@dataclass
class IntentScore:
    buyer_intent_score: int
    buyer_intent_label: str                 # strong_buyer_intent | possible_buyer_intent | not_buyer_intent
    intent_type: str | None                 # strongest signal
    detected_language: str                  # km | romanized_km | en | mixed | unknown
    matched_signals: list[str]
    matched_phrases: list[str]
    negative_signals: list[str]
    spam_score: int
    reason: str
    needs_human_review: bool
    normalized_text: str
    scorer_version: str = SCORER_VERSION
    classifier_version: str = ""
    signals_detail: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def detect_language(text: str) -> str:
    km = bool(re.search(r"[ក-៿]", text))
    latin_words = re.findall(r"[A-Za-z]{2,}", text)
    if not km and not latin_words:
        return "unknown"
    tokens = {n for _, n in normalize_tokens(text)}
    rom = {"howmuch", "jong", "tinh", "nov", "knhom", "mok", "arom", "jorb", "bong", "lan"} & tokens
    if km and latin_words:
        return "mixed"
    if km:
        return "km"
    if rom and {"howmuch", "jong", "tinh", "nov", "knhom", "mok", "arom", "jorb"} & tokens:
        return "romanized_km"
    return "mixed" if rom else "en"   # e.g. "how much b" — English with Cambodian chat particles


def score_comment(text: str, *, strong: int = STRONG, possible: int = POSSIBLE) -> IntentScore:
    r = classify(text or "")
    signals = list(r.signals)
    phrases = list(r.matched_phrases)
    folded = (text or "").casefold().strip()
    for pat, sig in SHORT_FORMS.items():
        if pat.match(folded) and sig not in signals:
            signals.append(sig)
            phrases.append(text.strip())
    for sig, items in EXTRA_PHRASES.items():
        for ph in items:
            if ph in folded and sig not in signals:
                signals.append(sig)
                phrases.append(ph)
                break

    spam, spam_reasons = 0, []
    for pat, pts, why in SPAM_PATTERNS:
        if pat.search(text or ""):
            spam += pts
            spam_reasons.append(why)
    spam = min(100, spam)

    base = max((SIGNAL_WEIGHTS.get(s, 40) for s in signals), default=0)
    bonus = 10 * max(0, len(set(signals)) - 1)
    score = min(100, base + bonus)
    negs = list(r.negation_phrases)
    if negs:
        score = min(score, 10)
    if spam >= 60:
        score = min(score, 20)
    elif spam >= 30:
        score = max(0, score - 20)

    label = "strong_buyer_intent" if score >= strong else "possible_buyer_intent" if score >= possible else "not_buyer_intent"
    primary = max(signals, key=lambda s: SIGNAL_WEIGHTS.get(s, 40)) if signals else None
    review = (possible <= score < strong) or (30 <= spam < 60 and bool(signals)) or (bool(negs) and bool(signals))
    if negs and signals:
        reason = f"buyer phrases found but negated by {negs[0]!r}"
    elif spam >= 60:
        reason = f"looks like spam/advertising ({', '.join(spam_reasons)})"
    elif signals:
        reason = f"{primary.replace('_', ' ')} via {', '.join(repr(p) for p in phrases[:3])}"
    else:
        reason = "no buyer phrase"
    return IntentScore(
        buyer_intent_score=score, buyer_intent_label=label, intent_type=primary,
        detected_language=detect_language(text or ""), matched_signals=signals, matched_phrases=phrases,
        negative_signals=negs + [f"spam:{s}" for s in spam_reasons], spam_score=spam, reason=reason,
        needs_human_review=review, normalized_text=r.normalized,
        classifier_version=f"{r.version}|{load_config().version}",
    )
