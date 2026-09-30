"""Fake Instagram pages served at https://www.instagram.com/... via Playwright routing (no network).

Hashtag / keyword search grid, a dealer's RX300 post with nested "View replies" threads and a "Load more comments"
button (icon button with an aria-label, like Instagram), a private individual's reel, a private account, an
unavailable post, a login wall and a challenge page.
"""
from __future__ import annotations

from urllib.parse import urlsplit

POST = "/p/RXPOST0001/"
REEL = "/reel/REEL00001/"
PRIVATE = "/p/PRIV00001/"
GONE = "/p/GONE00001/"
# private individuals on the pages (must never be stored)
PEOPLE = ["sokha.buyer", "Sokha Buyer", "vanna.kh", "friend.kh", "dara.private", "Dara Private", "chan.fan", "lina.asks", "late.buyer"]

REVEAL_JS = """<script>
document.addEventListener('click', e => { const b = e.target.closest('[data-reveal]'); if (!b) return;
  document.querySelectorAll('[data-group="' + b.dataset.reveal + '"]').forEach(x => x.style.display = ''); b.remove(); });
</script>"""


def _c(handle, text, cid, when="2d", inner="", name=None, post="RXPOST0001"):
    return (f'<li><div><a href="/{handle}/" role="link"><h3>{name or handle}</h3></a>'
            f'<span dir="auto">{text}</span>'
            f'<a href="/p/{post}/c/{cid}/"><time datetime="2024-09-2{cid[-1]}T08:00:00.000Z">{when}</time></a></div>{inner}</li>')


def _replies(group, items):
    return f'<ul data-group="{group}" style="display:none">{"".join(items)}</ul>'


COMMENTS = "".join([
    _c("sokha.buyer", "តម្លៃប៉ុន្មានបង?", "1790001", name="Sokha Buyer",
       inner='<button data-reveal="r1">View replies (2)</button>' + _replies("r1", [
           _c("ppauto.dealer", "26500$ bong", "1790002", "1d"),
           _c("vanna.kh", '<a href="/friend.kh/">@friend.kh</a> domlai man b?', "1790003", "1d")])),
    _c("chan.fan", "nice car 🔥", "1790004"),
    _c("lina.asks", "how much for the RX300? call 012 345 678", "1790005"),
    # loaded only after "Load more comments"
    '<div data-group="more" style="display:none">' + _c("late.buyer", "can deliver to Siem Reap?", "1790006", "5h") + "</div>",
])

POST_HTML = f"""<!doctype html><html><head><title>PP Auto Dealer on Instagram: "Lexus RX300 2004 for sale"</title></head><body>
<main><article style="width:600px">
 <header><a href="/ppauto.dealer/" role="link"><span>PP Auto Dealer</span></a></header>
 <div style="height:200px;background:#345"></div>
 <section><a href="/p/RXPOST0001/liked_by/"><span>1,234</span> likes</a></section>
 <ul>
  <li><div><a href="/ppauto.dealer/"><h2>ppauto.dealer</h2></a>
   <h1>Lexus RX300 2004 លក់ ភ្នំពេញ full option #rx300 #lexusrx300 #ឡានលក់</h1>
   <time datetime="2024-09-20T08:00:00.000Z">September 20</time></div></li>
  {COMMENTS}
 </ul>
 <button data-reveal="more"><svg aria-label="Load more comments" width="10" height="10"></svg></button>
</article></main>{REVEAL_JS}</body></html>"""

REEL_HTML = """<!doctype html><html><head><title>Dara Private (@dara.private) • Instagram reel</title></head><body>
<main><article style="width:600px">
 <header><a href="/dara.private/" role="link"><span>Dara Private</span></a></header>
 <div style="height:150px;background:#222"></div>
 <ul><li><div><a href="/dara.private/"><h2>dara.private</h2></a><h1>my old Lexus RX300, thinking of selling #rx300</h1>
  <time datetime="2024-09-18T08:00:00.000Z">September 18</time></div></li>
 <li><div><a href="/chan.fan/" role="link"><h3>chan.fan</h3></a><span dir="auto">nice ride</span>
  <a href="/p/REEL00001/c/1800001/"><time datetime="2024-09-19T08:00:00.000Z">1d</time></a></div></li></ul>
</article></main></body></html>"""

PRIVATE_HTML = "<!doctype html><html><head><title>Instagram</title></head><body><main><h2>This account is private</h2><p>Follow this account to see their photos and videos.</p></main></body></html>"
GONE_HTML = "<!doctype html><html><head><title>Page not found • Instagram</title></head><body><main><h2>Sorry, this page isn't available.</h2><p>The link you followed may be broken.</p></main></body></html>"
LOGIN_HTML = ("<!doctype html><html><head><title>Login • Instagram</title></head><body><main><h1>Log in to Instagram</h1>"
              "<form><input name='username'><input type='password' name='password'></form></main></body></html>")
LOGIN_SOFT = "<!doctype html><html><head><title>Instagram</title></head><body><main><p>Sign up to see photos and videos from your friends.</p><a href='/accounts/login/'>Log in</a></main></body></html>"
CHALLENGE_HTML = "<!doctype html><html><head><title>Instagram</title></head><body><main><h2>Help us confirm it's you</h2><p>Enter the code we sent</p></main></body></html>"


def search_html(links, lazy=()):
    a = "".join(f'<div><a href="{h}"><img alt="post" width="100" height="100"></a></div>' for h in links)
    b = "".join(f'<div data-group="lazy" style="display:none"><a href="{h}">post</a></div>' for h in lazy)
    return (f"<!doctype html><html><head><title>#rx300 • Instagram</title></head><body><main>{a}{b}"
            "<div style='height:3000px'></div></main><script>window.addEventListener('scroll', () => { if (window.scrollY > 40) "
            "document.querySelectorAll('[data-group=\"lazy\"]').forEach(x => x.style.display = ''); });</script></body></html>")


def install(s, *, mode: str = "normal") -> list[str]:
    """mode: normal | login | login_soft | challenge. Returns the list of requested document URLs."""
    seen: list[str] = []
    pages = {POST: POST_HTML, REEL: REEL_HTML, "/dara.private" + REEL: REEL_HTML, PRIVATE: PRIVATE_HTML, GONE: GONE_HTML,
             "/accounts/login/": LOGIN_HTML, "/challenge/": CHALLENGE_HTML}

    def handler(route):
        url = route.request.url
        if route.request.resource_type != "document":
            return route.fulfill(status=404, body="")
        seen.append(url)
        path = urlsplit(url).path
        body = None
        if path.startswith("/explore/"):
            body = {"login": LOGIN_HTML, "login_soft": LOGIN_SOFT, "challenge": CHALLENGE_HTML}.get(mode) or search_html(
                [POST + "?utm_source=ig_web_copy_link", "/dara.private" + REEL + "?igsh=abc123", PRIVATE, GONE, POST],
                lazy=["/p/LAZY00001/"])
        else:
            body = pages.get(path)
        if body is None:
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)

    s.context.route("**/*", lambda route: route.abort())          # nothing ever reaches the real network
    s.context.route("https://*.instagram.com/**", handler)
    return seen
