"""Instagram / X / Threads / Pinterest browser-session adapters against local fake sites (Playwright routes, no network)."""
from __future__ import annotations

import json
from functools import partial

import pytest

from fbm_intel.platforms import registry
from fbm_intel.platforms.contract import Challenged, Checkpoint, LoginRequired
from fbm_intel.platforms.sinks import PreviewSink
from fbm_intel.platforms.state import WorkerState
from fbm_intel.platforms.worker import run_cycle

from .fixtures import instagram_site, pinterest_site, threads_site, x_site
from .platform_contract import KEYER, assert_contract, assert_no_identity_leak, assert_post_valid, make_ctx

FAST = {"settle_ms": 50, "scroll_pause_ms": 150, "click_pause_ms": 80, "comment_time_limit_s": 30}

SPECS = {
    "instagram": dict(
        site=instagram_site, query="#rx300", post="https://www.instagram.com/p/RXPOST0001/",
        results={"https://www.instagram.com/p/RXPOST0001/", "https://www.instagram.com/reel/REEL00001/",
                 "https://www.instagram.com/p/PRIV00001/", "https://www.instagram.com/p/GONE00001/"},
        lazy="https://www.instagram.com/p/LAZY00001/",
        buyer="តម្លៃប៉ុន្មានបង?", replies={"26500$ bong", "[mention] domlai man b?"}, lazy_comment="can deliver to Siem Reap?",
        seller_reply="26500$ bong", org=True,
        private=("https://www.instagram.com/p/PRIV00001/", "private_account"),
        gone=("https://www.instagram.com/p/GONE00001/", "post_unavailable"),
        name_selector="article ul li h3", content_type="instagram_post"),
    "x": dict(
        site=x_site, query="RX300", post="https://x.com/i/status/1800000000000000001",
        results={"https://x.com/i/status/1800000000000000001", "https://x.com/i/status/1800000000000000004",
                 "https://x.com/i/status/1800000000000000002", "https://x.com/i/status/1800000000000000003"},
        lazy=None, buyer="តម្លៃប៉ុន្មានបង?", replies={"26500$ negotiable", "[mention] how much for the RX300?"},
        lazy_comment="can deliver to Siem Reap?", seller_reply="26500$ negotiable", org=False,
        private=("https://x.com/i/status/1800000000000000002", "protected_account"),
        gone=("https://x.com/i/status/1800000000000000003", "post_unavailable"),
        name_selector="[data-testid='User-Name']", content_type="x_post"),
    "threads": dict(
        site=threads_site, query="RX300", post="https://www.threads.com/t/DQrx300abc1",
        results={"https://www.threads.com/t/DQrx300abc1", "https://www.threads.com/t/DQpriv0001", "https://www.threads.com/t/DQgone0001"},
        lazy=None, buyer="តម្លៃប៉ុន្មានបង?", replies={"26500$ bong, inbox", "[mention] how much for the RX300?"},
        lazy_comment="can deliver to Siem Reap?", seller_reply="26500$ bong, inbox", org=False,
        private=("https://www.threads.com/t/DQpriv0001", "private_account"),
        gone=("https://www.threads.com/t/DQgone0001", "post_unavailable"),
        name_selector="a[href^='/@']:not([href*='/post/'])", content_type="threads_post"),
    "pinterest": dict(
        site=pinterest_site, query="RX300", post="https://www.pinterest.com/pin/912345678901234567/",
        results={"https://www.pinterest.com/pin/912345678901234567/", "https://www.pinterest.com/pin/912345678901234568/",
                 "https://www.pinterest.com/pin/912345678901234569/", "https://www.pinterest.com/pin/912345678901234570/"},
        lazy="https://www.pinterest.com/pin/912345678901234571/",
        buyer="how much for the RX300?", replies={"26500$, inbox us"}, lazy_comment="តម្លៃប៉ុន្មានបង?",
        seller_reply="26500$, inbox us", org=True,
        private=("https://www.pinterest.com/pin/912345678901234569/", "private_pin"),
        gone=("https://www.pinterest.com/pin/912345678901234570/", "pin_unavailable"),
        name_selector="[data-test-id='comment-author']", content_type="pinterest_pin"),
}
NAMES = list(SPECS)


def adapter(name, mode="normal", **limits):
    cls = registry.get(name)
    ctx = make_ctx(name, fixtures=partial(SPECS[name]["site"].install, mode=mode), limits={**FAST, **limits})
    return cls(ctx)


# ─── contract / URLs (no browser) ───────────────────────────────────────────

@pytest.mark.parametrize("name", NAMES)
def test_contract(name):
    cls = registry.get(name)
    assert_contract(cls)
    assert cls.access == "browser_session" and cls.login_url and cls.login_cookies
    assert not registry.load_config()["platforms"][name]["enabled"]          # ships disabled


@pytest.mark.parametrize("name", NAMES)
def test_health_requires_manual_login_profile(name, tmp_path, monkeypatch):
    cls = registry.get(name)
    ad = cls(make_ctx(name))
    monkeypatch.setattr(type(ad), "profile_dir", property(lambda self: tmp_path / "nope"))
    h = ad.health_check()
    assert h.state == "login_required" and f"python -m app.platform_login {name}" in h.detail
    assert adapter(name).health_check().ok      # fixtures → ok


@pytest.mark.parametrize("name,raw,canon", [
    ("instagram", "https://www.instagram.com/p/RXPOST0001/?utm_source=ig_web_copy_link&igsh=x", "https://www.instagram.com/p/RXPOST0001/"),
    ("instagram", "https://instagram.com/dara.private/reel/REEL00001?igsh=abc", "https://www.instagram.com/reel/REEL00001/"),
    ("instagram", "https://www.instagram.com/reels/REEL00001/", "https://www.instagram.com/reel/REEL00001/"),
    ("instagram", "https://www.instagram.com/dara.private/", None),
    ("x", "https://twitter.com/Some_User/status/1800000000000000001?s=20&t=abc", "https://x.com/i/status/1800000000000000001"),
    ("x", "https://mobile.x.com/some_user/status/1800000000000000001/photo/1", "https://x.com/i/status/1800000000000000001"),
    ("x", "https://x.com/i/web/status/1800000000000000001", "https://x.com/i/status/1800000000000000001"),
    ("x", "https://x.com/some_user", None),
    ("x", "https://evil.com/a/status/1800000000000000001", None),
    ("threads", "https://www.threads.net/@sreymom.rx/post/DQrx300abc1?xmt=AQG", "https://www.threads.com/t/DQrx300abc1"),
    ("threads", "https://www.threads.com/t/DQrx300abc1/", "https://www.threads.com/t/DQrx300abc1"),
    ("threads", "https://www.threads.com/@sreymom.rx", None),
    ("pinterest", "https://www.pinterest.com/pin/lexus-rx300-white--912345678901234568/?mt=login", "https://www.pinterest.com/pin/912345678901234568/"),
    ("pinterest", "https://pinterest.co.uk/pin/912345678901234567/", "https://www.pinterest.com/pin/912345678901234567/"),
    ("pinterest", "https://www.pinterest.com/mealea_pins/", None),
])
def test_canonicalize(name, raw, canon):
    ad = registry.get(name)(make_ctx(name))
    assert ad.canonicalize_url(raw) == canon


def test_canonical_urls_never_contain_handles():
    for name, spec in SPECS.items():
        for u in spec["results"]:
            assert "@" not in u and not any(p.lower() in u.lower() for p in spec["site"].PEOPLE), (name, u)


def test_instagram_hashtag_and_keyword_urls():
    ad = registry.get("instagram")(make_ctx("instagram"))
    assert ad.search_url_for("#RX300") == "https://www.instagram.com/explore/tags/rx300/"
    assert ad.search_url_for("#ឡានលក់").startswith("https://www.instagram.com/explore/search/keyword/?q=%23")  # Khmer tag → keyword page
    assert ad.search_url_for("Lexus RX300") == "https://www.instagram.com/explore/search/keyword/?q=Lexus%20RX300"
    off = registry.get("instagram")(make_ctx("instagram", adapter={"search": {"use_keyword_search": False, "keyword_url": None}}))
    assert off.search_url_for("#ឡានលក់") is None and off.last_skip_reason == "hashtag_not_valid_in_url_form"
    page = off.search("#ឡានលក់", Checkpoint("#ឡានលក់"))
    assert page.items == [] and page.exhausted and off.s is None            # no browser opened for an unusable query


# ─── browser runs against the fake sites ────────────────────────────────────

@pytest.mark.browser
@pytest.mark.parametrize("name", NAMES)
def test_search_scrolls_only_as_needed_and_checkpoints(name):
    spec = SPECS[name]
    with adapter(name, max_results_per_query=2) as ad:
        page = ad.search(spec["query"], Checkpoint(spec["query"]))
        assert len(page.items) == 2 and all(i.canonical_url in spec["results"] for i in page.items)
        cur = json.loads(page.next_checkpoint.cursor)
        assert cur["scroll_rounds"] == 0 and cur["newest_id"] and cur["last_id"] == page.items[-1].source_id
        assert ad.get_next_checkpoint() is page.next_checkpoint
        for i in page.items:
            assert i.url == i.canonical_url and "@" not in i.url
    with adapter(name, max_results_per_query=10) as ad:
        page = ad.search(spec["query"], Checkpoint(spec["query"]))
        got = {i.canonical_url for i in page.items}
        assert spec["results"] <= got
        if spec["lazy"]:
            assert spec["lazy"] in got and json.loads(page.next_checkpoint.cursor)["scroll_rounds"] >= 1
        # already-seen results are not returned again
        seen = Checkpoint(spec["query"], cursor=page.next_checkpoint.cursor, seen=[spec["post"]])
        again = ad.search(spec["query"], seen)
        assert spec["post"] not in {i.canonical_url for i in again.items}


@pytest.mark.browser
@pytest.mark.parametrize("name", NAMES)
def test_collect_post_and_comments(name):
    spec = SPECS[name]
    with adapter(name) as ad:
        ad.search(spec["query"], Checkpoint(spec["query"]))
        post = ad.collect_post(spec["post"])
        assert post is not None and post.source_content_type == spec["content_type"]
        assert post.canonical_post_url == spec["post"] == post.source_post_url
        assert "#rx300" in {h.casefold() for h in post.hashtags}
        assert post.published_text_displayed or name == "pinterest"               # pins often show no date
        batch = ad.collect_comments(post)
        post.comments, post.completeness_status = batch.comments, batch.completeness
        assert_post_valid(post, name)
        assert batch.completeness == "complete", [c.comment_text for c in batch.comments]
        texts = {c.comment_text: c for c in batch.comments}
        assert spec["buyer"] in texts and spec["lazy_comment"] in texts           # expanded + lazily loaded
        assert spec["replies"] <= set(texts)
        parent = texts[spec["buyer"]]
        for r in spec["replies"]:
            assert texts[r].comment_type == "reply" and texts[r].parent_fingerprint == parent.fingerprint
        assert parent.comment_type == "comment" and parent.commenter_key and parent.commenter_key_scope == "profile"
        assert texts[spec["seller_reply"]].is_post_author                          # seller replying is never a buyer
        if spec["org"]:
            assert post.organization is not None and post.author_key is None
        else:
            assert post.organization is None and post.author_key
        assert_no_identity_leak(post, [p for p in spec["site"].PEOPLE])
        blob = " ".join(str(x) for x in [post.source_post_url, post.canonical_post_url, post.search_url,
                                          *[c.source_comment_url for c in post.comments]])
        assert not any(p.lower() in blob.lower() for p in spec["site"].PEOPLE)


@pytest.mark.browser
@pytest.mark.parametrize("name", NAMES)
def test_comment_limit_is_partial(name):
    spec = SPECS[name]
    with adapter(name, max_comments_per_post=2) as ad:
        post = ad.collect_post(spec["post"])
        batch = ad.collect_comments(post)
        assert batch.completeness == "partial_limit" and 0 < len(batch.comments) <= 2


@pytest.mark.browser
@pytest.mark.parametrize("name", NAMES)
def test_private_and_unavailable_are_skipped(name):
    spec = SPECS[name]
    with adapter(name) as ad:
        for url, reason in (spec["private"], spec["gone"]):
            assert ad.collect_post(url) is None and ad.last_skip_reason == reason
        assert ad.collect_post("https://example.com/p/whatever/") is None and ad.last_skip_reason == "not_a_public_post_url"


@pytest.mark.browser
@pytest.mark.parametrize("name", NAMES)
def test_challenge_stops_headless(name):
    with adapter(name, mode="challenge") as ad, pytest.raises(Challenged):
        ad.search(SPECS[name]["query"], Checkpoint("q"))


@pytest.mark.browser
@pytest.mark.parametrize("name", NAMES)
def test_login_wall(name):
    with adapter(name, mode="login") as ad, pytest.raises(LoginRequired) as e:
        ad.search(SPECS[name]["query"], Checkpoint("q"))
    assert f"platform_login {name}" in e.value.detail or "login" in e.value.detail


@pytest.mark.browser
def test_instagram_soft_login_prompt_without_content():
    with adapter("instagram", mode="login_soft") as ad, pytest.raises(LoginRequired):
        ad.search("#rx300", Checkpoint("#rx300"))


@pytest.mark.browser
@pytest.mark.parametrize("name", NAMES)
def test_screenshots_hide_names(name):
    spec = SPECS[name]
    with adapter(name) as ad:
        post = ad.collect_post(spec["post"])
        post.comments = ad.collect_comments(post).comments
        buyer = next(c for c in post.comments if c.comment_text == spec["buyer"])
        ev = ad.capture_evidence(buyer)
        assert ev is not None and ev.kind == "comment" and ev.width > 0 and ev.png[:4] == b"\x89PNG"
        vis = ad.s.page.eval_on_selector_all(spec["name_selector"], "els => els.map(e => getComputedStyle(e).visibility)")
        assert vis and set(vis) == {"hidden"}
        pev = ad.capture_evidence(post)
        assert pev is not None and pev.kind == "post"


@pytest.mark.browser
def test_instagram_reel_private_author_is_key_only():
    with adapter("instagram") as ad:
        ad.search("#rx300", Checkpoint("#rx300"))
        post = ad.collect_post("https://www.instagram.com/reel/REEL00001/")
        assert post.source_content_type == "instagram_reel" and post.organization is None
        assert post.author_key == KEYER.key_for("instagram", "dara.private")
        assert_no_identity_leak(post, ["dara.private", "Dara Private"])
        assert "dara" not in (post.document_title or "").lower()


@pytest.mark.browser
def test_pinterest_pin_without_comments():
    with adapter("pinterest") as ad:
        post = ad.collect_post("https://www.pinterest.com/pin/912345678901234568/")
        assert post.post_title == "White Lexus RX300" and post.organization is None and post.author_key
        assert ad.collect_comments(post).completeness == "comments_unavailable"


@pytest.mark.browser
@pytest.mark.parametrize("name", NAMES)
def test_worker_cycle_end_to_end(name, tmp_path):
    cfg = registry.load_config()
    cfg["platforms"][name]["limits"] = FAST
    cfg["recency"] = {}            # fixture comments are dated 2024; the age rule is covered in test_platform_core
    sink = PreviewSink(tmp_path / "preview", "run")
    res = run_cycle(name, cfg=cfg, state=WorkerState(tmp_path / "state.sqlite"), sink=sink, keyer=KEYER,
                    fixtures=partial(SPECS[name]["site"].install), headed=False, max_queries=1)
    assert res.state == "ok", res.detail
    assert res.posts >= 1 and res.leads["confirmed_rx300_buyer"] >= 1, res.as_dict()
    assert any(r["text"] == SPECS[name]["buyer"] and r["lead_type"] == "confirmed_rx300_buyer" for r in res.review)
    reasons = {s["reason"] for s in res.skipped}
    assert {SPECS[name]["private"][1], SPECS[name]["gone"][1]} <= reasons
    assert res.screenshots >= 1
    written = " ".join(p.read_text(encoding="utf-8") for p in (tmp_path / "preview" / "run").rglob("*") if p.suffix in (".json", ".jsonl"))
    assert written and not any(p in written for p in SPECS[name]["site"].PEOPLE if len(p) > 5)
