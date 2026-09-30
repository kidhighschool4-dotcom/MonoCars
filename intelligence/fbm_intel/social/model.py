"""Platform-neutral public post / comment records (Facebook, TikTok, Instagram, Reddit all map into these)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..comments import redact
from ..normalize import normalize_text, sha256_hex, stable_hash
from .intent_score import IntentScore, score_comment

PLATFORMS = {"facebook", "instagram", "tiktok", "reddit"}
CONTENT_TYPES = {"facebook_post", "instagram_post", "instagram_reel", "tiktok_video", "reddit_post"}
COMPLETENESS = {"complete", "partial_limit", "partial_timeout", "login_required", "access_blocked", "comments_unavailable"}


@dataclass
class Evidence:
    png: bytes
    checksum_sha256: str
    width: int
    height: int
    kind: str  # post | comment


@dataclass
class SocialComment:
    fingerprint: str
    parent_fingerprint: str | None
    comment_type: str                      # comment | reply
    source_comment_id: str | None
    source_comment_url: str | None
    canonical_comment_url: str | None
    comment_url_available: bool
    commenter_key: str | None
    commenter_key_version: str | None
    commenter_key_scope: str               # profile | comment_only
    comment_text: str                      # original (phones/emails/links redacted)
    displayed_timestamp: str | None
    commented_at_observed: datetime | None
    content_hash: str
    intent: IntentScore
    screenshot: Evidence | None = None


@dataclass
class SocialPost:
    platform: str
    source_content_type: str
    source_post_id: str | None
    source_post_url: str
    canonical_post_url: str
    document_title: str | None
    post_title: str | None
    post_text: str | None
    hashtags: list[str]
    published_text_displayed: str | None
    published_at_observed: datetime | None
    engagement: dict
    visibility_status: str
    visibility_evidence: str
    search_query: str
    search_url: str | None
    captured_at: datetime
    adapter_version: str
    content_hash: str
    completeness_status: str = "comments_unavailable"
    comment_expansion_rounds: int = 0
    comments: list[SocialComment] = field(default_factory=list)
    screenshot: Evidence | None = None
    rejected_comment_count: int = 0        # non-buyer comments not persisted (buyers_only policy)
    rejection_reasons: dict = field(default_factory=dict)

    @property
    def comments_complete(self) -> bool:
        return self.completeness_status == "complete"

    @property
    def comments_collected_count(self) -> int:
        return sum(c.comment_type == "comment" for c in self.comments)

    @property
    def replies_collected_count(self) -> int:
        return sum(c.comment_type == "reply" for c in self.comments)


def comment_fingerprint(platform: str, post_url: str, text_normalized: str, displayed_timestamp: str | None,
                        parent_ref: str | None, commenter_key: str | None, occurrence: int) -> str:
    """Deterministic fallback identity when the platform shows no comment id/permalink (spec §4)."""
    base = stable_hash(platform, post_url, text_normalized, displayed_timestamp or "", parent_ref or "", commenter_key or "")
    return "fb:" + sha256_hex(f"{base}:{occurrence}")


def make_comment(*, platform: str, post_url: str, raw_text: str, is_reply: bool, parent: SocialComment | None,
                 commenter_key: str | None, key_version: str | None, displayed_timestamp: str | None,
                 commented_at: datetime | None, source_comment_id: str | None, source_comment_url: str | None,
                 occurrence_counter: dict) -> SocialComment | None:
    text = redact(normalize_text(raw_text))[:10000]
    if not text or text == "[mention]":
        return None
    intent = score_comment(text)
    if source_comment_id:
        fp = f"id:{source_comment_id}"
    else:
        key = (intent.normalized_text, displayed_timestamp, parent.fingerprint if parent else None, commenter_key)
        n = occurrence_counter.get(key, 0)
        occurrence_counter[key] = n + 1
        fp = comment_fingerprint(platform, post_url, intent.normalized_text, displayed_timestamp,
                                 parent.fingerprint if parent else None, commenter_key, n)
    return SocialComment(
        fingerprint=fp, parent_fingerprint=parent.fingerprint if parent else None,
        comment_type="reply" if is_reply else "comment", source_comment_id=source_comment_id,
        source_comment_url=source_comment_url, canonical_comment_url=source_comment_url,
        comment_url_available=bool(source_comment_url), commenter_key=commenter_key,
        commenter_key_version=key_version if commenter_key else None,
        commenter_key_scope="profile" if commenter_key else "comment_only",
        comment_text=text, displayed_timestamp=displayed_timestamp, commented_at_observed=commented_at,
        content_hash=sha256_hex(text.casefold()), intent=intent,
    )


def apply_persist_policy(post: SocialPost, policy: str, threshold: int) -> None:
    """policy 'all' keeps every public comment (scored). 'buyers' keeps comments at/above the threshold plus the
    parents of kept replies; rejected comment TEXT is dropped and only counted with reasons."""
    if policy == "all":
        return
    keep = {c.fingerprint for c in post.comments if c.intent.buyer_intent_score >= threshold}
    keep |= {c.parent_fingerprint for c in post.comments if c.fingerprint in keep and c.parent_fingerprint}
    rejected = [c for c in post.comments if c.fingerprint not in keep]
    post.rejected_comment_count = len(rejected)
    reasons: dict[str, int] = {}
    for c in rejected:
        k = "spam" if c.intent.spam_score >= 60 else "negated" if c.intent.negative_signals else "no_buyer_phrase"
        reasons[k] = reasons.get(k, 0) + 1
    post.rejection_reasons = reasons
    post.comments = [c for c in post.comments if c.fingerprint in keep]
