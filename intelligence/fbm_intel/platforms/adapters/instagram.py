"""Instagram public posts and reels — visible browser session, manual login. SHIPS DISABLED.

- Public content only: public posts (/p/<code>/) and reels (/reel/<code>/) of public accounts. Private accounts
  ("This account is private"), unavailable pages ("Sorry, this page isn't available") → skipped with a reason.
- Manual login only: `python -m app.platform_login instagram` opens a visible window with the persistent profile in
  private/instagram-profile; you log in yourself. Nothing here reads or types a password, and CAPTCHAs / "confirm it's
  you" checkpoints are never automated: a headed run shows them to you and waits, a headless run stops (Challenged).
- Discovery: hashtag pages https://www.instagram.com/explore/tags/<tag>/ for the discovery-config hashtags (tags that
  are not valid in URL form, e.g. Khmer-script tags, go to the keyword search page instead) and the keyword search
  page https://www.instagram.com/explore/search/keyword/?q=<q>.
- Collected: canonical URL (handle-free /p/ or /reel/ form), caption (+ hashtags), displayed date (time[datetime]),
  like count if shown, public comments and replies ("View replies" / "Load more comments" expanded within limits),
  displayed comment times, screenshots with names/avatars/handles hidden. Authors/commenters: pseudonymous keys only
  (never names, handles or profile URLs); clearly organizational accounts → Organization.
- Known blockers: Instagram's hashtag/keyword pages and comment lists require a logged-in session; logged-out
  visitors get a login wall (→ LoginRequired). Instagram's Terms of Use restrict automated collection (scraping)
  even of public content — the owner must decide whether to enable this adapter; it is disabled in config.
  Selectors live in config/instagram_adapter_v1.json and were validated only against the local fixture.
"""
from __future__ import annotations

from ..registry import register
from ._social_browser import SocialBrowserAdapter, load_adapter_config

_CFG = load_adapter_config("instagram")

# Live Instagram (2026) renders comments as anonymous <div>s, not ul/li. Every comment has its own permalink
# /p/<code>/c/<id>/ (replies: /c/<id>/r/<rid>/): tag the smallest block around each permalink as the comment, its text
# span (longest dir=auto span that is not a link, button or UI word) and replies. Read-only marks, nothing else changes.
PREMARK_JS = r"""() => {
  if (document.querySelector('article ul li')) return false;   // older list layout: the generic selectors handle it
  const UI = /^(reply|replies|see translation|like|likes|•|·|\d+[smhdwy]|\d+ (like|likes))$/i;
  for (const a of document.querySelectorAll('a[href*="/c/"]')) {
    const href = a.getAttribute('href') || '';
    if (!/\/(p|reel)\/[^/]+\/c\/\d+/.test(href)) continue;
    let e = a;
    while (e.parentElement && e.parentElement.querySelectorAll('a[href*="/c/"]').length === 1 && e.parentElement.tagName !== 'MAIN') e = e.parentElement;
    if (e.hasAttribute('data-fbm-comment')) continue;
    e.setAttribute('data-fbm-comment', '1');
    if (/\/c\/\d+\/r\/\d+/.test(href)) e.setAttribute('data-fbm-reply', '1');
    const spans = Array.from(e.querySelectorAll('span[dir="auto"]'))
      .filter(sp => !sp.closest('a') && !sp.closest('button,[role="button"]') && !UI.test((sp.textContent || '').trim()));
    const best = spans.sort((x, y) => (y.textContent || '').length - (x.textContent || '').length)[0];
    if (best) best.setAttribute('data-fbm-ctext', '1');
  }
  return true;
}"""


@register
class InstagramAdapter(SocialBrowserAdapter):
    name = "instagram"
    platform = "instagram"
    display_name = "Instagram (public posts & reels)"
    tier = 1
    adapter_version = _CFG["version"]
    content_type = "instagram_post"
    allowed_hosts = frozenset(_CFG["hosts"])
    config_name = "instagram"
    org_kind = "page"
    login_url = _CFG["login"]["url"]
    login_cookie_url = _CFG["login"]["cookie_url"]
    login_cookies = tuple(_CFG["login"]["cookies"])
    premark_js = PREMARK_JS
