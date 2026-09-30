"""Fake Facebook pages for FacebookPublicPostsAdapter tests.

Served at real https://www.facebook.com/... URLs via Playwright request routing — nothing touches the network.
Markup mirrors what the adapter relies on: role=feed/article, aria-label "Comment by"/"Reply by",
audience icons exposed as <svg><title>, comment permalinks with comment_id / reply_comment_id.
"""
from __future__ import annotations

import html

EXPAND_JS = """<script>
document.addEventListener('click', e => {
  const b = e.target.closest('[data-reveal]');
  if (!b) return;
  document.querySelectorAll('[data-group="' + b.dataset.reveal + '"]').forEach(x => x.style.display = 'block');
  b.remove();
});
</script>"""


def icon(label: str) -> str:
    return f'<span><svg width="12" height="12"><title>{label}</title></svg></span>' if label else ""


def result(href: str, label: str = "", group_text: str = "", body: str = "") -> str:
    return (f'<div role="article"><a href="https://www.facebook.com/someauthor?__cft__[0]=x">Author</a> '
            f'<a href="{href}">2d</a> {icon(label)} <span>{group_text}</span><div dir="auto">{html.escape(body)}</div></div>')


SEARCH = f"""<!doctype html><html><head><title>car sedan - Search results | Facebook</title></head><body>
<div role="main"><div role="feed">
{result("https://web.facebook.com/carshop.pp/posts/pfbid0111?__cft__[0]=AZX&__tn__=%2CO%2CP-R", "Shared with Public", body="2019 Camry sedan for sale $18,500")}
{result("https://www.facebook.com/john.smith/posts/222222222", "Shared with Friends", body="my sedan")}
{result("https://www.facebook.com/groups/555001/posts/333333333/", "", "Private group", "sedan in private group")}
{result("https://www.facebook.com/groups/carskh/posts/444444444/?mibextid=abc", "", "Public group", "Public group sedan post")}
{result("https://www.facebook.com/nobody.here/posts/555555555", "", body="no audience icon shown")}
{result("https://m.facebook.com/carshop.pp/posts/pfbid0111/?mibextid=dup#x", "Shared with Public", body="duplicate w/ tracking")}
{result("https://www.facebook.com/dealer.kh/posts/777777777", "Shared with Public", body="changes on post page")}
</div></div></body></html>"""


def comment(kind: str, text: str, permalink: str | None, author: str | None, time: str = "1d", group: str = "",
            inner: str = "") -> str:
    style = ' style="display:none"' if group else ""
    grp = f' data-group="{group}"' if group else ""
    who = f'<a href="{author}">Visible Name</a>' if author else "<span>Anonymous participant</span>"
    perma = f'<a href="{permalink}">{time}</a>' if permalink else f"<span>{time}</span>"
    label = "Comment by Visible Name" if kind == "comment" else "Reply by Visible Name to Someone's comment"
    return (f'<div role="article" aria-label="{label}"{grp}{style}>{who}<div dir="auto">{html.escape(text)}</div>'
            f"{perma}{inner}</div>")


P = "https://www.facebook.com/carshop.pp/posts/pfbid0111"
POST_111 = f"""<!doctype html><html><head><title>Car Shop PP | Facebook</title></head><body>
<div role="main">
 <div role="article">
  <h2><a href="https://www.facebook.com/carshop.pp?__cft__[0]=Q">Car Shop PP</a></h2>
  <a href="{P}?__cft__[0]=Z">2d</a> {icon("Shared with Public")}
  <div data-ad-preview="message">2019 Toyota Camry sedan for sale in Phnom Penh. $18,500. Full options.</div>
  <div role="button">Most relevant</div>
  <div role="menu"><div role="menuitem" style="display:none">All comments</div></div>
 </div>
 {comment("comment", "Is it still available? I want to buy", P + "?comment_id=C1&__cft__[0]=a",
          "https://www.facebook.com/dara.buyer?comment_id=C1&__cft__[0]=b", "3h",
          inner='<div role="button" data-reveal="r1">View 2 replies</div>'
                + comment("reply", "Yes still available", P + "?comment_id=C1&reply_comment_id=R1",
                          "https://www.facebook.com/carshop.pp", "2h", group="r1")
                + comment("reply", "How much last price?", P + "?comment_id=C1&reply_comment_id=R2",
                          "https://web.facebook.com/profile.php?id=100012345&__tn__=R", "1h", group="r1"))}
 {comment("comment", "តម្លៃប៉ុន្មាន? ខ្ញុំចង់ទិញ", P + "?comment_id=C2", "https://www.facebook.com/people/Sok-Ha/100077788/", "5h")}
 <div role="button" data-reveal="more1">View more comments</div>
 {comment("comment", "Can I see it this weekend?", P + "?comment_id=C3", "https://www.facebook.com/mony.kh", "1d", group="more1")}
 {comment("comment", "Nice car", None, None, "2d", group="more1")}
</div>{EXPAND_JS}</body></html>"""

G = "https://www.facebook.com/groups/carskh/posts/444444444"
POST_444 = f"""<!doctype html><html><head><title>Cars KH | Facebook</title></head><body><div role="main">
 <div role="article"><span>Cars Cambodia · Public group</span>
  <a href="https://www.facebook.com/seller.one">Seller</a> <a href="{G}">1d</a>
  <div data-ad-preview="message">Honda Accord sedan 2018 for sale</div></div>
 {comment("comment", "Interested, inbox me", G + "?comment_id=G1", "https://www.facebook.com/buyer.two", "4h")}
</div></body></html>"""

POST_777 = """<!doctype html><html><head><title>Dealer | Facebook</title></head><body><div role="main">
 <div role="article"><a href="https://www.facebook.com/dealer.kh">Dealer</a>
  <a href="https://www.facebook.com/dealer.kh/posts/777777777">1d</a><span><svg><title>Shared with Friends</title></svg></span>
  <div data-ad-preview="message">Now friends only</div></div></div></body></html>"""

RESTRICTED = """<!doctype html><html><head><title>Facebook</title></head><body>
<h1>You're Temporarily Blocked</h1><p>It looks like you were misusing this feature by going too fast.</p></body></html>"""

SEARCH_BLOCKED = f"""<!doctype html><html><head><title>Search | Facebook</title></head><body><div role="feed">
{result("https://www.facebook.com/fast.poster/posts/888888888", "Shared with Public", body="sedan")}</div></body></html>"""

R = "https://www.facebook.com/realshape.kh/posts/999999999"
POST_REAL_SHAPE = f"""<!doctype html><html><head><title>Real shape | Facebook</title></head><body>
<div role="dialog"><div>Notifications</div><div role="article" aria-label="">unrelated</div></div>
<div role="main"><div>feed behind the dialog</div></div>
<div role="dialog">
  <div><a href="https://www.facebook.com/realshape.kh">Real Shape Auto</a> <a href="{R}?__cft__[0]=q">5h</a>
       <span><svg><title>Shared with Public</title></svg></span></div>
  <div data-ad-comet-preview="message">Lexus RX 2019 for sale</div>
  {comment("comment", "domlai man b", R + "?comment_id=Z1", "https://www.facebook.com/somebody.kh", "1h")}
  {comment("comment", "nice lan b", R + "?comment_id=Z2", "https://www.facebook.com/other.kh", "1h")}
</div></body></html>"""

PAGES = {
    "/realshape.kh/posts/999999999": POST_REAL_SHAPE,
    "/search/posts": SEARCH,
    "/carshop.pp/posts/pfbid0111": POST_111,
    "/groups/carskh/posts/444444444": POST_444,
    "/dealer.kh/posts/777777777": POST_777,
    "/blocked/search/posts": SEARCH_BLOCKED,
    "/fast.poster/posts/888888888": RESTRICTED,
}


def install(context) -> list[str]:
    """Route every facebook.com request to the fixtures above. Returns the list of URLs requested."""
    from urllib.parse import urlsplit

    seen: list[str] = []

    def handler(route):
        url = route.request.url
        seen.append(url)
        path = urlsplit(url).path.rstrip("/") or "/"
        body = PAGES.get(path)
        if route.request.resource_type == "document" and body is not None:
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
        else:
            route.fulfill(status=404, body="")

    context.route("https://*.facebook.com/**", handler)
    return seen
