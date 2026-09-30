"""RX300 lead typing on top of buyer-intent scoring.

Four separate lead types:
- confirmed_rx300_buyer  — buyer intent about a Lexus RX300 (in the comment, or on a post that is about an RX300)
- potential_rx300_fit    — someone seeking a family SUV / taxi-use car (or buying a related model) who may fit an RX300
- seller_or_dealer       — selling / advertising; the post author replying; clearly organizational accounts
- irrelevant             — everything else

A seller's post is a source of interested comments; its author is never a buyer lead. Scores the TEXT, not the person.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from ..social.intent_score import IntentScore, score_comment

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rx300_leads_v1.json"
LEAD_TYPES = ("confirmed_rx300_buyer", "potential_rx300_fit", "seller_or_dealer", "irrelevant")
_KHMER_DIGITS = str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789")


@dataclass
class LeadResult:
    lead_type: str
    use_case: str | None                 # family | taxi | None
    rx300_mentioned: bool
    rx300_context: bool                  # the post/thread is about an RX300
    confidence: int                      # 0–100
    reasons: list[str] = field(default_factory=list)
    needs_review: bool = False
    version: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LeadRules:
    version: str
    rx_regex: tuple[re.Pattern, ...]
    rx_phrases: tuple[str, ...]
    related: tuple[str, ...]
    family: tuple[str, ...]
    taxi: tuple[str, ...]
    seeking: tuple[str, ...]
    seller: tuple[str, ...]
    seller_regex: tuple[re.Pattern, ...]
    org_hints: tuple[str, ...]


@lru_cache(maxsize=4)
def load_rules(path: str = str(CONFIG_PATH)) -> LeadRules:
    c = json.loads(Path(path).read_text(encoding="utf-8"))
    low = lambda xs: tuple(prep(x) for x in xs)  # noqa: E731
    return LeadRules(
        version=c["version"],
        rx_regex=tuple(re.compile(r, re.I) for r in c["rx300_model"]["regex"]),
        rx_phrases=low(c["rx300_model"]["phrases"]), related=low(c["related_models"]["phrases"]),
        family=low(c["family_suv_need"]["phrases"]), taxi=low(c["taxi_use"]["phrases"]), seeking=low(c["seeking"]["phrases"]),
        seller=low(c["seller_offer"]["phrases"]), seller_regex=tuple(re.compile(r, re.I) for r in c["seller_offer"].get("regex", [])),
        org_hints=low(c["organization_name_hints"]),
    )


def prep(text: str | None) -> str:
    t = (text or "").translate(_KHMER_DIGITS).casefold()
    t = t.replace("​", "")          # zero-width space often inside Khmer text
    return re.sub(r"\s+", " ", t).strip()


def _hits(t: str, phrases: tuple[str, ...]) -> list[str]:
    out = []
    for p in phrases:
        if not p:
            continue
        # Latin phrases need word boundaries ("grab" ≠ "grabbed", "suv" ≠ "suvarna"); Khmer has no spaces.
        if p.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", t):
                out.append(p)
        elif p in t:
            out.append(p)
    return out


def mentions_rx300(text: str | None, rules: LeadRules | None = None) -> bool:
    r = rules or load_rules()
    t = prep(text)
    return any(rx.search(t) for rx in r.rx_regex) or bool(_hits(t, r.rx_phrases))


def looks_organizational(name: str | None, rules: LeadRules | None = None) -> bool:
    """Name-based hint only (e.g. 'Sok Auto Import'). Platforms' own business flags are stronger evidence."""
    r = rules or load_rules()
    return bool(name) and bool(_hits(prep(name), r.org_hints))


@dataclass
class PostContext:
    text: str = ""                        # post title + text + hashtags
    author_is_organization: bool = False

    @property
    def prepared(self) -> str:
        return prep(self.text)


def _negated(intent: IntentScore) -> bool:
    """Real negations only ("ot jong tinh te"); spam flags like spam:contains_phone are not negations."""
    return any(not s.startswith("spam") for s in intent.negative_signals)


def _use_case(fam: list[str], taxi: list[str]) -> str | None:
    return "taxi" if taxi else "family" if fam else None


def classify_post(ctx: PostContext, rules: LeadRules | None = None) -> LeadResult:
    """Post-level typing. Most car posts are sellers (sources of comments); a post can itself be a buyer ('looking for RX300')."""
    r = rules or load_rules()
    t = ctx.prepared
    rx = mentions_rx300(t, r)
    negated = _negated(score_comment(ctx.text[:2000]))
    seeking, seller = _hits(t, r.seeking), _hits(t, r.seller) + [x.pattern for x in r.seller_regex if x.search(t)]
    fam, taxi = _hits(t, r.family), _hits(t, r.taxi)
    base = dict(use_case=_use_case(fam, taxi), rx300_mentioned=rx, rx300_context=rx, version=r.version)
    if ctx.author_is_organization:
        return LeadResult("seller_or_dealer", confidence=90, reasons=["organizational_author"], **base)
    if seeking and not seller and not negated:
        if rx:
            return LeadResult("confirmed_rx300_buyer", confidence=80, reasons=["post_seeking_rx300", *seeking[:3]], **base)
        if fam or taxi or _hits(t, r.related):
            return LeadResult("potential_rx300_fit", confidence=60, reasons=["post_seeking_suv", *(fam + taxi)[:3]],
                              needs_review=True, **base)
    if seller:
        return LeadResult("seller_or_dealer", confidence=75 if rx else 60, reasons=["seller_offer", *seller[:3]], **base)
    return LeadResult("irrelevant", confidence=50, reasons=[], **base)


def classify_comment(text: str, post: PostContext | None = None, *, intent: IntentScore | None = None,
                     is_post_author: bool = False, rules: LeadRules | None = None) -> LeadResult:
    r = rules or load_rules()
    post = post or PostContext()
    intent = intent or score_comment(text)
    t = prep(text)
    rx_here = mentions_rx300(t, r)
    rx_ctx = rx_here or mentions_rx300(post.prepared, r)
    related_ctx = bool(_hits(t, r.related) or _hits(post.prepared, r.related))
    fam, taxi = _hits(t, r.family), _hits(t, r.taxi)
    seeking = [] if _negated(intent) else _hits(t, r.seeking)   # "ot jong tinh te" negates the phrase
    seller = _hits(t, r.seller) + [x.pattern for x in r.seller_regex if x.search(t)]
    buyer = intent.buyer_intent_label in ("strong_buyer_intent", "possible_buyer_intent")
    strong = intent.buyer_intent_label == "strong_buyer_intent"
    base = dict(use_case=_use_case(fam, taxi), rx300_mentioned=rx_here, rx300_context=rx_ctx, version=r.version)

    if is_post_author:
        return LeadResult("seller_or_dealer", confidence=95, reasons=["post_author_reply"], **base)
    if seller and not buyer:
        return LeadResult("seller_or_dealer", confidence=70, reasons=["seller_offer", *seller[:3]], **base)
    if intent.spam_score >= 60 and not strong:
        return LeadResult("seller_or_dealer" if seller else "irrelevant", confidence=60, reasons=["spam_or_advertising"], **base)

    if (buyer or seeking) and rx_ctx:
        why = ["buyer_intent" if buyer else "seeking", "rx300_in_comment" if rx_here else "rx300_post"]
        conf = min(95, (intent.buyer_intent_score if buyer else 60) + (10 if rx_here else 0))
        return LeadResult("confirmed_rx300_buyer", confidence=conf, reasons=why + intent.matched_signals[:3],
                          needs_review=not strong or intent.needs_human_review, **base)
    if (buyer or seeking) and (fam or taxi):
        return LeadResult("potential_rx300_fit", confidence=55, reasons=["family_or_taxi_need", *(fam + taxi)[:3]],
                          needs_review=True, **base)
    if buyer and related_ctx:
        return LeadResult("potential_rx300_fit", confidence=45, reasons=["buyer_on_related_model"], needs_review=True, **base)
    if seeking and (fam or taxi or related_ctx):
        return LeadResult("potential_rx300_fit", confidence=45, reasons=["seeking_suv"], needs_review=True, **base)
    return LeadResult("irrelevant", confidence=60 if not buyer else 40,
                      reasons=["buyer_intent_without_rx300_fit"] if buyer else [], **base)
