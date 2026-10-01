"""Owner's profile-handling rules: individuals stay anonymous; only clear businesses keep page name/URL/screenshot."""
from __future__ import annotations

import copy

import pytest

from fbm_intel.browser import open_session
from fbm_intel.platforms import registry
from fbm_intel.platforms.base import capture_business_page_in, extract_business_info
from fbm_intel.platforms.leads import PostContext, classify_comment
from fbm_intel.platforms.sinks import PreviewSink, comment_record
from fbm_intel.platforms.state import WorkerState
from fbm_intel.platforms.worker import run_cycle
from fbm_intel.social.accounts import classify_account
from fbm_intel.social.model import make_comment

from .fixtures import tiktok_site
from .platform_contract import KEYER, make_ctx

V1 = "https://www.tiktok.com/@dealer.kh/video/7400000000000000001"


def test_account_classification():
    biz = classify_account("Sok Auto Import Co., Ltd", "https://www.facebook.com/sokauto")
    assert biz.type == "business" and biz.business_page_name == "Sok Auto Import Co., Ltd" and biz.business_page_url
    person = classify_account("Dara Sok", "https://www.facebook.com/dara.sok")
    assert person.type == "individual" and person.business_page_name is None and person.business_page_url is None
    assert classify_account(None, None, has_profile=False).type == "unknown"


def test_business_fields_only_for_businesses():
    c = make_comment(platform="tiktok", post_url=V1, raw_text="how much", is_reply=False, parent=None, commenter_key="k" * 64,
                     key_version="v", displayed_timestamp=None, commented_at=None, source_comment_id="1",
                     source_comment_url=None, occurrence_counter={})
    assert c.account_type == "individual" and c.identity_redacted and c.source_post_url == V1
    c.set_account(classify_account("Dara Sok", "https://x"))
    rec = comment_record(c)
    assert rec["business_page_name"] is None and rec["business_page_url"] is None and rec["business_page_screenshot"] is None


def test_business_commenter_is_never_a_buyer_lead():
    r = classify_comment("how much is the RX300?", PostContext("Lexus RX300 for sale"), is_business=True)
    assert r.lead_type == "seller_or_dealer" and "business_account" in r.reasons


def test_personal_profiles_are_never_opened():
    ad = registry.get("tiktok")(make_ctx("tiktok", fixtures=lambda s: None))
    with pytest.raises(PermissionError):
        capture_business_page_in(ad, "https://www.tiktok.com/@dara.sok", "individual")
    with pytest.raises(PermissionError):
        capture_business_page_in(ad, "https://www.tiktok.com/@dara.sok", "unknown")


def test_business_info_extraction_is_business_only():
    info = extract_business_info(["Page · Car dealership", "Street 271, Phnom Penh", "Call 012 888 999", "info@sokauto.example",
                                  "Some Follower Person"], ["https://www.sokauto.example/", "https://www.tiktok.com/@x"], ("tiktok.com",))
    assert info["category"] == "Car dealership" and "Phnom Penh" in info["sales_location"]
    assert info["contact_channels"] == {"phone": ["012 888 999"], "email": ["info@sokauto.example"], "website": ["https://www.sokauto.example/"]}


@pytest.mark.browser
def test_tiktok_cycle_business_vs_individual(tmp_path):
    cfg = registry.load_config()
    cfg["platforms"]["tiktok"].update(enabled=True, rate={"min_interval_s": 0}, discovery={"queries": ["car sedan"]},
                                      save_posts_without_buyers=True,
                                      limits_override={"settle_ms": 200, "scroll_pause_ms": 250, "page_load_interval_s": 0,
                                                       "comment_time_limit_s": 40})
    cfg["recency"] = {}
    sink = PreviewSink(tmp_path, "r")
    res = run_cycle("tiktok", cfg=cfg, state=WorkerState(tmp_path / "s.sqlite"), sink=sink, keyer=KEYER, headed=False,
                    fixtures=lambda s: tiktok_site.install(s.context))
    assert res.state in ("ok", "budget_exhausted"), res.detail
    import json
    rows = [json.loads(x) for x in (sink.dir / "tiktok.jsonl").read_text().splitlines()]
    comments = [c for r in rows for c in r["comments"]]
    biz = [c for c in comments if c["account_type"] == "business"]
    assert len(biz) == 1 and biz[0]["business_page_url"] == "https://www.tiktok.com/@sok.auto.import"
    assert biz[0]["lead"]["lead_type"] == "seller_or_dealer"
    assert biz[0]["business_page_screenshot"] and biz[0]["business_page_screenshot"].get("file")
    for c in comments:
        if c["account_type"] != "business":
            assert c["business_page_name"] is None and c["business_page_url"] is None and c["business_page_screenshot"] is None
            assert c["identity_redacted"] is True and c["source_post_url"] == V1
    # the public post URL is kept on purpose (owner's rule); everything else about individuals must be anonymous
    blob = json.dumps([{k: v for k, v in c.items() if k != "source_post_url"} for c in comments if c["account_type"] != "business"],
                      ensure_ascii=False)
    for leak in ("buyer.one", "Visible", "Some Follower Person", "/@"):
        assert leak not in blob
