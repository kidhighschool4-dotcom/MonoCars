"""Fake Threads pages served at https://www.threads.com/... via Playwright routing (no network).

Search results, a private individual's RX300 post (handle in the found URL, /t/<code> also served) with replies,
a nested reply thread behind "View more replies" and a reply loaded on scroll, a private profile, an unavailable
post, a login wall and a checkpoint challenge.
"""
from __future__ import annotations

from urllib.parse import urlsplit

CODE = "DQrx300abc1"
POST = f"/@sreymom.rx/post/{CODE}"
PRIVATE = "/@hidden.kh/post/DQpriv0001"
GONE = "/@gone.kh/post/DQgone0001"
PEOPLE = ["sreymom.rx", "Sreymom RX", "bora.buyer", "Bora Buyer", "piseth.q", "friend.kh", "fan.kh", "late.kh"]

REVEAL_JS = """<script>
document.addEventListener('click', e => { const b = e.target.closest('[data-reveal]'); if (!b) return;
  document.querySelectorAll('[data-group="' + b.dataset.reveal + '"]').forEach(x => x.style.display = ''); b.remove(); });
window.addEventListener('scroll', () => { if (window.scrollY > 40) document.querySelectorAll('[data-group="lazy"]').forEach(x => x.style.display = ''); });
</script>"""


def post(handle, name, text, code, when="2d", inner="", group=None):
    g = f' data-group="{group}" style="display:none"' if group else ""
    return (f'<div data-pressable-container="true"{g} style="width:560px;padding:6px">'
            f'<img alt="{name}\'s profile picture" width="36" height="36">'
            f'<a href="/@{handle}"><span>{name}</span></a>'
            f'<a href="/@{handle}/post/{code}"><time datetime="2024-09-2{code[-1]}T08:00:00.000Z">{when}</time></a>'
            f'<div><span dir="auto">{text}</span></div>{inner}</div>')


REPLIES = "".join([
    post("bora.buyer", "Bora Buyer", "តម្លៃប៉ុន្មានបង?", "DQreply0001", inner=(
        '<div role="button" data-reveal="t1">View 2 more replies</div>'
        + post("sreymom.rx", "Sreymom RX", "26500$ bong, inbox", "DQreply0002", "1d", group="t1")
        + post("piseth.q", "piseth.q", '<a href="/@friend.kh">@friend.kh</a> how much for the RX300?', "DQreply0003", "1d", group="t1"))),
    post("fan.kh", "fan.kh", "nice car 🔥", "DQreply0004"),
    post("late.kh", "late.kh", "can deliver to Siem Reap?", "DQreply0005", "5h", group="lazy"),
])

POST_HTML = (f"<!doctype html><html><head><title>Sreymom RX (@sreymom.rx) on Threads</title></head><body><main>"
             + post("sreymom.rx", "Sreymom RX", "Lexus RX300 2004 for sale in Phnom Penh, family SUV #rx300", CODE, "Sep 20")
             + f"<div>{REPLIES}</div><div style='height:1500px'></div></main>{REVEAL_JS}</body></html>")
PRIVATE_HTML = "<!doctype html><html><head><title>Threads</title></head><body><main><h2>This profile is private</h2></main></body></html>"
GONE_HTML = "<!doctype html><html><head><title>Threads</title></head><body><main><h2>Sorry, this page isn't available</h2></main></body></html>"
LOGIN_HTML = ("<!doctype html><html><head><title>Threads</title></head><body><main><h2>Log in or sign up for Threads</h2>"
              "<button>Continue with Instagram</button></main></body></html>")
CHALLENGE_HTML = "<!doctype html><html><head><title>Threads</title></head><body><main><h2>Help us confirm it's you</h2></main></body></html>"


def search_html(links):
    items = "".join(post("someone.kh", "someone", "RX300", h.rsplit("/", 1)[1]).replace(
        f'href="/@someone.kh/post/{h.rsplit("/", 1)[1]}"', f'href="{h}"') for h in links)
    return f"<!doctype html><html><head><title>Threads</title></head><body><main>{items}</main></body></html>"


def install(s, *, mode: str = "normal") -> list[str]:
    """mode: normal | login | challenge."""
    seen: list[str] = []
    pages = {POST: POST_HTML, f"/t/{CODE}": POST_HTML, PRIVATE: PRIVATE_HTML, GONE: GONE_HTML,
             "/t/DQpriv0001": PRIVATE_HTML, "/t/DQgone0001": GONE_HTML,
             "/login": LOGIN_HTML, "/challenge": CHALLENGE_HTML}

    def handler(route):
        url = route.request.url
        if route.request.resource_type != "document":
            return route.fulfill(status=404, body="")
        seen.append(url)
        path = urlsplit(url).path.rstrip("/")
        if path == "/search":
            body = {"login": LOGIN_HTML, "challenge": CHALLENGE_HTML}.get(mode) or search_html([POST + "?xmt=AQG", PRIVATE, GONE])
        else:
            body = pages.get(path)
        if body is None:
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)

    s.context.route("**/*", lambda route: route.abort())          # nothing ever reaches the real network
    s.context.route("https://*.threads.com/**", handler)
    s.context.route("https://*.threads.net/**", handler)
    return seen
