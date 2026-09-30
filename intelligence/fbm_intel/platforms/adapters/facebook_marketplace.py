"""Facebook Marketplace — the existing Marketplace adapter (fbm_intel.adapters.facebook) behind the common contract.

Saved owner session (python -m app.facebook_login), visible window by default. Marketplace search for the location →
listing pages → title / price / location / listed date / description. Marketplace listings have no public comments
(buyers message sellers privately — never touched), so these are seller-side sources: typed as seller_or_dealer unless
the listing itself is a "wanted" ad. The seller's name is never read; screenshots hide the seller block and avatars.
"""
from __future__ import annotations

import contextlib
import re
from datetime import datetime, timezone

from ...adapters import facebook as fbm
from ...adapters.base import ResultRef, SearchPageState
from ...browser import BlockedError, BlockStatus
from ...normalize import normalize_text, sha256_hex
from ...schemas import PageState
from ...social.model import SocialPost
from ..base import BrowserAdapterBase
from ..contract import AccessBlocked, Challenged, Checkpoint, CommentBatch, Health, LoginRequired, SearchItem, SearchPage
from ..registry import register

_ITEM = re.compile(r"facebook\.com/marketplace/item/(\d+)")
_BLOCK = {BlockStatus.LOGIN_WALL: LoginRequired, BlockStatus.CHECKPOINT: Challenged}
HIDE_CSS = ("a[href*='/marketplace/profile/'], a[href*='/marketplace/profile/'] *, a[href*='/profile.php'], "
            "svg image, img[alt*='profile' i], [aria-label*='seller' i] { visibility: hidden !important; }")


@register
class FacebookMarketplaceAdapter(BrowserAdapterBase):
    name = "facebook_marketplace"
    platform = "facebook_marketplace"
    display_name = "Facebook Marketplace"
    tier = 1
    adapter_version = "facebook-marketplace-contract-v1"
    content_type = "facebook_marketplace_listing"
    supports_comments = False
    allowed_hosts = frozenset(fbm.FB_HOSTS)
    hide_css = HIDE_CSS

    def __init__(self, ctx):
        super().__init__(ctx)
        self.inner = fbm.FacebookAdapter("marketplace", self.cfg.get("location_slug", "phnompenh"))
        self._refs: dict[str, tuple[ResultRef, str]] = {}
        self._logged_in = False
        self._current: str | None = None

    def health_check(self) -> Health:
        if callable(self.ctx.fixtures) or fbm.SESSION_PATH.exists():
            return Health("ok")
        return Health("login_required", "no Facebook session — run: python -m app.facebook_login")

    def session(self):
        if self.s is not None:
            return self.s
        from ...browser import open_session
        self._stack = contextlib.ExitStack()
        fixtures = callable(self.ctx.fixtures)
        self.s = self._stack.enter_context(open_session(set(self.allowed_hosts), 0 if fixtures else float(self.cfg.get("rate", {}).get("min_interval_s", 12)),
                                                        headless=fixtures or not self.ctx.headed,
                                                        storage_state=None if fixtures else str(fbm.SESSION_PATH)))
        if fixtures:
            self.ctx.fixtures(self.s)
            self._logged_in = True
        return self.s

    @contextlib.contextmanager
    def _mapped(self):
        try:
            yield
        except BlockedError as e:
            raise _BLOCK.get(e.status, AccessBlocked)(e.status.value, e.url) from e

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        s = self.session()
        with self._mapped():
            if not self._logged_in:
                self.inner.confirm_logged_in(s)
                self._logged_in = True
            st: SearchPageState | None = self.inner.open_search(s, query)
            refs = self.inner.collect_result_refs(s, st) if st else []
        items = []
        for r in refs[: (self.ctx.budget.max_posts_per_query if self.ctx.budget else 10)]:
            self._refs[r.url] = (r, st.url)
            items.append(SearchItem(url=r.url, canonical_url=r.url, query=query, search_url=st.url, source_id=r.source_listing_id,
                                    preview={"hint_title": r.hint_title}))
        self._next_checkpoint = Checkpoint(query=query, page=checkpoint.page + 1, seen=list(checkpoint.seen))
        return SearchPage(items, self._next_checkpoint, exhausted=not items)

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url)
        if not canon:
            self.last_skip_reason = "not_a_marketplace_item"
            return None
        ref = self._refs.get(canon, (ResultRef(url=canon, source_listing_id=_ITEM.search(canon).group(1)), None))[0]
        s = self.session()
        with self._mapped():
            self.inner.open_listing(s, ref)
            obs = self.inner.extract_observation(s, ref)
        if obs.page_state != PageState.OK:
            self.last_skip_reason = f"listing_{obs.page_state.value}"
            return None
        self._current = canon
        return self.normalize_result({**obs.model_dump(), "search_query": item.query if item else "",
                                      "search_url": item.search_url if item else None})

    def normalize_result(self, r: dict) -> SocialPost:
        title = normalize_text(r.get("title_raw") or "") or None
        desc = normalize_text(r.get("description_raw") or "") or None
        text = "\n".join(x for x in [title, r.get("price_text_raw"), r.get("location_text_raw"), desc] if x) or None
        canon = r.get("canonical_url") or r["source_url"]
        return SocialPost(
            platform=self.platform, source_content_type=self.content_type, source_post_id=r.get("source_listing_id"),
            source_post_url=r["source_url"], canonical_post_url=canon, document_title=None, post_title=title, post_text=text,
            hashtags=[], published_text_displayed=None, published_at_observed=r.get("published_at_observed"),
            engagement={k: v for k, v in {"price": r.get("price_text_raw"), "location": r.get("location_text_raw")}.items() if v},
            visibility_status="public_verified", visibility_evidence="Facebook Marketplace listing page (Marketplace is public to logged-in users)",
            search_query=r.get("search_query", ""), search_url=r.get("search_url"), captured_at=r.get("captured_at") or datetime.now(timezone.utc),
            adapter_version=self.adapter_version, content_hash=sha256_hex((text or "").casefold()),
            completeness_status="comments_unavailable", comments_supported=False)

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        return CommentBatch([], "comments_unavailable")

    def capture_evidence(self, item):
        if not isinstance(item, SocialPost) or self.s is None or item.canonical_post_url != self._current:
            return None
        return self.screenshot_locator(self.inner.evidence_locator(self.s), "post")

    def canonicalize_url(self, url: str) -> str | None:
        m = _ITEM.search(url or "")
        return f"https://www.facebook.com/marketplace/item/{m.group(1)}/" if m else None
