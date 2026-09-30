"""Shared bases for adapters: HTTP (official API / public web) and visible browser sessions.

HttpAdapterBase    — PoliteHttp from the platform's rate config; tests pass an httpx transport via ctx.fixtures.
BrowserAdapterBase — one isolated Playwright context per platform (persistent profile for manual login), opened lazily,
                     visible by default; challenges are shown to the human and never solved automatically.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import logging
import time
from pathlib import Path

import httpx

from ..social.model import Evidence
from .contract import AdapterContext, Challenged, Health, LoginRequired, PlatformAdapter
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
    challenge_wait_s: int = 180

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
