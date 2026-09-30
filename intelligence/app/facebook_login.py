"""One-time Facebook login bootstrap:  python -m app.facebook_login

Opens a VISIBLE Chromium window at Facebook's login page and waits. You type your credentials and finish any
two-factor / CAPTCHA yourself. This script never fills in, reads, stores or logs your password — it only waits
until Facebook shows you as logged in, then saves the Playwright session (cookies) to
private/facebook-session.json with owner-only permissions. Cookie values are never printed.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from playwright.sync_api import sync_playwright

from fbm_intel.adapters.facebook import SESSION_PATH, is_logged_in
from fbm_intel.browser import LOCALE, TIMEZONE, VIEWPORT

log = logging.getLogger("facebook_login")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="python -m app.facebook_login", description=__doc__)
    ap.add_argument("--timeout-min", type=int, default=10, help="how long to wait for you to finish logging in")
    a = ap.parse_args(argv)

    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(SESSION_PATH.parent, 0o700)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport=VIEWPORT, locale=LOCALE, timezone_id=TIMEZONE)
        page = context.new_page()
        page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
        log.info("A Chromium window is open at facebook.com/login.")
        log.info("Log in yourself (password, 2FA, any CAPTCHA). This script does not touch the form.")
        log.info("Waiting up to %d minutes…", a.timeout_min)

        deadline = time.monotonic() + a.timeout_min * 60
        while time.monotonic() < deadline:
            if page.is_closed():
                log.error("The browser window was closed before login finished. Nothing was saved.")
                return 1
            if is_logged_in(context, page):
                page.wait_for_timeout(3000)  # let Facebook finish setting session cookies
                context.storage_state(path=str(SESSION_PATH))
                os.chmod(SESSION_PATH, 0o600)
                n = len(context.cookies("https://www.facebook.com"))
                log.info("Logged in. Session saved to %s (%d Facebook cookies, values not shown, mode 600).",
                         SESSION_PATH.relative_to(SESSION_PATH.parents[1]), n)
                log.info("Next: python -m app.crawl --platform facebook --query \"car sedan\" --dry-run --headed")
                browser.close()
                return 0
            time.sleep(2)
        log.error("Timed out waiting for login. Nothing was saved.")
        browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
