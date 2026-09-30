"""Fake X pages served at https://x.com/... via Playwright routing (no network).

Live search timeline, a private individual's RX300 status with a conversation below it (a "Show replies" button that
reveals a reply-to-reply thread, and more replies loaded on scroll), a protected account, an unavailable post, a
redirect to /i/flow/login and an Arkose-style challenge.
"""
from __future__ import annotations

from urllib.parse import urlsplit

FOCAL_ID = "1800000000000000001"
POST = f"/rithy_rx/status/{FOCAL_ID}"
DEALER = "/pp_auto_import/status/1800000000000000004"
PROTECTED = "/locked_user/status/1800000000000000002"
GONE = "/gone_user/status/1800000000000000003"
PEOPLE = ["rithy_rx", "Rithy Owner", "buyer_one", "Buyer One", "kanha_q", "Kanha Q", "friend_kh", "fan_kh", "late_kh", "Late Buyer"]

REVEAL_JS = """<script>
document.addEventListener('click', e => { const b = e.target.closest('[data-reveal]'); if (!b) return;
  document.querySelectorAll('[data-group="' + b.dataset.reveal + '"]').forEach(x => x.style.display = ''); b.remove(); });
window.addEventListener('scroll', () => { if (window.scrollY > 40) document.querySelectorAll('[data-group="lazy"]').forEach(x => x.style.display = ''); });
</script>"""


def tweet(handle, name, text, sid, when="2h", focal=False, extra=""):
    return (f'<article data-testid="tweet" tabindex="{-1 if focal else 0}" style="width:560px;padding:8px">'
            f'<div data-testid="Tweet-User-Avatar"><img alt="" width="40" height="40"></div>'
            f'<div data-testid="User-Name"><a href="/{handle}" role="link"><span>{name}</span></a>'
            f'<a href="/{handle}" role="link" tabindex="-1"><span>@{handle}</span></a></div>'
            f'<div data-testid="tweetText" lang="en">{text}</div>'
            f'<a href="/{handle}/status/{sid}"><time datetime="2024-09-20T0{sid[-1]}:00:00.000Z">{when}</time></a>'
            f'<div role="group"><button data-testid="reply"><span>3</span></button><button data-testid="like"><span>45</span></button></div>{extra}</article>')


def cell(inner, group=None, thread_reply=False):
    g = f' data-group="{group}" style="display:none"' if group else ""
    t = ' data-thread-reply="true"' if thread_reply else ""
    return f'<div data-testid="cellInnerDiv"{t}{g}>{inner}</div>'


def status_page(focal_handle, focal_name, focal_text, cells=""):
    return (f"<!doctype html><html><head><title>{focal_name} on X: \"{focal_text[:30]}\" / X</title></head><body><main>"
            f'<section aria-label="Timeline: Conversation">'
            f"{cell(tweet(focal_handle, focal_name, focal_text, FOCAL_ID if focal_handle == 'rithy_rx' else '1800000000000000004', 'Sep 20', focal=True))}"
            f"{cells}<div style='height:1500px'></div></section></main>{REVEAL_JS}</body></html>")


CONVERSATION = "".join([
    cell(tweet("buyer_one", "Buyer One", "តម្លៃប៉ុន្មានបង?", "1800000000000000011")),
    cell('<div role="button" data-reveal="t1"><span>Show replies</span></div>'),
    cell(tweet("rithy_rx", "Rithy Owner", "26500$ negotiable", "1800000000000000012"), group="t1", thread_reply=True),
    cell(tweet("kanha_q", "Kanha Q", '<a href="/friend_kh">@friend_kh</a> how much for the RX300?', "1800000000000000013"), group="t1", thread_reply=True),
    cell(tweet("fan_kh", "Fan", "nice car 🔥", "1800000000000000014")),
    cell(tweet("late_kh", "Late Buyer", "can deliver to Siem Reap?", "1800000000000000015"), group="lazy"),
])

POST_HTML = status_page("rithy_rx", "Rithy Owner", "Selling my Lexus RX300 2003 in Phnom Penh, clean papers #RX300 #lexus", CONVERSATION)
DEALER_HTML = status_page("pp_auto_import", "PP Auto Import", "Lexus RX300 2005 arrived, price on request #rx300")
PROTECTED_HTML = "<!doctype html><html><head><title>X</title></head><body><main><h2>These posts are protected</h2><p>Only approved followers can see them.</p></main></body></html>"
GONE_HTML = "<!doctype html><html><head><title>X</title></head><body><main><span>Hmm...this page doesn't exist. Try searching for something else.</span></main></body></html>"
LOGIN_HTML = ("<!doctype html><html><head><title>Log in to X / X</title></head><body><div role='dialog'><h1>Sign in to X</h1>"
              "<input name='text'><input type='password' name='password'></div></body></html>")
CHALLENGE_HTML = ("<!doctype html><html><head><title>X</title></head><body><main><h1>Authenticate your account</h1>"
                  "<p>Solve this puzzle to verify you are human</p></main></body></html>")


def search_html(links):
    arts = "".join(cell(f'<article data-testid="tweet" tabindex="0"><div data-testid="tweetText">Lexus RX300</div>'
                        f'<a href="{h}"><time datetime="2024-09-20T00:00:00.000Z">1h</time></a></article>') for h in links)
    return f"<!doctype html><html><head><title>RX300 - Search / X</title></head><body><main>{arts}<div style='height:2000px'></div></main></body></html>"


def install(s, *, mode: str = "normal") -> list[str]:
    """mode: normal | login | challenge."""
    seen: list[str] = []
    pages = {POST: POST_HTML, f"/i/status/{FOCAL_ID}": POST_HTML, DEALER: DEALER_HTML, "/i/status/1800000000000000004": DEALER_HTML,
             PROTECTED: PROTECTED_HTML, "/i/status/1800000000000000002": PROTECTED_HTML, GONE: GONE_HTML,
             "/i/status/1800000000000000003": GONE_HTML, "/i/flow/login": LOGIN_HTML, "/account/access": CHALLENGE_HTML}

    def handler(route):
        url = route.request.url
        if route.request.resource_type != "document":
            return route.fulfill(status=404, body="")
        seen.append(url)
        path = urlsplit(url).path.rstrip("/")
        if path == "/search":
            body = {"login": LOGIN_HTML, "challenge": CHALLENGE_HTML}.get(mode) or search_html([POST + "?s=20", DEALER, PROTECTED, GONE, POST + "/photo/1"])
        else:
            body = pages.get(path)
        if body is None:
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)

    s.context.route("**/*", lambda route: route.abort())          # nothing ever reaches the real network
    s.context.route("https://x.com/**", handler)
    s.context.route("https://*.x.com/**", handler)
    return seen
