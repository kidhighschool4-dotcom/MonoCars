"""Supabase repository for public_social_posts / public_social_comments (all platforms). Service role, server only.
Idempotent: posts upsert on (owner, platform, canonical URL); comments insert-ignore on (post, fingerprint)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import httpx

from ..settings import Settings
from .model import Evidence, SocialPost

EVIDENCE_BUCKET = "listing-evidence"   # private bucket; the dashboard serves short-lived signed URLs


def evidence_path(platform: str, ev: Evidence) -> str:
    return f"social/{platform}/{datetime.now(timezone.utc):%Y/%m}/{ev.kind}-{ev.checksum_sha256[:16]}-{uuid.uuid4().hex[:8]}.png"


def upload_evidence(http: httpx.Client, supabase_url: str, auth_headers: dict, platform: str, ev: Evidence | None) -> str | None:
    """Upload a screenshot to the private evidence bucket (service role). Returns the object path, or None."""
    if ev is None:
        return None
    path = evidence_path(platform, ev)
    r = http.request("POST", f"{supabase_url}/storage/v1/object/{EVIDENCE_BUCKET}/{path}", content=ev.png,
                     headers={**auth_headers, "Content-Type": "image/png", "x-upsert": "false"})
    if r.status_code >= 400:
        raise RuntimeError(f"POST /storage/v1/object/{EVIDENCE_BUCKET}/{path} → {r.status_code}: {r.text[:300]}")
    return path


class SocialRepo:
    def __init__(self, settings: Settings, owner_id: str, client: httpx.Client | None = None):
        settings.require_supabase()
        self.s, self.owner_id = settings, owner_id
        self.http = client or httpx.Client(timeout=60)
        self._h = {"apikey": settings.service_role_key, "Authorization": f"Bearer {settings.service_role_key}"}

    def _req(self, method, path, *, params=None, body=None, prefer=None, content=None, headers=None):
        h = {**self._h, **(headers or {})}
        if prefer:
            h["Prefer"] = prefer
        r = self.http.request(method, f"{self.s.supabase_url}{path}", params=params, headers=h,
                              content=content if content is not None else (json.dumps(body, default=str) if body is not None else None))
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} → {r.status_code}: {r.text[:300]}")
        return r.json() if r.content and "json" in r.headers.get("content-type", "") else None

    def _upload(self, platform: str, ev: Evidence | None) -> str | None:
        return upload_evidence(self.http, self.s.supabase_url, self._h, platform, ev)

    def record_skip(self, platform, url, query, status, reason):
        self._req("POST", "/rest/v1/public_social_post_skips", body={
            "owner_id": self.owner_id, "platform": platform, "canonical_post_url": url, "search_query": query,
            "visibility_status": status, "skip_reason": reason})

    def save_post(self, p: SocialPost) -> tuple[str, int, int]:
        existing = self._req("GET", "/rest/v1/public_social_posts", params={
            "owner_id": f"eq.{self.owner_id}", "platform": f"eq.{p.platform}", "canonical_post_url": f"eq.{p.canonical_post_url}",
            "select": "id,screenshot_path"})
        shot = existing[0]["screenshot_path"] if existing and existing[0]["screenshot_path"] else self._upload(p.platform, p.screenshot)
        row = self._req("POST", "/rest/v1/public_social_posts", params={"on_conflict": "owner_id,platform,canonical_post_url"},
                        prefer="return=representation,resolution=merge-duplicates", body={
            "owner_id": self.owner_id, "platform": p.platform, "source_content_type": p.source_content_type,
            "source_post_id": p.source_post_id, "source_post_url": p.source_post_url, "canonical_post_url": p.canonical_post_url,
            "document_title": p.document_title, "post_title": p.post_title, "post_text": p.post_text, "hashtags": p.hashtags,
            "published_text_displayed": p.published_text_displayed, "published_at_observed": p.published_at_observed,
            "engagement": p.engagement, "visibility_status": p.visibility_status, "visibility_evidence": p.visibility_evidence,
            "search_query": p.search_query, "search_url": p.search_url, "captured_at": p.captured_at,
            "adapter_version": p.adapter_version, "content_hash": p.content_hash, "completeness_status": p.completeness_status,
            "comment_expansion_rounds": p.comment_expansion_rounds, "screenshot_path": shot,
            "rejected_comment_count": p.rejected_comment_count, "rejection_reasons": p.rejection_reasons,
            "updated_at": datetime.now(timezone.utc)})[0]
        post_id = row["id"]
        ids = self._fp_ids(post_id)
        new = {"comment": 0, "reply": 0}
        for level in ("comment", "reply"):
            batch = []
            for c in p.comments:
                if c.comment_type != level or c.fingerprint in ids:
                    continue
                parent = ids.get(c.parent_fingerprint) if c.parent_fingerprint else None
                if level == "reply" and not parent:
                    continue
                i = c.intent
                batch.append({
                    "owner_id": self.owner_id, "platform": p.platform, "post_id": post_id,
                    "source_comment_id": c.source_comment_id, "source_comment_url": c.source_comment_url,
                    "canonical_comment_url": c.canonical_comment_url, "comment_url_available": c.comment_url_available,
                    "comment_fingerprint": c.fingerprint, "parent_comment_id": parent, "comment_type": c.comment_type,
                    "commenter_key": c.commenter_key, "commenter_key_version": c.commenter_key_version,
                    "commenter_key_scope": c.commenter_key_scope, "comment_text": c.comment_text,
                    "comment_text_normalized": i.normalized_text, "displayed_timestamp": c.displayed_timestamp,
                    "commented_at_observed": c.commented_at_observed, "visibility_status": "public_verified",
                    "captured_at": p.captured_at, "adapter_version": p.adapter_version, "content_hash": c.content_hash,
                    "buyer_intent_score": i.buyer_intent_score, "buyer_intent_label": i.buyer_intent_label,
                    "intent_type": i.intent_type, "detected_language": i.detected_language,
                    "matched_signals": i.matched_signals, "matched_phrases": i.matched_phrases,
                    "negative_signals": i.negative_signals, "spam_score": i.spam_score, "intent_reason": i.reason,
                    "needs_human_review": i.needs_human_review, "scorer_version": i.scorer_version,
                    **(lambda path: {"screenshot_path": path, "comment_context_screenshot": path})(self._upload(p.platform, c.screenshot)),
                    "source_post_url": p.canonical_post_url, "identity_redacted": True if c.account_type != "business" else c.identity_redacted,
                    "account_type": c.account_type})
            if batch:
                created = self._req("POST", "/rest/v1/public_social_comments", params={"on_conflict": "post_id,comment_fingerprint"},
                                    prefer="return=representation,resolution=ignore-duplicates", body=batch)
                new[level] += len(created or [])
                ids = self._fp_ids(post_id)
        stored = self._req("GET", "/rest/v1/public_social_comments", params={"post_id": f"eq.{post_id}", "select": "comment_type"}) or []
        self._req("PATCH", "/rest/v1/public_social_posts", params={"id": f"eq.{post_id}"}, body={
            "comments_collected_count": sum(r["comment_type"] == "comment" for r in stored),
            "replies_collected_count": sum(r["comment_type"] == "reply" for r in stored)})
        return post_id, new["comment"], new["reply"]

    def _fp_ids(self, post_id: str) -> dict[str, str]:
        rows = self._req("GET", "/rest/v1/public_social_comments", params={"post_id": f"eq.{post_id}", "select": "id,comment_fingerprint"}) or []
        return {r["comment_fingerprint"]: r["id"] for r in rows}
