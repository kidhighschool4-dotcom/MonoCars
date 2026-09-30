"""FBM marketplace adapter — the first approved, automation-friendly source.

FBM is our own public site, so automated collection is authorized. Selectors are stable
data-testid attributes owned by the FBM codebase (components/cars/CarCard.tsx, app/cars/[id]/page.tsx).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin, urlsplit

from ..browser import BrowserSession
from ..normalize import canonicalize_url, normalize_text
from ..schemas import PageState, RawListingObservation
from .base import AccessStatus, PlatformAdapter, ResultRef, SearchPageState

LISTING_PATH = re.compile(r"^/cars/([0-9a-zA-Z-]{1,64})$")


class FbmAdapter(PlatformAdapter):
    platform = "fbm"
    version = "fbm-adapter-v1"
    min_interval_s = 1.0
    requires_login = False

    def __init__(self, base_url: str = "https://fbm-pied.vercel.app"):
        self.base_url = base_url.rstrip("/")
        self.allowed_hosts = {urlsplit(self.base_url).hostname or ""}

    def validate_access(self) -> AccessStatus:
        return AccessStatus(True, "first-party FBM public listings; automation authorized by owner")

    def build_search_url(self, query: str, filters: dict | None = None) -> str | None:
        q = normalize_text(query)
        if not q:
            return None
        url = f"{self.base_url}/cars?q={quote_plus(q)}"
        if filters and filters.get("carType"):
            url += f"&carType={quote_plus(filters['carType'])}"
        return url

    def collect_result_refs(self, s: BrowserSession, state: SearchPageState) -> list[ResultRef]:
        page = s.page
        page.locator("[data-testid='results-count'], [data-testid='results-empty']").first.wait_for(timeout=20000)
        refs: list[ResultRef] = []
        cards = page.locator("[data-testid='listing-card']")
        for i in range(cards.count()):
            card = cards.nth(i)
            href = card.get_attribute("href") or ""
            m = LISTING_PATH.match(urlsplit(href).path)
            if not m:
                continue
            refs.append(ResultRef(url=urljoin(self.base_url + "/", href), source_listing_id=m.group(1),
                                  hint_title=normalize_text(card.get_attribute("aria-label") or "") or None))
        return refs

    def _text(self, s: BrowserSession, testid: str) -> str | None:
        loc = s.page.locator(f"[data-testid='{testid}']")
        if loc.count() == 0:
            return None
        return normalize_text(loc.first.inner_text(timeout=5000)) or None

    def extract_observation(self, s: BrowserSession, ref: ResultRef) -> RawListingObservation:
        page = s.page
        state = PageState.OK
        if page.locator("[data-testid='listing-evidence']").count() == 0:
            state = PageState.NOT_FOUND
        status_text = (self._text(s, "listing-status") or "").lower()
        if "sold" in status_text or "unavailable" in status_text:
            state = PageState.SOLD_OR_REMOVED
        published = page.locator("[data-testid='listing-published']")
        published_at = None
        if published.count():
            dt = published.first.get_attribute("datetime")
            if dt:
                published_at = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        specs = {}
        for row in page.locator("[data-testid='listing-spec']").all():
            key = row.get_attribute("data-spec") or ""
            if key:
                specs[key] = normalize_text(row.inner_text())
        return RawListingObservation(
            source_platform=self.platform,
            source_listing_id=ref.source_listing_id,
            source_url=ref.url,
            canonical_url=canonicalize_url(ref.url),
            title_raw=self._text(s, "listing-title"),
            description_raw=(self._text(s, "listing-description") or "")[:5000] or None,
            price_text_raw=self._text(s, "listing-price"),
            location_text_raw=self._text(s, "listing-location"),
            seller_display_name=None,  # data minimization: seller identity is not needed (§6.4)
            published_at_observed=published_at,
            captured_at=datetime.now(timezone.utc),
            adapter_version=self.version,
            page_state=state,
            observation_payload={"specs": specs, "body_type": self._text(s, "listing-type")},
        )

    def evidence_locator(self, s: BrowserSession):
        return s.page.locator("[data-testid='listing-evidence']").first

    def image_locator(self, s: BrowserSession):
        return s.page.locator("[data-testid='listing-gallery'] img")

    def extract_comment_texts(self, s: BrowserSession) -> list[str]:
        # FBM listing pages currently have no public comment section; this reads it if one is added.
        texts = s.page.locator("[data-testid='listing-comment'] [data-testid='comment-text']")
        return [t.inner_text(timeout=3000) for t in texts.all()[:200]]

    def visibility(self, s: BrowserSession) -> dict:
        has = lambda t: s.page.locator(f"[data-testid='listing-evidence'] [data-testid='{t}']").count() > 0  # noqa: E731
        return {"title": has("listing-title"), "price": has("listing-price"), "location": has("listing-location"),
                "primary_image": has("listing-gallery"), "description": has("listing-description")}
