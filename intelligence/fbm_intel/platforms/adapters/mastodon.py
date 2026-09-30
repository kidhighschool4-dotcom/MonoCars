"""Mastodon public statuses via the documented Mastodon REST API of configured instances (no login).

Access method
- Discovery: public hashtag timelines `GET https://<instance>/api/v1/timelines/tag/<tag>?limit=..&max_id=..` on each
  configured instance (`instances`, default mastodon.social). Tags come from the discovery hashtags (without '#',
  lowercased); non-ASCII tags and plain-text queries are skipped (full-text status search needs an authenticated
  account, which this adapter does not use). Per-instance `max_id` cursors live in the checkpoint.
- Replies: `GET https://<instance>/api/v1/statuses/<id>/context` → `descendants`, threaded via `in_reply_to_id`.
- `allowed_hosts` is derived from the configured instances.

What is collected
- Statuses with visibility "public" only (not unlisted / followers-only / direct), without a content warning /
  sensitive flag, from accounts that did not set `noindex`: text (HTML stripped, @mentions removed), hashtags,
  created_at, replies / boosts / favourites counts, status id, canonical URL (the status `url`/`uri` on its origin
  server).
- Public replies (redacted by `make_comment`), their instance-local ids. Mastodon permalinks embed the author's
  @username, so comment permalinks are NOT stored (canonical_comment_url None) — the id is kept instead.
- Accounts whose display name reads as a business → Organization; everyone else only
  `key_for("mastodon", account.uri or acct@instance)`.

What is NOT collected
- Usernames, display names of individuals, avatars, profile URLs; boosts (reblogs); non-public replies.
- Screenshots: API adapter, `capture_evidence` returns None.

Blockers
- Instances can disable unauthenticated access to hashtag timelines (Mastodon 4.x admin setting) → that instance
  answers 401/403/422 and is recorded in `blocked_instances`; when all are blocked the cycle stops with AccessBlocked.
- No full-text search without an account token.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup

from ...normalize import normalize_text, sha256_hex
from ...social.model import SocialComment, SocialPost, make_comment
from ..base import HttpAdapterBase
from ..contract import (AccessBlocked, Checkpoint, CommentBatch, Health, LoginRequired, Organization, PlatformError,
                        SearchItem, SearchPage)
from ..http import safe_url
from ..leads import looks_organizational
from ..registry import register

VERSION = "mastodon-public-api-v1"
DEFAULT_INSTANCES = ("mastodon.social",)
_HOST = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_TAG = re.compile(r"^[a-z0-9_]{1,100}$")
_STATUS_PATHS = (re.compile(r"^/@[^/]+/(\d+)/?$"), re.compile(r"^/users/[^/]+/statuses/(\d+)/?$"))


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    doomed = [m for m in soup.select("a.mention, span.h-card") if "hashtag" not in (m.get("class") or [])]
    for m in doomed:
        if m.parent is not None:   # an <a> inside an already-removed h-card is gone with it
            m.extract()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all("p"):
        p.insert_after("\n")
    return soup.get_text().strip()


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _instances(cfg: dict) -> list[str]:
    out = []
    for i in cfg.get("instances") or DEFAULT_INSTANCES:
        h = str(i).strip().lower().removeprefix("https://").strip("/")
        if _HOST.match(h):
            out.append(h)
    return out


@register
class MastodonAdapter(HttpAdapterBase):
    name = "mastodon"
    platform = "mastodon"
    display_name = "Mastodon (public hashtag timelines)"
    tier = 2
    access = "official_api"
    adapter_version = VERSION
    content_type = "mastodon_status"
    required_env = ()
    allowed_hosts = frozenset(DEFAULT_INSTANCES)
    respect_robots = False

    def __init__(self, ctx):
        self.instances = _instances(ctx.config)
        self.allowed_hosts = frozenset(self.instances) or frozenset(DEFAULT_INSTANCES)   # before PoliteHttp is built
        super().__init__(ctx)
        self._statuses: dict[str, dict] = {}
        self.blocked_instances: dict[str, str] = {}
        self.skipped_queries: list[str] = []

    def _limit(self, key: str, default: int) -> int:
        b = self.ctx.budget
        if b is not None:
            return b.max_posts_per_query if key == "max_posts_per_query" else b.max_comments_per_post
        return int(self.cfg.get("budgets", {}).get(key, default))

    def health_check(self) -> Health:
        if not self.instances:
            return Health("misconfigured", "no valid instances configured (platforms.mastodon.instances)")
        return Health("ok")

    @staticmethod
    def tag_for(query: str) -> str | None:
        """'#RX300' → 'rx300'. Plain-text queries and non-ASCII tags → None (skipped)."""
        q = query.strip()
        if not q.startswith("#"):
            return None
        t = q[1:].lower()
        return t if t.isascii() and _TAG.match(t) else None

    def canonicalize_url(self, url: str) -> str | None:
        p = urlsplit(url)
        if p.scheme != "https" or not _HOST.match(p.netloc.lower()):
            return None
        return url.split("?")[0].split("#")[0] if any(r.match(p.path) for r in _STATUS_PATHS) else None

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        tag = self.tag_for(query)
        if tag is None:
            self.skipped_queries.append(query)
            nxt = Checkpoint(query=query, cursor=checkpoint.cursor, page=checkpoint.page, seen=list(checkpoint.seen),
                             exhausted=True)
            self._next_checkpoint = nxt
            return SearchPage(items=[], next_checkpoint=nxt, exhausted=True)
        cur = json.loads(checkpoint.cursor) if checkpoint.cursor else {}
        n = max(1, min(40, self._limit("max_posts_per_query", 10)))
        items: list[SearchItem] = []
        nxt_cur: dict = {}
        for inst in self.instances:
            if inst in self.blocked_instances:
                continue
            params = {"limit": n}
            if cur.get(inst):
                params["max_id"] = cur[inst]
            try:
                r = self.http.get(f"https://{inst}/api/v1/timelines/tag/{quote(tag)}", params=params)
            except (LoginRequired, AccessBlocked) as e:
                if "host not allowed" in e.detail:
                    raise
                self.blocked_instances[inst] = f"hashtag timeline not public ({e.detail})"
                continue
            shown = safe_url(str(r.request.url))
            if r.status_code >= 400:
                self.blocked_instances[inst] = f"HTTP {r.status_code}"
                continue
            statuses = r.json() if isinstance(r.json(), list) else []
            for s in statuses:
                s = {**s, "_instance": inst}
                if s.get("reblog"):
                    continue
                canon = s.get("url") or s.get("uri")
                if not canon or not canon.startswith("https://"):
                    continue
                self._statuses[canon] = s
                items.append(SearchItem(url=canon, canonical_url=canon, query=query, search_url=shown,
                                        source_id=f"{inst}:{s['id']}", preview={"status": s}))
            if statuses:
                nxt_cur[inst] = str(min(int(s["id"]) for s in statuses))
        if self.instances and not items and len(self.blocked_instances) >= len(self.instances):
            raise AccessBlocked("hashtag timelines not publicly accessible on: " + ", ".join(sorted(self.blocked_instances)))
        pages = int(cur.get("_pages", 0)) + 1
        if nxt_cur and pages < int(self.cfg.get("max_pages_deep", 5)):
            nxt_cur["_pages"] = pages
        else:
            nxt_cur = {}
        nxt = Checkpoint(query=query, cursor=json.dumps(nxt_cur) if nxt_cur else None, page=checkpoint.page + 1,
                         seen=list(checkpoint.seen), exhausted=not nxt_cur)
        self._next_checkpoint = nxt
        return SearchPage(items=items, next_checkpoint=nxt, exhausted=not items)

    @staticmethod
    def _not_public_reason(s: dict) -> str | None:
        if s.get("visibility") != "public":
            return f"not_public:{s.get('visibility')}"
        if s.get("sensitive") or s.get("spoiler_text"):
            return "content_warning_sensitive"
        if (s.get("account") or {}).get("noindex"):
            return "author_opted_out_noindex"
        if s.get("reblog"):
            return "boost_not_original"
        return None

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        s = (item.preview.get("status") if item and item.preview else None) or self._statuses.get(url)
        if s is None:
            # a status is only addressable through the instance that indexed it; we only collect what search returned
            self.last_skip_reason = "status_not_from_search"
            return None
        reason = self._not_public_reason(s)
        if reason:
            self.last_skip_reason = reason
            return None
        return self.normalize_result({**s, "search_query": item.query if item else "",
                                      "search_url": item.search_url if item else None})

    def _author_key(self, acct: dict, inst: str) -> str | None:
        ident = acct.get("uri") or (f"{acct['acct']}@{inst}" if acct.get("acct") and "@" not in acct["acct"] else acct.get("acct"))
        return self.keyer.key_for("mastodon", ident)

    def normalize_result(self, s: dict) -> SocialPost:
        inst = s.get("_instance") or urlsplit(s.get("url") or s.get("uri") or "").netloc
        canon = s.get("url") or s.get("uri")
        text = html_to_text(s.get("content"))[:20000] or None
        tags = [f"#{t['name']}" for t in s.get("tags") or [] if t.get("name")]
        eng = {k: s[f] for k, f in (("replies", "replies_count"), ("boosts", "reblogs_count"),
                                    ("favourites", "favourites_count")) if s.get(f) is not None}
        post = SocialPost(
            platform=self.platform, source_content_type=self.content_type, source_post_id=f"{inst}:{s['id']}",
            source_post_url=canon, canonical_post_url=canon, document_title=None, post_title=None, post_text=text,
            hashtags=list(dict.fromkeys(tags + re.findall(r"#\w+", text or ""))),
            published_text_displayed=s.get("created_at"), published_at_observed=_dt(s.get("created_at")), engagement=eng,
            visibility_status="public_verified",
            visibility_evidence=f"Mastodon API ({inst}): status visibility public, no content warning",
            search_query=s.get("search_query", ""), search_url=s.get("search_url"), captured_at=datetime.now(timezone.utc),
            adapter_version=VERSION, content_hash=sha256_hex(normalize_text(text).casefold()),
            completeness_status="comments_unavailable", comments_supported=True)
        acct = s.get("account") or {}
        if looks_organizational(acct.get("display_name")):
            post.organization = Organization(platform="mastodon", name=acct["display_name"], url=acct.get("url"),
                                             kind="other", evidence="Mastodon account whose display name reads as a business")
        else:
            post.author_key = self._author_key(acct, inst)
            post.author_key_version = self.keyer.version if post.author_key else None
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        inst, sid = post.source_post_id.split(":", 1)
        limit = self._limit("max_comments_per_post", 200)
        r = self.http.get(f"https://{inst}/api/v1/statuses/{quote(sid)}/context")
        if r.status_code >= 400:
            if r.status_code == 404:
                return CommentBatch([], "comments_unavailable")
            raise PlatformError(f"HTTP {r.status_code}", safe_url(str(r.request.url)))
        desc = sorted(r.json().get("descendants") or [], key=lambda x: (x.get("created_at") or "", int(x.get("id") or 0)))
        root_owner = self._author_key((self._statuses.get(post.canonical_post_url) or {}).get("account") or {}, inst) \
            if post.canonical_post_url in self._statuses else post.author_key
        by_id = {d["id"]: d for d in desc if d.get("id")}
        made: dict[str, SocialComment | None] = {}
        out: list[SocialComment] = []
        occ: dict = {}
        partial = False

        def parent_of(d: dict) -> SocialComment | None:
            pid = d.get("in_reply_to_id")
            while pid and pid != sid:        # walk up past skipped (non-public / empty) replies
                if made.get(pid) is not None:
                    return made[pid]
                pid = (by_id.get(pid) or {}).get("in_reply_to_id")
            return None

        for d in desc:
            if d.get("visibility") != "public" or d.get("reblog"):
                made[d["id"]] = None
                continue
            if len(out) >= limit:
                partial = True
                break
            parent = parent_of(d)
            key = self._author_key(d.get("account") or {}, inst)
            c = make_comment(platform=self.platform, post_url=post.canonical_post_url, raw_text=html_to_text(d.get("content")),
                             is_reply=parent is not None, parent=parent, commenter_key=key,
                             key_version=self.keyer.version if key else None, displayed_timestamp=d.get("created_at"),
                             commented_at=_dt(d.get("created_at")), source_comment_id=f"{inst}:{d['id']}",
                             source_comment_url=None, occurrence_counter=occ)
            made[d["id"]] = c
            if c is not None:
                c.is_post_author = bool(key and key == root_owner)
                out.append(c)
        return CommentBatch(out, "partial_limit" if partial else "complete", 1)

    def capture_evidence(self, item) -> None:
        return None  # official API: no rendered page is opened; the status URL + API record is the evidence
