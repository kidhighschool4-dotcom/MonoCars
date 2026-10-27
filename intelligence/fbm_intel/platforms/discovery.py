"""Discovery queries per platform from the campaign's config (config/<campaign>_discovery_v1.json): Khmer,
Romanized Khmer, English."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rx300_discovery_v1.json"


@dataclass(frozen=True)
class Query:
    text: str
    group: str        # rx300_confirmed | rx300_family | rx300_taxi | family_suv_seekers | hashtag | subreddit:<name>
    language: str     # en | km | romanized_km | tag


@lru_cache(maxsize=2)
def load(path: str = str(CONFIG_PATH)) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def queries_for(platform: str, override: dict | None = None, *, limit: int | None = None,
                record_platform: str | None = None, config_path: str | Path | None = None) -> list[Query]:
    """Ordered, de-duplicated queries for one platform. `override` = the platform's own config block, which may set
    `queries` (explicit list), `query_groups`, `languages`, `hashtags` or `use_hashtags`."""
    c = load(str(config_path)) if config_path else load()
    hints = c.get("per_platform", {})
    # adapter name first (e.g. "khmer24"), then the stored platform value it maps to (e.g. "classifieds")
    pp = {**hints.get(record_platform or "", {}), **hints.get(platform, {}), **(override or {})}
    out: list[Query] = []
    if pp.get("queries"):
        out += [Query(q, "configured", "any") for q in pp["queries"]]
    else:
        groups = pp.get("query_groups") or list(c["groups"])
        langs = pp.get("languages") or ["km", "romanized_km", "en"]
        # interleave languages so a small per-cycle limit still covers Khmer + Romanized + English
        per = {(g, lang): list(c["groups"].get(g, {}).get(lang, [])) for g in groups for lang in langs}
        while any(per.values()):
            for key in list(per):
                if per[key]:
                    out.append(Query(per[key].pop(0), key[0], key[1]))
        out += [Query(t, "plain", "en") for t in pp.get("plain_terms", [])]
    if pp.get("use_hashtags"):
        tags = pp.get("hashtags") or c.get("hashtags", [])
        out = [Query(t if t.startswith("#") else f"#{t}", "hashtag", "tag") for t in tags] + out
    seen, uniq = set(), []
    for q in out:
        k = q.text.casefold()
        if k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq[:limit] if limit else uniq
