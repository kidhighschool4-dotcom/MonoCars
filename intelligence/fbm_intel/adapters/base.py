"""Platform adapter contract (§8.3). Selectors live ONLY inside adapters, never in the orchestrator."""
from __future__ import annotations

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from PIL import Image

from ..browser import BrowserSession
from ..normalize import dhash_hex, sha256_hex
from ..schemas import RawListingObservation, ScreenshotEvidence


@dataclass
class ResultRef:
    url: str
    source_listing_id: str | None = None
    hint_title: str | None = None


@dataclass
class SearchPageState:
    url: str
    page_number: int = 1
    done: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class AccessStatus:
    allowed: bool
    reason: str


class PlatformAdapter(ABC):
    platform: str
    version: str
    allowed_hosts: set[str]
    min_interval_s: float = 2.0
    requires_login: bool = False

    # ── contract ──
    @abstractmethod
    def validate_access(self) -> AccessStatus: ...

    @abstractmethod
    def build_search_url(self, query: str, filters: dict | None = None) -> str | None: ...

    def open_search(self, s: BrowserSession, query: str, filters: dict | None = None) -> SearchPageState | None:
        url = self.build_search_url(query, filters)
        if url is None:
            return None
        s.goto(url)
        return SearchPageState(url=url)

    @abstractmethod
    def collect_result_refs(self, s: BrowserSession, state: SearchPageState) -> list[ResultRef]: ...

    def open_listing(self, s: BrowserSession, ref: ResultRef) -> None:
        s.goto(ref.url)

    @abstractmethod
    def extract_observation(self, s: BrowserSession, ref: ResultRef) -> RawListingObservation: ...

    @abstractmethod
    def evidence_locator(self, s: BrowserSession): ...

    def capture_evidence(self, s: BrowserSession, source_url: str) -> ScreenshotEvidence:
        """Focused screenshot of the listing container (§6.5 preferred capture order)."""
        loc = self.evidence_locator(s)
        png = loc.screenshot(animations="disabled", timeout=15000)
        with Image.open(io.BytesIO(png)) as im:
            width, height = im.size
        return ScreenshotEvidence(
            png_bytes=png, checksum_sha256=sha256_hex(png), perceptual_hash=dhash_hex(png),
            width=width, height=height, captured_at=datetime.now(timezone.utc),
            viewport=dict(s.page.viewport_size or {}), source_url=source_url,
            visibility=self.visibility(s),
        )

    def visibility(self, s: BrowserSession) -> dict:
        return {}

    def image_locator(self, s: BrowserSession):
        """Main listing photo, or None if the source has none (§6.5 capture order item 2)."""
        return None

    def capture_image(self, s: BrowserSession, source_url: str) -> ScreenshotEvidence | None:
        loc = self.image_locator(s)
        if loc is None or loc.count() == 0 or not loc.first.is_visible():
            return None
        loc = loc.first
        loc.scroll_into_view_if_needed(timeout=5000)
        try:  # wait for the photo itself, not just the element
            loc.evaluate("img => img.complete ? null : new Promise(r => { img.onload = img.onerror = r })", timeout=10000)
        except Exception:
            pass
        png = loc.screenshot(animations="disabled", timeout=15000)
        with Image.open(io.BytesIO(png)) as im:
            width, height = im.size
        return ScreenshotEvidence(
            png_bytes=png, checksum_sha256=sha256_hex(png), perceptual_hash=dhash_hex(png),
            width=width, height=height, captured_at=datetime.now(timezone.utc),
            viewport=dict(s.page.viewport_size or {}), source_url=source_url,
            crop_policy_version="crop-primary-image-v1", visibility={"primary_image": True},
        )

    def extract_comment_texts(self, s: BrowserSession) -> list[str]:
        """Raw text of PUBLIC comments on the listing post only — never author names or profiles.
        Sources without public comments return []."""
        return []

    def advance(self, s: BrowserSession, state: SearchPageState) -> SearchPageState:
        state.done = True
        return state
