"""One-time TikTok login:  python -m app.tiktok_login

Opens a VISIBLE Chromium window with the persistent profile in private/tiktok-profile. You log in yourself
(password, verification, CAPTCHA). Nothing here reads, types or stores your password; the browser profile keeps
the session for later runs. The profile folder is git-ignored and owner-only.
"""
from __future__ import annotations

import logging
import os
import sys
import time

from fbm_intel.browser import open_persistent_session
from fbm_intel.tiktok.adapter import TikTokPublicVideosAdapter
from fbm_intel.tiktok.collector import PROFILE_DIR

log = logging.getLogger("tiktok_login")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(PROFILE_DIR, 0o700)
    hosts = TikTokPublicVideosAdapter.allowed_hosts
    with open_persistent_session(hosts, str(PROFILE_DIR), 0, headless=False) as s:
        s.page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")
        log.info("Log in to TikTok yourself in the window (any verification too). Waiting up to 15 minutes…")
        deadline = time.monotonic() + 15 * 60
        while time.monotonic() < deadline:
            if any(c.get("name") == "sessionid" for c in s.context.cookies("https://www.tiktok.com")):
                s.page.wait_for_timeout(3000)
                log.info("Logged in. Session kept in the private browser profile (values not shown).")
                return 0
            time.sleep(3)
    log.error("Timed out; nothing changed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
