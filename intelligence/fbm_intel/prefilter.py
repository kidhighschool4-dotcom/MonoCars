"""Deterministic prefilter + dedup, run before any paid vision call (§8.5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .normalize import fold, hamming, normalize_location
from .schemas import PageState, ProductBrief, RawListingObservation

# Clear, unambiguous hard-rejection phrases (English + Khmer). Ambiguous text is NOT rejected here;
# it goes to the vision model (§8.5: don't reject Khmer just because an English rule misses).
HARD_REJECTION_TERMS: dict[str, list[str]] = {
    "rental_only": ["for rent", "car rental", "rent a car", "rental only", "ជួលឡាន", "សម្រាប់ជួល", "ឡានជួល"],
    "parts_only": ["spare parts", "parts only", "for parts", "គ្រឿងបន្លាស់"],
    "wanted_to_buy": ["wanted to buy", "wtb", "looking to buy", "want to buy", "ត្រូវការទិញ", "ចង់ទិញ"],
    "sold_or_unavailable": ["sold out", "already sold", "no longer available", "លក់ដាច់ហើយ", "លក់ហើយ"],
}

PHASH_DUPLICATE_MAX_DISTANCE = 4  # of 64 bits; tested in tests/test_prefilter.py


@dataclass
class PrefilterResult:
    outcome: str  # 'pass' | 'duplicate' | 'reject'
    reason_codes: list[str] = field(default_factory=list)
    duplicate_of: str | None = None


@dataclass
class KnownListing:
    id: str
    canonical_url_hash: str
    source_platform: str
    source_listing_id: str | None
    content_hash: str
    perceptual_hash: str | None


def detect_hard_rejections(*texts: str | None) -> list[str]:
    hay = " ".join(fold(t) for t in texts if t)
    return sorted({code for code, terms in HARD_REJECTION_TERMS.items() if any(term in hay for term in terms)})


def prefilter(
    obs: RawListingObservation,
    *,
    listing_id: str,
    canonical_url_hash: str,
    content_hash: str,
    perceptual_hash: str | None,
    has_screenshot: bool,
    brief: ProductBrief,
    known: list[KnownListing],
    max_age_days: int | None,
    now: datetime | None = None,
) -> PrefilterResult:
    now = now or datetime.now(timezone.utc)

    # 1. Duplicates — never pay for a second vision call (§20)
    for k in known:
        if k.id == listing_id:
            continue
        if k.canonical_url_hash == canonical_url_hash:
            return PrefilterResult("duplicate", ["duplicate_canonical_url"], k.id)
        if obs.source_listing_id and k.source_platform == obs.source_platform and k.source_listing_id == obs.source_listing_id:
            return PrefilterResult("duplicate", ["duplicate_source_listing_id"], k.id)
        if k.content_hash == content_hash:
            return PrefilterResult("duplicate", ["duplicate_content_hash"], k.id)
        if perceptual_hash and k.perceptual_hash and hamming(perceptual_hash, k.perceptual_hash) <= PHASH_DUPLICATE_MAX_DISTANCE:
            return PrefilterResult("duplicate", ["duplicate_screenshot_phash"], k.id)

    reasons: list[str] = []
    # 2. Evidence and page state
    if not has_screenshot:
        reasons.append("missing_screenshot")
    if obs.page_state != PageState.OK:
        reasons.append(f"page_state_{obs.page_state.value}")

    # 3. Clear hard-rejection text
    reasons += [f"hard_rejection_{c}" for c in detect_hard_rejections(obs.title_raw, obs.description_raw)]

    # 4. Geography — only when explicitly known and clearly outside the brief
    loc = normalize_location(obs.location_text_raw)
    if loc and brief.supported_locations and loc not in brief.supported_locations:
        reasons.append("unsupported_location")

    # 5. Staleness
    if max_age_days and obs.published_at_observed:
        age = (now - obs.published_at_observed).days
        if age > max_age_days:
            reasons.append("stale_listing")

    return PrefilterResult("reject" if reasons else "pass", reasons)
