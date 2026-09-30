"""Facebook adapter (owner-approved, supervised, low-volume). Surfaces: Marketplace and public post search.

Rules (architecture §8.3, §13 + owner instructions):
- Uses a session the owner created by logging in manually (python -m app.facebook_login). Never handles passwords.
- One keyword at a time, conservative scrolling, fixed human-scale delays. No stealth, no proxies, no CAPTCHA
  bypass, no messaging/commenting/reacting.
- Stops on CAPTCHA, checkpoint, warning, login wall or account restriction (BlockedError from the browser worker).
- Collects only listing facts. Seller/commenter names and profiles are never collected.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from ..browser import BlockedError, BlockStatus, BrowserSession
from ..normalize import canonicalize_url, normalize_text, parse_published_at
from ..schemas import PageState, RawListingObservation
from .base import AccessStatus, PlatformAdapter, ResultRef, SearchPageState

log = logging.getLogger("fbm_intel.facebook")

SESSION_PATH = Path(__file__).resolve().parents[2] / "private" / "facebook-session.json"
FB_HOSTS = {"facebook.com", "fbcdn.net", "facebook.net", "fbsbx.com"}
MARKETPLACE_ITEM = re.compile(r"/marketplace/item/(\d{6,25})")
POST_PATTERNS = [re.compile(p) for p in (r"/groups/[^/]+/posts/(\d+)", r"/[^/?#]+/posts/([\w]+)", r"story_fbid=(\d+)",
                                         r"/permalink/(\d+)", r"/share/p/([\w-]+)")]
UI_HEADINGS = {"marketplace", "notifications", "chats", "facebook", "search results", "today's picks", "browse all"}


def title_from_document(doc_title: str | None) -> str | None:
    """'(3) Marketplace – 2015 BMW Series 3 | Facebook' → '2015 BMW Series 3'."""
    t = normalize_text(doc_title or "")
    t = re.sub(r"^\(\d+\)\s*", "", t)
    t = re.sub(r"^marketplace\s*[–—-]\s*", "", t, flags=re.I)
    t = re.sub(r"\s*[|–—-]\s*facebook( marketplace)?$", "", t, flags=re.I)
    return None if not t or t.casefold() in UI_HEADINGS else t


def clean_card_title(card_text: str | None) -> str | None:
    """Card text is 'price [old price] title location' on one line; strip leading prices and 'Free'."""
    t = normalize_text(card_text or "")
    t = re.sub(r"^(?:(?:free|[$៛]\s?[\d,.]+|khr\s?[\d,.]+|[\d,.]+\s?(?:usd|khr|៛))\s*)+", "", t, flags=re.I)
    return t or None


PRICE_RE = re.compile(r"(?:[$៛]\s?[\d,.]+[kKmM]?|[\d,.]+\s?(?:USD|\$|៛|រៀល))")


def is_logged_in(context, page=None) -> bool:
    """Facebook sets the c_user cookie only for a logged-in account (value is never read out)."""
    has_cookie = any(c.get("name") == "c_user" for c in context.cookies("https://www.facebook.com"))
    if not has_cookie:
        return False
    if page is not None:
        url = (page.url or "").lower()
        if "/login" in url or "/checkpoint" in url:
            return False
    return True


class FacebookAdapter(PlatformAdapter):
    platform = "facebook"
    version = "facebook-adapter-v1"
    min_interval_s = 8.0           # between page loads — deliberately slow
    requires_login = True
    max_scrolls = 3                # per search, conservative
    scroll_pause_ms = 3500

    def __init__(self, surface: str = "marketplace", location_slug: str = "phnompenh", session_path: Path = SESSION_PATH):
        if surface not in ("marketplace", "posts"):
            raise ValueError("surface must be 'marketplace' or 'posts'")
        self.surface = surface
        self.location_slug = location_slug
        self.session_path = session_path
        self.allowed_hosts = set(FB_HOSTS)
        self.platform = "facebook" if surface == "marketplace" else "facebook_posts"

    # ── access ──
    def validate_access(self) -> AccessStatus:
        if not self.session_path.exists():
            return AccessStatus(False, f"no saved session at {self.session_path} — run: python -m app.facebook_login")
        return AccessStatus(True, "owner-approved supervised Facebook session")

    def confirm_logged_in(self, s: BrowserSession) -> None:
        s.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        s.page.wait_for_timeout(2500)
        if not is_logged_in(s.context, s.page):
            raise BlockedError(BlockStatus.LOGIN_WALL, s.page.url)
        log.info("Facebook session loaded and logged in (opened %s)", s.page.url)

    # ── search ──
    def build_search_url(self, query: str, filters: dict | None = None) -> str | None:
        q = normalize_text(query)
        if not q:
            return None
        if self.surface == "marketplace":
            return f"https://www.facebook.com/marketplace/{self.location_slug}/search/?query={quote(q)}&exact=false"
        return f"https://www.facebook.com/search/posts/?q={quote(q)}"

    def open_search(self, s: BrowserSession, query: str, filters: dict | None = None) -> SearchPageState | None:
        url = self.build_search_url(query, filters)
        if url is None:
            return None
        log.info("Opening Facebook %s search: %s", self.surface, url)
        s.goto(url, wait_until="domcontentloaded")
        s.page.wait_for_timeout(4000)
        return SearchPageState(url=url)

    def _pattern_hrefs(self, s: BrowserSession) -> list[tuple[str, str, str]]:
        """(listing id, absolute url, visible card text) for every result link currently in the DOM."""
        found = s.page.evaluate("""() => Array.from(document.querySelectorAll('a[href]')).map(a => [a.href, (a.innerText||'').slice(0, 300)])""")
        out: list[tuple[str, str, str]] = []
        for href, text in found:
            if self.surface == "marketplace":
                m = MARKETPLACE_ITEM.search(href)
                if m:
                    out.append((m.group(1), f"https://www.facebook.com/marketplace/item/{m.group(1)}/", text))
            else:
                path = urlsplit(href).path + ("?" + urlsplit(href).query if "story_fbid" in href else "")
                for pat in POST_PATTERNS:
                    m = pat.search(path)
                    if m and "/marketplace/" not in path:
                        out.append((m.group(1), href.split("#")[0].split("&__cft__")[0].split("?__cft__")[0], text))
                        break
        return out

    def collect_result_refs(self, s: BrowserSession, state: SearchPageState) -> list[ResultRef]:
        seen: dict[str, ResultRef] = {}
        for i in range(self.max_scrolls + 1):
            for lid, url, text in self._pattern_hrefs(s):
                if lid not in seen:
                    seen[lid] = ResultRef(url=url, source_listing_id=lid, hint_title=normalize_text(text) or None)
            if i == self.max_scrolls:
                break
            before = len(seen)
            s.page.mouse.wheel(0, 1600)
            s.page.wait_for_timeout(self.scroll_pause_ms)
            block = self._check_block(s)
            if block:
                raise BlockedError(block, s.page.url)
            if len(seen) == before and i > 0:
                log.info("No new results after scroll %d — stopping scroll", i + 1)
                break
        log.info("Found %d %s result(s) on %s", len(seen), self.surface, state.url)
        if not seen:
            log.info("No results found for this search (page text starts: %r)",
                     normalize_text(s.page.inner_text("body")[:160]))
        return list(seen.values())

    def _check_block(self, s: BrowserSession) -> BlockStatus | None:
        from ..browser import detect_block

        b = detect_block(s.page)
        return None if b == BlockStatus.NONE else b

    # ── listing ──
    def open_listing(self, s: BrowserSession, ref: ResultRef) -> None:
        log.info("Opening listing %s", ref.url)
        s.goto(ref.url, wait_until="domcontentloaded")
        s.page.wait_for_timeout(3500)

    def _main_text(self, s: BrowserSession) -> str:
        for sel in ("div[role='main']", "[role='dialog']", "body"):
            loc = s.page.locator(sel)
            if loc.count():
                try:
                    return loc.first.inner_text(timeout=5000)
                except Exception:
                    continue
        return ""

    def extract_observation(self, s: BrowserSession, ref: ResultRef) -> RawListingObservation:
        text = self._main_text(s)
        lines = [normalize_text(l) for l in text.splitlines() if normalize_text(l)]
        state = PageState.OK
        low = text.lower()
        if "this listing is no longer available" in low or "listing isn't available" in low or "content isn't available" in low:
            state = PageState.SOLD_OR_REMOVED
        if self.surface == "marketplace":
            title = self._heading(s) or self._document_title(s) or clean_card_title(ref.hint_title)
            price = next((l for l in lines[:12] if PRICE_RE.fullmatch(l.replace(" ", "")) or PRICE_RE.match(l)), None)
            listed = next((l for l in lines if l.lower().startswith("listed ")), None)
            location = None
            published = None
            if listed:  # "Listed 2 days ago in Phnom Penh, Cambodia"
                m = re.match(r"listed (.+?) in (.+)$", listed, re.IGNORECASE)
                if m:
                    published = parse_published_at(m.group(1))
                    location = m.group(2)
            description = self._section_after(lines, ("seller's description", "description"))
            if "sold" in (price or "").lower():
                state = PageState.SOLD_OR_REMOVED
        else:
            title = (lines[0] if lines else None)
            price = next((l for l in lines if PRICE_RE.search(l)), None)
            location, published = None, None
            description = "\n".join(lines[:40])[:5000] or None
        return RawListingObservation(
            source_platform=self.platform,
            source_listing_id=ref.source_listing_id,
            source_url=ref.url,
            canonical_url=canonicalize_url(ref.url),
            title_raw=title,
            description_raw=(description or "")[:5000] or None,
            price_text_raw=price,
            location_text_raw=location,
            seller_display_name=None,   # never collected
            published_at_observed=published,
            captured_at=datetime.now(timezone.utc),
            adapter_version=self.version,
            page_state=state,
            observation_payload={"surface": self.surface, "listed_line": None if self.surface != "marketplace" else listed},
        )

    def _heading(self, s: BrowserSession) -> str | None:
        """First level-1 heading in the listing that is a real title (not 'Marketplace', not a price)."""
        for h in s.page.locator("div[role='main'] h1, [role='dialog'] h1, div[role='main'] [role='heading'][aria-level='1']").all()[:6]:
            try:
                t = normalize_text(h.inner_text(timeout=2000))
            except Exception:  # noqa: BLE001
                continue
            if t and t.casefold() not in UI_HEADINGS and not PRICE_RE.fullmatch(t.replace(" ", "")):
                return t
        return None

    @staticmethod
    def _document_title(s: BrowserSession) -> str | None:
        return title_from_document(s.page.title())

    @staticmethod
    def _section_after(lines: list[str], headings: tuple[str, ...]) -> str | None:
        for i, l in enumerate(lines):
            if l.lower() in headings:
                chunk = []
                for nxt in lines[i + 1:i + 15]:
                    if nxt.lower() in ("seller information", "seller details", "send seller a message", "location is approximate"):
                        break
                    chunk.append(nxt)
                return "\n".join(chunk) or None
        return None

    def evidence_locator(self, s: BrowserSession):
        if self.surface == "posts":
            art = s.page.locator("div[role='main'] div[role='article'], div[role='article']")
            if art.count():
                return art.first
        for sel in ("div[role='main']", "[role='dialog']"):
            loc = s.page.locator(sel)
            if loc.count():
                return loc.first
        return s.page.locator("body")

    def image_locator(self, s: BrowserSession):
        loc = s.page.locator("div[role='main'] img[alt]:not([alt=''])")
        return loc if loc.count() else None

    def extract_comment_texts(self, s: BrowserSession) -> list[str]:
        """Public comment TEXT only (post surface). Marketplace items have no public comments.
        Author names are deliberately not read."""
        if self.surface != "posts":
            return []
        texts: list[str] = []
        for c in s.page.locator("div[role='article'] div[role='article'] div[dir='auto']").all()[:200]:
            try:
                t = normalize_text(c.inner_text(timeout=2000))
            except Exception:
                continue
            if t:
                texts.append(t)
        return texts
