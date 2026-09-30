"""Public-web adapters: khmer24, kh_classifieds, forums, web_sites, search_engine (MockTransport only — no network).

Fixtures under tests/fixtures/platform_web are hand-authored in the structure of the live pages (names / phones are
invented); nothing personal from the live check was saved.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from fbm_intel.platforms import registry
from fbm_intel.platforms.adapters.forums import ForumsAdapter
from fbm_intel.platforms.adapters.kh_classifieds import KhClassifiedsAdapter, clean_text
from fbm_intel.platforms.adapters.khmer24 import Khmer24Adapter
from fbm_intel.platforms.adapters.search_engine import SearchEngineAdapter
from fbm_intel.platforms.adapters.web_sites import WebSitesAdapter
from fbm_intel.platforms.contract import AccessBlocked, Challenged, Checkpoint
from fbm_intel.platforms.sinks import PreviewSink, post_record
from fbm_intel.platforms.state import WorkerState
from fbm_intel.platforms.worker import run_cycle

from .platform_contract import KEYER, assert_contract, assert_no_identity_leak, assert_post_valid, make_ctx

FX = Path(__file__).parent / "fixtures" / "platform_web"
FAST = {"rate": {"min_interval_s": 0}}
HTML = "text/html; charset=utf-8"
JSON = "application/json"
K24_PHONES = ["012345678", "012 345 678", "098765432", "0977778888", "097 777 8888", "077952108", "០៧៧ ៩៥២ ១០៨", "016111222"]


def fx(rel: str) -> str:
    return (FX / rel).read_text(encoding="utf-8")


class Router:
    """httpx.MockTransport over a route table {(host, path): body | (status, body, ctype) | callable(request)}."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        r = self.routes.get((req.url.host, req.url.path))
        if callable(r):
            r = r(req)
        if r is None:
            return httpx.Response(404, text="not found", headers={"content-type": "text/plain"})
        if isinstance(r, str):
            ctype = JSON if req.url.path.endswith(".json") else "text/plain" if req.url.path.endswith(".txt") else HTML
            return httpx.Response(200, text=r, headers={"content-type": ctype})
        status, body, ctype = r
        return httpx.Response(status, text=body, headers={"content-type": ctype})

    def paths(self) -> list[str]:
        return [str(r.url) for r in self.requests]


# ─── contract ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", [Khmer24Adapter, KhClassifiedsAdapter, ForumsAdapter, WebSitesAdapter, SearchEngineAdapter])
def test_contract(cls):
    assert_contract(cls)
    assert registry.get(cls.name) is cls


def test_all_disabled_by_default():
    cfg = registry.load_config()
    for n in ("khmer24", "kh_classifieds", "forums", "search_engine", "web_sites"):
        assert cfg["platforms"][n]["enabled"] is False


# ─── Khmer24 ────────────────────────────────────────────────────────────────

def k24_category(req: httpx.Request):
    q = parse_qs(req.url.query.decode())
    return fx("khmer24/category_empty.html") if q.get("page", ["1"])[0] != "1" else fx("khmer24/category.html")


def k24_routes(over: dict | None = None) -> Router:
    routes = {("www.khmer24.com", "/robots.txt"): fx("khmer24/robots.txt"),
              ("www.khmer24.com", "/c-cars-for-sale"): k24_category}
    for i in ("90000001", "90000002", "90000003", "90000004"):
        routes[("www.khmer24.com", f"/post-adid-{i}")] = fx(f"khmer24/ad_{i}.html")
    routes.update(over or {})
    return Router(routes)


def k24(router: Router, **cfg) -> Khmer24Adapter:
    return Khmer24Adapter(make_ctx("khmer24", fixtures=router.transport, **FAST, **cfg))


def test_khmer24_search_uses_category_filter_and_cursor():
    r = k24_routes()
    a = k24(r)
    page = a.search("Lexus RX300", Checkpoint(query="Lexus RX300"))
    assert [i.source_id for i in page.items] == ["90000001", "90000002", "90000003", "90000004"]   # promoted RX450h card ignored
    assert all(i.canonical_url.startswith("https://www.khmer24.com/post-adid-") for i in page.items)
    assert page.items[0].search_url == "https://www.khmer24.com/c-cars-for-sale?ad_field=lexus&ad_model=rx300"
    assert "/search" not in " ".join(r.paths())                                                    # robots-disallowed internal search never used
    cur = json.loads(page.next_checkpoint.cursor)
    assert cur == {"page": 2, "max_id": 90000004} and a.get_next_checkpoint() is page.next_checkpoint
    page2 = a.search("Lexus RX300", page.next_checkpoint)
    assert "page=2" in r.paths()[-1] and page2.exhausted and json.loads(page2.next_checkpoint.cursor)["page"] == 1


def test_khmer24_unmapped_query_filters_locally():
    r = k24_routes()
    page = k24(r).search("Toyota Prius", Checkpoint(query="Toyota Prius"))
    assert page.items == [] and r.paths()[-1] == "https://www.khmer24.com/c-cars-for-sale"


@pytest.mark.parametrize("url,expected", [
    ("https://www.khmer24.com/km/lexus-rx300-for-sale-adid-12334199", "https://www.khmer24.com/post-adid-12334199"),
    ("https://m.khmer24.com/en/lexus-rx300--lpg--adid-12011790?utm_source=fb", "https://www.khmer24.com/post-adid-12011790"),
    ("https://www.khmer24.com/post-adid-14067970", "https://www.khmer24.com/post-adid-14067970"),
    ("https://www.khmer24.com/c-cars-for-sale", None),
    ("https://t.me/carscambodia/1", None),
])
def test_khmer24_canonicalize(url, expected):
    assert k24(k24_routes()).canonicalize_url(url) == expected


def test_khmer24_dealer_is_organization_and_phones_not_stored():
    a = k24(k24_routes())
    post = a.collect_post("https://www.khmer24.com/km/lexus-rx300-adid-90000001")
    assert_post_valid(post, "classifieds")
    assert post.source_content_type == "classified_listing" and post.completeness_status == "comments_unavailable"
    assert post.organization and post.organization.kind == "dealer" and post.author_key is None
    assert "Price: $12,500" in post.post_text and "Year: 2004" in post.post_text and "Tuol Kouk" in post.post_text
    assert post.published_text_displayed == "2026-09-29 10:15:00" and post.published_at_observed.year == 2026
    blob = json.dumps(post_record(post), ensure_ascii=False, default=str)
    assert "[phone]" not in post.post_text and "ទំនាក់ទំនង" in post.post_text     # contact dropped from listing text
    for p in K24_PHONES:
        assert p not in blob, p
    assert "telephone" not in blob and a.collect_comments(post).completeness == "comments_unavailable"
    assert a.capture_evidence(post) is None


def test_khmer24_company_account_is_organization():
    post = k24(k24_routes()).collect_post("https://www.khmer24.com/post-adid-90000004")
    assert post.organization and post.organization.name == "Bopha Rith Showcase"
    assert "company" in post.organization.evidence


def test_khmer24_individual_seller_keyed_only():
    a = k24(k24_routes())
    wanted = a.collect_post("https://www.khmer24.com/post-adid-90000002")
    assert wanted.organization is None and wanted.author_key == KEYER.key_for("khmer24", "777")
    assert wanted.engagement["listing"]["listing_kind"] == "wanted"
    assert "$" not in (wanted.post_text or "")                       # a wanted ad's budget stays out of the text
    assert_no_identity_leak(wanted, ["Dara Chan", "darachan123", "khmer24.com/km/", "0977778888", "097 777 8888"])
    offer = a.collect_post("https://www.khmer24.com/post-adid-90000003")
    assert offer.organization is None and offer.author_key and offer.engagement["listing"]["listing_kind"] == "offer"
    assert "០៧៧" not in offer.post_text and "077" not in offer.post_text    # Khmer-digit phone removed
    assert_no_identity_leak(offer, ["Sophea Kim", "sopheakim61", "077952108"])


def test_khmer24_robots_disallow_blocks():
    r = k24_routes({("www.khmer24.com", "/robots.txt"): "User-agent: *\nDisallow: /c-cars-for-sale\n"})
    with pytest.raises(AccessBlocked, match="robots"):
        k24(r).search("Lexus RX300", Checkpoint(query="Lexus RX300"))
    assert not any("/c-cars-for-sale" in u for u in r.paths())


def test_khmer24_challenge_page():
    r = k24_routes({("www.khmer24.com", "/c-cars-for-sale"): (403, fx("challenge.html"), HTML)})
    with pytest.raises(Challenged):
        k24(r).search("Lexus RX300", Checkpoint(query="Lexus RX300"))


def test_khmer24_end_to_end_cycle_types_leads(tmp_path):
    cfg = registry.load_config()
    cfg["platforms"]["khmer24"].update(enabled=True, rate={"min_interval_s": 0}, discovery={"queries": ["Lexus RX300"]})
    sink = PreviewSink(tmp_path, "r")
    res = run_cycle("khmer24", cfg=cfg, state=WorkerState(tmp_path / "s.sqlite"), sink=sink, keyer=KEYER,
                    fixtures=k24_routes().transport)
    assert res.state == "ok", res.detail
    assert res.posts == 4 and res.organizations == 2
    rows = {r["source_post_id"]: r for r in map(json.loads, (sink.dir / "khmer24.jsonl").read_text().splitlines())}
    assert rows["90000002"]["lead"]["lead_type"] == "confirmed_rx300_buyer"
    assert rows["90000001"]["lead"]["lead_type"] == "seller_or_dealer"
    assert rows["90000004"]["lead"]["lead_type"] == "seller_or_dealer"
    assert rows["90000003"]["lead"]["lead_type"] == "seller_or_dealer"
    assert res.post_leads == {"confirmed_rx300_buyer": 1, "seller_or_dealer": 3}
    raw = (sink.dir / "khmer24.jsonl").read_text()
    for s in ["Dara Chan", "darachan123", "Sophea Kim", *K24_PHONES]:
        assert s not in raw, s


# ─── kh_classifieds ─────────────────────────────────────────────────────────

CLASSIFIED_SITE = json.loads((Path(__file__).parents[1] / "config" / "sites_v1.json").read_text())["classifieds"][0]


def kh_ctx(router=None, sites=None):
    return make_ctx("kh_classifieds", fixtures=router.transport if router else None, **FAST,
                    sites=sites if sites is not None else [{**CLASSIFIED_SITE, "enabled": True}])


def kh_routes(over: dict | None = None):
    routes = {("classifieds.example.com", "/robots.txt"): "User-agent: *\nDisallow: /user/\n",
              ("classifieds.example.com", "/cars"): fx("classifieds/search.html"),
              ("classifieds.example.com", "/ad/501"): fx("classifieds/ad_501.html"),
              ("classifieds.example.com", "/ad/502"): fx("classifieds/ad_502.html")}
    routes.update(over or {})
    return Router(routes)


def test_kh_classifieds_empty_config_is_misconfigured():
    a = KhClassifiedsAdapter(make_ctx("kh_classifieds"))
    h = a.health_check()
    assert h.state == "misconfigured" and "no classifieds sites configured" in h.detail


def test_kh_classifieds_search_and_listings():
    r = kh_routes()
    a = KhClassifiedsAdapter(kh_ctx(r))
    assert a.health_check().ok and a.allowed_hosts == frozenset({"classifieds.example.com"})
    page = a.search("Lexus RX300", Checkpoint(query="Lexus RX300"))
    assert [i.canonical_url for i in page.items] == ["https://classifieds.example.com/ad/501", "https://classifieds.example.com/ad/502"]
    assert json.loads(page.next_checkpoint.cursor) == {"example-classifieds": {"page": 2}}
    shop = a.collect_post(page.items[0].url, page.items[0])
    assert_post_valid(shop, "classifieds")
    assert shop.organization and "badge-shop" in shop.organization.evidence and shop.author_key is None
    assert "Price: $13,200" in shop.post_text and "012 999 000" not in shop.post_text
    buyer = a.collect_post(page.items[1].url, page.items[1])
    assert buyer.organization is None and buyer.author_key == KEYER.key_for("classifieds:classifieds.example.com", "chanthy_s")
    assert buyer.engagement["listing"]["listing_kind"] == "wanted" and buyer.published_at_observed.day == 29
    assert_no_identity_leak(buyer, ["Chanthy Sok", "chanthy_s", "088 123 4567"])


def test_kh_classifieds_robots_and_challenge():
    r = kh_routes({("classifieds.example.com", "/robots.txt"): "User-agent: *\nDisallow: /cars\n"})
    with pytest.raises(AccessBlocked):
        KhClassifiedsAdapter(kh_ctx(r)).search("rx300", Checkpoint(query="rx300"))
    r = kh_routes({("classifieds.example.com", "/cars"): (200, fx("challenge.html"), HTML)})
    with pytest.raises(Challenged):
        KhClassifiedsAdapter(kh_ctx(r)).search("rx300", Checkpoint(query="rx300"))


# ─── forums ─────────────────────────────────────────────────────────────────

DISCOURSE = {"name": "kh-forum", "type": "discourse", "base_url": "https://forum.example.com"}
HTML_FORUM = json.loads((Path(__file__).parents[1] / "config" / "sites_v1.json").read_text())["forums"][1]


def forum_routes(over: dict | None = None):
    routes = {("forum.example.com", "/robots.txt"): fx("forums/discourse_robots.txt"),
              ("forum.example.com", "/latest.json"): fx("forums/discourse_latest.json"),
              ("forum.example.com", "/t/123.json"): fx("forums/discourse_topic_123.json"),
              ("forum.example.com", "/t/123/posts.json"): fx("forums/discourse_posts_more.json"),
              ("forum2.example.com", "/search.json"): fx("forums/discourse_search.json"),
              ("board.example.com", "/search.php"): fx("forums/html_search.html"),
              ("board.example.com", "/viewtopic.php"): lambda req: fx("forums/html_thread_55.html")
              if parse_qs(req.url.query.decode()).get("t") == ["55"] else None}
    routes.update(over or {})
    return Router(routes)


def test_forums_empty_config_is_misconfigured():
    h = ForumsAdapter(make_ctx("forums")).health_check()
    assert h.state == "misconfigured" and "no forums configured" in h.detail


def test_discourse_robots_fallback_thread_and_replies():
    r = forum_routes()
    a = ForumsAdapter(make_ctx("forums", fixtures=r.transport, **FAST, sites=[DISCOURSE]))
    assert a.health_check().ok
    page = a.search("Lexus RX300", Checkpoint(query="Lexus RX300"))
    assert not any("/search" in u for u in r.paths())                    # robots.txt disallows /search → listing JSON
    assert [i.canonical_url for i in page.items] == ["https://forum.example.com/t/looking-for-lexus-rx300-in-phnom-penh/123"]
    assert page.items[0].search_url == "https://forum.example.com/latest.json"
    post = a.collect_post(page.items[0].url, page.items[0])
    assert post.source_content_type == "forum_thread" and post.engagement["views"] == 88
    batch = a.collect_comments(post)
    post.comments = batch.comments
    assert_post_valid(post, "forum")
    assert batch.completeness == "complete" and len(post.comments) == 4
    assert any("post_ids[]=1005" in u for u in r.paths())                 # rest of the stream via the posts endpoint
    by_id = {c.source_comment_id: c for c in post.comments}
    thanks, reply = by_id["forum.example.com:1003"], by_id["forum.example.com:1005"]
    assert thanks.comment_type == "reply" and thanks.parent_fingerprint == by_id["forum.example.com:1002"].fingerprint
    assert thanks.is_post_author and not by_id["forum.example.com:1004"].is_post_author
    assert reply.parent_fingerprint == by_id["forum.example.com:1004"].fingerprint and "ចង់ទិញ" not in reply.comment_text
    assert thanks.canonical_comment_url.endswith("/123/3")
    assert "012 888 999" not in post.post_text
    assert_no_identity_leak(post, ["vannak_pp", "rithy_cars", "sreymom88", "Vannak_Pp", "Sreymom88"])


def test_discourse_search_json_when_robots_allows():
    r = forum_routes()
    a = ForumsAdapter(make_ctx("forums", fixtures=r.transport, **FAST,
                               sites=[{**DISCOURSE, "name": "f2", "base_url": "https://forum2.example.com"}]))
    page = a.search("Lexus RX300", Checkpoint(query="Lexus RX300"))
    assert page.items and page.items[0].search_url.startswith("https://forum2.example.com/search.json?q=Lexus+RX300")
    assert json.loads(page.next_checkpoint.cursor) == {"f2": {"page": 2}}


def test_html_forum_thread_comments():
    r = forum_routes()
    a = ForumsAdapter(make_ctx("forums", fixtures=r.transport, **FAST, sites=[{**HTML_FORUM, "enabled": True}]))
    page = a.search("rx300", Checkpoint(query="rx300"))
    assert [i.canonical_url for i in page.items] == ["https://board.example.com/viewtopic.php?t=55",
                                                     "https://board.example.com/viewtopic.php?t=56"]
    post = a.collect_post(page.items[0].url, page.items[0])
    post.comments = a.collect_comments(post).comments
    assert_post_valid(post, "forum")
    assert "[phone]" in post.post_text and len(post.comments) == 2
    assert post.comments[1].is_post_author and not post.comments[0].is_post_author
    assert_no_identity_leak(post, ["kosal_driver", "mony_k"])


def test_forum_robots_disallow_and_challenge():
    r = forum_routes({("forum.example.com", "/robots.txt"): "User-agent: *\nDisallow: /\n"})
    with pytest.raises(AccessBlocked):
        ForumsAdapter(make_ctx("forums", fixtures=r.transport, **FAST, sites=[DISCOURSE])).search("rx300", Checkpoint(query="rx300"))
    r = forum_routes({("board.example.com", "/search.php"): (503, fx("challenge.html"), HTML)})
    with pytest.raises(Challenged):
        ForumsAdapter(make_ctx("forums", fixtures=r.transport, **FAST, sites=[{**HTML_FORUM, "enabled": True}])).search(
            "rx300", Checkpoint(query="rx300"))


# ─── web_sites ──────────────────────────────────────────────────────────────

WEB = json.loads((Path(__file__).parents[1] / "config" / "sites_v1.json").read_text())["web_sites"]


def web_routes(over: dict | None = None):
    routes = {("dealer.example.com", "/inventory"): fx("web_sites/dealer_inventory.html"),
              ("dealer.example.com", "/inventory/lexus-rx300-2004"): fx("web_sites/dealer_rx300.html"),
              ("blog.example.com", "/robots.txt"): "User-agent: *\nDisallow: /wp-admin/\n",
              ("blog.example.com", "/"): fx("web_sites/blog_search.html"),
              ("blog.example.com", "/2026/09/rx300-family-review/"): fx("web_sites/blog_post.html")}
    routes.update(over or {})
    return Router(routes)


def test_web_sites_empty_config_is_misconfigured():
    h = WebSitesAdapter(make_ctx("web_sites")).health_check()
    assert h.state == "misconfigured" and "no web sites configured" in h.detail


def test_dealer_site_is_organization():
    r = web_routes()
    a = WebSitesAdapter(make_ctx("web_sites", fixtures=r.transport, **FAST, sites=[{**WEB[0], "enabled": True}]))
    page = a.search("Lexus RX300", Checkpoint(query="Lexus RX300"))
    assert [i.canonical_url for i in page.items] == ["https://dealer.example.com/inventory/lexus-rx300-2004"]  # Prius filtered out
    post = a.collect_post(page.items[0].url, page.items[0])
    assert_post_valid(post, "web")
    assert post.organization.kind == "dealer" and post.organization.name == "Example Dealer"
    assert "023 456 789" not in post.post_text and not post.comments_supported
    assert a.collect_comments(post).completeness == "comments_unavailable"


def test_blog_comments_threaded_and_keyed():
    r = web_routes()
    a = WebSitesAdapter(make_ctx("web_sites", fixtures=r.transport, **FAST, sites=[{**WEB[1], "enabled": True}]))
    page = a.search("rx300", Checkpoint(query="rx300"))
    assert page.items[0].search_url == "https://blog.example.com/?s=rx300&paged=1"
    post = a.collect_post(page.items[0].url, page.items[0])
    assert post.organization is None and post.author_key
    assert "ចង់ទិញ" not in post.post_text                            # comments are not part of the page body
    post.comments = a.collect_comments(post).comments
    assert_post_valid(post, "web")
    c11, c12, c13 = post.comments
    assert c12.comment_type == "reply" and c12.parent_fingerprint == c11.fingerprint and c12.is_post_author
    assert c11.source_comment_id == "web:blog.example.com:comment-11" and "[phone]" in c11.comment_text
    assert "Around" not in c11.comment_text                           # reply text not folded into its parent
    assert c13.comment_type == "comment" and not c13.is_post_author
    assert_no_identity_leak(post, ["Piseth Long", "Blogger Neary", "Chenda", "010 222 333"])


def test_web_sites_robots_disallow():
    r = web_routes({("blog.example.com", "/robots.txt"): "User-agent: *\nDisallow: /\n"})
    with pytest.raises(AccessBlocked):
        WebSitesAdapter(make_ctx("web_sites", fixtures=r.transport, **FAST, sites=[{**WEB[1], "enabled": True}])).search(
            "rx300", Checkpoint(query="rx300"))


# ─── search_engine ──────────────────────────────────────────────────────────

@pytest.fixture
def no_search_env(monkeypatch):
    for k in ("GOOGLE_CSE_KEY", "GOOGLE_CSE_CX", "BRAVE_SEARCH_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_search_engine_misconfigured_without_keys(no_search_env):
    a = SearchEngineAdapter(make_ctx("search_engine"))
    h = a.health_check()
    assert h.state == "misconfigured" and h.detail == "missing: GOOGLE_CSE_KEY, GOOGLE_CSE_CX (or BRAVE_SEARCH_API_KEY)"
    assert a.missing_env() and SearchEngineAdapter.access == "official_api" and SearchEngineAdapter.respect_robots is False


def se_routes():
    return Router({("www.googleapis.com", "/customsearch/v1"): fx("search_engine/google.json"),
                   ("api.search.brave.com", "/res/v1/web/search"): lambda req: fx("search_engine/brave.json")
                   if req.headers.get("X-Subscription-Token") == "brave-secret" else (401, "{}", JSON)})


def test_google_search_routes_and_hides_key(no_search_env, monkeypatch):
    monkeypatch.setenv("GOOGLE_CSE_KEY", "g-secret-key")
    monkeypatch.setenv("GOOGLE_CSE_CX", "cx-secret")
    r = se_routes()
    a = SearchEngineAdapter(make_ctx("search_engine", fixtures=r.transport, **FAST))
    assert a.health_check().ok and a.missing_env() == []
    page = a.search("Lexus RX300", Checkpoint(query="Lexus RX300"))
    assert "g-secret-key" in r.paths()[0]                             # the API itself receives the key…
    assert all(i.search_url and "g-secret-key" not in i.search_url and "cx-secret" not in i.search_url for i in page.items)
    assert not any("robots.txt" in u for u in r.paths())               # official API: no robots fetch
    routed = {i.canonical_url: i.preview["routed_to"] for i in page.items}
    assert routed == {"https://www.khmer24.com/post-adid-12334199": "khmer24", "https://t.me/carscambodia/4521": "telegram",
                      "https://someblog.example.org/rx300": None}
    assert json.loads(page.next_checkpoint.cursor) == {"engine": "google", "offset": 10}
    n_requests = len(r.requests)
    posts = [a.collect_post(i.url, i) for i in page.items]
    assert len(r.requests) == n_requests                               # collect_post never fetches the result URL
    for p in posts:
        assert_post_valid(p, "web")
        assert p.visibility_evidence == "listed in public search results" and "g-secret-key" not in (p.search_url or "")
    assert posts[0].engagement == {"routed_to": "khmer24"} and posts[1].engagement == {"routed_to": "telegram"}
    assert posts[2].engagement == {"routed_to": None}
    assert "012 345 678" not in posts[0].post_text


def test_brave_search_key_in_header_only(no_search_env, monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-secret")
    r = se_routes()
    a = SearchEngineAdapter(make_ctx("search_engine", fixtures=r.transport, **FAST))
    page = a.search("rx300", Checkpoint(query="rx300"))
    assert [i.preview["routed_to"] for i in page.items] == ["telegram"]
    assert "brave-secret" not in page.items[0].search_url and "brave-secret" not in r.paths()[0]
    post = a.collect_post(page.items[0].url, page.items[0])
    assert post.engagement == {"routed_to": "telegram"} and post.published_at_observed is not None


def test_clean_text_redacts_khmer_digit_phones():
    assert clean_text("ទូរស័ព្ទ ០១២ ៣៤៥ ៦៧៨") == "ទូរស័ព្ទ [phone]"
    assert clean_text("Call 012 345 678, thanks", drop_contacts=True) == "Call, thanks"
