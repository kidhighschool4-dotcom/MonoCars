"""Threads public posts — visible browser session, manual login. SHIPS DISABLED.

- Public content only: posts of public profiles. Private profiles and unavailable posts → skipped with a reason.
- Manual login only: `python -m app.platform_login threads` opens a visible window with the persistent profile in
  private/threads-profile; you log in yourself (via Instagram). No password handling, no CAPTCHA/checkpoint automation
  (headed: shown to you and waited for; headless: Challenged).
- Discovery: https://www.threads.com/search?q=<q> (threads.net redirects there; both hosts are allowed).
- Collected: canonical https://www.threads.com/t/<code> — handle-free, so no private individual's handle is ever stored
  (the /@handle/post/<code> URL found in search is only used transiently to navigate) — text + hashtags, displayed time,
  like count if shown, public replies on the post page ("View more replies" expanded within limits), reply permalinks
  in /t/<code> form, screenshots with names/avatars/handles hidden. Authors: pseudonymous keys; organizations →
  Organization.
- Known blockers: Threads search and full reply lists require a logged-in session (→ LoginRequired otherwise). Meta's
  terms restrict automated collection of Threads content — the owner must decide whether to enable this adapter; it
  is disabled in config. Threads' markup has almost no stable ids; selectors (config/threads_adapter_v1.json) are
  structure-based and validated only against the local fixture.
"""
from __future__ import annotations

from ..registry import register
from ._social_browser import SocialBrowserAdapter, load_adapter_config

_CFG = load_adapter_config("threads")


@register
class ThreadsAdapter(SocialBrowserAdapter):
    name = "threads"
    platform = "threads"
    display_name = "Threads (public posts)"
    tier = 1
    adapter_version = _CFG["version"]
    content_type = "threads_post"
    allowed_hosts = frozenset(_CFG["hosts"])
    config_name = "threads"
    org_kind = "page"
    login_url = _CFG["login"]["url"]
    login_cookie_url = _CFG["login"]["cookie_url"]
    login_cookies = tuple(_CFG["login"]["cookies"])
