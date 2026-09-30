"""One-time manual login for a browser-session platform:  python -m app.platform_login <platform>

Opens a VISIBLE Chromium window with the platform's persistent profile (private/<platform>-profile) at its login page.
You log in yourself — password, two-factor, CAPTCHA, "confirm it's you". Nothing here reads, types or stores your
password; it only waits (up to 15 minutes) until the platform's logged-in cookie appears (cookie VALUES are never
printed or saved by this script; the browser profile keeps the session). The profile folder is git-ignored and
owner-only (0700).

Platforms: any registered adapter with access="browser_session" that defines `login_url` (instagram, x, threads,
pinterest, …). Adapters that define `login_cookies` are detected automatically; for others press Enter when done.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time

from fbm_intel.browser import open_persistent_session
from fbm_intel.platforms import registry
from fbm_intel.platforms.base import PRIVATE_DIR

log = logging.getLogger("platform_login")
WAIT_S = 15 * 60


def _cookie_present(cookies: list[dict], wanted) -> bool:
    for w in wanted:
        name, value = (w.get("name"), w.get("value")) if isinstance(w, dict) else (w, None)
        for c in cookies:
            if c.get("name") == name and c.get("value") and (value is None or c.get("value") == value):
                return True
    return False


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("platform", help="registered platform name, e.g. instagram, x, threads, pinterest")
    ap.add_argument("--wait-min", type=float, default=WAIT_S / 60, help="how long to wait for you to log in (minutes)")
    args = ap.parse_args(argv)

    try:
        cls = registry.get(args.platform)
    except KeyError as e:
        log.error("Unknown platform %r (%s)", args.platform, str(e).strip("'\""))
        return 2
    if cls.access != "browser_session" or not getattr(cls, "login_url", None):
        log.error("%s does not use a browser login (access=%s)", args.platform, cls.access)
        return 2

    profile = PRIVATE_DIR / (getattr(cls, "profile_name", "") or f"{cls.name}-profile")
    profile.mkdir(parents=True, exist_ok=True)
    os.chmod(profile, 0o700)
    wanted = tuple(getattr(cls, "login_cookies", ()) or ())
    cookie_url = getattr(cls, "login_cookie_url", None) or cls.login_url

    with open_persistent_session(set(cls.allowed_hosts), str(profile), 0, headless=False) as s:
        s.page.goto(cls.login_url, wait_until="domcontentloaded")
        log.info("Log in to %s yourself in the window (any verification too). Waiting up to %.0f minutes…",
                 cls.display_name or cls.name, args.wait_min)
        done = threading.Event()
        if not wanted:
            log.info("No login cookie configured for %s — press Enter here once you are logged in.", cls.name)
            threading.Thread(target=lambda: (sys.stdin.readline(), done.set()), daemon=True).start()
        deadline = time.monotonic() + args.wait_min * 60
        while time.monotonic() < deadline:
            if done.is_set() or (wanted and _cookie_present(s.context.cookies(cookie_url), wanted)):
                s.page.wait_for_timeout(3000)
                log.info("Logged in. Session kept in %s (values not shown). You can close this window.", profile)
                return 0
            time.sleep(3)
    log.error("Timed out; nothing changed. Run again when you are ready.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
