"""Where normalized results go.

PreviewSink  — no database writes: JSONL per platform + screenshots as local PNGs under artifacts/preview/<run>/ (git-ignored).
SupabaseSink — live: SocialRepo (public_social_posts/comments + evidence bucket) plus lead columns, organizations
               (kept apart from buyer leads) and per-platform worker status for the dashboard.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..social.model import Evidence, SocialComment, SocialPost

log = logging.getLogger("fbm_intel.platforms.sink")


def _plain(o):
    if isinstance(o, Evidence):
        return {"kind": o.kind, "width": o.width, "height": o.height, "sha256": o.checksum_sha256}
    if is_dataclass(o):
        return {k: _plain(v) for k, v in asdict(o).items()} if not isinstance(o, (SocialPost, SocialComment)) else None
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, dict):
        return {k: _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    return o


def comment_record(c: SocialComment) -> dict:
    i = c.intent
    return {
        "fingerprint": c.fingerprint, "parent_fingerprint": c.parent_fingerprint, "type": c.comment_type,
        "source_comment_id": c.source_comment_id, "comment_url": c.canonical_comment_url, "commenter_key": c.commenter_key,
        "commenter_key_scope": c.commenter_key_scope, "text": c.comment_text, "displayed_timestamp": c.displayed_timestamp,
        "commented_at": _plain(c.commented_at_observed), "is_post_author": c.is_post_author,
        "intent": {"score": i.buyer_intent_score, "label": i.buyer_intent_label, "type": i.intent_type,
                   "language": i.detected_language, "signals": i.matched_signals, "phrases": i.matched_phrases,
                   "negatives": i.negative_signals, "spam": i.spam_score, "review": i.needs_human_review},
        "lead": c.lead.as_dict() if c.lead is not None else None,
        "screenshot": _plain(c.screenshot),
    }


def post_record(p: SocialPost) -> dict:
    return {
        "platform": p.platform, "content_type": p.source_content_type, "source_post_id": p.source_post_id,
        "post_url": p.canonical_post_url, "source_post_url": p.source_post_url, "search_query": p.search_query,
        "search_url": p.search_url, "title": p.post_title or p.document_title, "text": p.post_text, "hashtags": p.hashtags,
        "published_displayed": p.published_text_displayed, "published_at": _plain(p.published_at_observed),
        "engagement": p.engagement, "visibility": p.visibility_status, "visibility_evidence": p.visibility_evidence,
        "captured_at": _plain(p.captured_at), "adapter_version": p.adapter_version, "completeness": p.completeness_status,
        "author_key": p.author_key, "organization": _plain(p.organization), "lead": p.lead.as_dict() if p.lead else None,
        "screenshot": _plain(p.screenshot), "rejected_comment_count": p.rejected_comment_count,
        "rejection_reasons": p.rejection_reasons, "comments": [comment_record(c) for c in p.comments],
    }


class PreviewSink:
    preview = True

    def __init__(self, root: str | Path, run_id: str | None = None):
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.dir = Path(root) / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "shots").mkdir(exist_ok=True)

    def _shot(self, ev: Evidence | None, name: str) -> str | None:
        if ev is None:
            return None
        path = self.dir / "shots" / f"{name}-{ev.checksum_sha256[:12]}.png"
        path.write_bytes(ev.png)
        return str(path.relative_to(self.dir))

    def save_post(self, name: str, p: SocialPost) -> dict:
        rec = post_record(p)
        if p.screenshot:
            rec["screenshot"]["file"] = self._shot(p.screenshot, f"{name}-post")
        for c, rc in zip(p.comments, rec["comments"]):
            if c.screenshot:
                rc["screenshot"]["file"] = self._shot(c.screenshot, f"{name}-comment")
        with open(self.dir / f"{name}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec

    def record_skip(self, name: str, platform: str, url: str | None, query: str, status: str, reason: str) -> None:
        with open(self.dir / f"{name}.skips.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"platform": platform, "url": url, "query": query, "status": status, "reason": reason},
                               ensure_ascii=False) + "\n")

    def save_status(self, name: str, status: dict) -> None:  # preview keeps status in the report only
        pass


class SupabaseSink:
    """Live writes. Requires migration 20261002_multi_platform_discovery.sql (lead columns, organizations, status)."""
    preview = False

    def __init__(self, settings, owner_id: str):
        from ..social.repo import SocialRepo
        self.repo = SocialRepo(settings, owner_id)
        self.owner_id = owner_id

    def save_post(self, name: str, p: SocialPost) -> dict:
        org_id = self._org(p) if p.organization else None
        post_id, _, _ = self.repo.save_post(p)
        lead = p.lead.as_dict() if p.lead else None
        self.repo._req("PATCH", "/rest/v1/public_social_posts", params={"id": f"eq.{post_id}"}, body={
            "author_key": p.author_key, "author_key_version": p.author_key_version, "organization_id": org_id,
            "lead_type": lead["lead_type"] if lead else None, "lead": lead, "source_adapter": name})
        ids = self.repo._fp_ids(post_id)
        for c in p.comments:
            if c.lead is None or c.fingerprint not in ids:
                continue
            L = c.lead
            self.repo._req("PATCH", "/rest/v1/public_social_comments", params={"id": f"eq.{ids[c.fingerprint]}"}, body={
                "lead_type": L.lead_type, "lead_use_case": L.use_case, "lead_confidence": L.confidence,
                "lead_reasons": L.reasons, "lead_needs_review": L.needs_review, "lead_version": L.version,
                "rx300_mentioned": L.rx300_mentioned, "rx300_context": L.rx300_context, "is_post_author": c.is_post_author})
        return {"post_id": post_id}

    def _org(self, p: SocialPost) -> str | None:
        o = p.organization
        rows = self.repo._req("POST", "/rest/v1/public_social_organizations", params={"on_conflict": "owner_id,platform,name"},
                              prefer="return=representation,resolution=merge-duplicates", body={
            "owner_id": self.owner_id, "platform": o.platform, "name": o.name[:300], "url": o.url, "kind": o.kind,
            "evidence": o.evidence[:500], "last_seen_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()})
        return rows[0]["id"] if rows else None

    def record_skip(self, name: str, platform: str, url: str | None, query: str, status: str, reason: str) -> None:
        self.repo.record_skip(platform, url, query, status if status in ("unverified", "private", "restricted") else "unverified",
                              reason)

    def save_status(self, name: str, status: dict) -> None:
        try:
            self.repo._req("POST", "/rest/v1/social_platform_status", params={"on_conflict": "owner_id,platform"},
                           prefer="resolution=merge-duplicates", body={"owner_id": self.owner_id, "platform": name, **status})
        except Exception as e:  # noqa: BLE001 - status mirroring must never stop collection
            log.warning("Could not mirror %s status: %s", name, e)
