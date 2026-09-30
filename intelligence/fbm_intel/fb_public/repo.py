"""Supabase repository for Facebook public posts/comments (service role, server-side only).

All filters go through PostgREST query parameters (never string-built SQL). Text search escapes the wildcard
characters so user text can't change the pattern. Profile-URL lookups hash the URL with the same HMAC key
first — profile URLs are never stored or sent to the database.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from ..settings import Settings
from .identity import PersonKeyer
from .model import ADAPTER_VERSION, PublicPost
from .urls import canonical_post_url

POST_COLS = ("id,source_post_id,source_post_url,canonical_post_url,post_text,published_at_observed,visibility_status,"
             "visibility_evidence,search_query,captured_at,comments_complete,comments_collected_count,"
             "replies_collected_count,comment_expansion_rounds,comments_incomplete_reason")
COMMENT_COLS = ("id,source_comment_id,source_comment_url,canonical_comment_url,parent_comment_id,comment_type,"
                "comment_text,commented_at_observed,captured_at,commenter_key_version,"
                "post:facebook_public_posts(canonical_post_url,source_post_url)")


def _like(text: str) -> str:
    """PostgREST ilike pattern with the user's text treated literally."""
    esc = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("*", "\\*")
    return f"*{esc}*"


class FacebookPublicRepo:
    def __init__(self, settings: Settings, owner_id: str, keyer: PersonKeyer, client: httpx.Client | None = None):
        settings.require_supabase()
        self.s, self.owner_id, self.keyer = settings, owner_id, keyer
        self.http = client or httpx.Client(timeout=60)
        self._h = {"apikey": settings.service_role_key, "Authorization": f"Bearer {settings.service_role_key}"}

    def _req(self, method: str, table: str, *, params: dict | None = None, body=None, prefer: str | None = None):
        h = dict(self._h)
        if prefer:
            h["Prefer"] = prefer
        r = self.http.request(method, f"{self.s.supabase_url}/rest/v1/{table}", params=params, headers=h,
                              content=json.dumps(body, default=str) if body is not None else None)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {table} → {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    def _get(self, table: str, **params) -> list[dict]:
        return self._req("GET", table, params={"owner_id": f"eq.{self.owner_id}", **params})

    # ── writes ──
    def record_skip(self, canonical_url: str | None, query: str, visibility_status: str, reason: str) -> None:
        self._req("POST", "facebook_public_post_skips", body={
            "owner_id": self.owner_id, "canonical_post_url": canonical_url, "search_query": query,
            "visibility_status": visibility_status if visibility_status in ("unverified", "private", "restricted") else "unverified",
            "skip_reason": reason, "adapter_version": ADAPTER_VERSION})

    def save_post(self, p: PublicPost) -> tuple[str, int, int]:
        """Upsert the post (by owner + canonical URL), then insert only new comments/replies.
        Returns (post_id, new_comments, new_replies)."""
        row = self._req("POST", "facebook_public_posts", params={"on_conflict": "owner_id,canonical_post_url"},
                        prefer="return=representation,resolution=merge-duplicates", body={
            "owner_id": self.owner_id, "source_post_id": p.source_post_id, "source_post_url": p.source_post_url,
            "canonical_post_url": p.canonical_post_url, "author_key": p.author_key, "author_key_version": p.author_key_version,
            "post_text": p.post_text, "published_at_observed": p.published_at_observed,
            "visibility_status": p.visibility_status, "visibility_evidence": p.visibility_evidence,
            "search_query": p.search_query, "captured_at": p.captured_at, "adapter_version": ADAPTER_VERSION,
            "content_hash": p.content_hash, "comments_complete": p.comments_complete,
            "comments_incomplete_reason": p.comments_incomplete_reason,
            "comment_expansion_rounds": p.comment_expansion_rounds, "updated_at": datetime.now(timezone.utc)})[0]
        post_id = row["id"]
        new = {"comment": 0, "reply": 0}
        ids = self._fingerprint_ids(post_id)
        for level in ("comment", "reply"):  # parents first so replies can reference them
            batch = []
            for c in p.comments:
                if c.comment_type != level or c.fingerprint in ids:
                    continue
                parent = ids.get(c.parent_fingerprint) if c.parent_fingerprint else None
                if level == "reply" and not parent:
                    continue
                batch.append({
                    "owner_id": self.owner_id, "post_id": post_id, "source_comment_id": c.source_comment_id,
                    "source_comment_url": c.source_comment_url, "canonical_comment_url": c.canonical_comment_url,
                    "comment_fingerprint": c.fingerprint, "parent_comment_id": parent, "commenter_key": c.commenter_key,
                    "commenter_key_version": c.commenter_key_version, "comment_text": c.comment_text,
                    "commented_at_observed": c.commented_at_observed, "comment_type": c.comment_type,
                    "visibility_status": "public_verified", "captured_at": p.captured_at,
                    "adapter_version": ADAPTER_VERSION, "content_hash": c.content_hash})
            if batch:
                created = self._req("POST", "facebook_public_comments", params={"on_conflict": "post_id,comment_fingerprint"},
                                    prefer="return=representation,resolution=ignore-duplicates", body=batch)
                new[level] += len(created or [])
                ids = self._fingerprint_ids(post_id)
        # counts reflect what is stored for this post
        stored = self._req("GET", "facebook_public_comments", params={"post_id": f"eq.{post_id}", "select": "comment_type"})
        self._req("PATCH", "facebook_public_posts", params={"id": f"eq.{post_id}"}, body={
            "comments_collected_count": sum(r["comment_type"] == "comment" for r in stored),
            "replies_collected_count": sum(r["comment_type"] == "reply" for r in stored)})
        return post_id, new["comment"], new["reply"]

    def _fingerprint_ids(self, post_id: str) -> dict[str, str]:
        rows = self._req("GET", "facebook_public_comments", params={"post_id": f"eq.{post_id}", "select": "id,comment_fingerprint"})
        return {r["comment_fingerprint"]: r["id"] for r in rows}

    # ── query API (canonical URLs in every result) ──
    def find_post_by_url(self, url: str) -> dict | None:
        rows = self._get("facebook_public_posts", canonical_post_url=f"eq.{canonical_post_url(url)}", select=POST_COLS)
        return rows[0] if rows else None

    def find_comments_by_post_url(self, url: str) -> list[dict]:
        post = self.find_post_by_url(url)
        if not post:
            return []
        return self._get("facebook_public_comments", post_id=f"eq.{post['id']}", select=COMMENT_COLS, order="captured_at.asc")

    def find_comment_by_url(self, canonical_comment_url: str) -> dict | None:
        rows = self._get("facebook_public_comments", canonical_comment_url=f"eq.{canonical_comment_url}", select=COMMENT_COLS)
        return rows[0] if rows else None

    def find_comments_by_profile_url(self, profile_url: str) -> list[dict]:
        key = self.keyer.key(profile_url)
        if key is None:
            return []
        return self._get("facebook_public_comments", commenter_key=f"eq.{key}",
                         commenter_key_version=f"eq.{self.keyer.version}", select=COMMENT_COLS, order="captured_at.desc")

    def find_posts_by_author_url(self, profile_url: str) -> list[dict]:
        key = self.keyer.key(profile_url)
        if key is None:
            return []
        return self._get("facebook_public_posts", author_key=f"eq.{key}", author_key_version=f"eq.{self.keyer.version}",
                         select=POST_COLS, order="captured_at.desc")

    def search_post_text(self, query: str, limit: int = 100) -> list[dict]:
        return self._get("facebook_public_posts", post_text=f"ilike.{_like(query)}", select=POST_COLS, limit=str(limit))

    def search_comment_text(self, query: str, limit: int = 200) -> list[dict]:
        return self._get("facebook_public_comments", comment_text=f"ilike.{_like(query)}", select=COMMENT_COLS, limit=str(limit))

    def find_posts_by_original_search_query(self, search_query: str) -> list[dict]:
        return self._get("facebook_public_posts", search_query=f"eq.{search_query}", select=POST_COLS, order="captured_at.desc")

    def find_comments_by_date_range(self, start: datetime, end: datetime) -> list[dict]:
        return self._req("GET", "facebook_public_comments", params=[
            ("owner_id", f"eq.{self.owner_id}"), ("commented_at_observed", f"gte.{start.isoformat()}"),
            ("commented_at_observed", f"lt.{end.isoformat()}"), ("select", COMMENT_COLS), ("order", "commented_at_observed.asc")])

    def purge_expired(self) -> dict:
        r = self.http.post(f"{self.s.supabase_url}/rest/v1/rpc/purge_expired_facebook_public_data", headers=self._h, json={})
        r.raise_for_status()
        return r.json()
