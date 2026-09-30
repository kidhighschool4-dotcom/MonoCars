"""Live Supabase checks for facebook_public_* tables (run after applying 20260930_facebook_public_posts.sql).

  .venv/bin/python -m pytest -m live tests/test_live_fb_public.py -v

Uses two throw-away accounts (owner + outsider) and synthetic data only; everything is deleted afterwards.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from fbm_intel.fb_public.identity import PersonKeyer
from fbm_intel.fb_public.model import Limits, PublicPost, RawComment, build_comments
from fbm_intel.fb_public.repo import FacebookPublicRepo
from fbm_intel.settings import Settings

pytestmark = pytest.mark.live
POST = "https://www.facebook.com/test.dealer.fbm/posts/pfbidTEST0001"


@pytest.fixture(scope="module")
def st():
    s = Settings.load()
    admin = {"apikey": s.service_role_key, "Authorization": f"Bearer {s.service_role_key}"}
    r = httpx.get(f"{s.supabase_url}/rest/v1/facebook_public_posts?select=id&limit=1", headers=admin)
    if r.status_code == 404 or "does not exist" in r.text or "schema cache" in r.text:
        pytest.skip("facebook_public_* tables not applied yet")
    return s


def _user(st, label):
    admin = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}"}
    email, pw = f"fbpub-{label}-{secrets.token_hex(5)}@example.com", secrets.token_urlsafe(24)
    uid = httpx.post(f"{st.supabase_url}/auth/v1/admin/users", headers=admin,
                     json={"email": email, "password": pw, "email_confirm": True}).json()["id"]
    tok = httpx.post(f"{st.supabase_url}/auth/v1/token?grant_type=password",
                     headers={"apikey": os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]},
                     json={"email": email, "password": pw}).json()["access_token"]
    return uid, tok


@pytest.fixture(scope="module")
def users(st):
    owner, outsider = _user(st, "owner"), _user(st, "outsider")
    yield owner, outsider
    admin = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}"}
    for uid, _ in (owner, outsider):  # ON DELETE CASCADE removes their rows too
        httpx.delete(f"{st.supabase_url}/auth/v1/admin/users/{uid}", headers=admin)


@pytest.fixture(scope="module")
def keyer():
    return PersonKeyer.from_env()


@pytest.fixture(scope="module")
def saved(st, users, keyer):
    repo = FacebookPublicRepo(st, users[0][0], keyer)
    raw = [RawComment("comment", "Is it still available? I want to buy", POST + "?comment_id=C1",
                      "https://www.facebook.com/dara.test.buyer?comment_id=C1", "3h"),
           RawComment("reply", "Yes, 50% off today_only", POST + "?comment_id=C1&reply_comment_id=R1",
                      "https://www.facebook.com/test.dealer.fbm", "2h"),
           RawComment("comment", "តម្លៃប៉ុន្មាន?", None, None, "1d")]
    comments, _ = build_comments(raw, POST, keyer, Limits())
    post = PublicPost(source_post_id="pfbidTEST0001", source_post_url=POST + "?__cft__=x", canonical_post_url=POST,
                      author_key=keyer.key("https://www.facebook.com/test.dealer.fbm"), author_key_version=keyer.version,
                      post_text="2019 Camry sedan for sale", published_at_observed=datetime.now(timezone.utc) - timedelta(days=2),
                      visibility_status="public_verified", visibility_evidence="audience_icon:Shared with Public",
                      search_query="car sedan", captured_at=datetime.now(timezone.utc), content_hash="h",
                      comments=comments, comments_complete=True, comments_incomplete_reason=None)
    first = repo.save_post(post)
    second = repo.save_post(post)
    return repo, first, second


def test_duplicates_not_created(saved):
    _, first, second = saved
    assert first[1:] == (2, 1) and second[1:] == (0, 0)


def test_query_by_urls_and_text(saved):
    repo, *_ = saved
    p = repo.find_post_by_url(POST + "/?__cft__[0]=zz")  # tracking variant resolves to the same post
    assert p["canonical_post_url"] == POST and p["comments_collected_count"] == 2 and p["replies_collected_count"] == 1
    cs = repo.find_comments_by_post_url(POST)
    assert {c["canonical_comment_url"] for c in cs} >= {POST + "?comment_id=C1", POST + "?comment_id=C1&reply_comment_id=R1"}
    assert all(c["post"]["canonical_post_url"] == POST for c in cs)
    assert repo.find_comment_by_url(POST + "?comment_id=C1")["comment_text"].startswith("Is it still")
    by_person = repo.find_comments_by_profile_url("https://web.facebook.com/Dara.Test.Buyer/?__tn__=R")
    assert [c["comment_text"] for c in by_person] == ["Is it still available? I want to buy"]
    assert repo.find_posts_by_author_url("https://www.facebook.com/test.dealer.fbm")[0]["canonical_post_url"] == POST
    assert len(repo.search_comment_text("still available")) == 1
    assert len(repo.search_comment_text("50%")) == 1 and repo.search_comment_text("%") == repo.search_comment_text("%")
    assert len(repo.search_comment_text("today_only")) == 1 and repo.search_comment_text("zzz_nope") == []
    assert len(repo.search_post_text("camry")) == 1
    assert repo.find_posts_by_original_search_query("car sedan")[0]["canonical_post_url"] == POST
    now = datetime.now(timezone.utc)
    assert len(repo.find_comments_by_date_range(now - timedelta(days=3), now + timedelta(hours=1))) == 3


def test_no_identity_stored(st, saved):
    admin = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}"}
    rows = httpx.get(f"{st.supabase_url}/rest/v1/facebook_public_comments?select=*&canonical_comment_url=like.*pfbidTEST0001*",
                     headers=admin).text
    assert "dara.test.buyer" not in rows.lower() and "profile" not in rows


def test_anonymous_access_denied(st, saved):
    anon = os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
    for t in ("facebook_public_posts", "facebook_public_comments", "facebook_public_post_skips"):
        r = httpx.get(f"{st.supabase_url}/rest/v1/{t}?select=*&limit=1", headers={"apikey": anon, "Authorization": f"Bearer {anon}"})
        assert r.status_code in (401, 403) or r.json() == []
    r = httpx.post(f"{st.supabase_url}/rest/v1/rpc/purge_expired_facebook_public_data",
                   headers={"apikey": anon, "Authorization": f"Bearer {anon}"}, json={})
    assert r.status_code >= 400


def test_rls_owner_only(st, users, saved):
    anon = os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
    (_, owner_tok), (_, other_tok) = users
    get = lambda tok: httpx.get(f"{st.supabase_url}/rest/v1/facebook_public_posts?select=canonical_post_url",  # noqa: E731
                                headers={"apikey": anon, "Authorization": f"Bearer {tok}"}).json()
    assert {r["canonical_post_url"] for r in get(owner_tok)} == {POST}
    assert get(other_tok) == []
    w = httpx.post(f"{st.supabase_url}/rest/v1/facebook_public_posts", headers={"apikey": anon, "Authorization": f"Bearer {owner_tok}"},
                   json={"owner_id": users[0][0], "source_post_url": POST, "canonical_post_url": POST + "2"})
    assert w.status_code in (401, 403)  # clients can never write


def test_only_verified_public_allowed(st, users):
    admin = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}"}
    r = httpx.post(f"{st.supabase_url}/rest/v1/facebook_public_posts", headers=admin, json={
        "owner_id": users[0][0], "source_post_url": POST, "canonical_post_url": POST + "X", "visibility_status": "unverified",
        "visibility_evidence": "", "search_query": "q", "captured_at": datetime.now(timezone.utc).isoformat(),
        "adapter_version": "t", "content_hash": "h"})
    assert r.status_code >= 400 and "fbpp_public_only" in r.text


def test_retention_purge(st, users, keyer):
    admin = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}", "Prefer": "return=representation"}
    old = POST.replace("0001", "OLD1")
    httpx.post(f"{st.supabase_url}/rest/v1/facebook_public_posts", headers=admin, json={
        "owner_id": users[0][0], "source_post_url": old, "canonical_post_url": old, "visibility_status": "public_verified",
        "visibility_evidence": "t", "search_query": "q", "captured_at": datetime.now(timezone.utc).isoformat(),
        "adapter_version": "t", "content_hash": "h", "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()})
    out = FacebookPublicRepo(st, users[0][0], keyer).purge_expired()
    assert out["posts"] >= 1
    assert FacebookPublicRepo(st, users[0][0], keyer).find_post_by_url(old) is None
