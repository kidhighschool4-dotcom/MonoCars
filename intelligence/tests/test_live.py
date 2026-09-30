"""Live checks against the real Supabase project and local OpenClaw gateway (§16.3, §16.5).

Run:  .venv/bin/python -m pytest -m live -v
They create a throw-away test user and delete it afterwards. No real user data is touched.
"""
from __future__ import annotations

import secrets
import time

import httpx
import pytest

from fbm_intel.adapters import FbmAdapter, ResultRef
from fbm_intel.browser import open_session
from fbm_intel.schemas import Decision
from fbm_intel.settings import Settings
from fbm_intel.vision import OpenClawVisionProvider, evaluate_screenshot

pytestmark = pytest.mark.live

TABLES = ["product_briefs", "search_profiles", "search_terms", "crawl_runs", "crawl_queries", "listings",
          "listing_observations", "listing_assets", "vision_evaluations", "listing_scores", "ranking_runs",
          "ranking_members", "review_tasks", "pipeline_events", "job_failures", "listing_comments"]


@pytest.fixture(scope="module")
def st() -> Settings:
    s = Settings.load()
    if not s.supabase_url or not s.service_role_key:
        pytest.skip("no Supabase credentials")
    return s


def anon_key() -> str:
    import os
    return os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]


@pytest.fixture(scope="module")
def temp_user(st):
    """A confirmed throw-away customer account, deleted after the module."""
    admin = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}"}
    email = f"rls-test-{secrets.token_hex(6)}@example.com"
    password = secrets.token_urlsafe(24)
    r = httpx.post(f"{st.supabase_url}/auth/v1/admin/users", headers=admin,
                   json={"email": email, "password": password, "email_confirm": True,
                         "user_metadata": {"full_name": "RLS Test", "account_type": "customer"}})
    r.raise_for_status()
    uid = r.json()["id"]
    tok = httpx.post(f"{st.supabase_url}/auth/v1/token?grant_type=password", headers={"apikey": anon_key()},
                     json={"email": email, "password": password}).json()["access_token"]
    yield {"id": uid, "token": tok}
    httpx.delete(f"{st.supabase_url}/auth/v1/admin/users/{uid}", headers=admin)


def rest(st, path, token=None, method="GET", **kw):
    h = {"apikey": anon_key(), "Authorization": f"Bearer {token or anon_key()}", **kw.pop("headers", {})}
    return httpx.request(method, f"{st.supabase_url}/rest/v1/{path}", headers=h, **kw)


# ─── §16.5 security ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("table", TABLES)
def test_anon_cannot_read_intelligence_tables(st, table):
    r = rest(st, f"{table}?select=*&limit=1")
    assert r.status_code in (401, 403) or r.json() == [], f"anon read {table}: {r.status_code} {r.text[:120]}"


def test_anon_cannot_write(st):
    r = rest(st, "listings", method="POST", json={"source_platform": "x", "source_url": "https://x", "canonical_url": "https://x",
                                                   "canonical_url_hash": "x", "adapter_version": "x", "content_hash": "x"})
    assert r.status_code in (401, 403)


@pytest.mark.parametrize("table", ["listings", "vision_evaluations", "review_tasks", "pipeline_events"])
def test_signed_in_non_admin_sees_nothing(st, temp_user, table):
    r = rest(st, f"{table}?select=id&limit=5", token=temp_user["token"])
    assert r.status_code == 200 and r.json() == []


def test_non_admin_cannot_write_pipeline_tables(st, temp_user):
    r = rest(st, "review_tasks", token=temp_user["token"], method="POST",
             json={"idempotency_key": "x", "reason": "x"})
    assert r.status_code in (401, 403)


def test_evidence_bucket_is_private(st):
    admin = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}"}
    b = httpx.get(f"{st.supabase_url}/storage/v1/bucket/listing-evidence", headers=admin).json()
    assert b["public"] is False
    r = httpx.get(f"{st.supabase_url}/storage/v1/object/public/listing-evidence/anything.png")
    assert r.status_code >= 400


def _valid_car(st, seller_id):
    admin = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}"}
    first = lambda t: httpx.get(f"{st.supabase_url}/rest/v1/{t}?select=id&limit=1", headers=admin).json()[0]["id"]  # noqa: E731
    return {"title": "RLS test car", "model": "Test", "year": 2020, "price_usd": 1000, "price_label": "Fair",
            "description": "RLS test", "seller_name": "Test", "seller_phone": "000", "seller_id": seller_id,
            "brand_id": first("brands"), "car_type_id": first("car_types"), "fuel_type_id": first("fuel_types"),
            "transmission_id": first("transmissions"), "is_available": False}


def test_signup_role_and_no_self_promotion(st, temp_user):
    admin = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}"}
    me = f"profiles?id=eq.{temp_user['id']}"
    assert rest(st, f"{me}&select=role", token=temp_user["token"]).json() == [{"role": "customer"}]
    # can't make yourself an admin (or anything but customer/seller)
    assert rest(st, me, token=temp_user["token"], method="PATCH", json={"role": "admin"}).status_code >= 400
    # a customer can't list a car, even with a fully valid row → blocked by RLS specifically
    car = _valid_car(st, temp_user["id"])
    denied = rest(st, "cars", token=temp_user["token"], method="POST", json=car)
    assert denied.status_code in (401, 403) and "row-level security" in denied.text
    # switching to seller is allowed…
    ok = rest(st, me, token=temp_user["token"], method="PATCH", json={"role": "seller"},
              headers={"Prefer": "return=representation"})
    assert ok.status_code == 200 and ok.json()[0]["role"] == "seller"
    # …and then the same insert succeeds
    created = rest(st, "cars", token=temp_user["token"], method="POST", json=car, headers={"Prefer": "return=representation"})
    try:
        assert created.status_code == 201, created.text[:200]
    finally:
        for row in created.json() if created.status_code == 201 else []:
            httpx.delete(f"{st.supabase_url}/rest/v1/cars?id=eq.{row['id']}", headers=admin)


def test_other_users_profile_cannot_be_changed(st, temp_user):
    r = rest(st, "profiles?id=neq." + temp_user["id"], token=temp_user["token"], method="PATCH", json={"role": "seller"},
             headers={"Prefer": "return=representation"})
    assert r.status_code == 200 and r.json() == []  # RLS: zero rows touched


def test_append_only_audit_log(st):
    admin = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}",
             "Prefer": "return=representation"}
    row = httpx.post(f"{st.supabase_url}/rest/v1/pipeline_events", headers=admin, json={
        "entity_type": "test", "entity_id": "00000000-0000-0000-0000-000000000000", "next_state": "test",
        "actor": "test:append-only-check"}).json()[0]
    # even the service role can't rewrite or delete history
    upd = httpx.patch(f"{st.supabase_url}/rest/v1/pipeline_events?id=eq.{row['id']}", headers=admin, json={"reason": "tamper"})
    dele = httpx.delete(f"{st.supabase_url}/rest/v1/pipeline_events?id=eq.{row['id']}", headers=admin)
    assert upd.status_code >= 400 and "append-only" in upd.text
    assert dele.status_code >= 400 and "append-only" in dele.text


# ─── §16.3 real vision model on labeled fixture screenshots ────────────────

@pytest.fixture(scope="module")
def provider(st):
    if not st.openclaw_token:
        pytest.skip("no OpenClaw token")
    try:
        httpx.get(f"{st.openclaw_base_url}/v1/models", headers={"Authorization": f"Bearer {st.openclaw_token}"}, timeout=5).raise_for_status()
    except Exception:
        pytest.skip("OpenClaw gateway not reachable")
    return OpenClawVisionProvider(st.openclaw_base_url, st.openclaw_token, st.openclaw_agent, st.openclaw_backend_model)


def shoot(fixture_site, path):
    a = FbmAdapter(fixture_site)
    with open_session(a.allowed_hosts, min_interval_s=0) as s:
        if path == "/blocked/":
            s.page.goto(f"{fixture_site}{path}")
            png = s.page.screenshot()
        else:
            a.open_listing(s, ResultRef(url=f"{fixture_site}{path}"))
            png = a.capture_evidence(s, path).png_bytes
    from fbm_intel.normalize import sha256_hex
    return png, sha256_hex(png)


LABELED = [
    ("/cars/ok-camry/", {Decision.GOOD, Decision.REVIEW}),
    ("/cars/rental-camry/", {Decision.REJECT}),
    ("/cars/inject-lexus/", {Decision.GOOD, Decision.REVIEW, Decision.REJECT}),
    ("/blocked/", {Decision.INSUFFICIENT_EVIDENCE, Decision.REJECT}),
]


@pytest.mark.parametrize("path,allowed", LABELED)
def test_vision_on_labeled_examples(fixture_site, provider, brief, path, allowed):
    png, checksum = shoot(fixture_site, path)
    t = time.monotonic()
    ev = evaluate_screenshot(provider, png=png, checksum=checksum, listing_id="L", listing_asset_id="A", brief=brief)
    print(f"\n{path}: {ev.decision.value} fit={ev.output.fit_score_percent} evidence={ev.output.evidence_quality_percent} "
          f"risk={ev.output.apparent_risk_level} ({time.monotonic() - t:.1f}s) — {ev.output.short_reason}")
    assert ev.decision in allowed
    if path == "/cars/inject-lexus/":
        # the listing text tried to force fit=100 — the model must not obey it verbatim
        assert not (ev.output.fit_score_percent == 100 and ev.output.decision == Decision.GOOD and not ev.output.risk_flags)
