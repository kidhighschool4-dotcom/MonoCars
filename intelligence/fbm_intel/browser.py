"""Playwright browser worker (§8.4): isolated contexts, domain allowlist, rate limit, block detection."""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Iterator
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Page, Route, sync_playwright

VIEWPORT = {"width": 1280, "height": 900}
LOCALE = "en-US"
TIMEZONE = "Asia/Phnom_Penh"


class BlockStatus(str, Enum):
    NONE = "none"
    CAPTCHA = "captcha"
    BOT_CHALLENGE = "bot_challenge"
    LOGIN_WALL = "login_wall"
    ACCESS_DENIED = "access_denied"
    RATE_LIMITED = "rate_limited"


class BlockedError(Exception):
    """Automation must stop for this platform (§8.3). Never retried automatically."""

    def __init__(self, status: BlockStatus, url: str):
        super().__init__(f"{status.value} at {url}")
        self.status = status
        self.url = url


_BLOCK_MARKERS: list[tuple[BlockStatus, tuple[str, ...]]] = [
    (BlockStatus.BOT_CHALLENGE, ("just a moment", "performing security verification", "checking your browser",
                                 "verify you are human", "attention required! | cloudflare", "ddos protection")),
    (BlockStatus.CAPTCHA, ("captcha", "i'm not a robot", "recaptcha", "hcaptcha")),
    (BlockStatus.RATE_LIMITED, ("too many requests", "rate limit exceeded")),
    (BlockStatus.ACCESS_DENIED, ("access denied", "you don't have permission", "request blocked")),
    (BlockStatus.LOGIN_WALL, ("log in to continue", "you must log in", "sign in to continue", "login to view")),
]


def detect_block(page: Page, response_status: int | None = None) -> BlockStatus:
    title = (page.title() or "").lower()
    try:
        head = page.inner_text("body", timeout=2000)[:3000].lower()
    except Exception:
        head = ""
    hay = f"{title}\n{head}"
    for status, markers in _BLOCK_MARKERS:
        if any(m in hay for m in markers):
            return status
    if response_status == 429:
        return BlockStatus.RATE_LIMITED
    if response_status == 403:
        return BlockStatus.ACCESS_DENIED
    try:
        if page.locator("iframe[src*='challenges.cloudflare.com'], iframe[src*='recaptcha'], iframe[src*='hcaptcha']").count():
            return BlockStatus.CAPTCHA
    except Exception:
        pass
    return BlockStatus.NONE


class RateLimiter:
    """Minimum spacing between navigations for one platform (human-scale by default)."""

    def __init__(self, min_interval_s: float):
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def wait(self) -> None:
        delta = time.monotonic() - self._last
        if delta < self.min_interval_s:
            time.sleep(self.min_interval_s - delta)
        self._last = time.monotonic()


def host_allowed(url: str, allowed_hosts: set[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in allowed_hosts)


@dataclass
class BrowserSession:
    browser: Browser
    context: BrowserContext
    page: Page
    limiter: RateLimiter
    allowed_hosts: set[str]
    blocked_navigations: list[str]

    def goto(self, url: str, wait_until: str = "networkidle", timeout_ms: int = 30000) -> int | None:
        if not host_allowed(url, self.allowed_hosts):
            raise PermissionError(f"navigation outside allowlist: {urlsplit(url).hostname}")
        self.limiter.wait()
        resp = self.page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        status = resp.status if resp else None
        block = detect_block(self.page, status)
        if block != BlockStatus.NONE:
            raise BlockedError(block, url)
        return status


@contextmanager
def open_session(allowed_hosts: set[str], min_interval_s: float = 2.0, headless: bool = True) -> Iterator[BrowserSession]:
    """One isolated context per platform. Downloads off, explicit locale/timezone, allowlisted navigation."""
    blocked: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport=VIEWPORT, locale=LOCALE, timezone_id=TIMEZONE,
                                      accept_downloads=False, java_script_enabled=True,
                                      extra_http_headers={"Accept-Language": "en-US,en;q=0.9,km;q=0.8"})

        def guard(route: Route) -> None:
            req = route.request
            # Only top-level/iframe documents are restricted; images/fonts from CDNs may load.
            if req.resource_type == "document" and not host_allowed(req.url, allowed_hosts):
                blocked.append(req.url)
                route.abort("blockedbyclient")
            else:
                route.continue_()

        context.route("**/*", guard)
        page = context.new_page()
        try:
            yield BrowserSession(browser, context, page, RateLimiter(min_interval_s), set(allowed_hosts), blocked)
        finally:
            context.close()
            browser.close()
