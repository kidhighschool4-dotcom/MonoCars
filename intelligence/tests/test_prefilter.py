from datetime import datetime, timedelta, timezone

from fbm_intel.prefilter import KnownListing, detect_hard_rejections, prefilter
from fbm_intel.schemas import PageState, RawListingObservation

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def obs(**kw) -> RawListingObservation:
    base = dict(source_platform="fbm", source_listing_id="abc", source_url="https://fbm.test/cars/abc",
                canonical_url="https://fbm.test/cars/abc", title_raw="2020 Toyota Camry", description_raw="Clean car",
                price_text_raw="$18,500", location_text_raw="Phnom Penh", captured_at=NOW, adapter_version="t",
                published_at_observed=NOW - timedelta(days=2))
    base.update(kw)
    return RawListingObservation(**base)


def run(o, brief, known=(), **kw):
    args = dict(listing_id="L1", canonical_url_hash="u1", content_hash="c1", perceptual_hash="0f0f0f0f0f0f0f0f",
                has_screenshot=True, brief=brief, known=list(known), max_age_days=30, now=NOW)
    args.update(kw)
    return prefilter(o, **args)


def known(**kw):
    base = dict(id="K1", canonical_url_hash="other", source_platform="fbm", source_listing_id="zzz",
                content_hash="other", perceptual_hash="ffffffffffffffff")
    base.update(kw)
    return KnownListing(**base)


def test_clean_listing_passes(brief):
    assert run(obs(), brief).outcome == "pass"


def test_duplicate_by_canonical_url(brief):
    r = run(obs(), brief, [known(canonical_url_hash="u1")])
    assert (r.outcome, r.duplicate_of, r.reason_codes) == ("duplicate", "K1", ["duplicate_canonical_url"])


def test_duplicate_by_platform_id(brief):
    assert run(obs(), brief, [known(source_listing_id="abc")]).reason_codes == ["duplicate_source_listing_id"]


def test_duplicate_by_content_hash(brief):
    assert run(obs(), brief, [known(content_hash="c1")]).reason_codes == ["duplicate_content_hash"]


def test_duplicate_by_near_identical_screenshot_and_title(brief):
    r = run(obs(), brief, [known(perceptual_hash="0f0f0f0f0f0f0f0e", title_key="2020 toyota camry")])  # 1 bit apart
    assert r.reason_codes == ["duplicate_screenshot_phash"]


def test_shared_placeholder_photo_is_not_a_duplicate(brief):
    # found in the live run: two different cars both showing "Photo coming soon"
    assert run(obs(), brief, [known(perceptual_hash="0f0f0f0f0f0f0f0f", title_key="2021 honda accord")]).outcome == "pass"


def test_different_screenshot_is_not_duplicate(brief):
    assert run(obs(), brief, [known(perceptual_hash="f0f0f0f0f0f0f0f0")]).outcome == "pass"


def test_self_is_never_a_duplicate(brief):
    assert run(obs(), brief, [known(id="L1", canonical_url_hash="u1")]).outcome == "pass"


def test_english_and_khmer_hard_rejections(brief):
    assert run(obs(title_raw="Toyota Camry for rent daily"), brief).reason_codes == ["hard_rejection_rental_only"]
    assert run(obs(title_raw="ជួលឡាន Camry"), brief).reason_codes == ["hard_rejection_rental_only"]
    assert run(obs(description_raw="Selling spare parts only"), brief).reason_codes == ["hard_rejection_parts_only"]
    assert "wanted_to_buy" in detect_hard_rejections("ត្រូវការទិញឡាន Prius")


def test_ambiguous_khmer_goes_to_vision_not_rejected(brief):
    # Khmer sale post without any clear rejection phrase must NOT be rejected by English-only rules (§8.5)
    assert run(obs(title_raw="ឡាន Toyota Prius លក់ ភ្នំពេញ", description_raw="ឡានស្អាត"), brief).outcome == "pass"


def test_unsupported_location_only_when_known(brief):
    assert run(obs(location_text_raw="Kampong Cham"), brief).reason_codes == ["unsupported_location"]
    assert run(obs(location_text_raw="somewhere unclear"), brief).outcome == "pass"


def test_stale_listing(brief):
    assert run(obs(published_at_observed=NOW - timedelta(days=45)), brief).reason_codes == ["stale_listing"]


def test_missing_screenshot_and_sold(brief):
    r = run(obs(page_state=PageState.SOLD_OR_REMOVED), brief, has_screenshot=False)
    assert r.reason_codes == ["missing_screenshot", "page_state_sold_or_removed"]
