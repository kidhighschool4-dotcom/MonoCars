from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest

from fbm_intel.schemas import ProductBrief, SearchProfile

from .fixtures.build_site import build


@pytest.fixture(scope="session")
def fixture_site(tmp_path_factory) -> str:
    """Serve the static FBM-shaped fixture marketplace on 127.0.0.1:<random port>."""
    root = build(tmp_path_factory.mktemp("fbm_site"))
    handler = functools.partial(_QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep pytest output clean
        pass


@pytest.fixture
def brief() -> ProductBrief:
    return ProductBrief(
        id="11111111-1111-1111-1111-111111111111", slug="test-brief", name="Test brief",
        summary="Used cars for sale in Cambodia", target_customer="Used-car buyers",
        positive_signals=["Vehicle for sale", "Price visible"],
        hard_rejections=["Rental only", "Spare parts only", "Wanted-to-buy post"],
        supported_locations=["Phnom Penh", "Kandal", "Siem Reap", "Battambang"],
        supported_categories=["sedan", "suv"], version=1)


@pytest.fixture
def profile() -> SearchProfile:
    return SearchProfile(
        id="22222222-2222-2222-2222-222222222222", slug="test-profile", name="Test", intent="Used cars in Cambodia",
        languages=["km", "en", "mixed"], locations=["Phnom Penh"], platforms=["fbm"], max_queries_per_run=5,
        max_pages_per_query=1, max_listings_per_run=50, maximum_listing_age_days=60, version=1)


GOOD_OUTPUT = {
    "decision": "good", "fit_score_percent": 88, "evidence_quality_percent": 90, "visual_condition_level": 4,
    "information_quality_level": 4, "apparent_risk_level": 1, "hard_rejections_detected": [],
    "visible_signals": ["Vehicle clearly shown", "Price visible"], "risk_flags": [], "missing_information": [],
    "cannot_determine": ["Service history"], "short_reason": "Clear sedan sale with price and photos.",
}
