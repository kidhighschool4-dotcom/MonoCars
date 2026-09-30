"""Reddit public posts via the official OAuth API (app-only auth, documented endpoints only).

Access method
- App-only OAuth: client-credentials grant at https://www.reddit.com/api/v1/access_token with `REDDIT_CLIENT_ID` /
  `REDDIT_CLIENT_SECRET` (a "script" or "web" app registered at reddit.com/prefs/apps). Requests go to
  https://oauth.reddit.com with a descriptive User-Agent (`REDDIT_USER_AGENT` when set, as Reddit's API rules ask).
- Search: `GET /r/<sub>/search?q=..&restrict_sr=1&sort=new&limit=..&after=<cursor>` across the configured subreddits
  (`subreddits` in the platform config, else the discovery hints). One page per subreddit per call; per-subreddit
  `after` cursors live in the checkpoint.
- Post + comments: `GET /comments/<id>?limit=..&depth=..&sort=new` (raw_json=1). Threaded: every reply links to its parent.
- Rate limits: `X-Ratelimit-Remaining` / `X-Ratelimit-Reset` are honoured — a short reset is waited out, a long one
  raises RateLimited; HTTP 429 → RateLimited.

What is collected
- Posts in public, non-quarantined, non-NSFW subreddits: title, selftext, flair-free hashtags, created time, score /
  comment count / upvote ratio, post id, canonical URL (https://www.reddit.com/r/<sub>/comments/<id>/).
- Comments and replies (text redacted by `make_comment`; `u/name` mentions masked), ids and permalinks (Reddit
  permalinks contain no username). "[removed]" / "[deleted]" comments are skipped.

What is NOT collected
- Usernames, profile URLs or avatars — commenters and post authors are only `key_for("reddit", author_fullname)`
  (fallback: the author name, used only as HMAC input and never stored).
- NSFW (`over_18`), quarantined, private or banned subreddits; "load more" comment stubs beyond the first response
  (reported as `partial_limit`).
- Screenshots: API adapter, `capture_evidence` returns None.

Blockers
- Needs `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` (health → misconfigured "missing: ..."); a private / banned
  subreddit (403/404) is recorded in `blocked_subreddits` and the others continue.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from ...normalize import normalize_text, sha256_hex
from ...social.model import SocialComment, SocialPost, make_comment
from ..base import HttpAdapterBase
from ..contract import (AccessBlocked, Checkpoint, CommentBatch, Health, LoginRequired, Misconfigured, PlatformError,
                        RateLimited, SearchItem, SearchPage)
from ..discovery import load as load_discovery
from ..http import safe_url
from ..registry import register

VERSION = "reddit-oauth-api-v1"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"
DEFAULT_UA = "python:fbm-listingintel:1.0 (public listings research; app-only OAuth)"
_SUB = re.compile(r"^[A-Za-z0-9_]{2,21}$")
_POST_PATH = re.compile(r"^/r/([A-Za-z0-9_]{2,21})/comments/([a-z0-9]{3,12})(?:/|$)", re.I)
_SHORT_PATH = re.compile(r"^/(?:comments/)?([a-z0-9]{3,12})/?$", re.I)
_USER_MENTION = re.compile(r"(?<![\w/])/?u/[A-Za-z0-9_-]{3,20}")
_HASHTAG = re.compile(r"#[^\s#.,!?;:()\[\]{}\"']+")
_GONE = {"[removed]", "[deleted]", ""}


def _dt(ts) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


@register
class RedditAdapter(HttpAdapterBase):
    name = "reddit"
    platform = "reddit"
    display_name = "Reddit (official API)"
    tier = 1
    access = "official_api"
    adapter_version = VERSION
    content_type = "reddit_post"
    required_env = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")
    allowed_hosts = frozenset({"www.reddit.com", "oauth.reddit.com"})
    respect_robots = False

    def __init__(self, ctx):
        super().__init__(ctx)
        self._token: str | None = None
        self._token_exp = 0.0
        self._posts: dict[str, dict] = {}
        self._threads: dict[str, list] = {}
        self.blocked_subreddits: dict[str, str] = {}
        self.ua = os.environ.get("REDDIT_USER_AGENT") or DEFAULT_UA

    # ── config ──
    def subreddits(self) -> list[str]:
        subs = self.cfg.get("subreddits") or (self.cfg.get("discovery") or {}).get("subreddits") \
            or load_discovery().get("per_platform", {}).get("reddit", {}).get("subreddits", [])
        return [s.removeprefix("r/") for s in subs if _SUB.match(s.removeprefix("r/"))]

    def _limit(self, key: str, default: int) -> int:
        b = self.ctx.budget
        if b is not None:
            return b.max_posts_per_query if key == "max_posts_per_query" else b.max_comments_per_post
        return int(self.cfg.get("budgets", {}).get(key, default))

    # ── auth + requests ──
    def _auth(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
        if not cid or not secret:
            raise Misconfigured("missing: " + ", ".join(k for k in self.required_env if not os.environ.get(k)))
        try:
            r = self.http.post_form(TOKEN_URL, {"grant_type": "client_credentials"}, auth=(cid, secret),
                                    headers={"User-Agent": self.ua})
        except LoginRequired as e:
            raise Misconfigured("Reddit rejected REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET (HTTP 401)", TOKEN_URL) from e
        data = r.json()
        if "access_token" not in data:
            raise Misconfigured(f"Reddit token endpoint returned no token ({data.get('error', 'unknown error')})", TOKEN_URL)
        self._token = data["access_token"]
        self._token_exp = time.time() + float(data.get("expires_in", 3600))
        return self._token

    def _get(self, path: str, params: dict) -> tuple[object, str]:
        url = f"{API}{path}"
        r = self.http.get(url, params={**{k: v for k, v in params.items() if v not in (None, "")}, "raw_json": 1},
                          headers={"Authorization": f"bearer {self._auth()}", "User-Agent": self.ua})
        shown = safe_url(str(r.request.url)) if r.request else safe_url(url)
        if r.status_code >= 400:   # 401/403/429/5xx are already mapped by PoliteHttp; 404 = banned / missing
            try:
                why = r.json().get("reason") or r.json().get("message") or ""
            except (ValueError, AttributeError):
                why = ""
            raise PlatformError(f"HTTP {r.status_code} {why}".strip(), shown)
        self._respect_ratelimit(r.headers, shown)
        return r.json(), shown

    def _respect_ratelimit(self, headers, url: str) -> None:
        try:
            remaining = float(headers.get("x-ratelimit-remaining", "inf"))
            reset = float(headers.get("x-ratelimit-reset", "0"))
        except ValueError:
            return
        if remaining >= 1:
            return
        max_wait = float(self.cfg.get("max_ratelimit_sleep_s", 30))
        if reset <= max_wait:
            time.sleep(reset)
        else:
            raise RateLimited(f"Reddit X-Ratelimit-Remaining={remaining:g}, reset in {reset:g}s", url, reset)

    # ── contract ──
    def health_check(self) -> Health:
        missing = self.missing_env()
        if missing:
            return Health("misconfigured", "missing: " + ", ".join(missing))
        if not self.subreddits():
            return Health("misconfigured", "no subreddits configured (platforms.reddit.subreddits)")
        return Health("ok")

    def canonicalize_url(self, url: str) -> str | None:
        p = urlsplit(url)
        host = p.netloc.lower().split(":")[0]
        if host not in ("reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "np.reddit.com", "oauth.reddit.com"):
            return None
        m = _POST_PATH.match(p.path)
        return f"https://www.reddit.com/r/{m.group(1)}/comments/{m.group(2).lower()}/" if m else None

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        cur = json.loads(checkpoint.cursor) if checkpoint.cursor else {}
        n = max(1, min(100, self._limit("max_posts_per_query", 10)))
        items: list[SearchItem] = []
        nxt_cur: dict = {}
        subs = self.subreddits()
        for sub in subs:
            if sub in self.blocked_subreddits:
                continue
            try:
                data, shown = self._get(f"/r/{sub}/search", {"q": query, "restrict_sr": 1, "sort": "new", "limit": n,
                                                            "after": cur.get(sub), "type": "link"})
            except AccessBlocked as e:   # private / banned / quarantined subreddit: skip it, keep the others
                self.blocked_subreddits[sub] = e.detail
                continue
            except PlatformError as e:
                if "HTTP 404" in e.detail:
                    self.blocked_subreddits[sub] = "not found / banned"
                    continue
                raise
            listing = (data or {}).get("data", {}) if isinstance(data, dict) else {}
            for ch in listing.get("children", []):
                if ch.get("kind") != "t3":
                    continue
                d = ch.get("data", {})
                canon = f"https://www.reddit.com/r/{d.get('subreddit', sub)}/comments/{d['id']}/"
                self._posts[d["id"]] = d
                items.append(SearchItem(url=canon, canonical_url=canon, query=query, search_url=shown,
                                        source_id=d.get("name") or f"t3_{d['id']}", preview={"post": d}))
            if listing.get("after"):
                nxt_cur[sub] = listing["after"]
        if subs and not items and len(self.blocked_subreddits) >= len(subs):
            raise AccessBlocked("every configured subreddit is private / banned: " + ", ".join(sorted(self.blocked_subreddits)))
        nxt = Checkpoint(query=query, cursor=json.dumps(nxt_cur) if nxt_cur else None, page=checkpoint.page + 1,
                         seen=list(checkpoint.seen), exhausted=not nxt_cur)
        self._next_checkpoint = nxt
        return SearchPage(items=items, next_checkpoint=nxt, exhausted=not items)

    def _thread(self, pid: str) -> list:
        if pid not in self._threads:
            depth = int(self.cfg.get("comment_depth", 8))
            data, _ = self._get(f"/comments/{quote(pid)}", {"limit": min(500, self._limit("max_comments_per_post", 200)),
                                                            "depth": depth, "sort": "new"})
            self._threads[pid] = data if isinstance(data, list) else []
        return self._threads[pid]

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url)
        if not canon:
            self.last_skip_reason = "not_a_reddit_post_url"
            return None
        pid = canon.rstrip("/").rsplit("/", 1)[1]
        d = (item.preview.get("post") if item and item.preview else None) or self._posts.get(pid)
        if d is None:
            try:
                th = self._thread(pid)
            except AccessBlocked:
                self.last_skip_reason = "subreddit_private_or_banned"
                return None
            kids = th[0].get("data", {}).get("children", []) if th else []
            d = kids[0].get("data") if kids else None
            if d is None:
                self.last_skip_reason = "post_not_found"
                return None
        reason = self._not_public_reason(d)
        if reason:
            self.last_skip_reason = reason
            return None
        return self.normalize_result({**d, "search_query": item.query if item else "",
                                      "search_url": item.search_url if item else None})

    @staticmethod
    def _not_public_reason(d: dict) -> str | None:
        if d.get("over_18"):
            return "nsfw_over_18"
        if d.get("quarantine"):
            return "quarantined_subreddit"
        if d.get("subreddit_type") not in (None, "public"):
            return f"subreddit_not_public:{d.get('subreddit_type')}"
        if d.get("removed_by_category") or d.get("selftext") in ("[removed]", "[deleted]"):
            return "post_removed"
        return None

    def normalize_result(self, d: dict) -> SocialPost:
        canon = f"https://www.reddit.com/r/{d.get('subreddit')}/comments/{d['id']}/"
        title = normalize_text(d.get("title")) or None
        body = (d.get("selftext") or "").strip()
        body = _USER_MENTION.sub("[mention]", body)[:20000] or None
        eng = {k: d[s] for k, s in (("score", "score"), ("comments", "num_comments"), ("upvote_ratio", "upvote_ratio"))
               if d.get(s) is not None}
        post = SocialPost(
            platform=self.platform, source_content_type=self.content_type, source_post_id=d.get("name") or f"t3_{d['id']}",
            source_post_url=canon, canonical_post_url=canon, document_title=f"r/{d.get('subreddit')}", post_title=title,
            post_text=body, hashtags=list(dict.fromkeys(_HASHTAG.findall(f"{title or ''} {body or ''}"))),
            published_text_displayed=None, published_at_observed=_dt(d.get("created_utc")), engagement=eng,
            visibility_status="public_verified",
            visibility_evidence=f"Reddit API: subreddit_type {d.get('subreddit_type', 'public')}, over_18 false, not quarantined",
            search_query=d.get("search_query", ""), search_url=d.get("search_url"), captured_at=datetime.now(timezone.utc),
            adapter_version=VERSION, content_hash=sha256_hex(f"{title or ''}\n{body or ''}".casefold()),
            completeness_status="comments_unavailable", comments_supported=True)
        author = d.get("author_fullname") or (d.get("author") if d.get("author") not in ("[deleted]", None) else None)
        post.author_key = self.keyer.key_for("reddit", author)
        post.author_key_version = self.keyer.version if post.author_key else None
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        pid = post.source_post_id.removeprefix("t3_")
        limit = self._limit("max_comments_per_post", 200)
        th = self._thread(pid)
        post_d = (th[0].get("data", {}).get("children") or [{}])[0].get("data", {}) if th else {}
        post_author = post_d.get("author_fullname") or self._posts.get(pid, {}).get("author_fullname")
        out: list[SocialComment] = []
        occ: dict = {}
        state = {"partial": False}

        def walk(children: list, parent: SocialComment | None) -> None:
            for ch in children:
                if ch.get("kind") == "more":
                    if (ch.get("data", {}).get("count") or 0) > 0 or ch.get("data", {}).get("children"):
                        state["partial"] = True
                    continue
                if ch.get("kind") != "t1":
                    continue
                if len(out) >= limit:
                    state["partial"] = True
                    return
                d = ch.get("data", {})
                body = (d.get("body") or "").strip()
                c = None
                if body not in _GONE and d.get("author") != "[deleted]":
                    author = d.get("author_fullname") or d.get("author")
                    key = self.keyer.key_for("reddit", author)
                    link = f"https://www.reddit.com{d['permalink']}" if d.get("permalink") else None
                    c = make_comment(platform=self.platform, post_url=post.canonical_post_url,
                                     raw_text=_USER_MENTION.sub("[mention]", body), is_reply=parent is not None, parent=parent,
                                     commenter_key=key, key_version=self.keyer.version if key else None,
                                     displayed_timestamp=None, commented_at=_dt(d.get("created_utc")),
                                     source_comment_id=d.get("name") or f"t1_{d.get('id')}", source_comment_url=link,
                                     occurrence_counter=occ)
                    if c is not None:
                        c.is_post_author = bool(post_author and d.get("author_fullname") == post_author) or bool(d.get("is_submitter"))
                        out.append(c)
                replies = d.get("replies")
                if isinstance(replies, dict):
                    # a removed comment's replies attach to the nearest kept ancestor
                    walk(replies.get("data", {}).get("children", []), c or parent)

        walk(th[1].get("data", {}).get("children", []) if len(th) > 1 else [], None)
        return CommentBatch(out, "partial_limit" if state["partial"] else "complete", 1)

    def capture_evidence(self, item) -> None:
        return None  # official API: no rendered page is opened; the permalink + API record is the evidence
