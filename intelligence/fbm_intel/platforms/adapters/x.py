"""X (Twitter) public posts — visible browser session, manual login. SHIPS DISABLED.

- Public content only: posts of public accounts. Protected accounts ("These posts are protected") and unavailable /
  deleted posts → skipped with a reason.
- Manual login only: `python -m app.platform_login x` opens a visible window with the persistent profile in
  private/x-profile; you log in yourself. Passwords are never read or typed; CAPTCHAs / Arkose puzzles / "verify you
  are human" are never automated (headed: shown to you and waited for; headless: Challenged).
- Discovery: https://x.com/search?q=<q>&f=live (latest), scrolled only until `max_posts_per_query` new posts are seen;
  the checkpoint cursor keeps the newest id seen so the next cycle stops scrolling when it reaches known posts.
- Collected: canonical https://x.com/i/status/<id> (handle-free), text + hashtags, displayed time (time[datetime]),
  like/reply counts if shown, the public replies shown below the focal post on the status page ("Show replies" /
  "Show more replies" expanded within limits), reply permalinks in i/status form, screenshots with names/avatars/
  handles hidden. Authors/repliers: pseudonymous keys derived from the handle path (key only, never stored).
- Known blockers: X search and reply threads require a logged-in session (logged-out → /i/flow/login → LoginRequired);
  X aggressively rate-limits and challenges automated browsing. X's Terms of Service prohibit crawling/scraping
  without prior written consent — the owner must decide whether to enable this adapter; it is disabled in config.
  Replies-to-replies are linked to their parent only through the configurable `reply_marker` selector (unverified
  live); otherwise every reply is stored as a comment on the focal post.
"""
from __future__ import annotations

from ..registry import register
from ._social_browser import SocialBrowserAdapter, load_adapter_config

_CFG = load_adapter_config("x")


@register
class XAdapter(SocialBrowserAdapter):
    name = "x"
    platform = "x"
    display_name = "X (public posts)"
    tier = 1
    adapter_version = _CFG["version"]
    content_type = "x_post"
    allowed_hosts = frozenset(_CFG["hosts"])
    config_name = "x"
    org_kind = "page"
    login_url = _CFG["login"]["url"]
    login_cookie_url = _CFG["login"]["cookie_url"]
    login_cookies = tuple(_CFG["login"]["cookies"])
