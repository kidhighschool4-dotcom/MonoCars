"""TikTok public videos — the existing Playwright adapter (fbm_intel.tiktok) behind the common contract.

Visible persistent profile (manual login: python -m app.tiktok_login). Search → public video pages → comments +
replies → buyer-comment screenshots with names/avatars hidden. CAPTCHAs are shown to the human in the window and never
solved automatically; unsolved/too many → the platform stops (other platforms continue).
"""
from __future__ import annotations

import contextlib

from ...browser import BlockedError
from ...social.model import SocialPost
from ...tiktok import adapter as tt
from ...tiktok.collector import PROFILE_DIR
from ...tiktok.urls import canonical_video_url, is_video_url, video_id
from ..base import BrowserAdapterBase
from ..contract import AccessBlocked, Challenged, Checkpoint, CommentBatch, Health, LoginRequired, SearchItem, SearchPage
from ..registry import register


@register
class TikTokAdapter(BrowserAdapterBase):
    name = "tiktok"
    platform = "tiktok"
    display_name = "TikTok"
    tier = 1
    adapter_version = "tiktok-contract-v1+" + tt.load_config()["version"]
    content_type = "tiktok_video"
    allowed_hosts = frozenset(tt.TikTokPublicVideosAdapter.allowed_hosts)

    def __init__(self, ctx):
        super().__init__(ctx)
        cfg = tt.load_config()
        b = ctx.budget
        if b is not None:
            cfg["limits"]["max_results_per_query"] = b.max_posts_per_query
            cfg["limits"]["max_comments_per_post"] = b.max_comments_per_post
        cfg["limits"].update(self.cfg.get("limits_override", {}))
        self.inner = tt.TikTokPublicVideosAdapter(ctx.keyer, cfg, headed=ctx.headed,
                                                  screenshot_threshold=int(self.cfg.get("screenshot_min_score", 70)))
        self._found: dict[str, tt.Found] = {}

    @property
    def profile_dir(self):
        return PROFILE_DIR

    def health_check(self) -> Health:
        if callable(self.ctx.fixtures) or PROFILE_DIR.exists():
            return Health("ok")
        return Health("login_required", "no TikTok profile yet — run: python -m app.tiktok_login")

    @contextlib.contextmanager
    def _mapped(self):
        try:
            yield
        except tt.LoginRequired as e:
            raise LoginRequired(str(e), getattr(self.s.page, "url", None) if self.s else None) from e
        except tt.AccessBlocked as e:
            raise Challenged(str(e), e.url) from e
        except BlockedError as e:
            raise AccessBlocked(f"{e.status.value}", e.url) from e

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        s = self.session()
        with self._mapped():
            found = self.inner.search(s, query, is_seen=self.ctx.is_seen)
        items = []
        for f in found:
            self._found[f.canonical_url] = f
            items.append(SearchItem(url=f.url, canonical_url=f.canonical_url, query=query, search_url=f.search_url,
                                    source_id=video_id(f.canonical_url)))
        self._next_checkpoint = Checkpoint(query=query, cursor=None, page=checkpoint.page + 1, seen=list(checkpoint.seen))
        return SearchPage(items, self._next_checkpoint, exhausted=not items)

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url) or url
        f = self._found.get(canon) or tt.Found(url, canon, item.query if item else "", item.search_url if item else "")
        with self._mapped():
            post = self.inner.collect_video(self.session(), f)
        if post is None:
            self.last_skip_reason = "private_unavailable_or_not_verified_public"
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        # comments + replies were expanded on the video page in collect_post (same page visit)
        return CommentBatch(post.comments, post.completeness_status, post.comment_expansion_rounds)

    def capture_business_page(self, url, account_type):
        from ..base import capture_business_page_in
        return capture_business_page_in(self, url, account_type, max_height=700)   # header + bio, not the follower lists

    def capture_evidence(self, item):
        return getattr(item, "screenshot", None)  # captured on the page (names hidden) during collect_post

    def canonicalize_url(self, url: str) -> str | None:
        return canonical_video_url(url) if is_video_url(url) else None

    def normalize_result(self, result: dict) -> SocialPost:
        """Fields read from a rendered public video page → SocialPost (collect_post does this on the live page)."""
        from datetime import datetime, timezone

        from ...fb_public.model import parse_fb_time
        from ...normalize import normalize_text, sha256_hex
        canon = canonical_video_url(result["url"])
        desc = normalize_text(result.get("description") or "") or None
        published = result.get("published")
        return SocialPost(
            platform="tiktok", source_content_type="tiktok_video", source_post_id=video_id(canon), source_post_url=result["url"],
            canonical_post_url=canon, document_title=result.get("document_title"), post_title=None, post_text=desc,
            hashtags=sorted(set(tt.HASHTAG_RE.findall(desc or ""))), published_text_displayed=published,
            published_at_observed=parse_fb_time(published.split("·")[-1].strip()) if published else None,
            engagement={k: v for k, v in (result.get("engagement") or {}).items() if v},
            visibility_status="public_verified", visibility_evidence=result.get("visibility_evidence") or "public video page rendered",
            search_query=result.get("search_query", ""), search_url=result.get("search_url"),
            captured_at=datetime.now(timezone.utc), adapter_version=self.adapter_version,
            content_hash=sha256_hex((desc or "").casefold()))
