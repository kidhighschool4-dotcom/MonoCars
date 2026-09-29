"""Adapter contract tests (§16.2) and a full pipeline run against saved fixtures — real Chromium, no network."""
from __future__ import annotations

import pytest

from fbm_intel.adapters import FbmAdapter, ManualUrlAdapter, ResultRef
from fbm_intel.browser import BlockedError, BlockStatus, open_session
from fbm_intel.normalize import sha256_hex
from fbm_intel.orchestrator import Pipeline, RunReport
from fbm_intel.schemas import PageState
from fbm_intel.scoring import RankingPolicy
from fbm_intel.vision import StaticVisionProvider

from .conftest import GOOD_OUTPUT
from .memory_store import MemoryStore

pytestmark = pytest.mark.browser


# ─── Adapter contract ───────────────────────────────────────────────────────

def test_search_extraction_and_evidence(fixture_site):
    a = FbmAdapter(fixture_site)
    with open_session(a.allowed_hosts, min_interval_s=0) as s:
        state = a.open_search(s, "camry")
        refs = a.collect_result_refs(s, state)
        assert [r.source_listing_id for r in refs][:3] == ["ok-camry", "km-prius", "rental-camry"]
        assert len(refs) == 7 and a.advance(s, state).done  # single page → pagination terminates

        ok = next(r for r in refs if r.source_listing_id == "ok-camry")
        a.open_listing(s, ok)
        obs = a.extract_observation(s, ok)
        assert (obs.title_raw, obs.price_text_raw, obs.location_text_raw) == ("2020 Toyota Camry", "$18,500", "Phnom Penh")
        assert obs.page_state == PageState.OK and obs.published_at_observed.year == 2026
        assert obs.seller_display_name is None  # data minimization
        ev = a.capture_evidence(s, ok.url)
        assert ev.checksum_sha256 == sha256_hex(ev.png_bytes) and ev.width == 932  # 900px + 2×16px padding
        assert ev.visibility == {"title": True, "price": True, "location": True, "primary_image": True, "description": True}


def test_evidence_crop_excludes_seller_contact(fixture_site):
    a = FbmAdapter(fixture_site)
    with open_session(a.allowed_hosts, min_interval_s=0) as s:
        ref = ResultRef(url=f"{fixture_site}/cars/ok-camry", source_listing_id="ok-camry")
        a.open_listing(s, ref)
        crop_text = a.evidence_locator(s).inner_text()
        assert "+855" not in crop_text and "Private Person" not in crop_text


def test_khmer_and_sold_listings(fixture_site):
    a = FbmAdapter(fixture_site)
    with open_session(a.allowed_hosts, min_interval_s=0) as s:
        km = ResultRef(url=f"{fixture_site}/cars/km-prius", source_listing_id="km-prius")
        a.open_listing(s, km)
        assert a.extract_observation(s, km).title_raw == "ឡាន Toyota Prius 2012 លក់ ភ្នំពេញ"
        sold = ResultRef(url=f"{fixture_site}/cars/sold-crv", source_listing_id="sold-crv")
        a.open_listing(s, sold)
        assert a.extract_observation(s, sold).page_state == PageState.SOLD_OR_REMOVED


def test_bot_challenge_stops_immediately(fixture_site):
    a = FbmAdapter(fixture_site)
    with open_session(a.allowed_hosts, min_interval_s=0) as s:
        with pytest.raises(BlockedError) as e:
            s.goto(f"{fixture_site}/blocked/")
        assert e.value.status == BlockStatus.BOT_CHALLENGE


def test_navigation_outside_allowlist_is_refused(fixture_site):
    a = FbmAdapter(fixture_site)
    with open_session(a.allowed_hosts, min_interval_s=0) as s:
        with pytest.raises(PermissionError):
            s.goto("https://example.com/")
        # a page-initiated navigation to another host is aborted by the route guard
        s.goto(f"{fixture_site}/cars/")
        s.page.evaluate("() => { const f = document.createElement('iframe'); f.src = 'https://example.com/'; document.body.appendChild(f) }")
        s.page.wait_for_timeout(500)
        assert any("example.com" in u for u in s.blocked_navigations)


class TestManualUrl:
    def test_rejects_unapproved_hosts_and_schemes(self):
        a = ManualUrlAdapter({"fbm-pied.vercel.app"})
        for bad in ["http://fbm-pied.vercel.app/cars/1", "https://evil.com/cars/1", "https://user:pw@fbm-pied.vercel.app/",
                    "https://fbm-pied.vercel.app.evil.com/"]:
            with pytest.raises((ValueError, PermissionError)):
                a.check_url(bad)
        assert a.check_url("https://fbm-pied.vercel.app/cars/1")

    def test_extracts_open_graph(self, fixture_site):
        a = ManualUrlAdapter({"127.0.0.1"})
        with open_session(a.allowed_hosts, min_interval_s=0) as s:
            ref = ResultRef(url=f"{fixture_site}/manual/")
            a.open_listing(s, ref)
            obs = a.extract_observation(s, ref)
            assert (obs.title_raw, obs.price_text_raw) == ("2022 Toyota Fortuner", "38500 USD")
            assert a.capture_evidence(s, ref.url).width > 0


# ─── Full pipeline on fixtures ──────────────────────────────────────────────

def test_full_pipeline_is_correct_and_idempotent(fixture_site, brief, profile):
    store = MemoryStore()
    provider = StaticVisionProvider(default=GOOD_OUTPUT)
    pipe = Pipeline(store, provider, brief, profile, ranking_policy=RankingPolicy(minimum_acceptable_score=75))
    terms = [{"id": "t1", "text": "camry"}]

    run = store.create_crawl_run(profile.id, "test")
    report = RunReport(crawl_run_id=run["id"])
    pipe.crawl(FbmAdapter(fixture_site), terms, report)
    pipe.evaluate_pending(report)
    pipe.score_evaluated(report)
    ranking = pipe.rank_profile(report)

    states = {l["source_listing_id"]: l["lifecycle_status"] for l in store.t["listings"]}
    assert states["rental-camry"] == "prefilter_rejected"   # clear hard rejection, no paid vision call
    assert states["sold-crv"] == "prefilter_rejected"       # sold page
    assert states["far-away"] == "prefilter_rejected"       # Kampong Cham is outside the brief
    assert states["dup-camry"] == "duplicate"               # same content as ok-camry
    assert {states[k] for k in ("ok-camry", "km-prius", "inject-lexus")} == {"ranked"}
    assert provider.calls == 3                              # only non-duplicate, non-rejected listings evaluated
    assert report.counters.duplicates == 1 and report.counters.prefilter_rejected == 3

    assert ranking["status"] in ("recommended", "manual_review") and ranking["selected"]
    members = store.t["ranking_members"]
    assert len(members) == 3 and sum(m["selected"] for m in members) == 1
    assert all(m["component_scores"] and m["reason_codes"] for m in members)
    assert any(t["reason"].startswith("recommendation_") for t in store.t["review_tasks"])  # human approval required

    # audit: every listing has a complete, legal transition history
    ok_id = next(l["id"] for l in store.t["listings"] if l["source_listing_id"] == "ok-camry")
    path = [e["next_state"] for e in store.t["pipeline_events"] if e["entity_id"] == ok_id]
    assert path == ["captured", "vision_pending", "vision_processing", "vision_good", "scoring_pending", "scored",
                    "eligible", "ranked"]

    # ── second run over the same site: no new paid evaluations, no new ranking run ──
    run2 = store.create_crawl_run(profile.id, "test")
    report2 = RunReport(crawl_run_id=run2["id"])
    pipe.crawl(FbmAdapter(fixture_site), terms, report2)
    pipe.evaluate_pending(report2)
    pipe.score_evaluated(report2)
    ranking2 = pipe.rank_profile(report2)
    assert provider.calls == 3 and report2.counters.listings_captured == 0
    assert len(store.t["vision_evaluations"]) == 3
    assert ranking2["ranking_run_id"] == ranking["ranking_run_id"] and ranking2["new"] is False


def test_blocked_platform_stops_run(fixture_site, brief, profile):
    class BlockingAdapter(FbmAdapter):
        def build_search_url(self, query, filters=None):
            return f"{self.base_url}/blocked/"

    store = MemoryStore()
    provider = StaticVisionProvider(default=GOOD_OUTPUT)
    pipe = Pipeline(store, provider, brief, profile)
    run = store.create_crawl_run(profile.id, "test")
    report = RunReport(crawl_run_id=run["id"])
    pipe.crawl(BlockingAdapter(fixture_site), [{"id": "t1", "text": "a"}, {"id": "t2", "text": "b"}], report)
    assert report.counters.blocks == 1 and report.counters.queries_attempted == 1  # stopped, second query never ran
    assert store.t["crawl_queries"][0]["status"] == "blocked" and provider.calls == 0


def test_vision_failure_is_recorded_not_dropped(fixture_site, brief, profile):
    store = MemoryStore()
    provider = StaticVisionProvider(default={**GOOD_OUTPUT, "decision": "not-a-decision"})
    pipe = Pipeline(store, provider, brief, profile)
    run = store.create_crawl_run(profile.id, "test")
    report = RunReport(crawl_run_id=run["id"])
    pipe.crawl(FbmAdapter(fixture_site), [{"id": "t1", "text": "camry"}], report, listing_budget=1)
    pipe.evaluate_pending(report)
    listing = store.t["listings"][0]
    assert listing["lifecycle_status"] == "terminal_error"
    assert store.t["job_failures"][0]["error_class"] == "VisionSchemaError"
    assert store.t["review_tasks"][0]["reason"] == "vision_evaluation_failed"  # §14.3 never silently dropped


def test_policy_change_reprefilter(fixture_site, brief, profile):
    """Listings rejected as stale under v1 are re-checked under v2 without re-crawling or re-paying."""
    store = MemoryStore()
    provider = StaticVisionProvider(default=GOOD_OUTPUT)
    strict = profile.model_copy(update={"maximum_listing_age_days": 1})
    pipe = Pipeline(store, provider, brief, strict)
    run = store.create_crawl_run(profile.id, "test")
    report = RunReport(crawl_run_id=run["id"])
    pipe.crawl(FbmAdapter(fixture_site), [{"id": "t1", "text": "camry"}], report)
    stale = [l for l in store.t["listings"] if l["status_reason"] == "stale_listing"]
    assert {l["source_listing_id"] for l in stale} >= {"ok-camry", "km-prius"} and provider.calls == 0

    relaxed = Pipeline(store, provider, brief, profile.model_copy(update={"maximum_listing_age_days": 3650, "version": 2}))
    r2 = RunReport()
    n = relaxed.reprefilter(r2)
    assert n >= len(stale)
    states = {l["source_listing_id"]: l["lifecycle_status"] for l in store.t["listings"]}
    assert states["ok-camry"] == "vision_pending" and states["rental-camry"] == "prefilter_rejected"
    assert states["dup-camry"] == "duplicate"
