"""Fake Pinterest pages served at https://www.pinterest.com/... via Playwright routing (no network).

Pin search grid (more pins load on scroll), a business account's RX300 pin with comments + a "View 1 reply" button,
a private individual's pin without any comments section, a secret pin, a deleted pin, a login wall and a challenge.
"""
from __future__ import annotations

from urllib.parse import urlsplit

PIN = "/pin/912345678901234567/"
PIN_QUIET = "/pin/lexus-rx300-white--912345678901234568/"
PIN_SECRET = "/pin/912345678901234569/"
PIN_GONE = "/pin/912345678901234570/"
PEOPLE = ["mealea_pins", "Mealea Pins", "rachana_b", "Rachana B", "pin_fan", "sophea_rx"]

REVEAL_JS = """<script>
document.addEventListener('click', e => { const b = e.target.closest('[data-reveal]'); if (!b) return;
  document.querySelectorAll('[data-group="' + b.dataset.reveal + '"]').forEach(x => x.style.display = ''); b.remove(); });
window.addEventListener('scroll', () => { if (window.scrollY > 40) document.querySelectorAll('[data-group="lazy"]').forEach(x => x.style.display = ''); });
</script>"""


def comment(handle, name, text, when="2d", inner="", group=None):
    g = f' data-group="{group}" style="display:none"' if group else ""
    return (f'<div data-test-id="comment"{g}><a href="/{handle}/"><img data-test-id="comment-avatar" width="30" height="30">'
            f'<span data-test-id="comment-author">{name}</span></a><span data-test-id="comment-text">{text}</span>'
            f'<span data-test-id="comment-time">{when}</span>{inner}</div>')


def pin_page(author_handle, author_name, title, desc, comments_html=None, badge=False):
    comments = f'<div data-test-id="comments-list">{comments_html}</div>' if comments_html is not None else ""
    b = '<span data-test-id="business-badge">Business</span>' if badge else ""
    return (f"<!doctype html><html><head><title>{title} | Pinterest</title></head><body><div data-test-id='closeup-body' style='width:600px'>"
            f"<div style='height:200px;background:#eee'></div><h1 data-test-id='pin-title'>{title}</h1>"
            f"<div data-test-id='pin-description'><span>{desc}</span></div>"
            f"<div data-test-id='creator-profile'><a href='/{author_handle}/'><div data-test-id='creator-profile-name'>{author_name}</div></a>{b}</div>"
            f"<div data-test-id='reactions-count'>12</div>{comments}</div>{REVEAL_JS}</body></html>")


PIN_HTML = pin_page("ppautoshop", "PP Auto Shop", "Lexus RX300 2005 for sale", "Clean RX300 in Phnom Penh, family SUV #rx300 #lexus",
                    comment("rachana_b", "Rachana B", "how much for the RX300?", inner=(
                        '<button data-reveal="r1">View 1 reply</button>'
                        + comment("ppautoshop", "PP Auto Shop", "26500$, inbox us", "1d", group="r1")))
                    + comment("pin_fan", "pin_fan", "love this color")
                    + comment("sophea_rx", "sophea_rx", "តម្លៃប៉ុន្មានបង?", "5h", group="lazy") + "<div style='height:1500px'></div>",
                    badge=True)
QUIET_HTML = pin_page("mealea_pins", "Mealea Pins", "White Lexus RX300", "dream car #rx300")
SECRET_HTML = "<!doctype html><html><head><title>Pinterest</title></head><body><main><h2>This Pin is private</h2></main></body></html>"
GONE_HTML = "<!doctype html><html><head><title>Pinterest</title></head><body><main><h2>Sorry, we couldn't find that page</h2></main></body></html>"
LOGIN_HTML = ("<!doctype html><html><head><title>Pinterest</title></head><body><main><h2>Log in to see more</h2>"
              "<input name='id'><input type='password' name='password'></main></body></html>")
CHALLENGE_HTML = "<!doctype html><html><head><title>Pinterest</title></head><body><main><h2>Verify you're human</h2><div>Complete the captcha</div></main></body></html>"


def search_html(links, lazy=()):
    a = "".join(f'<div data-test-id="pin"><a href="{h}"><img alt="pin" width="100" height="100"></a></div>' for h in links)
    b = "".join(f'<div data-test-id="pin" data-group="lazy" style="display:none"><a href="{h}">pin</a></div>' for h in lazy)
    return (f"<!doctype html><html><head><title>rx300 | Pinterest</title></head><body><main>{a}{b}<div style='height:3000px'></div></main>"
            f"{REVEAL_JS}</body></html>")


def install(s, *, mode: str = "normal") -> list[str]:
    """mode: normal | login | challenge."""
    seen: list[str] = []
    pages = {PIN: PIN_HTML, "/pin/912345678901234568/": QUIET_HTML, PIN_QUIET: QUIET_HTML, PIN_SECRET: SECRET_HTML, PIN_GONE: GONE_HTML}

    def handler(route):
        url = route.request.url
        if route.request.resource_type != "document":
            return route.fulfill(status=404, body="")
        seen.append(url)
        path = urlsplit(url).path
        if path.startswith("/search/pins"):
            body = {"login": LOGIN_HTML, "challenge": CHALLENGE_HTML}.get(mode) or search_html(
                [PIN + "?mt=login", PIN_QUIET, PIN_SECRET, PIN_GONE], lazy=["/pin/912345678901234571/"])
        else:
            body = pages.get(path)
        if body is None:
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)

    s.context.route("**/*", lambda route: route.abort())          # nothing ever reaches the real network
    s.context.route("https://*.pinterest.com/**", handler)
    return seen
