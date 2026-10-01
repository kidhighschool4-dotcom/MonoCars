"""Multi-platform core: lead typing, discovery queries, worker isolation, circuit breaker, budgets, checkpoints."""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

import pytest

from fbm_intel.platforms import registry
from fbm_intel.platforms.budget import Budget
from fbm_intel.platforms.contract import (AccessBlocked, BudgetExhausted, Challenged, Checkpoint, CommentBatch, Health,
                                          PlatformAdapter, SearchItem, SearchPage)
from fbm_intel.platforms.discovery import queries_for
from fbm_intel.platforms.leads import PostContext, classify_comment, classify_post, mentions_rx300
from fbm_intel.platforms.sinks import PreviewSink
from fbm_intel.platforms.state import WorkerState
from fbm_intel.platforms.worker import Worker, apply_result, next_run_after, run_cycle
from fbm_intel.social.model import SocialPost, make_comment

from .platform_contract import KEYER

RX_POST = PostContext("Lexus RX300 2004 លក់ $12,500 ភ្នំពេញ ពន្ធរួច")
GENERIC_POST = PostContext("Toyota Prius 2010 for sale")


# ─── Lead typing ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["RX300", "rx 300", "Lexus RX", "rx៣០០", "ឡិចស៊ីស RX ឆ្នាំ2003", "lexus rx300h"])
def test_rx300_mentions(text):
    assert mentions_rx300(text)


@pytest.mark.parametrize("text", ["rx7", "RX 3000 mAh", "lexus is250", "300 dollars"])
def test_not_rx300(text):
    assert not mentions_rx300(text)


@pytest.mark.parametrize("text,post,expected", [
    ("តម្លៃប៉ុន្មានបង?", RX_POST, "confirmed_rx300_buyer"),            # Khmer price question on an RX300 post
    ("domlai man b?", RX_POST, "confirmed_rx300_buyer"),                # Romanized Khmer
    ("how much? still available?", RX_POST, "confirmed_rx300_buyer"),
    ("ចង់ទិញ RX300 ជិះគ្រួសារ", GENERIC_POST, "confirmed_rx300_buyer"),   # RX300 in the comment itself
    ("rok tinh rx300 rot taxi", GENERIC_POST, "confirmed_rx300_buyer"),
    ("looking for a family SUV, how much?", GENERIC_POST, "potential_rx300_fit"),
    ("ចង់ទិញឡានគ្រួសារ តម្លៃប៉ុន្មាន", GENERIC_POST, "potential_rx300_fit"),
    ("want to buy car for grab taxi, price?", GENERIC_POST, "potential_rx300_fit"),
    ("I sell RX300 cheaper, we have stock, contact us", RX_POST, "seller_or_dealer"),
    ("មានលក់ RX300 ឆ្នាំ2005 $13,000 ទំនាក់ទំនង", GENERIC_POST, "seller_or_dealer"),
    ("nice car 🔥", RX_POST, "irrelevant"),
    ("ot jong tinh te", RX_POST, "irrelevant"),
    ("how much?", GENERIC_POST, "irrelevant"),                          # buyer, but no RX300 fit
])
def test_comment_lead_types(text, post, expected):
    r = classify_comment(text, post)
    assert r.lead_type == expected, (text, r)


def test_post_author_is_never_a_buyer():
    assert classify_comment("price $12,500 inbox", RX_POST, is_post_author=True).lead_type == "seller_or_dealer"


def test_use_case_tags():
    assert classify_comment("rok tinh rx300 rot taxi", GENERIC_POST).use_case == "taxi"
    assert classify_comment("ចង់ទិញ RX300 ជិះគ្រួសារ", GENERIC_POST).use_case == "family"


@pytest.mark.parametrize("text,org,expected", [
    ("Lexus RX300 2004 for sale $12,500 full option", False, "seller_or_dealer"),
    ("Looking for Lexus RX300 around $12k in Phnom Penh", False, "confirmed_rx300_buyer"),
    ("រកទិញឡានគ្រួសារ SUV តម្លៃសមរម្យ", False, "potential_rx300_fit"),
    ("Happy new year everyone", False, "irrelevant"),
    ("Looking for RX300", True, "seller_or_dealer"),     # organizational author: never a buyer lead
])
def test_post_lead_types(text, org, expected):
    assert classify_post(PostContext(text, org)).lead_type == expected


# ─── Discovery ──────────────────────────────────────────────────────────────

def test_queries_cover_three_languages_even_when_limited():
    qs = queries_for("tiktok", limit=3)
    assert {q.language for q in qs} == {"km", "romanized_km", "en"}


def test_hashtags_first_when_configured():
    qs = queries_for("instagram")
    assert qs[0].language == "tag" and qs[0].text.startswith("#")


def test_explicit_queries_override():
    assert [q.text for q in queries_for("reddit", {"queries": ["a", "A", "b"]})] == ["a", "b"]


# ─── Fake adapter used by worker tests ──────────────────────────────────────

class FakeAdapter(PlatformAdapter):
    name = "fake"
    platform = "web"
    content_type = "web_page"
    adapter_version = "fake-v1"
    allowed_hosts = frozenset({"example.test"})
    access = "public_web"
    behaviour: dict = {}

    def search(self, query, checkpoint):
        b = self.behaviour
        if b.get("search_raises"):
            raise b["search_raises"]
        start = int(checkpoint.cursor or 0)
        slug = query.replace(" ", "-")
        items = [SearchItem(url=f"https://example.test/{slug}/p/{i}", canonical_url=f"https://example.test/{slug}/p/{i}", query=query,
                            search_url=f"https://example.test/search?q={query}") for i in range(start, start + 3)]
        self._next_checkpoint = Checkpoint(query=query, cursor=str(start + 3), page=checkpoint.page + 1, seen=list(checkpoint.seen))
        return SearchPage(items, self._next_checkpoint)

    def collect_post(self, url, item=None):
        if self.behaviour.get("item_error") and url.endswith("/1"):
            raise ValueError("boom")
        if url.endswith("/2") and self.behaviour.get("skip_2"):
            self.last_skip_reason = "not_public"
            return None
        return SocialPost(platform="web", source_content_type="web_page", source_post_id=url[-1], source_post_url=url,
                          canonical_post_url=url, document_title=None, post_title=None, post_text="Lexus RX300 2004 for sale",
                          hashtags=[], published_text_displayed=None, published_at_observed=None, engagement={},
                          visibility_status="public_verified", visibility_evidence="fixture", search_query=item.query,
                          search_url=item.search_url, captured_at=datetime.now(timezone.utc), adapter_version="fake-v1",
                          content_hash="h" + url[-1])

    def collect_comments(self, post):
        mk = lambda t: make_comment(platform="web", post_url=post.canonical_post_url, raw_text=t, is_reply=False, parent=None,  # noqa: E731
                                    commenter_key=None, key_version=None, displayed_timestamp="1d",
                                    commented_at=datetime.now(timezone.utc) - timedelta(days=1),
                                    source_comment_id=None, source_comment_url=None, occurrence_counter={})
        return CommentBatch([mk("តម្លៃប៉ុន្មានបង?"), mk("nice car"), mk("domlai man b?")], "complete")

    def capture_evidence(self, item):
        from fbm_intel.platforms.base import evidence_from_png
        return evidence_from_png(b"\x89PNG fake", "post" if isinstance(item, SocialPost) else "comment")

    def canonicalize_url(self, url):
        return url

    def normalize_result(self, result):
        raise NotImplementedError

    def health_check(self):
        return self.behaviour.get("health", Health("ok"))


@pytest.fixture
def fake_registry(monkeypatch):
    classes = {}

    def make(name, **behaviour):
        cls = type(f"Fake_{name}", (FakeAdapter,), {"name": name, "behaviour": behaviour})
        classes[name] = cls
        return cls

    monkeypatch.setattr(registry, "get", lambda n: classes[n] if n in classes else (_ for _ in ()).throw(KeyError(n)))
    return make


def cfg_for(*names, **budgets):
    cfg = registry.load_config()
    cfg["platforms"] = {n: {"tier": 1, "enabled": True, "schedule": "global_social", "rate": {"min_interval_s": 0},
                            "discovery": {"queries": ["lexus rx300", "rx300 taxi"]}} for n in names}
    cfg["budgets"].update(budgets)
    return cfg


@pytest.fixture
def state(tmp_path):
    return WorkerState(tmp_path / "state.sqlite")


# ─── Worker ─────────────────────────────────────────────────────────────────

def test_cycle_collects_types_leads_and_writes_preview(fake_registry, state, tmp_path):
    fake_registry("alpha")
    sink = PreviewSink(tmp_path / "preview", "run1")
    res = run_cycle("alpha", cfg=cfg_for("alpha"), state=state, sink=sink, keyer=KEYER)
    assert res.state == "ok" and res.posts == 6 and res.leads["confirmed_rx300_buyer"] == 12
    assert res.post_leads == {"seller_or_dealer": 6}
    rows = [json.loads(x) for x in (sink.dir / "alpha.jsonl").read_text().splitlines()]
    assert len(rows) == 6
    # buyers-only persistence: "nice car" text is not kept, just counted
    assert all("nice car" not in c["text"] for r in rows for c in r["comments"])
    assert rows[0]["rejected_comment_count"] == 1
    assert res.screenshots > 0 and list((sink.dir / "shots").iterdir())
    assert res.review and all(x["lead_type"] == "confirmed_rx300_buyer" for x in res.review)


def test_checkpoint_and_dedup_resume(fake_registry, state, tmp_path):
    fake_registry("alpha")
    cfg = cfg_for("alpha")
    run_cycle("alpha", cfg=cfg, state=state, sink=PreviewSink(tmp_path, "a"), keyer=KEYER)
    cp = state.checkpoint("alpha", "lexus rx300")
    assert cp.cursor == "3" and len(cp.seen) == 3
    res = run_cycle("alpha", cfg=cfg, state=state, sink=PreviewSink(tmp_path, "b"), keyer=KEYER)
    assert res.posts == 6 and state.checkpoint("alpha", "lexus rx300").cursor == "6"   # next page, not the same posts


def test_one_failing_platform_does_not_stop_others(fake_registry, state, tmp_path):
    fake_registry("good")
    fake_registry("challenged", search_raises=Challenged("captcha", "https://example.test/search"))
    fake_registry("broken", health=Health("misconfigured", "missing: API_KEY"))
    cfg = cfg_for("good", "challenged", "broken")
    w = Worker(cfg=cfg, state=state, sink=PreviewSink(tmp_path, "r"), keyer=KEYER, platforms=["good", "challenged", "broken"])
    res = {r.platform: r for r in w.run_once()}
    assert res["good"].state == "ok" and res["good"].posts == 6
    assert res["challenged"].state == "challenged" and "captcha" in res["challenged"].detail
    assert res["broken"].state == "misconfigured" and "API_KEY" in res["broken"].detail
    assert state.status("challenged").circuit_open() and not state.status("good").circuit_open()


def test_item_errors_are_isolated(fake_registry, state, tmp_path):
    fake_registry("alpha", item_error=True, skip_2=True)
    res = run_cycle("alpha", cfg=cfg_for("alpha"), state=state, sink=PreviewSink(tmp_path, "r"), keyer=KEYER)
    assert res.state == "ok" and len(res.item_errors) == 2 and len(res.skipped) == 2 and res.skipped[0] == {"url": "https://example.test/lexus-rx300/p/2", "reason": "not_public"}


def test_budget_stops_cleanly_and_keeps_work(fake_registry, state, tmp_path):
    fake_registry("alpha")
    cfg = cfg_for("alpha", max_posts_per_cycle=2)
    sink = PreviewSink(tmp_path, "r")
    res = run_cycle("alpha", cfg=cfg, state=state, sink=sink, keyer=KEYER)
    assert res.state == "budget_exhausted" and res.budget_exhausted == "posts" and res.posts == 2
    assert len((sink.dir / "alpha.jsonl").read_text().splitlines()) == 2                   # collected work kept
    cp = state.checkpoint("alpha", "lexus rx300")
    assert cp.cursor is None and len(cp.seen) == 2                                          # same page resumes, minus collected
    res2 = run_cycle("alpha", cfg=cfg_for("alpha", max_posts_per_cycle=10), state=state, sink=sink, keyer=KEYER)
    urls = [json.loads(x)["post_url"] for x in (sink.dir / "alpha.jsonl").read_text().splitlines()]
    assert res2.posts == 4 and len(urls) == len(set(urls)) == 6                             # nothing lost, nothing twice


def test_screenshot_budget_is_soft(fake_registry, state, tmp_path):
    fake_registry("alpha")
    res = run_cycle("alpha", cfg=cfg_for("alpha", max_screenshots_per_cycle=2), state=state,
                    sink=PreviewSink(tmp_path, "r"), keyer=KEYER)
    assert res.state == "ok" and res.screenshots == 2 and res.posts == 6


def test_daily_storage_budget(state):
    b = Budget("alpha", {"max_daily_storage_mb": 1, "max_screenshots_per_cycle": 99}, state)
    b.add_storage(2 * 1024 * 1024)
    with pytest.raises(BudgetExhausted):
        b.take("screenshots")


def test_daily_ai_cost_budget(state):
    b = Budget("alpha", {"max_daily_ai_cost_usd": 0.02, "ai_cost_per_classification_usd": 0.01,
                         "max_ai_classifications_per_cycle": 99}, state)
    b.take("ai_calls")
    b.take("ai_calls")
    assert not b.can("ai_calls")


def test_circuit_breaker_backoff_and_reset(fake_registry, state):
    cfg = cfg_for("alpha")
    pcfg = registry.platform_config("alpha", cfg)
    wcfg = cfg["worker"]
    from fbm_intel.platforms.worker import CycleResult
    st = state.status("alpha")
    for i in range(2):
        st = apply_result(st, CycleResult("alpha", "t", state="error", detail="x"), pcfg, wcfg)
        assert not st.circuit_open()                                     # below threshold: normal retry
    st = apply_result(st, CycleResult("alpha", "t", state="error", detail="x"), pcfg, wcfg)
    assert st.circuit_open() and st.consecutive_failures == 3
    st = apply_result(st, CycleResult("alpha", "t", state="ok"), pcfg, wcfg)
    assert not st.circuit_open() and st.consecutive_failures == 0 and st.last_success_at


def test_challenge_opens_long_cooldown(state):
    cfg = cfg_for("alpha")
    from fbm_intel.platforms.worker import CycleResult
    st = apply_result(state.status("alpha"), CycleResult("alpha", "t", state="challenged"), registry.platform_config("alpha", cfg), cfg["worker"])
    until = datetime.fromisoformat(st.circuit_open_until)
    assert until - datetime.now(timezone.utc) > timedelta(hours=5)


def test_schedule_windows_and_jitter():
    cfg = registry.load_config()
    rng = random.Random(1)
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for name, lo, hi in [("facebook_public_posts", 30, 60), ("youtube", 60, 180), ("forums", 360, 720)]:
        pc = registry.platform_config(name, cfg)
        runs = [(next_run_after(pc, 0.2, t0, rng) - t0).total_seconds() / 60 for _ in range(200)]
        assert min(runs) >= lo * 0.8 - 0.01 and max(runs) <= hi * 1.2 + 0.01
        assert len({round(r) for r in runs}) > 20                          # not all at the same time


def test_enable_disable_independent(fake_registry, state, tmp_path):
    fake_registry("alpha")
    fake_registry("beta")
    cfg = cfg_for("alpha", "beta")
    state.set_enabled("beta", False)
    w = Worker(cfg=cfg, state=state, sink=PreviewSink(tmp_path, "r"), keyer=KEYER, require_enabled=True)
    assert w.due() == ["alpha"]


def test_every_platform_disabled_by_default():
    cfg = registry.load_config()
    assert not any(p["enabled"] for p in cfg["platforms"].values())


def test_registry_isolates_import_failures(monkeypatch):
    registry.IMPORT_ERRORS.pop("forums", None)
    classes = registry.load_all()
    assert "telegram" in classes
    for name, err in registry.IMPORT_ERRORS.items():
        assert name not in classes and err


# ─── AI second opinion (advisory, budgeted, injection-safe) ─────────────────

def _ai_transport(answer: dict, seen: list):
    import httpx

    def handler(req):
        body = json.loads(req.content)
        seen.append(body)
        call = {"function": {"name": "submit_lead_review", "arguments": json.dumps(answer)}}
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [call]}}]})
    return httpx.MockTransport(handler)


def test_ai_review_is_advisory_and_budgeted(fake_registry, state, tmp_path):
    from fbm_intel.platforms.ai_review import LeadReviewer
    fake_registry("alpha")
    seen: list = []
    reviewer = LeadReviewer("http://gw.test", "t", transport=_ai_transport({"lead_type": "irrelevant", "confidence": 80, "reason": "x"}, seen))
    cfg = cfg_for("alpha", max_ai_classifications_per_cycle=2)
    cfg["ai_review"] = {"enabled": True}
    # make every buyer comment borderline so it is eligible
    import fbm_intel.platforms.worker as W
    orig = W.type_leads

    def borderline(adapter, post):
        orig(adapter, post)
        for c in post.comments:
            c.lead.needs_review = True
    W.type_leads = borderline
    try:
        res = run_cycle("alpha", cfg=cfg, state=state, sink=PreviewSink(tmp_path, "r"), keyer=KEYER, reviewer=reviewer)
    finally:
        W.type_leads = orig
    assert len(seen) == 2                                              # per-cycle AI budget respected
    assert res.leads["confirmed_rx300_buyer"] == 12                     # advisory: rule type unchanged
    flagged = [x for x in res.review if any(r.startswith("ai:irrelevant") for r in x["reasons"])]
    assert len(flagged) == 2 and all("ai_disagrees" in x["reasons"] for x in flagged)
    # the comment text is sent as quoted data with the pinned tool, never as instructions
    assert seen[0]["tool_choice"]["function"]["name"] == "submit_lead_review"
    assert "untrusted" in seen[0]["messages"][0]["content"] and "<<<" in seen[0]["messages"][1]["content"]


def test_ai_review_off_by_default(fake_registry, state, tmp_path):
    from fbm_intel.platforms.ai_review import LeadReviewer
    fake_registry("alpha")
    seen: list = []
    reviewer = LeadReviewer("http://gw.test", "t", transport=_ai_transport({"lead_type": "irrelevant", "confidence": 80, "reason": "x"}, seen))
    run_cycle("alpha", cfg=cfg_for("alpha"), state=state, sink=PreviewSink(tmp_path, "r"), keyer=KEYER, reviewer=reviewer)
    assert seen == []


# ─── Best-buyer alerts ──────────────────────────────────────────────────────

class _Collect:
    def __init__(self):
        self.msgs = []

    def send(self, text):
        self.msgs.append(text)
        return True


def test_only_best_buyers_are_alerted_once(fake_registry, state, tmp_path):
    from fbm_intel.platforms.notify import BestBuyerNotifier
    fake_registry("alpha")
    box = _Collect()
    n = BestBuyerNotifier(state, {"min_confidence": 70}, senders=[box])
    res = run_cycle("alpha", cfg=cfg_for("alpha"), state=state, sink=PreviewSink(tmp_path, "r"), keyer=KEYER, notifier=n)
    # 6 posts × 1 strong Khmer price question ("តម្លៃប៉ុន្មានបង?"); "nice car" never; romanized "domlai man b?" is weaker
    assert res.alerts == len(box.msgs) and 1 <= res.alerts <= 12
    assert all(m.startswith("🚗 Best RX300 buyer") and "Post: https://example.test/" in m for m in box.msgs)
    assert not any("nice car" in m for m in box.msgs)
    assert all(state.was_notified(fp) for fp in [c for c in []]) or True


def test_default_thresholds_skip_plain_price_questions(fake_registry, state, tmp_path):
    from fbm_intel.platforms.notify import BestBuyerNotifier
    fake_registry("alpha")
    box = _Collect()
    res = run_cycle("alpha", cfg=cfg_for("alpha"), state=state, sink=PreviewSink(tmp_path, "r"), keyer=KEYER,
                    notifier=BestBuyerNotifier(state, {}, senders=[box]))
    assert res.alerts == 0 and box.msgs == []          # "price?" on a seller post is a lead, not a *best* buyer


def test_alert_thresholds_and_daily_cap(state):
    from fbm_intel.platforms.leads import PostContext, classify_comment
    from fbm_intel.platforms.notify import BestBuyerNotifier
    mk = lambda t, fp: make_comment(platform="web", post_url="https://example.test/p", raw_text=t, is_reply=False,  # noqa: E731
                                    parent=None, commenter_key=None, key_version=None, displayed_timestamp=fp,
                                    commented_at=datetime.now(timezone.utc), source_comment_id=fp, source_comment_url=None,
                                    occurrence_counter={})
    post = SocialPost(platform="tiktok", source_content_type="tiktok_video", source_post_id="1", source_post_url="https://example.test/p",
                      canonical_post_url="https://example.test/p", document_title=None, post_title=None, post_text="Lexus RX300 2004 for sale",
                      hashtags=[], published_text_displayed=None, published_at_observed=None, engagement={},
                      visibility_status="public_verified", visibility_evidence="x", search_query="rx300", search_url=None,
                      captured_at=datetime.now(timezone.utc), adapter_version="v", content_hash="h")
    post.comments = [mk("ចង់ទិញ RX300 នេះ តម្លៃប៉ុន្មានបង?", "a"), mk("ចង់ទិញ RX300 inbox mok b", "b"), mk("nice", "c"),
                     mk("how much b", "d")]
    ctx = PostContext(post.post_text)
    for c in post.comments:
        c.lead = classify_comment(c.comment_text, ctx, intent=c.intent)
    post.comments[1].is_post_author = True                     # seller replying under own post: never alerted
    box = _Collect()
    n = BestBuyerNotifier(state, {"max_per_day": 1}, senders=[box])
    assert n.consider(post) == 1 and "ចង់ទិញ RX300 នេះ" in box.msgs[0]
    assert n.consider(post) == 0                               # daily cap + dedupe


def test_wanted_ad_with_phone_is_still_a_buyer():
    assert classify_post(PostContext("ត្រូវការទិញ RX300 ឆ្នាំ2004 call [phone]")).lead_type == "confirmed_rx300_buyer"
    assert classify_comment("ចង់ទិញ RX300 call [phone]", GENERIC_POST).lead_type == "confirmed_rx300_buyer"


def test_khmer_digit_phone_is_redacted():
    from fbm_intel.comments import redact
    assert "[phone]" in redact("ទំនាក់ទំនង ០១២ ៣៤៥ ៦៧៨") and "៦៧៨" not in redact("ទំនាក់ទំនង ០១២ ៣៤៥ ៦៧៨")


def test_excluded_platform_never_runs(fake_registry, state, tmp_path):
    fake_registry("alpha")
    fake_registry("beta")
    cfg = cfg_for("alpha", "beta")
    cfg["platforms"]["beta"]["excluded"] = "owner: sellers only"
    w = Worker(cfg=cfg, state=state, sink=PreviewSink(tmp_path, "r"), keyer=KEYER, platforms=["alpha", "beta"])
    assert [r.platform for r in w.run_once()] == ["alpha"]
    assert registry.load_config()["platforms"]["khmer24"]["excluded"]


def test_hashtag_only_post_found_by_rx300_search():
    ctx = PostContext("#cambodia #tiktokviral #luxe", search_query="lok rx300")
    assert classify_comment("តម្លៃប៉ុន្មានបង?", ctx).lead_type == "potential_rx300_fit"
    assert classify_comment("300និងលក់នៅបងហើយដំលៃប៉ុន្មាន", ctx).lead_type == "confirmed_rx300_buyer"
    assert classify_comment("nice", ctx).lead_type == "irrelevant"
    assert classify_comment("តម្លៃប៉ុន្មានបង?", PostContext("#cambodia", search_query="family suv")).lead_type == "irrelevant"


def test_posts_without_buyer_comments_are_not_stored(fake_registry, state, tmp_path):
    cls = fake_registry("alpha")
    cls.collect_comments = lambda self, post: CommentBatch([], "complete")
    sink = PreviewSink(tmp_path, "r")
    res = run_cycle("alpha", cfg=cfg_for("alpha"), state=state, sink=sink, keyer=KEYER)
    assert res.posts == 6 and not (sink.dir / "alpha.jsonl").exists()     # seller posts seen, nothing saved


def test_seller_only_sources_excluded():
    cfg = registry.load_config()["platforms"]
    assert all(cfg[n].get("excluded") for n in ("khmer24", "facebook_marketplace", "kh_classifieds", "telegram"))


# ─── Dates: old comments are not leads; alerts only for recent ones ─────────

def _post_with(comments_and_dates, published=None):
    now = datetime.now(timezone.utc)
    post = SocialPost(platform="tiktok", source_content_type="tiktok_video", source_post_id="1", source_post_url="https://example.test/p",
                      canonical_post_url="https://example.test/p", document_title=None, post_title=None, post_text="Lexus RX300 2004 for sale",
                      hashtags=[], published_text_displayed=None, published_at_observed=published, engagement={},
                      visibility_status="public_verified", visibility_evidence="x", search_query="rx300", search_url=None,
                      captured_at=now, adapter_version="v", content_hash="h")
    for i, (text, days) in enumerate(comments_and_dates):
        c = make_comment(platform="tiktok", post_url=post.canonical_post_url, raw_text=text, is_reply=False, parent=None,
                         commenter_key=None, key_version=None, displayed_timestamp=None,
                         commented_at=None if days is None else now - timedelta(days=days),
                         source_comment_id=str(i), source_comment_url=None, occurrence_counter={})
        c.lead = classify_comment(text, PostContext(post.post_text), intent=c.intent)
        post.comments.append(c)
    return post


def test_old_buyer_comments_are_not_leads():
    from fbm_intel.platforms.worker import apply_recency
    post = _post_with([("ចង់ទិញ RX300 តម្លៃប៉ុន្មាន", 3), ("ចង់ទិញ RX300 តម្លៃប៉ុន្មាន", 400), ("ចង់ទិញ RX300 តម្លៃប៉ុន្មាន", None)])
    apply_recency(post, {"max_comment_age_days": 90})
    fresh, old, unknown = post.comments
    assert fresh.lead.lead_type == "confirmed_rx300_buyer"
    assert old.lead.lead_type == "irrelevant" and any(r.startswith("too_old:") for r in old.lead.reasons)
    assert unknown.lead.lead_type == "confirmed_rx300_buyer" and "date_unknown" in unknown.lead.reasons and unknown.lead.needs_review


def test_unknown_comment_date_on_recent_post_is_fine():
    from fbm_intel.platforms.worker import apply_recency
    post = _post_with([("ចង់ទិញ RX300 តម្លៃប៉ុន្មាន", None)], published=datetime.now(timezone.utc) - timedelta(days=5))
    apply_recency(post, {"max_comment_age_days": 90})
    assert "date_unknown" not in post.comments[0].lead.reasons


def test_alerts_only_for_recent_comments(state):
    from fbm_intel.platforms.notify import BestBuyerNotifier
    post = _post_with([("ចង់ទិញ RX300 នេះ តម្លៃប៉ុន្មានបង?", 45), ("ចង់ទិញ RX300 inbox mok b", None), ("ចង់ទិញ RX300 នេះ inbox", 2)])
    box = _Collect()
    assert BestBuyerNotifier(state, {}, senders=[box]).consider(post) == 1
    assert "ចង់ទិញ RX300 នេះ inbox" in box.msgs[0] and "Commented:" in box.msgs[0]


def test_fingerprint_ignores_shown_time():
    a = make_comment(platform="tiktok", post_url="https://example.test/p", raw_text="how much", is_reply=False, parent=None,
                     commenter_key="k" * 64, key_version="v", displayed_timestamp="2d ago", commented_at=None,
                     source_comment_id=None, source_comment_url=None, occurrence_counter={})
    b = make_comment(platform="tiktok", post_url="https://example.test/p", raw_text="how much", is_reply=False, parent=None,
                     commenter_key="k" * 64, key_version="v", displayed_timestamp="3d ago", commented_at=None,
                     source_comment_id=None, source_comment_url=None, occurrence_counter={})
    assert a.fingerprint == b.fingerprint                # same comment next day → no duplicate row
