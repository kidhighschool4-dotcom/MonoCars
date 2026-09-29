"""Keyword planner (§8.2, §12.1): the model proposes, Python validates, dedupes and caps."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import httpx
from pydantic import ValidationError

from . import versions
from .normalize import fold, normalize_location, normalize_text
from .schemas import ProductBrief, SearchPlan, SearchProfile, SearchQuery

MAX_QUERY_LEN = 120
FORBIDDEN_QUERY_PATTERNS = [
    r"\bphone\b", r"\bnumber\b", r"\bemail\b", r"\baddress of\b", r"\bprofile\b", r"\bprivate\b", r"\bgroup\b",
    r"\bcaptcha\b", r"\bbypass\b", r"\blogin\b", r"\bpassword\b", r"\bmessage\b", r"\bcontact\b",
    r"លេខទូរស័ព្ទ", r"ទំនាក់ទំនង",
]

DEFAULT_NEGATIVE_TERMS = ["rental", "for rent", "ជួល", "spare parts", "គ្រឿងបន្លាស់", "wanted to buy", "ត្រូវការទិញ"]

# Reviewed seed vocabulary (fixed, versioned). Used when no LLM plan is approved yet.
SEED_TEMPLATES = [
    ("{cat} for sale {loc}", "en", "generic", 90),
    ("ឡាន {cat} លក់ {loc_km}", "mixed", "generic", 95),
    ("ឡានលក់ {loc_km}", "km", "generic", 85),
    ("used car {loc}", "en", "generic", 70),
]
SEED_MODELS = ["Toyota Camry", "Toyota Prius", "Lexus RX", "Toyota Highlander", "Honda CR-V", "Toyota Land Cruiser"]
KM_LOCATION = {"Phnom Penh": "ភ្នំពេញ", "Kandal": "កណ្តាល", "Siem Reap": "សៀមរាប", "Battambang": "បាត់ដំបង"}


class PlanValidationError(Exception):
    pass


def validate_plan(raw: dict, profile: SearchProfile, brief: ProductBrief, planner_version: str) -> SearchPlan:
    """Normalize, dedupe, cap and reject disallowed queries. Raises if nothing usable remains."""
    queries_in = raw.get("queries")
    if not isinstance(queries_in, list):
        raise PlanValidationError("plan has no queries list")
    seen: set[str] = set()
    kept: list[SearchQuery] = []
    allowed_langs = set(profile.languages)
    supported_locs = set(brief.supported_locations) | set(profile.locations)
    for q in queries_in:
        try:
            sq = SearchQuery.model_validate({**q, "text": normalize_text(str(q.get("text", "")))})
        except (ValidationError, AttributeError):
            continue
        key = fold(sq.text)
        if not key or key in seen or len(sq.text) > MAX_QUERY_LEN:
            continue
        if sq.language not in allowed_langs:
            continue
        if any(re.search(p, key) for p in FORBIDDEN_QUERY_PATTERNS):
            continue
        loc = normalize_location(sq.text)
        if loc and supported_locs and loc not in supported_locs:
            continue  # unsupported geography
        seen.add(key)
        kept.append(sq)
    kept.sort(key=lambda q: (-q.priority, fold(q.text)))
    kept = kept[: profile.max_queries_per_run]
    if not kept:
        raise PlanValidationError("no valid queries after validation")
    negatives = [normalize_text(t) for t in raw.get("negative_terms") or [] if isinstance(t, str) and normalize_text(t)]
    negatives = list(dict.fromkeys(negatives + DEFAULT_NEGATIVE_TERMS))[:30]
    return SearchPlan(intent=profile.intent, queries=kept, negative_terms=negatives,
                      planner_version=planner_version, generated_at=datetime.now(timezone.utc))


def seed_plan(profile: SearchProfile, brief: ProductBrief) -> SearchPlan:
    """Deterministic reviewed vocabulary — no model call."""
    queries = []
    cats = brief.supported_categories or ["car"]
    for loc in profile.locations or brief.supported_locations:
        for cat in cats:
            for tpl, lang, category, prio in SEED_TEMPLATES:
                queries.append({"text": tpl.format(cat=cat, loc=loc, loc_km=KM_LOCATION.get(loc, loc)),
                                "language": lang, "category": category, "priority": prio})
        for model in SEED_MODELS:
            queries.append({"text": f"{model} លក់ {KM_LOCATION.get(loc, loc)}", "language": "mixed", "category": "model", "priority": 80})
    return validate_plan({"queries": queries}, profile, brief, versions.SEED_PLANNER_VERSION)


PLANNER_SYSTEM = """Generate a bounded multilingual search plan for approved public vehicle-listing sources in Cambodia.
Return only the provided schema via the function. Do not include private-data searches, phone/contact lookups,
contact actions, platform bypass instructions, or unsupported locations. Include Khmer, English and common
mixed Khmer-English variants where appropriate (e.g. 'ឡាន Camry លក់ ភ្នំពេញ'). Respect the exact query budget."""


def plan_schema(max_queries: int) -> dict:
    return {
        "type": "object", "additionalProperties": False, "required": ["queries", "negative_terms"],
        "properties": {
            "queries": {"type": "array", "maxItems": max_queries, "items": {
                "type": "object", "additionalProperties": False, "required": ["text", "language", "category", "priority"],
                "properties": {
                    "text": {"type": "string", "maxLength": MAX_QUERY_LEN},
                    "language": {"type": "string", "enum": ["km", "en", "mixed"]},
                    "category": {"type": "string", "enum": ["generic", "model", "location", "brand"]},
                    "priority": {"type": "integer", "minimum": 0, "maximum": 100},
                }}},
            "negative_terms": {"type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 30},
        },
    }


def llm_plan(profile: SearchProfile, brief: ProductBrief, *, base_url: str, token: str, agent: str,
             backend_model: str | None = None, timeout_s: float = 120) -> SearchPlan:
    user = json.dumps({
        "intent": profile.intent, "product_summary": brief.summary,
        "supported_locations": profile.locations or brief.supported_locations,
        "supported_categories": brief.supported_categories,
        "languages": profile.languages, "negative_concepts": brief.hard_rejections,
        "brand_model_dictionary": SEED_MODELS, "query_limit": profile.max_queries_per_run,
    }, ensure_ascii=False)
    headers = {"Authorization": f"Bearer {token}"}
    if backend_model:
        headers["x-openclaw-model"] = backend_model
    body = {
        "model": f"openclaw/{agent}", "max_completion_tokens": 2000,
        "messages": [{"role": "system", "content": PLANNER_SYSTEM}, {"role": "user", "content": user}],
        "tools": [{"type": "function", "function": {"name": "submit_search_plan", "description": "Submit the plan",
                                                    "parameters": plan_schema(profile.max_queries_per_run)}}],
        "tool_choice": {"type": "function", "function": {"name": "submit_search_plan"}},
    }
    r = httpx.post(f"{base_url.rstrip('/')}/v1/chat/completions", json=body, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    calls = (r.json().get("choices") or [{}])[0].get("message", {}).get("tool_calls") or []
    if not calls:
        raise PlanValidationError("planner returned no plan")
    raw = json.loads(calls[0]["function"]["arguments"])
    return validate_plan(raw, profile, brief, versions.PLANNER_VERSION)
