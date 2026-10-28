"""Facebook public posts — the existing Playwright adapter (fbm_intel.fb_public) behind the common contract.

Saved owner session (manual login: python -m app.facebook_login), visible window by default. Only posts whose audience
is verified "Public" / public group are opened; comments + replies are expanded within limits; post + buyer-comment
screenshots are taken with names/avatars hidden. Checkpoint / login wall / restriction → the platform stops.
"""
from __future__ import annotations

import contextlib

from ...adapters.facebook import SESSION_PATH, is_logged_in
from ...browser import BlockedError, BlockStatus
from ...fb_public import adapter as fbp
from ...fb_public.model import Limits, PublicPost
from ...fb_public.urls import canonical_post_url, is_post_url
from ...social.intent_score import score_comment
from ...social.model import SocialComment, SocialPost
from ..base import BrowserAdapterBase
from ..contract import AccessBlocked, Challenged, Checkpoint, CommentBatch, Health, LoginRequired, SearchItem, SearchPage
from ..registry import register

_BLOCK = {BlockStatus.LOGIN_WALL: LoginRequired, BlockStatus.CHECKPOINT: Challenged}


def to_social(p: PublicPost, adapter_version: str) -> SocialPost:
    comments = []
    for c in p.comments:
        comments.append(SocialComment(
            fingerprint=c.fingerprint, parent_fingerprint=c.parent_fingerprint, comment_type=c.comment_type,
            source_comment_id=c.source_comment_id, source_comment_url=c.source_comment_url,
            canonical_comment_url=c.canonical_comment_url, comment_url_available=bool(c.source_comment_url),
            commenter_key=c.commenter_key, commenter_key_version=c.commenter_key_version,
            commenter_key_scope="profile" if c.commenter_key else "comment_only", comment_text=c.comment_text,
            displayed_timestamp=None, commented_at_observed=c.commented_at_observed, content_hash=c.content_hash,
            intent=score_comment(c.comment_text), screenshot=getattr(c, "screenshot", None),
            is_post_author=bool(p.author_key and c.commenter_key == p.author_key), source_post_url=p.canonical_post_url,
            account_type=c.account_type, business_page_name=c.business_page_name if c.account_type == "business" else None,
            business_page_url=c.business_page_url if c.account_type == "business" else None))
    return SocialPost(
        platform="facebook", source_content_type="facebook_post", source_post_id=p.source_post_id,
        source_post_url=p.source_post_url, canonical_post_url=p.canonical_post_url, document_title=None, post_title=None,
        post_text=p.post_text, hashtags=[], published_text_displayed=None, published_at_observed=p.published_at_observed,
        engagement={}, visibility_status=p.visibility_status, visibility_evidence=p.visibility_evidence,
        search_query=p.search_query, search_url=None, captured_at=p.captured_at, adapter_version=adapter_version,
        content_hash=p.content_hash, completeness_status="complete" if p.comments_complete else
        ("partial_limit" if p.comments_incomplete_reason == "configured_limit_reached" else "partial_timeout"),
        comment_expansion_rounds=p.comment_expansion_rounds, comments=comments, screenshot=getattr(p, "screenshot", None),
        author_key=p.author_key, author_key_version=p.author_key_version)


@register
class FacebookPublicPostsAdapter(BrowserAdapterBase):
    name = "facebook_public_posts"
    platform = "facebook"
    display_name = "Facebook public posts"
    tier = 1
    adapter_version = "facebook-public-contract-v1"
    content_type = "facebook_post"
    allowed_hosts = frozenset(fbp.FacebookPublicPostsAdapter.allowed_hosts)

    def __init__(self, ctx):
        super().__init__(ctx)
        b = ctx.budget
        limits = Limits(**{"max_posts_per_query": b.max_posts_per_query if b else 10,
                           "max_comments_per_post": b.max_comments_per_post if b else 200,
                           "page_load_interval_s": float(self.cfg.get("rate", {}).get("min_interval_s", 12)),
                           **self.cfg.get("limits_override", {})})
        self.inner = fbp.FacebookPublicPostsAdapter(ctx.keyer, limits)
        self._results: dict[str, fbp.SearchResult] = {}
        self._logged_in = False
        self._query = ""

    def health_check(self) -> Health:
        if callable(self.ctx.fixtures) or SESSION_PATH.exists():
            return Health("ok")
        return Health("login_required", "no Facebook session — run: python -m app.facebook_login")

    def session(self):
        if self.s is not None:
            return self.s
        from ...browser import open_session
        self._stack = contextlib.ExitStack()
        fixtures = callable(self.ctx.fixtures)
        self.s = self._stack.enter_context(open_session(set(self.allowed_hosts), 0 if fixtures else self.inner.limits.page_load_interval_s,
                                                        headless=fixtures or not self.ctx.headed,
                                                        storage_state=None if fixtures else str(SESSION_PATH)))
        if fixtures:
            self.ctx.fixtures(self.s)
            self._logged_in = True
        return self.s

    @contextlib.contextmanager
    def _mapped(self):
        try:
            yield
        except fbp.PartialPost as e:
            raise _BLOCK.get(e.cause.status, AccessBlocked)(e.cause.status.value, e.cause.url) from e
        except BlockedError as e:
            raise _BLOCK.get(e.status, AccessBlocked)(e.status.value, e.url) from e

    def _ensure_login(self, s) -> None:
        if self._logged_in:
            return
        s.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        s.page.wait_for_timeout(2500)
        if not is_logged_in(s.context, s.page):
            raise LoginRequired("Facebook session expired — run: python -m app.facebook_login", s.page.url)
        self._logged_in = True

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        s = self.session()
        with self._mapped():
            self._ensure_login(s)
            url = self.inner.open_search(s, query)
            results = self.inner.collect_results(s)
        self._query = query
        items = []
        for r in results:
            self._results[r.canonical_url] = r
            items.append(SearchItem(url=r.url, canonical_url=r.canonical_url, query=query, search_url=url,
                                    preview={"visibility": r.visibility.status, "skip_reason": r.visibility.skip_reason}))
        self._next_checkpoint = Checkpoint(query=query, page=checkpoint.page + 1, seen=list(checkpoint.seen))
        return SearchPage(items, self._next_checkpoint, exhausted=not items)

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url) or url
        r = self._results.get(canon)
        if r is None:
            self.last_skip_reason = "not_from_search"
            return None
        if not r.visibility.verified and not r.check_on_post_page:
            self.last_skip_reason = r.visibility.skip_reason or "public_visibility_not_confirmed"
            return None
        with self._mapped():
            p = self.inner.collect_post(self.session(), r, item.query if item else self._query)
        if p is None:
            self.last_skip_reason = r.visibility.skip_reason or "visibility_changed"
            return None
        post = to_social(p, self.adapter_version)
        post.search_url = item.search_url if item else None
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        return CommentBatch(post.comments, post.completeness_status, post.comment_expansion_rounds)

    def capture_business_page(self, url, account_type):
        from ...fb_public.adapter import _HIDE_CHROME_JS
        from ..base import capture_business_page_in
        return capture_business_page_in(self, url, account_type, extra_hide_js=_HIDE_CHROME_JS)

    def capture_evidence(self, item):
        return getattr(item, "screenshot", None)  # taken on the post page (names hidden) during collect_post

    def canonicalize_url(self, url: str) -> str | None:
        return canonical_post_url(url) if is_post_url(url) else None

    def normalize_result(self, result: dict) -> SocialPost:
        """A PublicPost (as dict or object) from fbm_intel.fb_public → SocialPost."""
        p = result["post"] if isinstance(result, dict) else result
        return to_social(p, self.adapter_version)
