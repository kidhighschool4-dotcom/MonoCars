"""Telegram public channels via the public web preview (https://t.me/s/<channel>), no login, no Bot/MTProto API.

- Search: the preview's own in-channel search (`?q=`) over each configured public channel; older pages via `before=`.
- Posts: channel messages. Comments: NOT available — discussion-group replies are not part of the public web preview
  (would need a logged-in MTProto client inside the group), so posts are stored with completeness `comments_unavailable`.
- Public groups: not viewable in the web preview → not collected (reported as a blocker).
- A public channel is a publisher, stored as an Organization only when it is clearly organizational (configured, or its
  title reads like a business); otherwise only a pseudonymous key is kept.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup

from ...comments import redact
from ...normalize import normalize_text, sha256_hex
from ...social.model import SocialPost
from ..base import HttpAdapterBase
from ..contract import Checkpoint, CommentBatch, Health, Organization, SearchItem, SearchPage
from ..http import safe_url
from ..leads import looks_organizational
from ..registry import register

VERSION = "telegram-public-web-v1"
_POST_PATH = re.compile(r"^/(?:s/)?([A-Za-z][A-Za-z0-9_]{3,31})/(\d+)/?$")


def parse_messages(html: str) -> tuple[str | None, list[dict]]:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one(".tgme_channel_info_header_title") or soup.select_one(".tgme_widget_message_owner_name")
    title = normalize_text(title_el.get_text(" ")) if title_el else None
    out = []
    for m in soup.select(".tgme_widget_message[data-post]"):
        ref = m.get("data-post", "")
        if "/" not in ref:
            continue
        ch, mid = ref.split("/", 1)
        text_el = m.select_one(".tgme_widget_message_text")
        t = m.select_one("time[datetime]")
        views = m.select_one(".tgme_widget_message_views")
        out.append({
            "channel": ch, "id": mid, "text": text_el.get_text("\n") if text_el else "",
            "datetime": t["datetime"] if t else None, "time_text": t.get_text(strip=True) if t else None,
            "views": views.get_text(strip=True) if views else None,
            "hashtags": [a.get_text(strip=True) for a in (text_el.select("a[href^='?q=%23']") if text_el else [])],
            "has_media": bool(m.select_one(".tgme_widget_message_photo_wrap, .tgme_widget_message_video_player")),
            "channel_title": title,
        })
    return title, out


@register
class TelegramChannelsAdapter(HttpAdapterBase):
    name = "telegram"
    platform = "telegram"
    display_name = "Telegram (public channels)"
    tier = 2
    access = "public_web"
    adapter_version = VERSION
    supports_comments = False
    content_type = "telegram_channel_post"
    allowed_hosts = frozenset({"t.me"})

    def channels(self) -> list[dict]:
        out = []
        for c in self.cfg.get("channels", []):
            out.append(c if isinstance(c, dict) else {"name": c})
        return [c for c in out if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", c["name"])]

    def health_check(self) -> Health:
        if not self.channels():
            return Health("misconfigured", "no public channels configured (platforms.telegram.channels); "
                                           "Telegram has no public cross-channel search on the web")
        return Health("ok")

    def canonicalize_url(self, url: str) -> str | None:
        p = urlsplit(url)
        if p.netloc.lower() not in ("t.me", "telegram.me", "www.t.me"):
            return None
        m = _POST_PATH.match(p.path)
        return f"https://t.me/{m.group(1)}/{m.group(2)}" if m else None

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        cursor = json.loads(checkpoint.cursor) if checkpoint.cursor else {}
        items: list[SearchItem] = []
        self._cache: dict[str, dict] = getattr(self, "_cache", {})
        for ch in self.channels():
            name = ch["name"]
            url = f"https://t.me/s/{name}?q={quote(query)}"
            r = self.http.get(url)
            _, msgs = parse_messages(r.text)
            newest = int(cursor.get(name, 0))
            for m in sorted(msgs, key=lambda x: int(x["id"]), reverse=True):
                if int(m["id"]) <= newest and not checkpoint.exhausted:
                    continue
                canon = f"https://t.me/{m['channel']}/{m['id']}"
                m["channel_config"] = ch
                self._cache[canon] = m
                items.append(SearchItem(url=canon, canonical_url=canon, query=query, search_url=safe_url(url),
                                        source_id=f"{m['channel']}/{m['id']}", preview=m))
            if msgs:
                cursor[name] = max(newest, max(int(m["id"]) for m in msgs))
        nxt = Checkpoint(query=query, cursor=json.dumps(cursor), page=checkpoint.page + 1, seen=list(checkpoint.seen))
        self._next_checkpoint = nxt
        return SearchPage(items=items, next_checkpoint=nxt, exhausted=not items)

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url)
        if not canon:
            self.last_skip_reason = "not_a_public_channel_post"
            return None
        m = (item.preview if item and item.preview else None) or getattr(self, "_cache", {}).get(canon)
        if m is None:
            ch, mid = canon.rsplit("/", 2)[-2:]
            r = self.http.get(f"https://t.me/s/{ch}?before={int(mid) + 1}")
            _, msgs = parse_messages(r.text)
            m = next((x for x in msgs if x["id"] == mid), None)
            if m is None:
                self.last_skip_reason = "message_not_in_public_preview"
                return None
        post = self.normalize_result({**m, "search_query": item.query if item else "", "search_url": item.search_url if item else None})
        return post

    def normalize_result(self, m: dict) -> SocialPost:
        text = redact(normalize_text(m.get("text") or ""))[:20000] or None   # phones/emails/links out of stored text
        dt = None
        if m.get("datetime"):
            try:
                dt = datetime.fromisoformat(m["datetime"])
            except ValueError:
                dt = None
        canon = f"https://t.me/{m['channel']}/{m['id']}"
        post = SocialPost(
            platform=self.platform, source_content_type=self.content_type, source_post_id=f"{m['channel']}/{m['id']}",
            source_post_url=canon, canonical_post_url=canon, document_title=m.get("channel_title"), post_title=None,
            post_text=text, hashtags=m.get("hashtags") or re.findall(r"#\w+", text or ""),
            published_text_displayed=m.get("time_text"), published_at_observed=dt,
            engagement={"views": m["views"]} if m.get("views") else {}, visibility_status="public_verified",
            visibility_evidence="Shown in the public channel web preview (t.me/s)", search_query=m.get("search_query", ""),
            search_url=m.get("search_url"), captured_at=datetime.now(timezone.utc), adapter_version=VERSION,
            content_hash=sha256_hex((text or "").casefold()), completeness_status="comments_unavailable",
            comments_supported=False)
        ch = m.get("channel_config") or {}
        if ch.get("organizational") or looks_organizational(m.get("channel_title")) or looks_organizational(m["channel"]):
            post.organization = Organization(platform="telegram", name=m.get("channel_title") or m["channel"],
                                             url=f"https://t.me/{m['channel']}", kind="channel",
                                             evidence="configured as organizational" if ch.get("organizational")
                                             else "public channel whose name reads as a business")
        else:  # a private individual's channel: no title/name kept, only a pseudonymous key
            post.document_title = None
            post.author_key = self.keyer.key_for("telegram", m["channel"].casefold())
            post.author_key_version = self.keyer.version
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        return CommentBatch([], "comments_unavailable")

    def capture_evidence(self, item) -> None:
        return None  # no browser for this adapter; the public URL itself is the evidence
