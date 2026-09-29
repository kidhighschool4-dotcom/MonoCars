"""Strict schemas for every service boundary (architecture §6).

Observed facts and inferred judgments live in different models (§4.3).
All models forbid unknown fields so a provider can't smuggle data through.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import versions

Percent = Annotated[int, Field(ge=0, le=100)]
Level = Annotated[int, Field(ge=1, le=5)]
ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ─── Configuration ──────────────────────────────────────────────────────────

class ProductBrief(Strict):
    id: str | None = None
    slug: str
    name: str
    summary: str
    target_customer: str
    positive_signals: list[str]
    hard_rejections: list[str]
    supported_locations: list[str]
    supported_categories: list[str]
    version: int = Field(ge=1)


class SearchProfile(Strict):
    id: str | None = None
    slug: str
    name: str
    intent: str
    languages: list[Literal["km", "en", "mixed"]]
    locations: list[str]
    platforms: list[str]
    max_queries_per_run: int = Field(ge=1, le=200)
    max_pages_per_query: int = Field(ge=1, le=50)
    max_listings_per_run: int = Field(ge=1, le=5000)
    maximum_listing_age_days: int | None = Field(default=None, gt=0)
    version: int = Field(ge=1)
    enabled: bool = True


class SearchQuery(Strict):
    text: str = Field(min_length=1, max_length=120)
    language: Literal["km", "en", "mixed"]
    category: Literal["generic", "model", "location", "brand"]
    priority: int = Field(ge=0, le=100)


class SearchPlan(Strict):
    intent: str
    queries: list[SearchQuery]
    negative_terms: list[str] = []
    planner_version: str
    generated_at: datetime


# ─── Observation (facts only) ───────────────────────────────────────────────

class PageState(str, Enum):
    OK = "ok"
    SOLD_OR_REMOVED = "sold_or_removed"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"
    LOGIN_WALL = "login_wall"


class RawListingObservation(Strict):
    source_platform: str
    source_listing_id: str | None = None
    source_url: str
    canonical_url: str
    title_raw: str | None = None
    description_raw: str | None = Field(default=None, max_length=5000)
    price_text_raw: str | None = None
    location_text_raw: str | None = None
    seller_display_name: str | None = None
    published_at_observed: datetime | None = None
    captured_at: datetime
    adapter_version: str
    page_state: PageState = PageState.OK
    observation_payload: dict = {}


class ScreenshotEvidence(Strict):
    png_bytes: bytes = Field(repr=False)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    perceptual_hash: str | None = None
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    mime_type: Literal["image/png"] = "image/png"
    captured_at: datetime
    viewport: dict
    source_url: str
    crop_policy_version: str = versions.SCREENSHOT_POLICY_VERSION
    visibility: dict = {}


# ─── Inference (vision) ─────────────────────────────────────────────────────

class Decision(str, Enum):
    GOOD = "good"
    REVIEW = "review"
    REJECT = "reject"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class VisionModelOutput(Strict):
    """Exactly what the vision model must return (the tool-call arguments)."""

    decision: Decision
    fit_score_percent: Percent
    evidence_quality_percent: Percent
    visual_condition_level: Level
    information_quality_level: Level
    apparent_risk_level: Level
    hard_rejections_detected: list[ShortText] = Field(default_factory=list, max_length=10)
    visible_signals: list[ShortText] = Field(default_factory=list, max_length=12)
    risk_flags: list[ShortText] = Field(default_factory=list, max_length=12)
    missing_information: list[ShortText] = Field(default_factory=list, max_length=12)
    cannot_determine: list[ShortText] = Field(default_factory=list, max_length=12)
    short_reason: str = Field(min_length=1, max_length=400)

    @field_validator("hard_rejections_detected", "visible_signals", "risk_flags", "missing_information", "cannot_determine")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        seen: dict[str, None] = {}
        for item in v:
            seen.setdefault(item.strip(), None)
        return list(seen)


class VisionEvaluation(Strict):
    """Validated evaluation ready to persist: model output + policy decision + provenance."""

    schema_version: str = versions.VISION_SCHEMA_VERSION
    listing_id: str
    listing_asset_id: str
    output: VisionModelOutput
    decision: Decision  # after Python routing policy (§11); may differ from output.decision
    provider: str
    model: str
    prompt_version: str = versions.VISION_PROMPT_VERSION
    rubric_version: str = versions.RUBRIC_VERSION
    product_brief_id: str | None
    product_brief_version: int
    input_checksum_sha256: str
    raw_response: dict
    latency_ms: int | None = None
    usage: dict | None = None
    evaluated_at: datetime


# ─── Scoring / ranking ──────────────────────────────────────────────────────

class Eligibility(str, Enum):
    ELIGIBLE = "eligible"
    MANUAL_REVIEW = "manual_review"
    REJECTED = "rejected"


class RankingCandidate(Strict):
    """Normalized, validated ranking input (§6.7). Never contains raw model prose."""

    listing_id: str
    eligibility: Eligibility
    vision_decision: Decision
    fit_score_percent: Percent
    evidence_quality_percent: Percent
    information_quality_level: Level
    visual_condition_level: Level
    apparent_risk_level: Level
    freshness_score_percent: Percent
    hard_rejection_flags: list[str] = []
    missing_information: list[str] = []
    duplicate_group: str
    price_usd: int | None = None


class ScoredCandidate(Strict):
    listing_id: str
    eligibility: Eligibility
    component_scores: dict[str, float]
    penalties: dict[str, float]
    composite_score: float = Field(ge=0, le=100)
    reason_codes: list[str]


class RankingResult(Strict):
    status: Literal["recommended", "no_qualifying_candidate", "manual_review", "empty"]
    selected_listing_id: str | None
    minimum_acceptable_score: float
    selected_composite_score: float | None
    members: list[dict]
    reason_codes: list[str]
    candidate_set_hash: str
    policy_version: str = versions.RANKING_POLICY_VERSION
