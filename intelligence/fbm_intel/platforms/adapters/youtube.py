"""YouTube public videos via the official YouTube Data API v3 (documented endpoints only, API key auth).

Access method
- `search.list` (type=video, q, regionCode / relevanceLanguage from config or discovery hints, pageToken as cursor),
  `videos.list` (snippet, statistics, status — batched for a whole search page), `commentThreads.list` (top-level
  comments + the replies the API inlines) and `comments.list` (remaining replies of a thread), all with
  textFormat=plainText. Credential: `YOUTUBE_API_KEY` (a Google Cloud API key with the YouTube Data API enabled).
- Quota: every call's documented unit cost (search.list = 100, the others = 1) is added to the daily usage through the
  worker budget; a call that would exceed `daily_quota_units` stops with BudgetExhausted("youtube_quota").
  The API's own `quotaExceeded` / `rateLimitExceeded` (403) → RateLimited.

What is collected
- Public videos only (`status.privacyStatus == "public"`): title, description, hashtags (from title/description),
  publishedAt, displayed statistics (views / likes / comment count), video id, canonical watch URL.
- Public comments and replies (plain text, phones/emails/links redacted by `make_comment`), comment ids and
  permalinks (`watch?v=<id>&lc=<commentId>`), bounded by the budget's `max_comments_per_post` (→ `partial_limit`).
- The uploading channel is stored as an Organization only when its title reads as a business; otherwise only a
  pseudonymous `author_key` (HMAC of the channel id).

What is NOT collected
- Commenter display names, channel URLs, avatars or handles (only `key_for("youtube", authorChannelId)`).
- Screenshots: this is an API adapter with no rendered page, so `capture_evidence` returns None; the video/comment
  permalink plus the API record is the evidence.
- Private / unlisted / members-only videos, live chat, captions.

Blockers
- Needs `YOUTUBE_API_KEY` (health → misconfigured "missing: YOUTUBE_API_KEY" without it).
- Default API quota is 10,000 units/day; each search page costs 100 units.
- Videos with comments disabled → completeness `comments_unavailable` (not an error).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from ...normalize import normalize_text, sha256_hex
from ...social.model import SocialComment, SocialPost, make_comment
from ..base import HttpAdapterBase
from ..contract import (AccessBlocked, BudgetExhausted, Checkpoint, CommentBatch, Health, Misconfigured, Organization,
                        PlatformError, RateLimited, SearchItem, SearchPage)
from ..discovery import load as load_discovery
from ..http import PoliteHttp, host_allowed, safe_url
from ..leads import looks_organizational
from ..registry import register

VERSION = "youtube-data-api-v3-v1"
API = "https://www.googleapis.com/youtube/v3"
COST = {"search": 100, "videos": 1, "commentThreads": 1, "comments": 1}
_QUOTA_REASONS = {"quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded", "userRateLimitExceeded"}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HASHTAG = re.compile(r"#[^\s#.,!?;:()\[\]{}\"']+")


class _CommentsDisabled(Exception):
    pass


class _NotFound(Exception):
    pass


def _error_reason(r: httpx.Response) -> tuple[str, str]:
    try:
        err = r.json().get("error", {})
        errs = err.get("errors") or [{}]
        return errs[0].get("reason", "") or "", err.get("message", "") or ""
    except (ValueError, AttributeError):
        return "", ""


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def hashtags_in(text: str) -> list[str]:
    return list(dict.fromkeys(_HASHTAG.findall(text or "")))


@register
class YouTubeAdapter(HttpAdapterBase):
    name = "youtube"
    platform = "youtube"
    display_name = "YouTube (Data API v3)"
    tier = 1
    access = "official_api"
    adapter_version = VERSION
    content_type = "youtube_video"
    required_env = ("YOUTUBE_API_KEY",)
    allowed_hosts = frozenset({"www.googleapis.com", "youtube.googleapis.com"})
    respect_robots = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self._videos: dict[str, dict] = {}
        self.units_used = 0
        hints = load_discovery().get("per_platform", {}).get("youtube", {})
        disc = {**hints, **(self.cfg.get("discovery") or {})}
        self.region_code = self.cfg.get("region_code") or disc.get("region_code")
        self.relevance_language = self.cfg.get("relevance_language") or disc.get("relevance_language")

    # ── limits ──
    def _limit(self, key: str, default: int) -> int:
        b = self.ctx.budget
        if b is not None:
            return b.max_posts_per_query if key == "max_posts_per_query" else b.max_comments_per_post
        return int(self.cfg.get("budgets", {}).get(key, default))

    def _charge(self, cost: int) -> None:
        b = self.ctx.budget
        used = b.api_units_today() if (b is not None and getattr(b, "state", None) is not None) else self.units_used
        quota = int(self.cfg.get("daily_quota_units", 10000))
        if used + cost > quota:
            raise BudgetExhausted("youtube_quota")
        self.units_used += cost
        if b is not None:
            b.add_api_units(cost)

    # ── transport: PoliteHttp policy, but 400/403/404 bodies are inspected for the API's error reason ──
    def _call(self, endpoint: str, params: dict) -> tuple[dict, str]:
        key = os.environ.get("YOUTUBE_API_KEY")
        if not key:
            raise Misconfigured("missing: YOUTUBE_API_KEY")
        self._charge(COST[endpoint])
        q = {k: v for k, v in params.items() if v not in (None, "")}
        url = f"{API}/{endpoint}?{urlencode({**q, 'key': key})}"
        shown = safe_url(url)
        host = urlsplit(url).netloc
        if not host_allowed(host, self.http.allowed):
            raise AccessBlocked(f"host not allowed for this adapter: {host}", shown)
        self.http._pace(host)
        self.http.requests += 1
        try:
            r = self.http.client.get(url)
        except httpx.TimeoutException as e:
            raise PlatformError(f"timeout: {type(e).__name__}", shown) from e
        except httpx.HTTPError as e:
            raise PlatformError(f"network error: {type(e).__name__}", shown) from e
        if r.status_code in (400, 403, 404):
            reason, msg = _error_reason(r)
            if reason in _QUOTA_REASONS:
                raise RateLimited(f"YouTube API {reason}", shown)
            if reason == "commentsDisabled":
                raise _CommentsDisabled()
            if reason in ("keyInvalid", "keyExpired") or "api key" in msg.lower():
                raise Misconfigured(f"YouTube API key rejected ({reason or 'invalid'}); check YOUTUBE_API_KEY", shown)
            if r.status_code == 404 or reason in ("videoNotFound", "commentThreadNotFound"):
                raise _NotFound(reason or "notFound")
            if r.status_code == 403:
                raise AccessBlocked(f"HTTP 403 {reason or 'forbidden'}", shown)
            raise PlatformError(f"HTTP 400 {reason or msg[:120]}", shown)
        PoliteHttp.check(r, shown)
        return r.json(), shown

    # ── contract ──
    def health_check(self) -> Health:
        missing = self.missing_env()
        return Health("misconfigured", "missing: " + ", ".join(missing)) if missing else Health("ok")

    def canonicalize_url(self, url: str) -> str | None:
        p = urlsplit(url)
        host = p.netloc.lower().split(":")[0]
        vid = None
        if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
            if p.path == "/watch":
                vid = (parse_qs(p.query).get("v") or [None])[0]
            elif p.path.startswith(("/shorts/", "/embed/", "/live/")):
                vid = p.path.split("/")[2] if len(p.path.split("/")) > 2 else None
        elif host == "youtu.be":
            vid = p.path.strip("/").split("/")[0]
        return f"https://www.youtube.com/watch?v={vid}" if vid and _VIDEO_ID.match(vid) else None

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        cur = json.loads(checkpoint.cursor) if checkpoint.cursor else {}
        n = max(1, min(50, self._limit("max_posts_per_query", 10)))
        data, shown = self._call("search", {
            "part": "snippet", "type": "video", "q": query, "maxResults": n, "regionCode": self.region_code,
            "relevanceLanguage": self.relevance_language, "pageToken": cur.get("page_token"), "safeSearch": "none"})
        ids = [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]
        if ids:
            vd, _ = self._call("videos", {"part": "snippet,statistics,status", "id": ",".join(ids), "maxResults": len(ids)})
            for v in vd.get("items", []):
                self._videos[v["id"]] = v
        items = []
        for vid in ids:
            canon = f"https://www.youtube.com/watch?v={vid}"
            items.append(SearchItem(url=canon, canonical_url=canon, query=query, search_url=shown, source_id=vid,
                                    preview={"video": self._videos.get(vid)}))
        token = data.get("nextPageToken")
        pages = int(cur.get("pages", 0)) + 1
        max_pages = int(self.cfg.get("max_pages_deep", 5))
        # page deeper while there are pages; after max_pages_deep (or the end) start again from the top next cycle
        nxt_cur = {"page_token": token, "pages": pages} if token and pages < max_pages else {}
        nxt = Checkpoint(query=query, cursor=json.dumps(nxt_cur) if nxt_cur else None, page=checkpoint.page + 1,
                         seen=list(checkpoint.seen), exhausted=not nxt_cur)
        self._next_checkpoint = nxt
        return SearchPage(items=items, next_checkpoint=nxt, exhausted=not items)

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url)
        if not canon:
            self.last_skip_reason = "not_a_youtube_video_url"
            return None
        vid = canon.rsplit("=", 1)[1]
        v = (item.preview.get("video") if item and item.preview else None) or self._videos.get(vid)
        if v is None:
            try:
                vd, _ = self._call("videos", {"part": "snippet,statistics,status", "id": vid})
            except _NotFound:
                vd = {}
            v = (vd.get("items") or [None])[0]
            if v is None:
                self.last_skip_reason = "video_not_found"
                return None
            self._videos[vid] = v
        status = v.get("status", {})
        if status.get("privacyStatus") != "public":
            self.last_skip_reason = f"not_public:{status.get('privacyStatus') or 'unknown'}"
            return None
        return self.normalize_result({**v, "search_query": item.query if item else "",
                                      "search_url": item.search_url if item else None})

    def normalize_result(self, v: dict) -> SocialPost:
        sn, st = v.get("snippet", {}), v.get("statistics", {})
        vid = v["id"] if isinstance(v.get("id"), str) else v.get("id", {}).get("videoId")
        canon = f"https://www.youtube.com/watch?v={vid}"
        title = normalize_text(sn.get("title")) or None
        desc = (sn.get("description") or "").strip()[:20000] or None
        engagement = {k: _int(st[c]) for k, c in (("views", "viewCount"), ("likes", "likeCount"),
                                                  ("comments", "commentCount")) if st.get(c) is not None}
        post = SocialPost(
            platform=self.platform, source_content_type=self.content_type, source_post_id=vid, source_post_url=canon,
            canonical_post_url=canon, document_title=None, post_title=title, post_text=desc,
            hashtags=hashtags_in(f"{title or ''} {desc or ''}"), published_text_displayed=sn.get("publishedAt"),
            published_at_observed=_dt(sn.get("publishedAt")), engagement=engagement, visibility_status="public_verified",
            visibility_evidence=f"YouTube Data API: video status.privacyStatus {v.get('status', {}).get('privacyStatus', 'public')}",
            search_query=v.get("search_query", ""), search_url=v.get("search_url"), captured_at=datetime.now(timezone.utc),
            adapter_version=VERSION, content_hash=sha256_hex(f"{title or ''}\n{desc or ''}".casefold()),
            completeness_status="comments_unavailable", comments_supported=True)
        channel_id, channel_title = sn.get("channelId"), sn.get("channelTitle")
        self._channel_of = getattr(self, "_channel_of", {})
        self._channel_of[vid] = channel_id
        if looks_organizational(channel_title):
            post.organization = Organization(platform="youtube", name=channel_title,
                                             url=f"https://www.youtube.com/channel/{channel_id}" if channel_id else None,
                                             kind="channel", evidence="YouTube channel whose title reads as a business")
        else:
            post.author_key = self.keyer.key_for("youtube", channel_id)
            post.author_key_version = self.keyer.version if post.author_key else None
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        vid = post.source_post_id
        limit = self._limit("max_comments_per_post", 200)
        owner = getattr(self, "_channel_of", {}).get(vid)
        out: list[SocialComment] = []
        occ: dict = {}
        rounds = 0

        def add(snip: dict, cid: str, parent: SocialComment | None) -> SocialComment | None:
            author = (snip.get("authorChannelId") or {}).get("value")
            key = self.keyer.key_for("youtube", author)
            c = make_comment(platform=self.platform, post_url=post.canonical_post_url,
                             raw_text=snip.get("textOriginal") or snip.get("textDisplay") or "", is_reply=parent is not None,
                             parent=parent, commenter_key=key, key_version=self.keyer.version if key else None,
                             displayed_timestamp=snip.get("publishedAt"), commented_at=_dt(snip.get("publishedAt")),
                             source_comment_id=cid, source_comment_url=f"https://www.youtube.com/watch?v={vid}&lc={cid}",
                             occurrence_counter=occ)
            if c is not None:
                c.is_post_author = bool(owner and author == owner)
                out.append(c)
            return c

        token = None
        try:
            while True:
                n = max(1, min(100, limit - len(out)))
                data, _ = self._call("commentThreads", {"part": "snippet,replies", "videoId": vid, "maxResults": n,
                                                        "textFormat": "plainText", "order": "time", "pageToken": token})
                rounds += 1
                for th in data.get("items", []):
                    if len(out) >= limit:
                        return CommentBatch(out, "partial_limit", rounds)
                    top = th.get("snippet", {}).get("topLevelComment", {})
                    parent = add(top.get("snippet", {}), top.get("id") or th.get("id"), None)
                    if parent is None:
                        continue
                    total = int(th.get("snippet", {}).get("totalReplyCount") or 0)
                    inline = (th.get("replies") or {}).get("comments", [])
                    replies = inline
                    if total > len(inline):
                        replies, r_rounds = self._all_replies(th.get("id"), limit - len(out))
                        rounds += r_rounds
                    for rp in sorted(replies, key=lambda x: x.get("snippet", {}).get("publishedAt") or ""):
                        if len(out) >= limit:
                            return CommentBatch(out, "partial_limit", rounds)
                        add(rp.get("snippet", {}), rp.get("id"), parent)
                token = data.get("nextPageToken")
                if not token:
                    return CommentBatch(out, "complete", rounds)
                if len(out) >= limit:
                    return CommentBatch(out, "partial_limit", rounds)
        except _CommentsDisabled:
            return CommentBatch(out, "comments_unavailable", rounds)
        except _NotFound:
            return CommentBatch(out, "comments_unavailable", rounds)

    def _all_replies(self, parent_id: str, room: int) -> tuple[list[dict], int]:
        out, token, rounds = [], None, 0
        while room > 0:
            data, _ = self._call("comments", {"part": "snippet", "parentId": parent_id, "maxResults": max(1, min(100, room + 1)),
                                              "textFormat": "plainText", "pageToken": token})
            rounds += 1
            items = data.get("items", [])
            out += items
            room -= len(items)
            token = data.get("nextPageToken")
            if not token:
                break
        return out, rounds

    def capture_evidence(self, item) -> None:
        return None  # official API: no rendered page is opened; the permalink + API record is the evidence
