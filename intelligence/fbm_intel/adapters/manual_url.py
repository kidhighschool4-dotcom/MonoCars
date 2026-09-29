"""Manual URL submission (§13 fallback): a person supplies a permitted listing URL; we capture that page only.

No search, no crawling, no pagination. Only hosts on the explicit allowlist can be captured, and any
block/CAPTCHA/login wall stops immediately.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from ..browser import BrowserSession
from ..normalize import canonicalize_url, normalize_text
from ..schemas import RawListingObservation
from .base import AccessStatus, PlatformAdapter, ResultRef, SearchPageState


class ManualUrlAdapter(PlatformAdapter):
    platform = "manual_url"
    version = "manual-url-adapter-v1"
    min_interval_s = 3.0

    def __init__(self, allowed_hosts: set[str]):
        self.allowed_hosts = {h.lower().removeprefix("www.") for h in allowed_hosts}

    def validate_access(self) -> AccessStatus:
        return AccessStatus(bool(self.allowed_hosts), "owner-approved hosts only")

    def check_url(self, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise ValueError("only https URLs can be submitted")
        host = (parts.hostname or "").lower().removeprefix("www.")
        if not any(host == h or host.endswith("." + h) for h in self.allowed_hosts):
            raise PermissionError(f"host not on the approved list: {host}")
        if parts.username or parts.password:
            raise ValueError("URLs with credentials are not allowed")
        return url

    def build_search_url(self, query: str, filters: dict | None = None) -> str | None:
        return None  # manual submission never searches

    def collect_result_refs(self, s: BrowserSession, state: SearchPageState) -> list[ResultRef]:
        return []

    def _meta(self, s: BrowserSession, *names: str) -> str | None:
        for n in names:
            loc = s.page.locator(f"meta[property='{n}'], meta[name='{n}']")
            if loc.count():
                v = normalize_text(loc.first.get_attribute("content"))
                if v:
                    return v
        return None

    def extract_observation(self, s: BrowserSession, ref: ResultRef) -> RawListingObservation:
        title = self._meta(s, "og:title", "twitter:title") or normalize_text(s.page.title()) or None
        amount = self._meta(s, "product:price:amount", "og:price:amount")
        currency = self._meta(s, "product:price:currency", "og:price:currency") or ""
        return RawListingObservation(
            source_platform=self.platform,
            source_listing_id=None,
            source_url=ref.url,
            canonical_url=canonicalize_url(s.page.url or ref.url),
            title_raw=title,
            description_raw=(self._meta(s, "og:description", "description") or "")[:5000] or None,
            price_text_raw=f"{amount} {currency}".strip() if amount else None,
            location_text_raw=self._meta(s, "og:locality", "place:location"),
            seller_display_name=None,
            captured_at=datetime.now(timezone.utc),
            adapter_version=self.version,
            observation_payload={"final_url_host": urlsplit(s.page.url).hostname},
        )

    def evidence_locator(self, s: BrowserSession):
        for sel in ("[data-testid='listing-evidence']", "main article", "article", "main"):
            loc = s.page.locator(sel)
            if loc.count():
                return loc.first
        return s.page.locator("body")
