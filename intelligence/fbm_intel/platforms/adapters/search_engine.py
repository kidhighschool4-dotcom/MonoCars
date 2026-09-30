"""Web search discovery via OFFICIAL search APIs only — never scraped search-result HTML.

Access: official_api (respect_robots False — the APIs' own terms / quotas govern):
- Google Programmable Search JSON API: GET https://www.googleapis.com/customsearch/v1?key=&cx=&q=&start=
  (env GOOGLE_CSE_KEY + GOOGLE_CSE_CX; 10 results per call, `start` ≤ 91 → at most 100 results per query).
- Brave Search API: GET https://api.search.brave.com/res/v1/web/search?q=&count=&offset= with header
  X-Subscription-Token (env BRAVE_SEARCH_API_KEY; offset ≤ 9).
Either engine suffices; order from platforms.search_engine.engines (default google, then brave).
`restrict_sites` (config) adds `site:` operators, e.g. to point discovery at khmer24.com / t.me.
Discovery only: collect_post does NOT fetch the result URL. It returns a `web_page` SocialPost built from the result's
title + snippet (visibility_evidence "listed in public search results") with engagement {"routed_to": <adapter name>}
naming the registered adapter whose canonicalize_url accepts the URL (or None), so the worker/report can show which
adapter would collect it; when an adapter accepts it, its canonical URL is used (cross-platform dedupe).
Credentials never appear in search_url (safe_url strips key/cx; Brave's key travels in a header).
Screenshots: none — capture_evidence returns None. Comments: none (search snippets) → comments_unavailable.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlencode, urlsplit

from ...social.model import SocialPost
from ..base import HttpAdapterBase
from ..contract import AdapterContext, Checkpoint, CommentBatch, Health, Misconfigured, SearchItem, SearchPage
from ..http import safe_url
from ..registry import register
from .kh_classifieds import base_post, clean_text, parse_date, strip_url

VERSION = "search-engine-official-api-v1"
GOOGLE_URL = "https://www.googleapis.com/customsearch/v1"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
_NOT_ROUTED = {"search_engine"}


@register
class SearchEngineAdapter(HttpAdapterBase):
    name = "search_engine"
    platform = "web"
    display_name = "Web search (Google Programmable Search / Brave Search APIs)"
    tier = 3
    access = "official_api"
    respect_robots = False
    adapter_version = VERSION
    supports_comments = False
    content_type = "web_page"
    required_env = ("GOOGLE_CSE_KEY", "GOOGLE_CSE_CX", "BRAVE_SEARCH_API_KEY")   # google pair OR brave key
    allowed_hosts = frozenset({"www.googleapis.com", "api.search.brave.com"})

    def __init__(self, ctx: AdapterContext):
        super().__init__(ctx)
        self._routers: dict | None = None
        self._results: dict[str, dict] = {}

    # ── credentials ──
    def engines(self) -> list[str]:
        have = {"google": bool(os.environ.get("GOOGLE_CSE_KEY") and os.environ.get("GOOGLE_CSE_CX")),
                "brave": bool(os.environ.get("BRAVE_SEARCH_API_KEY"))}
        return [e for e in self.cfg.get("engines", ["google", "brave"]) if have.get(e)]

    def missing_env(self) -> list[str]:
        if self.engines():
            return []
        return ["GOOGLE_CSE_KEY", "GOOGLE_CSE_CX (or BRAVE_SEARCH_API_KEY)"]

    def health_check(self) -> Health:
        missing = self.missing_env()
        return Health("misconfigured", "missing: " + ", ".join(missing)) if missing else Health("ok")

    # ── search ──
    def _q(self, query: str) -> str:
        sites = self.cfg.get("restrict_sites") or []
        return f"{query} (" + " OR ".join(f"site:{s}" for s in sites) + ")" if sites else query

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        engines = self.engines()
        if not engines:
            raise Misconfigured("missing: " + ", ".join(self.missing_env()))
        cursor = json.loads(checkpoint.cursor) if checkpoint.cursor else {}
        engine = cursor.get("engine") if cursor.get("engine") in engines else engines[0]
        offset = int(cursor.get("offset", 0))
        per = int(self.cfg.get("results_per_page", 10))
        if engine == "google":
            params = {"key": os.environ["GOOGLE_CSE_KEY"], "cx": os.environ["GOOGLE_CSE_CX"], "q": self._q(query),
                      "num": min(per, 10), "start": offset + 1}
            for k in ("gl", "lr", "hl"):
                if self.cfg.get(k):
                    params[k] = self.cfg[k]
            url = f"{GOOGLE_URL}?{urlencode(params)}"
            data = self.http.get(url).json()
            results = [{"url": r.get("link"), "title": r.get("title"), "snippet": r.get("snippet"),
                        "date": ((r.get("pagemap") or {}).get("metatags") or [{}])[0].get("article:published_time")}
                       for r in data.get("items") or []]
            max_offset = 90
        else:
            params = {"q": self._q(query), "count": min(per, 20), "offset": offset // max(per, 1)}
            if self.cfg.get("country"):
                params["country"] = self.cfg["country"]
            url = f"{BRAVE_URL}?{urlencode(params)}"
            data = self.http.get(url, headers={"X-Subscription-Token": os.environ["BRAVE_SEARCH_API_KEY"],
                                               "Accept": "application/json"}).json()
            results = [{"url": r.get("url"), "title": r.get("title"), "snippet": r.get("description"), "date": r.get("page_age")}
                       for r in (data.get("web") or {}).get("results") or []]
            max_offset = 9 * per
        items: list[SearchItem] = []
        seen = set(checkpoint.seen)
        shown = safe_url(url)
        for r in results:
            if not r["url"] or not r["url"].startswith(("http://", "https://")):
                continue
            canon = self.canonicalize_url(r["url"])
            if not canon or canon in seen:
                continue
            seen.add(canon)
            r["search_url"] = shown
            self._results[canon] = r
            items.append(SearchItem(url=r["url"], canonical_url=canon, query=query, search_url=shown,
                                    preview={"title": r.get("title"), "snippet": r.get("snippet"), "date": r.get("date"),
                                             "engine": engine, "routed_to": self.route(r["url"])[0]}))
        nxt_off = offset + per
        exhausted = not results or nxt_off > max_offset
        nxt = Checkpoint(query=query, cursor=json.dumps({"engine": engine, "offset": 0 if exhausted else nxt_off}),
                         page=checkpoint.page + 1, seen=list(checkpoint.seen))
        self._next_checkpoint = nxt
        return SearchPage(items=items, next_checkpoint=nxt, exhausted=exhausted)

    # ── routing ──
    def _router_instances(self) -> dict:
        if self._routers is None:
            from .. import registry
            self._routers = {}
            for name, cls in registry.load_all().items():
                if name in _NOT_ROUTED:
                    continue
                try:
                    ctx = AdapterContext(config=registry.platform_config(name), keyer=self.keyer, headed=False, preview=True)
                    self._routers[name] = cls(ctx)
                except Exception:  # noqa: BLE001 - an adapter that cannot be built just does not route
                    continue
        return self._routers

    def route(self, url: str) -> tuple[str | None, str | None]:
        """(adapter name, that adapter's canonical URL) for the first registered adapter that owns the URL."""
        for name, a in self._router_instances().items():
            try:
                canon = a.canonicalize_url(url)
            except Exception:  # noqa: BLE001
                continue
            if canon:
                return name, canon
        return None, None

    def canonicalize_url(self, url: str) -> str | None:
        if not url or not re.match(r"https?://[^/\s]+", url):
            return None
        _, routed = self.route(url)
        return routed or strip_url(url)

    # ── posts ──
    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url)
        r = (self._results.get(canon) if canon else None) or (
            {"url": item.url, **item.preview, "search_url": item.search_url} if item and item.preview else None)
        if not canon or not r:
            self.last_skip_reason = "no_search_result_context"   # never fetched here; only search results are used
            return None
        return self.normalize_result({**r, "canonical": canon, "search_query": item.query if item else ""})

    def normalize_result(self, r: dict) -> SocialPost:
        routed, routed_canon = self.route(r["url"])
        canon = r.get("canonical") or routed_canon or strip_url(r["url"])
        post = base_post(self, url=canon, source_id=None, title=clean_text(r.get("title"), 500),
                         text=clean_text(r.get("snippet"), 2000), published_text=r.get("date"),
                         published_at=parse_date(r.get("date")) if r.get("date") else None,
                         evidence="listed in public search results", query=r.get("search_query", ""),
                         search_url=r.get("search_url"), engagement={"routed_to": routed}, hashtags=[])
        post.source_post_url = r["url"] if urlsplit(r["url"]).scheme == "https" else canon
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        return CommentBatch([], "comments_unavailable")

    def capture_evidence(self, item) -> None:
        return None   # search results only; nothing rendered

    def close(self) -> None:
        for a in (self._routers or {}).values():
            try:
                a.close()
            except Exception:  # noqa: BLE001
                pass
        super().close()
