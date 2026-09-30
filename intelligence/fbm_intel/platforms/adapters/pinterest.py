"""Pinterest public pins — visible browser session, manual login (optional). SHIPS DISABLED.

- Public content only: public pins (/pin/<id>/). Secret/private pins and deleted pins → skipped with a reason.
- Manual login only: `python -m app.platform_login pinterest` opens a visible window with the persistent profile in
  private/pinterest-profile; you log in yourself. No password handling, no CAPTCHA automation (headed: shown to you
  and waited for; headless: Challenged).
- Discovery: https://www.pinterest.com/search/pins/?q=<q>, scrolled only as far as `max_posts_per_query` needs.
- Collected: canonical https://www.pinterest.com/pin/<id>/, title, description (+ hashtags), displayed date if shown,
  reaction/comment counts if shown, public comments/replies when the pin shows any (most pins have none →
  completeness `comments_unavailable`), screenshots with names/avatars hidden. Pinners/commenters: pseudonymous keys;
  business accounts (badge or business-like name) → Organization.
- Known blockers: Pinterest pins rarely have comments, so this is a low-yield buyer source; logged-out visitors get
  sign-up walls after a few pages. Pinterest's Terms of Service prohibit scraping/automated collection without
  permission — the owner must decide whether to enable this adapter; it is disabled in config. Selectors
  (config/pinterest_adapter_v1.json) were validated only against the local fixture.
"""
from __future__ import annotations

from ..registry import register
from ._social_browser import SocialBrowserAdapter, load_adapter_config

_CFG = load_adapter_config("pinterest")


@register
class PinterestAdapter(SocialBrowserAdapter):
    name = "pinterest"
    platform = "pinterest"
    display_name = "Pinterest (public pins)"
    tier = 2
    adapter_version = _CFG["version"]
    content_type = "pinterest_pin"
    allowed_hosts = frozenset(_CFG["hosts"])
    config_name = "pinterest"
    org_kind = "page"
    login_url = _CFG["login"]["url"]
    login_cookie_url = _CFG["login"]["cookie_url"]
    login_cookies = tuple(_CFG["login"]["cookies"])
