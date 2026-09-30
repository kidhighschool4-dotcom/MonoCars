"""Records, limits and the pure logic that turns raw extracted comments into linked, de-duplicated rows."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..normalize import normalize_text, sha256_hex, stable_hash
from ..social.model import Evidence
from .identity import PersonKeyer
from .urls import canonical_comment_url, comment_ids

ADAPTER_VERSION = "facebook-public-posts-v1"
INCOMPLETE_REASONS = {"configured_limit_reached", "timeout", "facebook_stopped_loading", "login_wall", "checkpoint",
                      "captcha", "rate_limit", "post_unavailable", "visibility_changed", "not_attempted", "unknown"}


@dataclass(frozen=True)
class Limits:
    max_posts_per_query: int = 10
    max_search_scrolls: int = 3
    max_comments_per_post: int = 200
    max_replies_per_comment: int = 50
    max_comment_expansion_rounds: int = 15
    max_clicks_per_round: int = 15
    comment_load_timeout_seconds: int = 90
    page_load_interval_s: float = 8.0
    expansion_click_pause_ms: int = 1200
    settle_ms: int = 3500              # wait after each page load
    scroll_pause_ms: int = 3500


@dataclass
class RawComment:
    """What the browser extracted for one comment/reply. author_href is used ONLY to compute the HMAC key."""
    kind: str                      # 'comment' | 'reply'
    text: str
    permalink: str | None
    author_href: str | None
    time_text: str | None
    dom_parent: int | None = None  # index of the enclosing top-level comment in the raw list, if known


@dataclass
class PublicComment:
    fingerprint: str
    parent_fingerprint: str | None
    comment_type: str
    source_comment_id: str | None
    source_comment_url: str | None
    canonical_comment_url: str | None
    commenter_key: str | None
    commenter_key_version: str | None
    comment_text: str
    commented_at_observed: datetime | None
    content_hash: str
    comment_text_normalized: str = ""
    buyer_intent: bool = False
    buyer_intent_signals: list[str] = field(default_factory=list)
    matched_phrases: list[str] = field(default_factory=list)
    intent_classifier_version: str | None = None
    screenshot: Evidence | None = None   # buyer-intent comments only; commenter name/avatar hidden before capture


@dataclass
class PublicPost:
    source_post_id: str | None
    source_post_url: str
    canonical_post_url: str
    author_key: str | None
    author_key_version: str | None
    post_text: str | None
    published_at_observed: datetime | None
    visibility_status: str
    visibility_evidence: str
    search_query: str
    captured_at: datetime
    content_hash: str
    comments: list[PublicComment] = field(default_factory=list)
    comments_complete: bool = False
    comments_incomplete_reason: str | None = "not_attempted"
    comment_expansion_rounds: int = 0
    screenshot: Evidence | None = None   # post region; author name/avatar hidden before capture

    @property
    def comments_collected_count(self) -> int:
        return sum(c.comment_type == "comment" for c in self.comments)

    @property
    def replies_collected_count(self) -> int:
        return sum(c.comment_type == "reply" for c in self.comments)


_REL = re.compile(r"^(\d+)\s*(s|m|min|mins|h|hr|hrs|d|w|wk|y|yr)s?$")
_UNITS = {"s": timedelta(seconds=1), "m": timedelta(minutes=1), "min": timedelta(minutes=1), "mins": timedelta(minutes=1),
          "h": timedelta(hours=1), "hr": timedelta(hours=1), "hrs": timedelta(hours=1), "d": timedelta(days=1),
          "w": timedelta(weeks=1), "wk": timedelta(weeks=1), "y": timedelta(days=365), "yr": timedelta(days=365)}


def parse_fb_time(text: str | None, now: datetime | None = None) -> datetime | None:
    """Facebook's compact relative times ('3h', '2d', '1w', 'Just now', 'Yesterday')."""
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    t = normalize_text(text).casefold()
    if t in ("just now", "now"):
        return now
    if t == "yesterday" or t.startswith("yesterday at"):
        return now - timedelta(days=1)
    m = _REL.match(t)
    if m:
        return now - int(m.group(1)) * _UNITS[m.group(2)]
    from ..normalize import parse_published_at
    return parse_published_at(t, now)


def build_comments(raw: list[RawComment], post_canonical_url: str, keyer: PersonKeyer, limits: Limits,
                   now: datetime | None = None) -> tuple[list[PublicComment], bool]:
    """Link replies to parents, compute stable fingerprints, enforce limits.

    Returns (comments, truncated) — truncated=True if a configured limit dropped anything.
    Fingerprint = Facebook's own comment/reply id when available; otherwise a deterministic fallback hash of
    (canonical post URL, commenter HMAC key, normalized text, parent fingerprint, occurrence #).
    The observed time is deliberately NOT part of the fallback: Facebook only shows relative times ("2d"),
    which would change between crawls and create duplicates.
    """
    now = now or datetime.now(timezone.utc)
    out: list[PublicComment] = []
    by_raw_index: dict[int, PublicComment] = {}
    by_source_id: dict[str, PublicComment] = {}
    replies_per_parent: dict[str, int] = {}
    seen: dict[str, int] = {}
    last_top: PublicComment | None = None
    truncated = False

    for i, r in enumerate(raw):
        from ..comments import redact
        text = redact(normalize_text(r.text))[:10000]   # phone numbers / emails / links typed in comments → [phone] etc.
        if not text or text == "[mention]":
            continue
        cid, rid = comment_ids(r.permalink) if r.permalink else (None, None)
        is_reply = r.kind == "reply" or bool(rid)
        own_id = rid if is_reply and rid else (cid if not is_reply else None)
        key = keyer.key(r.author_href)

        parent: PublicComment | None = None
        if is_reply:
            if rid and cid and cid in by_source_id:
                parent = by_source_id[cid]
            elif r.dom_parent is not None and r.dom_parent in by_raw_index:
                parent = by_raw_index[r.dom_parent]
            else:
                parent = last_top
            if parent is None:
                continue  # orphan reply we can't place — skip rather than guess
            if replies_per_parent.get(parent.fingerprint, 0) >= limits.max_replies_per_comment:
                truncated = True
                continue

        if len(out) >= limits.max_comments_per_post:
            truncated = True
            break

        if own_id:
            fp = f"id:{own_id}"
        else:
            base = stable_hash(post_canonical_url, key or "", text.casefold(), parent.fingerprint if parent else "")
            n = seen.get(base, 0)
            seen[base] = n + 1
            fp = "fb:" + sha256_hex(f"{base}:{n}")
        if any(c.fingerprint == fp for c in out):
            continue  # same comment rendered twice

        canon = canonical_comment_url(post_canonical_url, cid, rid) if cid else None
        from .urls import canonicalize
        source_url = canonicalize(r.permalink, keep_comment_params=True) if r.permalink else None
        from ..comments import classify
        intent = classify(text)
        c = PublicComment(
            comment_text_normalized=intent.normalized, buyer_intent=intent.is_buyer,
            buyer_intent_signals=intent.signals if intent.is_buyer else [],
            matched_phrases=intent.matched_phrases if intent.is_buyer else [],
            intent_classifier_version=intent.version,
            fingerprint=fp, parent_fingerprint=parent.fingerprint if parent else None,
            comment_type="reply" if is_reply else "comment", source_comment_id=own_id,
            source_comment_url=source_url, canonical_comment_url=canon,
            commenter_key=key, commenter_key_version=keyer.version if key else None,
            comment_text=text, commented_at_observed=parse_fb_time(r.time_text, now),
            content_hash=sha256_hex(text.casefold()),
        )
        out.append(c)
        by_raw_index[i] = c
        if own_id:
            by_source_id[own_id] = c
        if is_reply:
            replies_per_parent[parent.fingerprint] = replies_per_parent.get(parent.fingerprint, 0) + 1
        else:
            last_top = c
    return out, truncated


def keep_buyer_intent(comments: list[PublicComment]) -> list[PublicComment]:
    """Keep only comments/replies that show buying intent, plus the parent of any kept reply (for context and FK)."""
    buyers = {c.fingerprint for c in comments if c.buyer_intent}
    parents = {c.parent_fingerprint for c in comments if c.fingerprint in buyers and c.parent_fingerprint}
    keep = buyers | parents
    return [c for c in comments if c.fingerprint in keep]
