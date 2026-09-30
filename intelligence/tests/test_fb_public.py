"""FacebookPublicPostsAdapter: canonicalization, visibility, HMAC keys, comment building, and a full routed-browser crawl."""
from __future__ import annotations

import hashlib
import json

import pytest

from fbm_intel.fb_public import collector
from fbm_intel.fb_public.adapter import FacebookPublicPostsAdapter
from fbm_intel.fb_public.identity import PersonKeyer
from fbm_intel.fb_public.model import Limits, PublicPost, RawComment, build_comments
from fbm_intel.fb_public.urls import (NotFacebookUrl, canonical_comment_url, canonical_post_url, canonical_profile_url,
                                      comment_ids, is_group_post, post_id)
from fbm_intel.fb_public.visibility import VisibilitySignals, verify

from .fixtures import fb_public_site

SECRET = "k" * 64
KEYER = PersonKeyer(SECRET, "hmac-sha256-v1")
FAST = Limits(page_load_interval_s=0, settle_ms=150, scroll_pause_ms=100, expansion_click_pause_ms=80, max_search_scrolls=1)
POST = "https://www.facebook.com/carshop.pp/posts/pfbid0111"


# ─── URL canonicalization / tracking removal ────────────────────────────────

class TestUrls:
    @pytest.mark.parametrize("raw", [
        "https://web.facebook.com/carshop.pp/posts/pfbid0111?__cft__[0]=AZX&__tn__=%2CO%2CP-R",
        "https://m.facebook.com/carshop.pp/posts/pfbid0111/?mibextid=abc#comments",
        "http://www.facebook.com//carshop.pp/posts/pfbid0111/?rdid=1&share_url=x&_rdc=1&_rdr",
    ])
    def test_post_tracking_removed(self, raw):
        assert canonical_post_url(raw) == POST

    def test_permalink_keeps_identity_params_only(self):
        assert canonical_post_url("https://facebook.com/permalink.php?ref=x&id=42&story_fbid=99&__cft__=y") == \
            "https://www.facebook.com/permalink.php?story_fbid=99&id=42"

    def test_post_ids(self):
        assert post_id(POST) == "pfbid0111"
        assert post_id("https://www.facebook.com/groups/carskh/posts/444/") == "444"
        assert post_id("https://www.facebook.com/permalink.php?story_fbid=99&id=42") == "99"
        assert is_group_post("https://www.facebook.com/groups/carskh/posts/444/")
        assert post_id("https://www.facebook.com/carshop.pp") is None

    def test_comment_permalinks(self):
        assert comment_ids(POST + "?comment_id=C1&reply_comment_id=R2&__cft__=x") == ("C1", "R2")
        assert canonical_comment_url(POST, "C1", "R2") == POST + "?comment_id=C1&reply_comment_id=R2"
        assert canonical_comment_url(POST, None, None) is None

    @pytest.mark.parametrize("raw,canon", [
        ("https://www.facebook.com/Dara.Buyer?comment_id=C1&__cft__[0]=b", "https://www.facebook.com/dara.buyer"),
        ("https://web.facebook.com/profile.php?id=100012345&__tn__=R", "https://www.facebook.com/profile.php?id=100012345"),
        ("https://www.facebook.com/people/Sok-Ha/100077788/", "https://www.facebook.com/profile.php?id=100077788"),
        ("https://www.facebook.com/groups/carskh", None),
        ("https://www.facebook.com/hashtag/cars", None),
        ("https://www.facebook.com/profile.php?id=abc", None),
        ("https://example.com/dara", None),
        (None, None),
    ])
    def test_profile_urls(self, raw, canon):
        assert canonical_profile_url(raw) == canon

    def test_post_url_from_photo_set(self):
        from fbm_intel.fb_public.urls import post_url_from_photo_set as f
        photo = "https://www.facebook.com/photo/?fbid=111&set=pcb.1234567890&__cft__[0]=x"
        assert f(photo, "https://web.facebook.com/CHANGAN.Cambodia?__tn__=R") == "https://www.facebook.com/changan.cambodia/posts/1234567890"
        assert f(photo, "https://www.facebook.com/profile.php?id=42") == \
            "https://www.facebook.com/permalink.php?story_fbid=1234567890&id=42"
        assert f("https://www.facebook.com/photo/?fbid=1&set=a.999", "https://www.facebook.com/x") is None  # album, not a post
        assert f(photo, None) is None

    def test_rejects_non_facebook(self):
        with pytest.raises(NotFacebookUrl):
            canonical_post_url("https://evil-facebook.com/x/posts/1")


# ─── Visibility ─────────────────────────────────────────────────────────────

class TestVisibility:
    def sig(self, labels=(), group=False, gtexts=(), unavailable=False):
        return VisibilitySignals(url=POST, is_group_post=group, audience_labels=tuple(labels),
                                 group_privacy_texts=tuple(gtexts), content_unavailable=unavailable)

    def test_public_icon(self):
        v = verify(self.sig(["Shared with Public"]))
        assert v.verified and v.evidence == "audience_icon:Shared with Public"

    @pytest.mark.parametrize("label", ["Shared with Friends", "Friends", "Custom", "Only me", "Friends of friends"])
    def test_friends_only_rejected(self, label):
        v = verify(self.sig([label]))
        assert not v.verified and v.status == "restricted"

    def test_no_evidence_is_unverified(self):
        v = verify(self.sig(["Like", "Comment"]))
        assert (v.status, v.skip_reason) == ("unverified", "public_visibility_not_confirmed")

    def test_contradictory_is_unverified(self):
        assert verify(self.sig(["Public", "Shared with Friends"])).status == "unverified"

    def test_private_group_rejected(self):
        v = verify(self.sig(group=True, gtexts=["Cars KH · Private group"]))
        assert (v.status, v.skip_reason) == ("private", "private_group")

    def test_public_group_verified(self):
        assert verify(self.sig(group=True, gtexts=["Cars KH · Public group"])).verified

    def test_group_audience_icon_label(self):
        # seen on real Facebook search results: the group post's audience icon reads "Shared with Public group"
        assert verify(self.sig(["Shared with Public group"], group=True)).verified
        assert verify(self.sig(["Shared with Private group"], group=True)).status == "private"

    def test_group_without_privacy_text_unverified(self):
        assert verify(self.sig(["Shared with Public"], group=True)).status == "unverified"

    def test_unavailable(self):
        assert verify(self.sig(["Public"], unavailable=True)).status == "restricted"


# ─── HMAC person keys ───────────────────────────────────────────────────────

class TestKeys:
    def test_same_person_same_key_across_url_forms(self):
        a = KEYER.key("https://web.facebook.com/Dara.Buyer?comment_id=C1&__cft__[0]=b")
        assert a == KEYER.key("https://www.facebook.com/dara.buyer/") and len(a) == 64

    def test_is_keyed_not_plain_hash(self):
        url = "https://www.facebook.com/dara.buyer"
        assert KEYER.key(url) != hashlib.sha256(url.encode()).hexdigest()
        assert PersonKeyer("z" * 64, "hmac-sha256-v2").key(url) != KEYER.key(url)  # rotation changes keys

    def test_non_profile_gives_none(self):
        assert KEYER.key("https://www.facebook.com/groups/x") is None and KEYER.key(None) is None

    def test_secret_never_shown(self):
        assert SECRET not in repr(KEYER)
        with pytest.raises(ValueError):
            PersonKeyer("short", "v1")


# ─── Comment building ───────────────────────────────────────────────────────

def rc(kind, text, cid=None, rid=None, author="https://www.facebook.com/dara.buyer", parent=None):
    link = None
    if cid:
        link = f"{POST}?comment_id={cid}" + (f"&reply_comment_id={rid}" if rid else "") + "&__cft__=x"
    return RawComment(kind=kind, text=text, permalink=link, author_href=author, time_text="2d", dom_parent=parent)


class TestBuildComments:
    def test_parent_reply_relationships(self):
        out, trunc = build_comments([rc("comment", "Still available?", "C1"), rc("reply", "Yes", "C1", "R1"),
                                     rc("comment", "Price?", "C2"), rc("reply", "18k", "C1", "R2")], POST, KEYER, Limits())
        by = {c.source_comment_id: c for c in out}
        assert not trunc and [c.comment_type for c in out] == ["comment", "reply", "comment", "reply"]
        assert by["R1"].parent_fingerprint == by["C1"].fingerprint == by["R2"].parent_fingerprint
        assert by["R2"].canonical_comment_url == POST + "?comment_id=C1&reply_comment_id=R2"

    def test_dom_parent_when_no_ids(self):
        out, _ = build_comments([rc("comment", "A"), rc("reply", "B", parent=0)], POST, KEYER, Limits())
        assert out[1].parent_fingerprint == out[0].fingerprint

    def test_missing_ids_use_deterministic_fallback(self):
        raw = [rc("comment", "Nice car", author=None), rc("comment", "Nice car", author=None)]
        a, _ = build_comments(raw, POST, KEYER, Limits())
        b, _ = build_comments(raw, POST, KEYER, Limits())
        assert [c.fingerprint for c in a] == [c.fingerprint for c in b]           # stable across crawls
        assert a[0].fingerprint != a[1].fingerprint                                 # identical texts stay distinct
        assert a[0].fingerprint.startswith("fb:") and a[0].canonical_comment_url is None

    def test_missing_profile_url_gives_null_key(self):
        out, _ = build_comments([rc("comment", "hi", "C9", author=None)], POST, KEYER, Limits())
        assert out[0].commenter_key is None and out[0].commenter_key_version is None

    def test_limits_mark_truncation(self):
        raw = [rc("comment", f"c{i}", f"C{i}") for i in range(5)]
        out, trunc = build_comments(raw, POST, KEYER, Limits(max_comments_per_post=3))
        assert len(out) == 3 and trunc
        raw = [rc("comment", "p", "C1")] + [rc("reply", f"r{i}", "C1", f"R{i}") for i in range(4)]
        out, trunc = build_comments(raw, POST, KEYER, Limits(max_replies_per_comment=2))
        assert sum(c.comment_type == "reply" for c in out) == 2 and trunc

    def test_orphan_reply_skipped_not_guessed(self):
        out, _ = build_comments([rc("reply", "orphan", "C7", "R7")], POST, KEYER, Limits())
        assert out == []


# ─── Full crawl through a real browser, routed to fixtures ──────────────────

class MemoryRepo:
    """Same write contract as FacebookPublicRepo, with the same uniqueness rules."""

    def __init__(self):
        self.posts: dict[str, dict] = {}
        self.comments: dict[tuple[str, str], dict] = {}
        self.skips: list[dict] = []

    def record_skip(self, url, query, status, reason):
        self.skips.append({"url": url, "status": status, "reason": reason})

    def save_post(self, p: PublicPost):
        row = self.posts.setdefault(p.canonical_post_url, {"id": p.canonical_post_url})
        row.update(complete=p.comments_complete, reason=p.comments_incomplete_reason, evidence=p.visibility_evidence,
                   author_key=p.author_key, text=p.post_text)
        new = {"comment": 0, "reply": 0}
        for c in p.comments:
            k = (row["id"], c.fingerprint)
            if k in self.comments:
                continue
            if c.parent_fingerprint:
                assert (row["id"], c.parent_fingerprint) in self.comments  # FK: parent stored first
            self.comments[k] = c.__dict__.copy()
            new[c.comment_type] += 1
        return row["id"], new["comment"], new["reply"]


def crawl(repo, limits=FAST, query="car sedan", search_base="https://www.facebook.com"):
    def hook(s):
        hook.urls = fb_public_site.install(s.context)

    rep = collector.run(FacebookPublicPostsAdapter(KEYER, limits, search_base=search_base), query, repo=repo,
                        headless=True, check_login=False, on_session=hook)
    return rep, hook.urls


@pytest.mark.browser
def test_full_public_crawl():
    repo = MemoryRepo()
    rep, urls = crawl(repo)

    # 1. Posts search (not Marketplace) was reached
    assert rep.search_url == "https://www.facebook.com/search/posts/?q=car%20sedan"
    assert not any("/marketplace/" in u for u in urls)
    # 3. private / friends-only / unverified / changed are skipped with reasons
    reasons = {s["url"].rsplit("/", 1)[-1]: (s["visibility_status"], s["skip_reason"]) for s in rep.skipped}
    assert reasons == {"222222222": ("restricted", "not_public_audience"),
                       "333333333": ("private", "private_group"),
                       "555555555": ("unverified", "public_visibility_not_confirmed"),
                       "777777777": ("restricted", "visibility_changed")}
    assert len(repo.skips) == 4
    # 2. verified-public posts collected (tracking-variant duplicate collapsed to one)
    assert set(repo.posts) == {POST, "https://www.facebook.com/groups/carskh/posts/444444444"}
    assert repo.posts[POST]["evidence"] == "audience_icon:Shared with Public"
    # 4/5. comments + replies expanded, text captured, parent links intact
    cs = [c for (pid, _), c in repo.comments.items() if pid == POST]
    texts = {c["comment_text"] for c in cs}
    assert texts == {"Is it still available? I want to buy", "Yes still available", "How much last price?",
                     "តម្លៃប៉ុន្មាន? ខ្ញុំចង់ទិញ", "Can I see it this weekend?", "Nice car"}
    replies = [c for c in cs if c["comment_type"] == "reply"]
    assert len(replies) == 2 and all(r["parent_fingerprint"] == "id:C1" for r in replies)
    assert repo.posts[POST]["complete"] is True and repo.posts[POST]["reason"] is None
    # 6. profile links became keys WITHOUT opening any profile; no names/URLs stored
    assert not any(u.rstrip("/").endswith(("dara.buyer", "mony.kh", "100012345", "100077788")) for u in urls)
    dump = json.dumps(list(repo.comments.values()), default=str)
    for leaked in ("Visible Name", "dara.buyer", "profile.php", "Sok-Ha", "mony.kh"):
        assert leaked not in dump
    keyed = {c["source_comment_id"]: c["commenter_key"] for c in cs}
    assert keyed["C1"] == KEYER.key("https://www.facebook.com/dara.buyer")
    assert keyed["C2"] == KEYER.key("https://www.facebook.com/profile.php?id=100077788")
    assert next(c for c in cs if c["comment_text"] == "Nice car")["commenter_key"] is None
    # 8. crawling again creates no duplicates
    before = len(repo.comments)
    rep2, _ = crawl(repo)
    assert len(repo.comments) == before and rep2.new_comments == 0 and rep2.new_replies == 0


@pytest.mark.browser
def test_truncated_expansion_is_reported():
    repo = MemoryRepo()
    crawl(repo, Limits(page_load_interval_s=0, settle_ms=150, scroll_pause_ms=100, expansion_click_pause_ms=80,
                       max_search_scrolls=1, max_comment_expansion_rounds=1))
    p = repo.posts[POST]
    assert p["complete"] is False and p["reason"] == "configured_limit_reached"


@pytest.mark.browser
def test_restriction_stops_crawl_safely():
    repo = MemoryRepo()
    rep, urls = crawl(repo, search_base="https://www.facebook.com/blocked")
    assert rep.stopped and rep.stopped.startswith("account_restricted")
    assert repo.posts == {} and repo.comments == {}


@pytest.mark.browser
def test_dry_run_writes_nothing_and_opens_no_posts():
    repo = MemoryRepo()
    rep = collector.run(FacebookPublicPostsAdapter(KEYER, FAST), "car sedan", repo=repo, dry_run=True,
                        check_login=False, on_session=lambda s: fb_public_site.install(s.context))
    assert rep.verified_public == 3 and repo.posts == {} and repo.skips == []


def test_buyer_only_keeps_intent_and_parents():
    from fbm_intel.fb_public.model import keep_buyer_intent
    raw = [rc("comment", "Nice car", "C1"), rc("reply", "How much last price?", "C1", "R1"),
           rc("comment", "Is it still available? I want to buy", "C2"), rc("comment", "Good luck bro", "C3")]
    out, _ = build_comments(raw, POST, KEYER, Limits())
    kept = keep_buyer_intent(out)
    assert [c.comment_text for c in kept] == ["Nice car", "How much last price?", "Is it still available? I want to buy"]
    assert all(c.parent_fingerprint in {k.fingerprint for k in kept} for c in kept if c.parent_fingerprint)


@pytest.mark.browser
def test_real_facebook_post_layout():
    """Regression from the live run: post in the 2nd of several dialogs, audience icon outside any role=article."""
    from fbm_intel.browser import open_session
    from fbm_intel.fb_public.adapter import SearchResult
    from fbm_intel.fb_public.visibility import Visibility

    ad = FacebookPublicPostsAdapter(KEYER, FAST)
    url = "https://www.facebook.com/realshape.kh/posts/999999999"
    with open_session(ad.allowed_hosts, 0) as s:
        fb_public_site.install(s.context)
        post = ad.collect_post(s, SearchResult(url, url, Visibility("public_verified", "audience_icon:Shared with Public", None)), "q")
    assert post is not None and post.visibility_evidence == "audience_icon:Shared with Public"
    assert post.post_text == "Lexus RX 2019 for sale"
    assert [c.comment_text for c in post.comments] == ["domlai man b", "nice lan b"]
    assert [c.buyer_intent for c in post.comments] == [True, False]
