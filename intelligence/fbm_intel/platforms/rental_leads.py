"""Rental-seeker lead typing (campaign "rental": people looking for a place to rent in Phnom Penh).

- rental_seeker            — wants to rent: says so, or asks price / availability / viewing under a rental post
- potential_rental_seeker  — buyer-style interest (price, contact) where the rental context is weaker
- seller_or_dealer         — landlords, agents, the post author replying, business accounts
- irrelevant               — everything else

A rental listing is a source of interested comments; its author is never a lead. Same LeadResult shape as the RX300
typing (rx300_* flags stay False); `use_case` holds the kind of place: house | apartment | room | commercial.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from ..social.intent_score import IntentScore, score_comment
from .leads import LeadResult, _hits, prep

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rental_leads_v1.json"
SEEKER_LEADS = ("rental_seeker", "potential_rental_seeker")
_INQUIRY_TYPES = {"asks_price", "asks_availability", "asks_contact", "asks_location", "asks_viewing", "asks_details"}
_KIND_ORDER = ("commercial", "room", "apartment", "house")
# "2 bedrooms" describes a house/apartment, not a room for rent
_BEDROOMS = re.compile(r"\d*\s*(bed\s*rooms?|bedrooms?|br\b|បន្ទប់គេង|បន្ទប់ទឹក|bathrooms?)")
# the car scorer treats rent words as "not buying"; for rentals they are the point
_RENT_WORDS = re.compile(r"ជួល|rent|lease|chhoul|chhuol")


_NOT_SEEKING = re.compile(r"(អត់|មិន)\s*(ចង់|ត្រូវការ|រក)|\bnot\s+(looking|interested|renting)|\bdon'?t\s+(want|need)|"
                          r"\b(ot|min)\s+(jong|chong|trov|rok)\b")


def _negated(intent: IntentScore, text: str = "") -> bool:
    return bool(_NOT_SEEKING.search(text)) or \
        any(not s.startswith("spam") and not _RENT_WORDS.search(s) for s in intent.negative_signals)


@dataclass(frozen=True)
class RentalRules:
    version: str
    offer: tuple[str, ...]
    seeking: tuple[str, ...]
    inquiry: tuple[str, ...]
    landlord: tuple[str, ...]
    kinds: dict
    org_hints: tuple[str, ...]


@lru_cache(maxsize=2)
def load_rules(path: str = str(CONFIG_PATH)) -> RentalRules:
    c = json.loads(Path(path).read_text(encoding="utf-8"))
    low = lambda xs: tuple(prep(x) for x in xs)  # noqa: E731
    return RentalRules(version=c["version"], offer=low(c["rental_offer"]["phrases"]), seeking=low(c["seeking"]["phrases"]),
                       inquiry=low(c["inquiry"]["phrases"]), landlord=low(c["landlord_strong"]["phrases"]),
                       kinds={k: low(v) for k, v in c["kinds"].items()}, org_hints=low(c["organization_name_hints"]))


def kind_of(text: str, rules: RentalRules | None = None) -> str | None:
    r = rules or load_rules()
    t = _BEDROOMS.sub(" ", prep(text))
    return next((k for k in _KIND_ORDER if _hits(t, r.kinds.get(k, ()))), None)


def _is_question(t: str) -> bool:
    """'មានបន្ទប់ទំនេរទេ?' asks; 'មានបន្ទប់ទំនេរ' offers. Khmer questions end in ទេ / អត់ / ឬទេ, often without '?'."""
    return "?" in t or bool(re.search(r"(ទេ|អត់|ឬទេ|រឺទេ|te|ot)\s*(បង|អូន|ប្អូន|bong|oun)?\s*[!.…]*$", t))


def looks_organizational(name: str | None, rules: RentalRules | None = None) -> bool:
    r = rules or load_rules()
    return bool(name) and bool(_hits(prep(name), r.org_hints))


@dataclass
class PostContext:
    text: str = ""
    author_is_organization: bool = False
    search_query: str = ""

    @property
    def prepared(self) -> str:
        return prep(self.text)

    @property
    def is_rental(self) -> bool:
        """The post offers a place for rent (or itself asks for one) — not news, memes or car sales."""
        r = load_rules()
        t = self.prepared
        return bool(_hits(t, r.offer) or _hits(t, r.seeking))


def classify_post(ctx: PostContext, rules: RentalRules | None = None) -> LeadResult:
    r = rules or load_rules()
    t = ctx.prepared
    seeking = _hits(t, r.seeking)
    # "រកបន្ទប់ជួល" (looking for a room to rent) contains "បន្ទប់ជួល" (room for rent): the request wins
    offer = [o for o in _hits(t, r.offer) if not any(o in sk for sk in seeking)]
    negated = _negated(score_comment(ctx.text[:2000]), t)
    base = dict(use_case=kind_of(t, r), rx300_mentioned=False, rx300_context=False, version=r.version)
    if ctx.author_is_organization:
        return LeadResult("seller_or_dealer", confidence=90, reasons=["organizational_author"], **base)
    if seeking and not negated and (not offer or _is_question(t)):
        return LeadResult("rental_seeker", confidence=80, reasons=["post_seeking_rental", *seeking[:3]], **base)
    if offer:
        return LeadResult("seller_or_dealer", confidence=75, reasons=["rental_listing", *offer[:3]], **base)
    return LeadResult("irrelevant", confidence=50, reasons=[], **base)


def classify_comment(text: str, post: PostContext | None = None, *, intent: IntentScore | None = None,
                     is_post_author: bool = False, is_business: bool = False, rules: RentalRules | None = None) -> LeadResult:
    r = rules or load_rules()
    post = post or PostContext()
    intent = intent or score_comment(text)
    t = prep(text)
    question = _is_question(t)
    seeking = [] if _negated(intent, t) else _hits(t, r.seeking)
    inquiry = _hits(t, r.inquiry)
    landlord = [] if question else _hits(t, r.landlord)
    generic = intent.buyer_intent_label in ("strong_buyer_intent", "possible_buyer_intent") and \
        (intent.intent_type in _INQUIRY_TYPES or bool(set(intent.matched_signals) & _INQUIRY_TYPES))
    base = dict(use_case=kind_of(t, r) or kind_of(post.prepared, r), rx300_mentioned=False,
                rx300_context=post.is_rental, version=r.version)

    if is_post_author:
        return LeadResult("seller_or_dealer", confidence=95, reasons=["post_author_reply"], **base)
    if is_business:
        return LeadResult("seller_or_dealer", confidence=90, reasons=["business_account"], **base)
    if landlord and not seeking:
        return LeadResult("seller_or_dealer", confidence=85, reasons=["landlord_or_agent_offer", *landlord[:3]], **base)
    if post.text.strip() and not post.is_rental and not seeking:
        return LeadResult("irrelevant", confidence=70, reasons=["not_a_rental_post"], **base)
    if intent.spam_score >= 60 and not seeking:
        return LeadResult("irrelevant", confidence=60, reasons=["spam_or_advertising"], **base)

    if seeking:
        conf = min(95, 85 + (5 if base["use_case"] else 0) + (5 if inquiry else 0))
        return LeadResult("rental_seeker", confidence=conf, reasons=["seeking_rental", *seeking[:3]], **base)
    if inquiry and post.is_rental:
        return LeadResult("rental_seeker", confidence=80, reasons=["rental_inquiry", *inquiry[:3]],
                          needs_review=not question, **base)
    if generic and post.is_rental:
        strong = intent.buyer_intent_label == "strong_buyer_intent"
        return LeadResult("rental_seeker", confidence=min(90, intent.buyer_intent_score + 5),
                          reasons=["inquiry_on_rental_post", *intent.matched_signals[:3]],
                          needs_review=not strong or intent.needs_human_review, **base)
    if inquiry or generic:
        return LeadResult("potential_rental_seeker", confidence=50, reasons=["inquiry_without_rental_context"],
                          needs_review=True, **base)
    return LeadResult("irrelevant", confidence=60, reasons=[], **base)


def lift_intent(intent: IntentScore, lead: LeadResult) -> None:
    """Rental words the car-intent scorer doesn't know ('ចង់ជួល', 'looking for a room') still mark real interest, so the
    stored intent score (screenshots, thresholds, alerts) follows the rental lead's confidence."""
    if lead.lead_type == "rental_seeker" and intent.buyer_intent_score < lead.confidence:
        intent.buyer_intent_score = lead.confidence
        intent.buyer_intent_label = "strong_buyer_intent" if lead.confidence >= 70 else "possible_buyer_intent"
        intent.intent_type = intent.intent_type or "seeks_rental"
        intent.reason = (intent.reason + "; " if intent.reason else "") + "rental lead: " + ", ".join(lead.reasons[:3])


# ─── Post rating ────────────────────────────────────────────────────────────

_COUNT_RE = re.compile(r"([\d.,]+)\s*([kmKM]?)")


def _count(v) -> int:
    """'1.2K' → 1200, '38' → 38; anything else → 0."""
    m = _COUNT_RE.search(str(v or ""))
    if not m:
        return 0
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return 0
    return int(n * {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1))


def score_post(post, *, now: datetime | None = None) -> tuple[int, dict]:
    """0–100 % lead quality of one post: how worth following up it is.

    leads (0–60)      rental-seeker comments, weighted by confidence (+ the post itself asking for a place)
    fresh (0–20)      ≤ 7 days 20 · ≤ 30 days 14 · ≤ 90 days 7 · older 0 · unknown 8
    engagement (0–10) likes + comments + shares on a log scale (1 000 interactions ≈ 10)
    relevance (0–10)  the post is a rental listing or a rental request
    """
    seekers = [c for c in post.comments if c.lead is not None and c.lead.lead_type == "rental_seeker"]
    potential = [c for c in post.comments if c.lead is not None and c.lead.lead_type == "potential_rental_seeker"]
    lead_pts = sum(c.lead.confidence / 100 * 15 for c in seekers) + 4 * len(potential)
    if post.lead is not None and post.lead.lead_type == "rental_seeker":
        lead_pts += 20
    leads = min(60, round(lead_pts))

    when = post.published_at_observed
    if when is None:
        fresh = 8
    else:
        age = ((now or datetime.now(timezone.utc)) - (when if when.tzinfo else when.replace(tzinfo=timezone.utc))).days
        fresh = 20 if age <= 7 else 14 if age <= 30 else 7 if age <= 90 else 0

    interactions = sum(_count(v) for v in (post.engagement or {}).values())
    engagement = min(10, round(10 * math.log10(1 + interactions) / 3))

    lead_type = post.lead.lead_type if post.lead is not None else None
    relevance = 10 if lead_type in ("rental_seeker",) or (post.lead is not None and "rental_listing" in post.lead.reasons) else 0

    detail = {"leads": leads, "fresh": fresh, "engagement": engagement, "relevance": relevance,
              "seekers": len(seekers), "potential": len(potential)}
    return min(100, leads + fresh + engagement + relevance), detail
