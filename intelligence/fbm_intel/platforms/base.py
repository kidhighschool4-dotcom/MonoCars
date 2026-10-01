"""Shared bases for adapters: HTTP (official API / public web) and visible browser sessions.

HttpAdapterBase    — PoliteHttp from the platform's rate config; tests pass an httpx transport via ctx.fixtures.
BrowserAdapterBase — one isolated Playwright context per platform (persistent profile for manual login), opened lazily,
                     visible by default; challenges are shown to the human and never solved automatically.
"""
from __future__ import annotations

import contextlib
import hashlib
import re
import io
import logging
import time
from pathlib import Path

import httpx

from ..social.model import Evidence
from .contract import AdapterContext, BusinessInfo, Challenged, Health, LoginRequired, PlatformAdapter
from .http import PoliteHttp

log = logging.getLogger("fbm_intel.platforms")
PRIVATE_DIR = Path(__file__).resolve().parents[2] / "private"

# Hides names/avatars before any screenshot. Adapters add platform-specific selectors.
BASE_HIDE_CSS = "img[alt*='profile' i], img[alt*='avatar' i], [class*='avatar' i], [data-testid*='avatar' i] { visibility: hidden !important; }"


def evidence_from_png(png: bytes, kind: str) -> Evidence:
    try:
        from PIL import Image
        w, h = Image.open(io.BytesIO(png)).size
    except Exception:  # noqa: BLE001
        w = h = 0
    return Evidence(png=png, checksum_sha256=hashlib.sha256(png).hexdigest(), width=w, height=h, kind=kind)


class HttpAdapterBase(PlatformAdapter):
    respect_robots: bool = True          # public_web → True; official APIs set False (their terms/quotas govern)
    extra_headers: dict = {}

    def __init__(self, ctx: AdapterContext):
        super().__init__(ctx)
        rate = self.cfg.get("rate", {})
        transport = ctx.fixtures if isinstance(ctx.fixtures, httpx.BaseTransport) else None
        self.http = PoliteHttp(self.allowed_hosts, min_interval_s=float(rate.get("min_interval_s", 2)),
                               respect_robots=self.respect_robots, transport=transport, headers=self.extra_headers)

    def close(self) -> None:
        self.http.close()

    def health_check(self) -> Health:
        missing = self.missing_env()
        return Health("misconfigured", "missing: " + ", ".join(missing)) if missing else Health("ok")


class BrowserAdapterBase(PlatformAdapter):
    access = "browser_session"
    profile_name: str = ""               # private/<profile_name> persistent profile (manual login)
    login_url: str | None = None
    hide_css: str = BASE_HIDE_CSS
    challenge_wait_s: int = 600

    def __init__(self, ctx: AdapterContext):
        super().__init__(ctx)
        self._stack: contextlib.ExitStack | None = None
        self.s = None

    @property
    def profile_dir(self) -> Path:
        return PRIVATE_DIR / (self.profile_name or f"{self.name}-profile")

    def session(self):
        """Open the platform's browser context once per cycle. Tests: ctx.fixtures is a callable(session)."""
        if self.s is not None:
            return self.s
        from ..browser import open_persistent_session, open_session
        self._stack = contextlib.ExitStack()
        interval = float(self.cfg.get("rate", {}).get("min_interval_s", 10))
        if callable(self.ctx.fixtures) and not isinstance(self.ctx.fixtures, httpx.BaseTransport):
            self.s = self._stack.enter_context(open_session(set(self.allowed_hosts), 0, headless=True))
            self.ctx.fixtures(self.s)
        else:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self.profile_dir.chmod(0o700)
            self.s = self._stack.enter_context(open_persistent_session(set(self.allowed_hosts), str(self.profile_dir),
                                                                       interval, headless=not self.ctx.headed))
        return self.s

    def close(self) -> None:
        if self._stack:
            try:
                self._stack.close()
            finally:
                self._stack, self.s = None, None

    def health_check(self) -> Health:
        if not (callable(self.ctx.fixtures) or self.profile_dir.exists()):
            return Health("login_required", f"no browser profile yet — run: python -m app.platform_login {self.name}")
        return Health("ok")

    # ── human-in-the-loop challenge handling ──
    def is_challenged(self) -> bool:
        return False

    def is_login_wall(self) -> bool:
        return False

    def guard(self) -> None:
        """Called after every navigation. Visible run: show the challenge and wait for the human; else stop."""
        if self.is_challenged():
            if not self.ctx.headed:
                raise Challenged("challenge shown; run headed to solve it yourself", self.s.page.url)
            with contextlib.suppress(Exception):
                self.s.page.bring_to_front()
            print("\a", end="", flush=True)
            from .notify import on_challenge
            on_challenge(self.display_name or self.name, getattr(self.s.page, "url", None), self.challenge_wait_s)
            log.warning("%s: CAPTCHA/verification shown. Solve it yourself in the browser window (up to %ds)…",
                        self.display_name or self.name, self.challenge_wait_s)
            deadline = time.monotonic() + self.challenge_wait_s
            while time.monotonic() < deadline:
                time.sleep(3)
                if not self.is_challenged():
                    log.info("%s: challenge cleared by you; continuing", self.name)
                    return
            raise Challenged("challenge not solved in time", self.s.page.url)
        if self.is_login_wall():
            raise LoginRequired(f"login wall — run: python -m app.platform_login {self.name}", self.s.page.url)

    def screenshot_locator(self, locator, kind: str, max_height: int = 1400) -> Evidence | None:
        page = self.s.page
        page.add_style_tag(content=self.hide_css)
        page.wait_for_timeout(150)
        box = locator.bounding_box()
        if not box:
            return None
        if box["height"] > max_height:
            png = page.screenshot(clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": max_height}, full_page=True)
        else:
            png = locator.screenshot()
        return evidence_from_png(png, kind)


# People on a business page (followers, friends, customers, commenters) are hidden before the screenshot and never read.
BUSINESS_PEOPLE_HIDE_CSS = (
    "[role='article'], [role='feed'], [role='complementary'], [role='banner'], [role='navigation'], "
    "a[href*='/friends'], a[href*='followers'], a[href*='following'], a[href*='/people'], "
    "[aria-label*='follower' i], [aria-label*='friend' i], [data-e2e*='follow'], [data-e2e*='comment'], "
    "[contenteditable='true'], [aria-label^='Comment as' i] { visibility: hidden !important; }")
_BIZ_TEXT_JS = r"""() => {
  const lines = (document.body.innerText || '').split('\n').map(t => t.trim()).filter(t => t && t.length < 160).slice(0, 220);
  const links = Array.from(document.querySelectorAll('a[href^="http"]')).map(a => a.href).slice(0, 200);
  return {lines, links, title: document.title};
}"""
_PHONE = re.compile(r"(?:\+?855|0)[\s.-]?\d{2}[\s.-]?\d{3}[\s.-]?\d{3,4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def extract_business_info(lines: list[str], links: list[str], own_hosts: tuple[str, ...]) -> dict:
    """Business-relevant facts only: category, sales location, official contact channels."""
    category = next((l.split("·", 1)[1].strip() for l in lines if re.match(r"^(page|business|shop)\s*·", l, re.I)), None)
    location = next((l for l in lines if re.search(r"(phnom penh|ភ្នំពេញ|siem reap|battambang|cambodia|កម្ពុជា|street|ផ្លូវ|sangkat|khan)", l, re.I)
                     and len(l) < 120), None)
    contacts: dict = {}
    phones = sorted({m.group(0).strip() for l in lines for m in [_PHONE.search(l)] if m})[:3]
    emails = sorted({m.group(0) for l in lines for m in [_EMAIL.search(l)] if m})[:2]
    sites = sorted({u for u in links if not any(h in u for h in own_hosts) and not u.startswith("https://l.facebook.com")})[:2]
    if phones:
        contacts["phone"] = phones
    if emails:
        contacts["email"] = emails
    if sites:
        contacts["website"] = sites
    return {"category": category, "sales_location": location, "contact_channels": contacts}


def capture_business_page_in(adapter, url: str, account_type: str, extra_hide_js: str | None = None,
                             max_height: int = 1100) -> BusinessInfo | None:
    """Shared browser routine: a NEW tab in the adapter's session (the post page stays as it is)."""
    if account_type != "business":
        raise PermissionError("business pages only — personal profiles are never opened")
    from urllib.parse import urlsplit
    from .http import host_allowed
    if not host_allowed(urlsplit(url).netloc, adapter.allowed_hosts):
        return None
    s = adapter.session()
    page = s.context.new_page()
    try:
        s.limiter.wait()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3500)
        page.add_style_tag(content=BUSINESS_PEOPLE_HIDE_CSS)
        if extra_hide_js:
            page.evaluate(extra_hide_js)
        page.wait_for_timeout(200)
        data = page.evaluate(_BIZ_TEXT_JS)
        vp = page.viewport_size or {"width": 1280, "height": 900}
        png = page.screenshot(clip={"x": 0, "y": 0, "width": vp["width"], "height": min(max_height, vp["height"])})
        info = extract_business_info(data["lines"], data["links"], tuple(adapter.allowed_hosts))
        return BusinessInfo(name=None, url=url, screenshot=evidence_from_png(png, "business"), **info)
    except Exception as e:  # noqa: BLE001 - optional evidence; never stops collection
        log.info("business page capture failed for %s: %s", url, type(e).__name__)
        return None
    finally:
        with contextlib.suppress(Exception):
            page.close()
