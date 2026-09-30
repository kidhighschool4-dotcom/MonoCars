"""Bluesky public posts via the public AppView XRPC API (https://public.api.bsky.app, documented lexicons only).

Access method
- `app.bsky.feed.searchPosts` (q, limit, cursor, sort=latest, lang when configured) for discovery; the `cursor` is
  kept in the checkpoint.
- `app.bsky.feed.getPostThread` (uri, depth, parentHeight=0) for the reply tree; every reply links to its parent.
- No login and no password/app-password session. If the public AppView answers searchPosts with 401/403 (Bluesky
  has at times required auth for search), the adapter raises Misconfigured with the precise blocker instead.

What is collected
- Public posts: text, hashtags (tag facets + inline #tags), createdAt, like / repost / reply / quote counts, AT-URI,
  canonical URL https://bsky.app/profile/<did>/post/<rkey> (always the DID, never the handle).
- Replies (text redacted by `make_comment`; @handle mentions masked), their AT-URIs and DID-based permalinks.
- Authors whose displayName reads as a business → Organization; everyone else only `key_for("bluesky", did)`.

What is NOT collected
- Handles, display names (of private individuals), avatars, profile URLs.
- Posts from accounts that asked logged-out viewers not to see them (`!no-unauthenticated` label), blocked /
  not-found thread nodes.
- Screenshots: API adapter, `capture_evidence` returns None.

Blockers
- public searchPosts may require authentication; an app password session would be needed (not implemented on purpose).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from ...normalize import sha256_hex
from ...social.model import SocialComment, SocialPost, make_comment
from ..base import HttpAdapterBase
from ..contract import (AccessBlocked, Checkpoint, CommentBatch, Health, LoginRequired, Misconfigured, Organization,
                        PlatformError, SearchItem, SearchPage)
from ..http import safe_url
from ..leads import looks_organizational
from ..registry import register

VERSION = "bluesky-public-appview-v1"
XRPC = "https://public.api.bsky.app/xrpc"
SEARCH_BLOCKER = "public searchPosts requires authentication; an app password session would be needed"
_AT_URI = re.compile(r"^at://(did:[a-z0-9]+:[A-Za-z0-9._:%-]+)/app\.bsky\.feed\.post/([A-Za-z0-9]+)$")
_WEB_PATH = re.compile(r"^/profile/([^/]+)/post/([A-Za-z0-9]+)/?$")
_HASHTAG = re.compile(r"#[^\s#.,!?;:()\[\]{}\"']+")


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def web_url(at_uri: str) -> str | None:
    m = _AT_URI.match(at_uri or "")
    return f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}" if m else None


def _hidden_from_logged_out(view: dict) -> bool:
    labels = (view.get("labels") or []) + ((view.get("author") or {}).get("labels") or [])
    return any(lb.get("val") == "!no-unauthenticated" for lb in labels)


@register
class BlueskyAdapter(HttpAdapterBase):
    name = "bluesky"
    platform = "bluesky"
    display_name = "Bluesky (public AppView)"
    tier = 2
    access = "official_api"
    adapter_version = VERSION
    content_type = "bluesky_post"
    required_env = ()
    allowed_hosts = frozenset({"public.api.bsky.app"})
    respect_robots = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self._views: dict[str, dict] = {}

    def _limit(self, key: str, default: int) -> int:
        b = self.ctx.budget
        if b is not None:
            return b.max_posts_per_query if key == "max_posts_per_query" else b.max_comments_per_post
        return int(self.cfg.get("budgets", {}).get(key, default))

    def health_check(self) -> Health:
        return Health("ok")

    def canonicalize_url(self, url: str) -> str | None:
        if url.startswith("at://"):
            return web_url(url)
        p = urlsplit(url)
        if p.netloc.lower() not in ("bsky.app", "www.bsky.app"):
            return None
        m = _WEB_PATH.match(p.path)
        if not m or not m.group(1).startswith("did:"):
            return None   # handle-based URLs need a resolve call; search results always carry the DID
        return f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}"

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        cur = json.loads(checkpoint.cursor) if checkpoint.cursor else {}
        n = max(1, min(100, self._limit("max_posts_per_query", 10)))
        params = {"q": query, "limit": n, "sort": "latest"}
        if self.cfg.get("lang"):
            params["lang"] = self.cfg["lang"]
        if cur.get("cursor"):
            params["cursor"] = cur["cursor"]
        try:
            r = self.http.get(f"{XRPC}/app.bsky.feed.searchPosts", params=params)
        except (LoginRequired, AccessBlocked) as e:
            if isinstance(e, AccessBlocked) and "host not allowed" in e.detail:
                raise
            raise Misconfigured(SEARCH_BLOCKER, e.url) from e
        if r.status_code >= 400:
            raise PlatformError(f"HTTP {r.status_code} {r.text[:120]}", safe_url(str(r.request.url)))
        shown = safe_url(str(r.request.url))
        data = r.json()
        items = []
        for pv in data.get("posts", []):
            canon = web_url(pv.get("uri", ""))
            if not canon:
                continue
            self._views[canon] = pv
            items.append(SearchItem(url=canon, canonical_url=canon, query=query, search_url=shown, source_id=pv["uri"],
                                    preview={"post": pv}))
        pages = int(cur.get("pages", 0)) + 1
        nxt_cur = {"cursor": data["cursor"], "pages": pages} if data.get("cursor") and items and \
            pages < int(self.cfg.get("max_pages_deep", 5)) else {}
        nxt = Checkpoint(query=query, cursor=json.dumps(nxt_cur) if nxt_cur else None, page=checkpoint.page + 1,
                         seen=list(checkpoint.seen), exhausted=not nxt_cur)
        self._next_checkpoint = nxt
        return SearchPage(items=items, next_checkpoint=nxt, exhausted=not items)

    def _thread(self, at_uri: str) -> dict:
        r = self.http.get(f"{XRPC}/app.bsky.feed.getPostThread",
                          params={"uri": at_uri, "depth": int(self.cfg.get("thread_depth", 6)), "parentHeight": 0})
        if r.status_code >= 400:
            raise PlatformError(f"HTTP {r.status_code} {r.text[:120]}", safe_url(str(r.request.url)))
        return r.json().get("thread") or {}

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url)
        if not canon:
            self.last_skip_reason = "not_a_bluesky_post_url"
            return None
        pv = (item.preview.get("post") if item and item.preview else None) or self._views.get(canon)
        if pv is None:
            did, rkey = canon.split("/profile/")[1].split("/post/")
            th = self._thread(f"at://{did}/app.bsky.feed.post/{rkey}")
            if th.get("$type") != "app.bsky.feed.defs#threadViewPost":
                self.last_skip_reason = "post_not_found_or_blocked"
                return None
            pv = th["post"]
        if _hidden_from_logged_out(pv):
            self.last_skip_reason = "author_opted_out_of_logged_out_visibility"
            return None
        return self.normalize_result({**pv, "search_query": item.query if item else "",
                                      "search_url": item.search_url if item else None})

    def normalize_result(self, pv: dict) -> SocialPost:
        rec, author = pv.get("record") or {}, pv.get("author") or {}
        canon = web_url(pv["uri"])
        text = (rec.get("text") or "").strip()[:20000] or None
        tags = [f"#{f['tag']}" for fc in rec.get("facets") or [] for f in fc.get("features") or []
                if f.get("$type") == "app.bsky.richtext.facet#tag" and f.get("tag")]
        eng = {k: pv[s] for k, s in (("likes", "likeCount"), ("reposts", "repostCount"), ("replies", "replyCount"),
                                     ("quotes", "quoteCount")) if pv.get(s) is not None}
        post = SocialPost(
            platform=self.platform, source_content_type=self.content_type, source_post_id=pv["uri"], source_post_url=canon,
            canonical_post_url=canon, document_title=None, post_title=None, post_text=text,
            hashtags=list(dict.fromkeys(tags + _HASHTAG.findall(text or ""))), published_text_displayed=rec.get("createdAt"),
            published_at_observed=_dt(rec.get("createdAt")), engagement=eng, visibility_status="public_verified",
            visibility_evidence="Bluesky public AppView (unauthenticated) returned the post; no !no-unauthenticated label",
            search_query=pv.get("search_query", ""), search_url=pv.get("search_url"), captured_at=datetime.now(timezone.utc),
            adapter_version=VERSION, content_hash=sha256_hex((text or "").casefold()),
            completeness_status="comments_unavailable", comments_supported=True)
        did = author.get("did")
        if looks_organizational(author.get("displayName")):
            post.organization = Organization(platform="bluesky", name=author["displayName"],
                                             url=f"https://bsky.app/profile/{did}" if did else None, kind="other",
                                             evidence="Bluesky account whose display name reads as a business")
        else:
            post.author_key = self.keyer.key_for("bluesky", did)
            post.author_key_version = self.keyer.version if post.author_key else None
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        limit = self._limit("max_comments_per_post", 200)
        th = self._thread(post.source_post_id)
        if th.get("$type") != "app.bsky.feed.defs#threadViewPost":
            return CommentBatch([], "comments_unavailable")
        owner = (th.get("post", {}).get("author") or {}).get("did")
        out: list[SocialComment] = []
        occ: dict = {}
        state = {"partial": False}

        def walk(nodes: list, parent: SocialComment | None, depth: int) -> None:
            for node in sorted(nodes or [], key=lambda x: ((x.get("post") or {}).get("record") or {}).get("createdAt") or ""):
                if node.get("$type") != "app.bsky.feed.defs#threadViewPost":
                    continue   # notFoundPost / blockedPost
                pv = node.get("post") or {}
                if _hidden_from_logged_out(pv):
                    continue
                if len(out) >= limit:
                    state["partial"] = True
                    return
                did = (pv.get("author") or {}).get("did")
                key = self.keyer.key_for("bluesky", did)
                rec = pv.get("record") or {}
                c = make_comment(platform=self.platform, post_url=post.canonical_post_url, raw_text=rec.get("text") or "",
                                 is_reply=parent is not None, parent=parent, commenter_key=key,
                                 key_version=self.keyer.version if key else None, displayed_timestamp=rec.get("createdAt"),
                                 commented_at=_dt(rec.get("createdAt")), source_comment_id=pv.get("uri"),
                                 source_comment_url=web_url(pv.get("uri", "")), occurrence_counter=occ)
                if c is not None:
                    c.is_post_author = bool(owner and did == owner)
                    out.append(c)
                if node.get("replies"):
                    walk(node["replies"], c or parent, depth + 1)
                elif (pv.get("replyCount") or 0) > 0:
                    state["partial"] = True   # deeper than the requested thread depth
        walk(th.get("replies") or [], None, 1)
        return CommentBatch(out, "partial_limit" if state["partial"] else "complete", 1)

    def capture_evidence(self, item) -> None:
        return None  # official API: no rendered page is opened; the permalink + API record is the evidence
