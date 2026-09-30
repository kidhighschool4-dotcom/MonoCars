"""Official-API adapters (YouTube, Reddit, Bluesky, Mastodon) against authored fixtures — no network access.

Every request goes through an httpx.MockTransport routed on the URL path; payload shapes follow each API's documented
response format (tests/fixtures/platform_api/*.json).
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from fbm_intel.platforms import registry
from fbm_intel.platforms.adapters.bluesky import SEARCH_BLOCKER, BlueskyAdapter
from fbm_intel.platforms.adapters.mastodon import MastodonAdapter, html_to_text
from fbm_intel.platforms.adapters.reddit import RedditAdapter
from fbm_intel.platforms.adapters.youtube import YouTubeAdapter
from fbm_intel.platforms.budget import Budget
from fbm_intel.platforms.contract import (AccessBlocked, BudgetExhausted, Checkpoint, Misconfigured, RateLimited)
from fbm_intel.platforms.sinks import PreviewSink
from fbm_intel.platforms.state import WorkerState
from fbm_intel.platforms.worker import run_cycle

from .platform_contract import KEYER, assert_contract, assert_no_identity_leak, assert_post_valid, make_ctx

FIX = Path(__file__).parent / "fixtures" / "platform_api"
FAST = {"rate": {"min_interval_s": 0}}


def load(name: str):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def J(payload, status=200, headers=None):
    return httpx.Response(status, json=payload, headers=headers or {})


class Router:
    """Records every request; `routes` maps a callable(request) → Response."""

    def __init__(self, fn):
        self.fn = fn
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.fn(request)

    @property
    def transport(self):
        return httpx.MockTransport(self)


def comments_by_id(post):
    return {c.source_comment_id: c for c in post.comments}


# ─── YouTube ────────────────────────────────────────────────────────────────

YT = load("youtube")
YT_KEY = "SECRET-YT-KEY-123"
YT_FORBIDDEN = ["SreyPov", "DaraBuyer", "Visal", "Sokha Vlog", "SokhaVlog", "UCsreypov0000000000000", "UCdarabuyer00000000000",
                "yt3.ggpht.com", "youtube.com/@", "youtube.com/channel/UCsokhavlog"]


def yt_handler(overrides=None):
    overrides = overrides or {}

    def fn(req: httpx.Request):
        assert req.url.host == "www.googleapis.com"
        ep = req.url.path.rsplit("/", 1)[1]
        if ep in overrides:
            return overrides[ep](req)
        if ep == "commentThreads" and req.url.params.get("videoId") == "BBBBBBBBBBB":
            return J(YT["error_commentsDisabled"], 403)
        return J(YT[ep])
    return Router(fn)


@pytest.fixture
def yt_env(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", YT_KEY)


def yt(router, **cfg):
    return YouTubeAdapter(make_ctx("youtube", fixtures=router.transport, **FAST, **cfg))


def test_youtube_contract():
    assert_contract(YouTubeAdapter)
    assert YouTubeAdapter.access == "official_api" and YouTubeAdapter.required_env == ("YOUTUBE_API_KEY",)


def test_youtube_search_cursor_and_key_hidden(yt_env):
    r = yt_handler()
    a = yt(r)
    page = a.search("lexus rx300", Checkpoint(query="lexus rx300"))
    assert [i.source_id for i in page.items] == ["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"]
    assert page.items[0].canonical_url == "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    for it in page.items:
        assert YT_KEY not in (it.search_url or "") and "key=" not in it.search_url
        assert "regionCode=KH" in it.search_url and "type=video" in it.search_url
    assert r.requests[0].url.params["key"] == YT_KEY          # the key was used, just never stored
    cp = Checkpoint.from_dict(page.next_checkpoint.to_dict(), "lexus rx300")
    assert json.loads(cp.cursor)["page_token"] == "CAoQAA"
    a.search("lexus rx300", cp)
    assert r.requests[-2].url.params["pageToken"] == "CAoQAA"   # [-1] is the batched videos.list
    assert a.get_next_checkpoint() is not None


def test_youtube_post_comments_threading_privacy(yt_env):
    a = yt(yt_handler())
    page = a.search("lexus rx300", Checkpoint(query="lexus rx300"))
    post = a.collect_post(page.items[0].url, page.items[0])
    assert post.post_title.startswith("Lexus RX300") and "#lexusrx300" in post.hashtags and "#rx300" in post.hashtags
    assert post.engagement == {"views": 15230, "likes": 321, "comments": 7}
    assert post.published_at_observed.year == 2026 and post.source_post_id == "AAAAAAAAAAA"
    assert "privacyStatus public" in post.visibility_evidence
    assert post.organization is None and post.author_key == KEYER.key_for("youtube", "UCsokhavlog00000000000")
    batch = a.collect_comments(post)
    post.comments, post.completeness_status = batch.comments, batch.completeness
    assert batch.completeness == "complete"
    by = comments_by_id(post)
    assert set(by) == {"UgxThread1", "UgxThread1.reply1", "UgxThread2", "UgxThread2.r1", "UgxThread2.r2", "UgxThread2.r3", "UgxThread3"}
    assert by["UgxThread2.r3"].parent_fingerprint == by["UgxThread2"].fingerprint and by["UgxThread2.r3"].comment_type == "reply"
    assert by["UgxThread1.reply1"].is_post_author and not by["UgxThread1"].is_post_author
    assert by["UgxThread2"].canonical_comment_url == "https://www.youtube.com/watch?v=AAAAAAAAAAA&lc=UgxThread2"
    assert by["UgxThread1"].commenter_key == KEYER.key_for("youtube", "UCsreypov0000000000000")
    assert_post_valid(post, "youtube")
    assert_no_identity_leak(post, YT_FORBIDDEN)


def test_youtube_org_channel_comments_disabled_and_private_skip(yt_env):
    a = yt(yt_handler())
    page = a.search("rx300", Checkpoint(query="rx300"))
    org = a.collect_post(page.items[1].url, page.items[1])
    assert org.organization and org.organization.name == "Phnom Penh Auto Import" and org.author_key is None
    assert a.collect_comments(org).completeness == "comments_unavailable"
    assert a.collect_post(page.items[2].url, page.items[2]) is None and a.last_skip_reason == "not_public:unlisted"


def test_youtube_comment_limit_partial(yt_env):
    a = yt(yt_handler(), budgets={"max_comments_per_post": 3})
    page = a.search("rx300", Checkpoint(query="rx300"))
    post = a.collect_post(page.items[0].url, page.items[0])
    b = a.collect_comments(post)
    assert len(b.comments) == 3 and b.completeness == "partial_limit"


def test_youtube_quota_budget(yt_env, tmp_path):
    state = WorkerState(tmp_path / "s.sqlite")
    state.add_usage("youtube", api_units=8950)
    ctx = make_ctx("youtube", fixtures=yt_handler().transport, **FAST)
    ctx.budget = Budget("youtube", ctx.config["budgets"], state)
    with pytest.raises(BudgetExhausted) as e:
        YouTubeAdapter(ctx).search("rx300", Checkpoint(query="rx300"))
    assert e.value.budget == "youtube_quota"
    state2 = WorkerState(tmp_path / "s2.sqlite")
    ctx.budget = Budget("youtube", ctx.config["budgets"], state2)
    YouTubeAdapter(ctx).search("rx300", Checkpoint(query="rx300"))
    assert state2.usage("youtube")["api_units"] == 101        # search 100 + videos.list 1


def test_youtube_errors(yt_env, monkeypatch):
    with pytest.raises(RateLimited):
        yt(yt_handler({"search": lambda r: J({}, 429)})).search("rx300", Checkpoint(query="rx300"))
    with pytest.raises(RateLimited):
        yt(yt_handler({"search": lambda r: J(YT["error_quotaExceeded"], 403)})).search("rx300", Checkpoint(query="rx300"))
    with pytest.raises(AccessBlocked) as e:
        yt(yt_handler({"search": lambda r: J(YT["error_forbidden"], 403)})).search("rx300", Checkpoint(query="rx300"))
    assert YT_KEY not in (e.value.url or "")
    with pytest.raises(Misconfigured):
        yt(yt_handler({"search": lambda r: J(YT["error_keyInvalid"], 400)})).search("rx300", Checkpoint(query="rx300"))
    monkeypatch.delenv("YOUTUBE_API_KEY")
    h = yt(yt_handler()).health_check()
    assert h.state == "misconfigured" and h.detail == "missing: YOUTUBE_API_KEY"


def test_youtube_canonicalize():
    a = YouTubeAdapter(make_ctx("youtube", **FAST))
    assert a.canonicalize_url("https://youtu.be/AAAAAAAAAAA?t=3") == "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    assert a.canonicalize_url("https://m.youtube.com/watch?v=AAAAAAAAAAA&feature=share") == "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    assert a.canonicalize_url("https://www.youtube.com/shorts/AAAAAAAAAAA") == "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    assert a.canonicalize_url("https://www.youtube.com/@SokhaVlog") is None
    assert a.capture_evidence(None) is None


# ─── Reddit ─────────────────────────────────────────────────────────────────

RD = load("reddit")
RD_FORBIDDEN = ["khmer_driver", "rx_fan_99", "tuk_tuk_tom", "phnom_penh_pete", "helpful_mod", "t2_bbb222", "t2_aaa111", "/user/", "/u/"]


def rd_handler(overrides=None, headers=None):
    overrides = overrides or {}

    def fn(req: httpx.Request):
        path = req.url.path
        for k, f in overrides.items():
            if k in path:
                return f(req)
        if req.url.host == "www.reddit.com" and path == "/api/v1/access_token":
            assert req.method == "POST" and req.headers["authorization"].startswith("Basic ")
            return J(RD["token"])
        assert req.url.host == "oauth.reddit.com" and req.headers["authorization"] == "bearer fake-app-only-token"
        assert "fbm" in req.headers["user-agent"].lower() or "test-agent" in req.headers["user-agent"]
        if path == "/r/cambodia/search":
            return J(RD["search_cambodia"], headers=headers)
        if path == "/r/phnompenh/search":
            return J(RD["forbidden_private"], 403)
        if path.endswith("/search"):
            return J(RD["search_empty"])
        if path == "/comments/abc123":
            return J(RD["thread_abc123"], headers=headers)
        return J({"message": "Not Found", "error": 404}, 404)
    return Router(fn)


@pytest.fixture
def rd_env(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csecret")


def rd(router, **cfg):
    return RedditAdapter(make_ctx("reddit", fixtures=router.transport, **FAST, **cfg))


def test_reddit_contract():
    assert_contract(RedditAdapter)


def test_reddit_search_blocked_subreddit_isolated_and_cursor(rd_env):
    r = rd_handler()
    a = rd(r)
    assert a.subreddits() == ["cambodia", "phnompenh", "Lexus"]
    page = a.search("rx300", Checkpoint(query="rx300"))
    assert [i.source_id for i in page.items] == ["t3_abc123", "t3_nsfw01"]
    assert page.items[0].canonical_url == "https://www.reddit.com/r/cambodia/comments/abc123/"
    assert "phnompenh" in a.blocked_subreddits                  # private subreddit recorded, others continued
    assert all("restrict_sr=1" in i.search_url and "sort=new" in i.search_url for i in page.items)
    cp = Checkpoint.from_dict(page.next_checkpoint.to_dict(), "rx300")
    assert json.loads(cp.cursor) == {"cambodia": "t3_nsfw01"}
    a.search("rx300", cp)
    assert [q.url.params.get("after") for q in r.requests if q.url.path == "/r/cambodia/search"] == [None, "t3_nsfw01"]
    assert sum(q.url.path == "/api/v1/access_token" for q in r.requests) == 1   # token reused
    assert a.collect_post(page.items[1].url, page.items[1]) is None and a.last_skip_reason == "nsfw_over_18"


def test_reddit_post_threaded_comments_privacy(rd_env):
    a = rd(rd_handler())
    page = a.search("rx300", Checkpoint(query="rx300"))
    post = a.collect_post(page.items[0].url, page.items[0])
    assert post.post_title.startswith("Looking to buy") and "#rx300" in post.hashtags and "[mention]" in post.post_text
    assert post.engagement["score"] == 14 and post.published_at_observed is not None
    assert post.author_key == KEYER.key_for("reddit", "t2_aaa111")
    b = a.collect_comments(post)
    post.comments = b.comments
    assert b.completeness == "complete"
    by = comments_by_id(post)
    assert set(by) == {"t1_c1", "t1_c2", "t1_c4", "t1_c6"}          # [removed] c3 / [deleted] c5 skipped
    assert by["t1_c2"].parent_fingerprint == by["t1_c1"].fingerprint and by["t1_c2"].is_post_author
    assert by["t1_c4"].parent_fingerprint == by["t1_c1"].fingerprint   # child of removed c3 → nearest kept ancestor
    assert by["t1_c6"].comment_type == "comment"
    assert by["t1_c1"].canonical_comment_url == "https://www.reddit.com/r/cambodia/comments/abc123/looking_to_buy_a_lexus_rx300/c1/"
    assert by["t1_c1"].commenter_key == KEYER.key_for("reddit", "t2_bbb222")
    assert_post_valid(post, "reddit")
    assert_no_identity_leak(post, RD_FORBIDDEN)


def test_reddit_comment_limit_partial(rd_env):
    a = rd(rd_handler(), budgets={"max_comments_per_post": 2})
    page = a.search("rx300", Checkpoint(query="rx300"))
    post = a.collect_post(page.items[0].url, page.items[0])
    b = a.collect_comments(post)
    assert len(b.comments) == 2 and b.completeness == "partial_limit"


def test_reddit_errors_and_health(rd_env, monkeypatch):
    with pytest.raises(RateLimited):
        rd(rd_handler({"/r/cambodia/search": lambda r: J({}, 429)})).search("rx300", Checkpoint(query="rx300"))
    with pytest.raises(RateLimited) as e:
        rd(rd_handler(headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "600", "x-ratelimit-used": "100"})) \
            .search("rx300", Checkpoint(query="rx300"))
    assert e.value.retry_after_s == 600
    with pytest.raises(AccessBlocked):
        rd(rd_handler({"/search": lambda r: J(RD["forbidden_private"], 403)})).search("rx300", Checkpoint(query="rx300"))
    with pytest.raises(Misconfigured):
        rd(rd_handler({"/api/v1/access_token": lambda r: J({"message": "Unauthorized", "error": 401}, 401)})) \
            .search("rx300", Checkpoint(query="rx300"))
    monkeypatch.setenv("REDDIT_USER_AGENT", "test-agent:1.0 (by /u/nobody)")
    rd(rd_handler()).search("rx300", Checkpoint(query="rx300"))   # custom UA accepted by the router assertion
    monkeypatch.delenv("REDDIT_CLIENT_SECRET")
    h = rd(rd_handler()).health_check()
    assert h.state == "misconfigured" and h.detail == "missing: REDDIT_CLIENT_SECRET"


def test_reddit_canonicalize():
    a = RedditAdapter(make_ctx("reddit", **FAST))
    assert a.canonicalize_url("https://old.reddit.com/r/cambodia/comments/ABC123/some_slug/?utm=1") == \
        "https://www.reddit.com/r/cambodia/comments/abc123/"
    assert a.canonicalize_url("https://www.reddit.com/user/khmer_driver") is None


# ─── Bluesky ────────────────────────────────────────────────────────────────

BS = load("bluesky")
BS_FORBIDDEN = ["sokha.bsky.social", "Sokha K", "dara.bsky.social", "Dara P", "Quiet Person", "quiet.bsky.social", "cdn.bsky.app"]


def bs_handler(overrides=None):
    overrides = overrides or {}

    def fn(req: httpx.Request):
        assert req.url.host == "public.api.bsky.app"
        ep = req.url.path.rsplit("/", 1)[1]
        if ep in overrides:
            return overrides[ep](req)
        if ep == "app.bsky.feed.searchPosts":
            return J(BS["searchPosts"])
        if ep == "app.bsky.feed.getPostThread":
            if req.url.params["uri"].endswith("3kpost1aaaa"):
                return J(BS["thread_post1"])
            return J({"thread": {"$type": "app.bsky.feed.defs#threadViewPost", "post": BS["searchPosts"]["posts"][1], "replies": []}})
        return J({"error": "MethodNotImplemented"}, 501)
    return Router(fn)


def bs(router, **cfg):
    return BlueskyAdapter(make_ctx("bluesky", fixtures=router.transport, **FAST, **cfg))


def test_bluesky_contract():
    assert_contract(BlueskyAdapter)


def test_bluesky_search_cursor(tmp_path):
    r = bs_handler()
    a = bs(r, lang="en")
    page = a.search("lexus rx300", Checkpoint(query="lexus rx300"))
    assert [i.canonical_url for i in page.items] == [
        "https://bsky.app/profile/did:plc:sokha111aaaaaaaaaaaaaaaa/post/3kpost1aaaa",
        "https://bsky.app/profile/did:plc:angkor222bbbbbbbbbbbbbbbb/post/3kpost2bbbb"]
    assert "lang=en" in page.items[0].search_url
    cp = Checkpoint.from_dict(page.next_checkpoint.to_dict(), "lexus rx300")
    a.search("lexus rx300", cp)
    assert r.requests[-1].url.params["cursor"] == "25"


def test_bluesky_post_thread_privacy():
    a = bs(bs_handler())
    page = a.search("rx300", Checkpoint(query="rx300"))
    post = a.collect_post(page.items[0].url, page.items[0])
    assert post.hashtags[:2] == ["#rx300", "#cambodia"] and post.engagement["likes"] == 5
    assert post.author_key == KEYER.key_for("bluesky", "did:plc:sokha111aaaaaaaaaaaaaaaa") and post.organization is None
    b = a.collect_comments(post)
    post.comments = b.comments
    assert b.completeness == "complete"
    assert len(post.comments) == 2                            # notFound + !no-unauthenticated reply skipped
    top, reply = post.comments
    assert top.comment_type == "comment" and reply.parent_fingerprint == top.fingerprint and reply.is_post_author
    assert top.canonical_comment_url == "https://bsky.app/profile/did:plc:dara333cccccccccccccccc/post/3kreply1ccc"
    assert top.commenter_key == KEYER.key_for("bluesky", "did:plc:dara333cccccccccccccccc")
    assert top.comment_text.startswith("[mention]")
    assert_post_valid(post, "bluesky")
    assert_no_identity_leak(post, BS_FORBIDDEN)
    org = a.collect_post(page.items[1].url, page.items[1])
    assert org.organization and org.organization.name == "Angkor Motors" and org.author_key is None


def test_bluesky_limit_and_errors():
    a = bs(bs_handler(), budgets={"max_comments_per_post": 1})
    page = a.search("rx300", Checkpoint(query="rx300"))
    b = a.collect_comments(a.collect_post(page.items[0].url, page.items[0]))
    assert len(b.comments) == 1 and b.completeness == "partial_limit"
    for status in (401, 403):
        with pytest.raises(Misconfigured) as e:
            bs(bs_handler({"app.bsky.feed.searchPosts": lambda r, s=status: J({"error": "AuthMissing"}, s)})) \
                .search("rx300", Checkpoint(query="rx300"))
        assert e.value.detail == SEARCH_BLOCKER
    with pytest.raises(RateLimited):
        bs(bs_handler({"app.bsky.feed.searchPosts": lambda r: J({"error": "RateLimitExceeded"}, 429)})) \
            .search("rx300", Checkpoint(query="rx300"))
    assert bs(bs_handler()).health_check().ok


# ─── Mastodon ───────────────────────────────────────────────────────────────

MA = load("mastodon")
MA_FORBIDDEN = ["alicechan", "Alice Chan", "bobbuilder", "Bob Builder", "carlakh", "Carla KH", "secretsam", "followers-only"]


def ma_handler(overrides=None):
    overrides = overrides or {}

    def fn(req: httpx.Request):
        path = req.url.path
        for k, f in overrides.items():
            if k in f"{req.url.host}{path}":
                return f(req)
        if path.startswith("/api/v1/timelines/tag/"):
            return J(MA["tag_timeline"] if req.url.host == "mastodon.social" else [])
        if path.endswith("/context"):
            sid = path.split("/")[4]
            return J(MA.get(f"context_{sid}", {"ancestors": [], "descendants": []}))
        return J({"error": "Record not found"}, 404)
    return Router(fn)


def ma(router, **cfg):
    return MastodonAdapter(make_ctx("mastodon", fixtures=router.transport, **FAST, **cfg))


def test_mastodon_contract_and_hosts():
    assert_contract(MastodonAdapter)
    a = MastodonAdapter(make_ctx("mastodon", instances=["mastodon.social", "https://kh.example/", "bad host!"], **FAST))
    assert a.allowed_hosts == frozenset({"mastodon.social", "kh.example"}) and a.http.allowed == a.allowed_hosts


def test_mastodon_tags():
    assert MastodonAdapter.tag_for("#RX300") == "rx300"
    assert MastodonAdapter.tag_for("#ឡានលក់") is None and MastodonAdapter.tag_for("lexus rx300") is None


def test_mastodon_search_cursor_and_skips():
    r = ma_handler()
    a = ma(r, instances=["mastodon.social", "kh.example"])
    page = a.search("#RX300", Checkpoint(query="#RX300"))
    assert len(page.items) == 3 and all(i.search_url.startswith("https://mastodon.social/api/v1/timelines/tag/rx300") for i in page.items)
    cp = Checkpoint.from_dict(page.next_checkpoint.to_dict(), "#RX300")
    assert json.loads(cp.cursor)["mastodon.social"] == "113000000000000001"
    a.search("#RX300", cp)
    assert r.requests[-2].url.params["max_id"] == "113000000000000001"
    assert a.collect_post(page.items[1].url, page.items[1]) is None and a.last_skip_reason == "not_public:unlisted"
    assert a.collect_post(page.items[2].url, page.items[2]) is None and a.last_skip_reason == "content_warning_sensitive"
    empty = a.search("#ឡានលក់", Checkpoint(query="#ឡានលក់"))
    assert empty.items == [] and empty.exhausted


def test_mastodon_post_replies_privacy():
    a = ma(ma_handler())
    page = a.search("#rx300", Checkpoint(query="#rx300"))
    post = a.collect_post(page.items[0].url, page.items[0])
    assert post.canonical_post_url == "https://mastodon.social/@alicechan/113000000000000003"
    assert post.post_text.startswith("Lexus RX300 2003 for sale") and "<" not in post.post_text
    assert post.hashtags[:2] == ["#rx300", "#cambodia"] and post.engagement == {"replies": 4, "boosts": 1, "favourites": 6}
    assert post.author_key == KEYER.key_for("mastodon", "https://mastodon.social/users/alicechan")
    b = a.collect_comments(post)
    post.comments = b.comments
    by = comments_by_id(post)
    assert set(by) == {"mastodon.social:113000000000000010", "mastodon.social:113000000000000011", "mastodon.social:113000000000000013"}
    bob, alice, carla = (by[f"mastodon.social:1130000000000000{n}"] for n in (10, 11, 13))
    assert bob.comment_type == "comment" and bob.comment_text.startswith("how much for the RX300")
    assert alice.parent_fingerprint == bob.fingerprint and alice.is_post_author
    assert carla.comment_type == "comment"                      # its private parent was skipped
    assert all(c.canonical_comment_url is None for c in post.comments)
    assert_post_valid(post, "mastodon")
    assert_no_identity_leak(post, MA_FORBIDDEN)
    lim = ma(ma_handler(), budgets={"max_comments_per_post": 1})
    p2 = lim.search("#rx300", Checkpoint(query="#rx300"))
    b2 = lim.collect_comments(lim.collect_post(p2.items[0].url, p2.items[0]))
    assert len(b2.comments) == 1 and b2.completeness == "partial_limit"


def test_mastodon_errors():
    with pytest.raises(RateLimited):
        ma(ma_handler({"/api/v1/timelines/tag/": lambda r: J({"error": "Too many requests"}, 429)})).search("#rx300", Checkpoint(query="#rx300"))
    with pytest.raises(AccessBlocked):
        ma(ma_handler({"/api/v1/timelines/tag/": lambda r: J({"error": "This method requires an authenticated user"}, 401)})) \
            .search("#rx300", Checkpoint(query="#rx300"))
    a = ma(ma_handler({"kh.example/api/v1/timelines/tag/": lambda r: J({"error": "forbidden"}, 403)}),
           instances=["mastodon.social", "kh.example"])
    assert len(a.search("#rx300", Checkpoint(query="#rx300")).items) == 3 and "kh.example" in a.blocked_instances
    h = MastodonAdapter(make_ctx("mastodon", instances=["not a host"], **FAST)).health_check()
    assert h.state == "misconfigured"


def test_html_to_text_strips_mentions_keeps_hashtags():
    assert html_to_text('<p><span class="h-card"><a class="u-url mention">@<span>x</span></a></span> hi <a class="mention hashtag">#<span>rx300</span></a></p>') == "hi #rx300"


# ─── End-to-end through the worker ──────────────────────────────────────────

E2E = {
    "youtube": (lambda: yt_handler(), {"queries": ["lexus rx300"]}, {"YOUTUBE_API_KEY": YT_KEY}),
    "reddit": (lambda: rd_handler(), {"queries": ["rx300"]}, {"REDDIT_CLIENT_ID": "cid", "REDDIT_CLIENT_SECRET": "csecret"}),
    "bluesky": (lambda: bs_handler(), {"queries": ["lexus rx300"]}, {}),
    "mastodon": (lambda: ma_handler(), {"queries": ["#rx300"]}, {}),
}


@pytest.mark.parametrize("name", list(E2E))
def test_run_cycle_end_to_end(name, tmp_path, monkeypatch):
    make_router, discovery, env = E2E[name]
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    cfg = registry.load_config()
    cfg["platforms"][name].update({"rate": {"min_interval_s": 0}, "discovery": discovery})
    state = WorkerState(tmp_path / "state.sqlite")
    sink = PreviewSink(tmp_path / "preview", "run")
    router = make_router()
    res = run_cycle(name, cfg=cfg, state=state, sink=sink, keyer=KEYER, fixtures=router.transport)
    assert res.state == "ok", res.detail
    assert res.posts >= 1 and res.leads["confirmed_rx300_buyer"] >= 1, res.as_dict()
    lines = [json.loads(x) for x in (sink.dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines and all(rec["visibility"] == "public_verified" for rec in lines)
    blob = json.dumps(lines, ensure_ascii=False)
    for secret in (YT_KEY, "csecret", "fake-app-only-token"):
        assert secret not in blob
    assert any(c["lead"]["lead_type"] == "confirmed_rx300_buyer" for rec in lines for c in rec["comments"])
    if name == "youtube":
        assert state.usage("youtube")["api_units"] >= 101
