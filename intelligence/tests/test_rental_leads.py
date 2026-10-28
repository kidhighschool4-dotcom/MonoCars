"""Rental-seeker lead typing, post rating and the campaign switch."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fbm_intel.platforms import campaign
from fbm_intel.platforms.discovery import queries_for
from fbm_intel.platforms.leads import LeadResult
from fbm_intel.platforms.rental_leads import PostContext, classify_comment, classify_post, kind_of, lift_intent, score_post
from fbm_intel.social.intent_score import score_comment

LISTING = PostContext(text="ផ្ទះជួល នៅទួលគោក 350$/ខែ 2 បន្ទប់គេង")


@pytest.mark.parametrize("text", [
    "ខ្ញុំចង់ជួល", "តម្លៃប៉ុន្មាន?", "ផ្ទះនេះនៅទំនេរទេ", "how much per month?", "still available?",
    "I am looking for a room to rent near AUPP", "can i see the room tomorrow", "មានបន្ទប់ទំនេរទេបង", "jong chhoul ptes nis",
])
def test_seekers_under_a_listing(text):
    assert classify_comment(text, LISTING).lead_type == "rental_seeker"


@pytest.mark.parametrize("text", [
    "មានបន្ទប់ទំនេរ ទំនាក់ទំនង 012345678", "we have more rooms, dm if interested", "ខ្ញុំមានផ្ទះជួលនៅសែនសុខ",
])
def test_landlords_and_agents(text):
    assert classify_comment(text, LISTING).lead_type == "seller_or_dealer"


@pytest.mark.parametrize("text", ["អត់ចង់ជួលទេ", "I don't want to rent", "nice house", "ot jong chhoul te"])
def test_not_seekers(text):
    assert classify_comment(text, LISTING).lead_type == "irrelevant"


def test_author_business_and_non_rental_posts():
    assert classify_comment("still available?", LISTING, is_post_author=True).lead_type == "seller_or_dealer"
    assert classify_comment("still available?", LISTING, is_business=True).lead_type == "seller_or_dealer"
    news = PostContext(text="Breaking news: flood in Phnom Penh")
    assert classify_comment("តម្លៃប៉ុន្មាន?", news).lead_type == "irrelevant"
    assert classify_comment("I need a room to rent in BKK1", news).lead_type == "rental_seeker"  # says it outright


def test_posts_and_kinds():
    assert classify_post(LISTING).lead_type == "seller_or_dealer"
    assert classify_post(PostContext(text="រកបន្ទប់ជួល ក្បែរ AUPP តម្លៃក្រោម 150$")).lead_type == "rental_seeker"
    assert classify_post(PostContext(text="RX300 for sale 1999")).lead_type == "irrelevant"
    assert kind_of(LISTING.text) == "house"                       # "2 bedrooms" is not a room rental
    assert kind_of("condo for rent BKK1") == "apartment"
    assert kind_of("shophouse for rent near market") == "commercial"
    assert kind_of("បន្ទប់ជួល 80$") == "room"


def test_rent_words_lift_the_intent_score():
    i = score_comment("ខ្ញុំចង់ជួល")
    assert i.buyer_intent_score < 70
    lead = classify_comment("ខ្ញុំចង់ជួល", LISTING, intent=i)
    lift_intent(i, lead)
    assert i.buyer_intent_score == lead.confidence and i.buyer_intent_label == "strong_buyer_intent"


class _C:
    def __init__(self, lt, conf):
        self.lead = LeadResult(lt, None, False, False, conf)


class _P:
    def __init__(self, comments, days_old=None, engagement=None, lead="seller_or_dealer"):
        self.comments = comments
        self.published_at_observed = None if days_old is None else datetime.now(timezone.utc) - timedelta(days=days_old)
        self.engagement = engagement or {}
        self.lead = LeadResult(lead, None, False, False, 75, reasons=["rental_listing"])


def test_post_rating_ranks_lead_rich_fresh_posts_first():
    busy = _P([_C("rental_seeker", 90)] * 4 + [_C("irrelevant", 60)], days_old=2, engagement={"like": "1.2K", "comment": "40"})
    quiet = _P([_C("irrelevant", 60)], days_old=200)
    s_busy, d_busy = score_post(busy)
    s_quiet, _ = score_post(quiet)
    assert 0 <= s_quiet < s_busy <= 100
    assert d_busy["seekers"] == 4 and d_busy["fresh"] == 20 and d_busy["relevance"] == 10
    assert score_post(_P([_C("rental_seeker", 95)] * 20, days_old=1, engagement={"like": "9M"}))[0] == 100


@pytest.mark.rental_campaign
def test_shipped_config_runs_the_rental_campaign():
    c = campaign.current()
    assert c.name == "rental" and c.focus == "rental_seeker"
    qs = [q.text for q in queries_for("tiktok", config_path=c.discovery_path)]
    assert qs and not any("rx300" in q.casefold() for q in qs)
    assert any("ផ្ទះជួល" in q for q in qs) and any("phnom penh" in q.casefold() for q in qs)


def test_group_post_url_from_photo_set():
    from fbm_intel.fb_public.urls import group_post_url_from_photo_set, is_group_post
    u = group_post_url_from_photo_set("https://www.facebook.com/photo/?fbid=123456&set=gm.1234567890123456&idorvanity=987654321098765")
    assert u == "https://www.facebook.com/groups/987654321098765/posts/1234567890123456" and is_group_post(u)
    assert group_post_url_from_photo_set("https://www.facebook.com/photo/?fbid=1&set=a.123456") is None          # album, not a post
    assert group_post_url_from_photo_set("https://www.facebook.com/photo/?fbid=1&set=gm.1234567") is None         # no group
    assert group_post_url_from_photo_set("https://example.com/photo/?set=gm.1234567&idorvanity=55555") is None
