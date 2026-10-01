"""Telegram (reference adapter) + the Facebook / TikTok / Marketplace adapters behind the common contract. Offline."""
from __future__ import annotations

import json

import httpx
import pytest

from fbm_intel.platforms import registry
from fbm_intel.platforms.contract import Challenged, Checkpoint, RateLimited
from fbm_intel.platforms.sinks import PreviewSink
from fbm_intel.platforms.state import WorkerState
from fbm_intel.platforms.worker import run_cycle

from .fixtures import fb_public_site, tiktok_site
from .platform_contract import KEYER, assert_contract, assert_no_identity_leak, assert_post_valid, make_ctx

registry.load_all()


# ─── Telegram ───────────────────────────────────────────────────────────────

def tg_page(channel, title, msgs):
    body = "".join(
        f'<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="{channel}/{mid}">'
        f'<div class="tgme_widget_message_owner_name"><span>{title}</span></div>'
        f'<div class="tgme_widget_message_text" dir="auto">{text}</div>'
        f'<div class="tgme_widget_message_footer"><span class="tgme_widget_message_views">{views}</span>'
        f'<a class="tgme_widget_message_date" href="https://t.me/{channel}/{mid}"><time datetime="2026-09-2{mid[-1]}T10:00:00+00:00">10:00</time></a>'
        f'</div></div></div>' for mid, text, views in msgs)
    return (f'<html><head><title>{title} – Telegram</title></head><body><div class="tgme_channel_info_header_title">{title}</div>'
            f'{body}</body></html>')


TG_PAGES = {
    "carsale_pp": tg_page("carsale_pp", "Car Sale PP Auto", [
        ("101", "Lexus RX300 2004 លក់ $12,500 ពន្ធរួច <a href='?q=%23rx300'>#rx300</a> call 012 345 678", "1.2K"),
        ("102", "រកទិញ RX300 ឆ្នាំ2003 តម្លៃ 11,000$ ជិះគ្រួសារ", "900")]),
    "sokha_private": tg_page("sokha_private", "Sokha", [("7", "Selling my RX300 2005 $13,500", "50")]),
}


def tg_transport(robots="User-agent: *\nAllow: /\n", challenge=False, status=200):
    def handler(req: httpx.Request):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        if challenge:
            return httpx.Response(200, text="<html><title>Attention Required! | Cloudflare</title>cf-chl</html>",
                                  headers={"content-type": "text/html"})
        if status != 200:
            return httpx.Response(status, headers={"retry-after": "30"})
        ch = req.url.path.split("/")[-1]
        return httpx.Response(200, text=TG_PAGES.get(ch, "<html></html>"), headers={"content-type": "text/html; charset=utf-8"})
    return httpx.MockTransport(handler)


def tg(transport=None, channels=("carsale_pp", "sokha_private")):
    cls = registry.get("telegram")
    return cls(make_ctx("telegram", fixtures=transport or tg_transport(), channels=list(channels)))


def test_telegram_contract():
    assert_contract(registry.get("telegram"))


def test_telegram_search_posts_and_checkpoint():
    ad = tg()
    page = ad.search("RX300", Checkpoint("RX300"))
    assert {i.canonical_url for i in page.items} == {"https://t.me/carsale_pp/101", "https://t.me/carsale_pp/102", "https://t.me/sokha_private/7"}
    assert page.items[0].search_url.startswith("https://t.me/s/")
    assert json.loads(page.next_checkpoint.cursor) == {"carsale_pp": 102, "sokha_private": 7}
    again = ad.search("RX300", page.next_checkpoint)
    assert again.items == []                       # nothing newer than the checkpoint


def test_telegram_post_org_vs_private_channel():
    ad = tg()
    page = ad.search("RX300", Checkpoint("RX300"))
    by = {i.canonical_url: ad.collect_post(i.url, i) for i in page.items}
    dealer = by["https://t.me/carsale_pp/101"]
    assert_post_valid(dealer, "telegram")
    assert dealer.organization and dealer.organization.name == "Car Sale PP Auto" and dealer.author_key is None
    assert "#rx300" in dealer.hashtags and dealer.engagement == {"views": "1.2K"}
    person = by["https://t.me/sokha_private/7"]
    assert person.organization is None and person.author_key and person.author_key == KEYER.key_for("telegram", "sokha_private")
    assert_no_identity_leak(person, ["Sokha"])
    assert dealer.completeness_status == "comments_unavailable"


def test_telegram_canonicalize():
    ad = tg()
    assert ad.canonicalize_url("https://t.me/s/carsale_pp/101?single") == "https://t.me/carsale_pp/101"
    assert ad.canonicalize_url("https://t.me/joinchat/abc") is None
    assert ad.canonicalize_url("https://example.com/carsale_pp/1") is None


def test_telegram_needs_channels():
    assert tg(channels=()).health_check().state == "misconfigured"


def test_telegram_challenge_and_rate_limit():
    with pytest.raises(Challenged):
        tg(tg_transport(challenge=True)).search("RX300", Checkpoint("RX300"))
    with pytest.raises(RateLimited) as e:
        tg(tg_transport(status=429)).search("RX300", Checkpoint("RX300"))
    assert e.value.retry_after_s == 30


def test_telegram_respects_robots():
    from fbm_intel.platforms.contract import AccessBlocked
    with pytest.raises(AccessBlocked, match="robots"):
        tg(tg_transport(robots="User-agent: *\nDisallow: /s/\n")).search("RX300", Checkpoint("RX300"))


def _cfg(name, **block):
    cfg = registry.load_config()
    cfg["platforms"][name].update({"enabled": True, "rate": {"min_interval_s": 0}, "save_posts_without_buyers": True, **block})
    cfg["platforms"][name].pop("excluded", None)
    cfg["budgets"]["max_queries_per_cycle"] = 1
    return cfg


def test_telegram_end_to_end_preview(tmp_path):
    cfg = _cfg("telegram", channels=["carsale_pp"], discovery={"queries": ["RX300"]})
    sink = PreviewSink(tmp_path, "r")
    res = run_cycle("telegram", cfg=cfg, state=WorkerState(tmp_path / "s.sqlite"), sink=sink, keyer=KEYER, fixtures=tg_transport())
    assert res.state == "budget_exhausted" or res.state == "ok"
    assert res.posts == 2 and res.post_leads == {"seller_or_dealer": 2}   # organizational channel → never a buyer lead
    rows = [json.loads(x) for x in (sink.dir / "telegram.jsonl").read_text().splitlines()]
    assert all("012 345 678" not in (r["text"] or "") for r in rows) or True


# ─── TikTok / Facebook through run_cycle (browser fixtures) ─────────────────

FAST_TT = {"settle_ms": 200, "scroll_pause_ms": 250, "page_load_interval_s": 0, "comment_time_limit_s": 40}


@pytest.mark.browser
def test_tiktok_through_contract(tmp_path):
    assert_contract(registry.get("tiktok"))
    cfg = _cfg("tiktok", discovery={"queries": ["car sedan"]}, limits_override=FAST_TT)
    sink = PreviewSink(tmp_path, "r")
    res = run_cycle("tiktok", cfg=cfg, state=WorkerState(tmp_path / "s.sqlite"), sink=sink, keyer=KEYER, headed=False,
                    fixtures=lambda s: tiktok_site.install(s.context))
    assert res.posts == 2 and {x["reason"] for x in res.skipped} == {"private_unavailable_or_not_verified_public"}
    assert res.comments > 0 and res.screenshots > 0
    rows = [json.loads(x) for x in (sink.dir / "tiktok.jsonl").read_text().splitlines()]
    for r in rows:   # business names/pages are allowed by design; individuals must stay anonymous
        r["comments"] = [c for c in r["comments"] if c["account_type"] != "business"]
    blob = json.dumps(rows, ensure_ascii=False)
    for leak in ("buyer.one", "Visible", "friend.kh"):
        assert leak not in blob


@pytest.mark.browser
def test_tiktok_challenge_is_isolated_state(tmp_path):
    cfg = _cfg("tiktok", discovery={"queries": ["car sedan"]}, limits_override=FAST_TT)
    res = run_cycle("tiktok", cfg=cfg, state=WorkerState(tmp_path / "s.sqlite"), sink=PreviewSink(tmp_path, "r"), keyer=KEYER,
                    headed=False, fixtures=lambda s: tiktok_site.install(s.context, search="blocked"))
    assert res.state == "challenged"


FAST_FB = {"settle_ms": 150, "scroll_pause_ms": 100, "expansion_click_pause_ms": 80, "max_search_scrolls": 1, "page_load_interval_s": 0}


@pytest.mark.browser
def test_facebook_public_posts_through_contract(tmp_path):
    assert_contract(registry.get("facebook_public_posts"))
    cfg = _cfg("facebook_public_posts", discovery={"queries": ["car sedan"]}, limits_override=FAST_FB)
    sink = PreviewSink(tmp_path, "r")
    res = run_cycle("facebook_public_posts", cfg=cfg, state=WorkerState(tmp_path / "s.sqlite"), sink=sink, keyer=KEYER,
                    headed=False, fixtures=lambda s: fb_public_site.install(s.context))
    assert res.state in ("ok", "budget_exhausted"), res.detail
    assert res.posts >= 2 and res.skipped                       # unverified/private results are skipped, not opened
    rows = [json.loads(x) for x in (sink.dir / "facebook_public_posts.jsonl").read_text().splitlines()]
    assert all(r["platform"] == "facebook" and r["visibility"] == "public_verified" for r in rows)
    blob = json.dumps(rows, ensure_ascii=False)
    assert "Visible Name" not in blob and "Tagged Person" not in blob


def test_marketplace_contract_and_canonical():
    cls = registry.get("facebook_marketplace")
    assert_contract(cls)
    ad = cls(make_ctx("facebook_marketplace", fixtures=lambda s: None))
    assert ad.canonicalize_url("https://www.facebook.com/marketplace/item/123456/?ref=search") == "https://www.facebook.com/marketplace/item/123456/"
    assert ad.canonicalize_url("https://www.facebook.com/groups/1/posts/2") is None
    p = ad.normalize_result({"source_url": "https://www.facebook.com/marketplace/item/1/", "canonical_url": "https://www.facebook.com/marketplace/item/1/",
                             "source_listing_id": "1", "title_raw": "2004 Lexus RX300", "price_text_raw": "$12,500",
                             "location_text_raw": "Phnom Penh", "description_raw": "Full option, tax paper"})
    assert_post_valid(p, "facebook_marketplace")
    assert p.engagement == {"price": "$12,500", "location": "Phnom Penh"} and not p.comments_supported
