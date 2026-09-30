"""Polite HTTP client for official-API and public-web adapters.

- only the adapter's allowed hosts; https only
- per-host minimum interval (the platform's rate limit)
- robots.txt respected for public-web pages (official APIs are governed by their own terms/quotas instead)
- 429 → RateLimited, 401 → LoginRequired, 403 → AccessBlocked, challenge pages → Challenged (never bypassed)
- credentials never appear in logs or returned search URLs
Tests inject an httpx.MockTransport.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import urllib.robotparser
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from .contract import AccessBlocked, Challenged, LoginRequired, PlatformError, RateLimited

log = logging.getLogger("fbm_intel.platforms.http")
USER_AGENT = "FBM-ListingIntel/1.0 (+https://fbm-pied.vercel.app; public listings research; contact via site)"
BROWSER_LIKE_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36 FBM-ListingIntel/1.0")
_CHALLENGE = re.compile(r"cf-chl|challenge-platform|g-recaptcha|h-captcha|hcaptcha|captcha-delivery|verify you are human|"
                        r"are you a robot|attention required! \| cloudflare", re.I)
_SECRET_PARAMS = {"key", "api_key", "apikey", "access_token", "token", "client_secret", "cx", "sig", "signature"}

_last_hit: dict[str, float] = {}
_hit_lock = threading.Lock()


def safe_url(url: str) -> str:
    """URL with credential query params removed (for logs, search_url fields and reports)."""
    p = urlsplit(url)
    if not p.query:
        return url
    kept = [(k, v) for k, v in (kv.split("=", 1) if "=" in kv else (kv, "") for kv in p.query.split("&"))
            if k.lower() not in _SECRET_PARAMS]
    return urlunsplit((p.scheme, p.netloc, p.path, "&".join(f"{k}={v}" for k, v in kept), ""))


def host_allowed(host: str, allowed: frozenset[str] | set[str]) -> bool:
    host = host.lower().split(":")[0]
    return any(host == a or host.endswith("." + a) for a in allowed)


class PoliteHttp:
    def __init__(self, allowed_hosts: frozenset[str] | set[str], *, min_interval_s: float = 2.0, respect_robots: bool = True,
                 transport: httpx.BaseTransport | None = None, timeout_s: float = 30.0, user_agent: str = USER_AGENT,
                 max_bytes: int = 5_000_000, headers: dict | None = None):
        self.allowed = frozenset(allowed_hosts)
        self.min_interval_s = min_interval_s
        self.respect_robots = respect_robots
        self.max_bytes = max_bytes
        self.client = httpx.Client(transport=transport, timeout=timeout_s, follow_redirects=True,
                                   headers={"User-Agent": user_agent, "Accept-Language": "en,km;q=0.8", **(headers or {})})
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.requests = 0

    def close(self) -> None:
        self.client.close()

    # ── policy ──
    def _pace(self, host: str) -> None:
        with _hit_lock:
            wait = _last_hit.get(host, 0) + self.min_interval_s - time.monotonic()
            _last_hit[host] = max(time.monotonic(), _last_hit.get(host, 0) + self.min_interval_s)
        if wait > 0:
            time.sleep(wait)

    def robots_allows(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        p = urlsplit(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(base + "/robots.txt")
                if r.status_code >= 400:
                    rp = None  # no robots.txt → allowed
                else:
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp = None
            self._robots[base] = rp
        rp = self._robots[base]
        return True if rp is None else rp.can_fetch(USER_AGENT.split("/")[0], url)

    # ── requests ──
    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None, expect: str = "any") -> httpx.Response:
        full = f"{url}{'&' if '?' in url else '?'}{urlencode(params)}" if params else url
        p = urlsplit(full)
        if p.scheme != "https" or not host_allowed(p.netloc, self.allowed):
            raise AccessBlocked(f"host not allowed for this adapter: {p.netloc}", safe_url(full))
        if not self.robots_allows(full):
            raise AccessBlocked("disallowed by robots.txt", safe_url(full))
        self._pace(p.netloc)
        self.requests += 1
        try:
            r = self.client.get(full, headers=headers)
        except httpx.TimeoutException as e:
            raise PlatformError(f"timeout: {e}", safe_url(full)) from e
        except httpx.HTTPError as e:
            raise PlatformError(f"network error: {type(e).__name__}", safe_url(full)) from e
        if len(r.content) > self.max_bytes:
            raise PlatformError("response too large", safe_url(full))
        self.check(r, safe_url(full))
        return r

    def post_form(self, url: str, data: dict, *, auth: tuple[str, str] | None = None, headers: dict | None = None) -> httpx.Response:
        """Only for documented OAuth token endpoints (e.g. Reddit app-only auth)."""
        p = urlsplit(url)
        if p.scheme != "https" or not host_allowed(p.netloc, self.allowed):
            raise AccessBlocked(f"host not allowed for this adapter: {p.netloc}", url)
        self._pace(p.netloc)
        r = self.client.post(url, data=data, auth=auth, headers=headers)
        self.check(r, url)
        return r

    @staticmethod
    def check(r: httpx.Response, url: str) -> None:
        if r.status_code == 429:
            ra = r.headers.get("retry-after")
            raise RateLimited("HTTP 429", url, float(ra) if ra and ra.isdigit() else None)
        if r.status_code == 401:
            raise LoginRequired("HTTP 401 (credentials missing/invalid)", url)
        ctype = r.headers.get("content-type", "")
        if "html" in ctype and _CHALLENGE.search(r.text[:20000]):
            raise Challenged("challenge / CAPTCHA page", url)
        if r.status_code == 403:
            raise AccessBlocked("HTTP 403", url)
        if r.status_code >= 500:
            raise PlatformError(f"HTTP {r.status_code}", url)
