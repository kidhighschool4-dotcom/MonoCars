from datetime import datetime, timedelta, timezone
import io

import pytest
from PIL import Image

from fbm_intel.normalize import (canonicalize_url, content_hash, dhash_hex, freshness_percent, hamming,
                                 normalize_location, normalize_text, parse_price_usd, parse_published_at, stable_hash)


class TestCanonicalUrl:
    def test_strips_tracking_fragment_www_and_trailing_slash(self):
        a = canonicalize_url("https://www.Example.com/cars/123/?utm_source=fb&fbclid=x&b=2&a=1#photos")
        assert a == "https://example.com/cars/123?a=1&b=2"

    def test_same_listing_different_forms_are_equal(self):
        assert canonicalize_url("http://example.com:80/cars/1") == canonicalize_url("https://example.com/cars/1/")

    def test_keeps_non_default_port(self):
        assert canonicalize_url("http://127.0.0.1:8123/cars/1") == "https://127.0.0.1:8123/cars/1"

    @pytest.mark.parametrize("bad", ["javascript:alert(1)", "file:///etc/passwd", "ftp://x.com/a", "https:///nohost"])
    def test_rejects_non_web_urls(self, bad):
        with pytest.raises(ValueError):
            canonicalize_url(bad)


class TestPrice:
    @pytest.mark.parametrize("text,usd", [
        ("$18,500", 18500), ("18500 USD", 18500), ("USD 18 500", 18500), ("$12.8k", 12800),
        ("៛52,480,000", 12800), ("52.48 លានរៀល", 12800), ("KHR52,480,000", 12800), ("$១៨,៥០០", 18500), ("Price: $95,000 negotiable", 95000),
    ])
    def test_parses(self, text, usd):
        assert parse_price_usd(text) == usd

    @pytest.mark.parametrize("text", [None, "", "Call for price", "តម្លៃចរចា", "$0"])
    def test_unknown_price_is_none(self, text):
        assert parse_price_usd(text) is None


class TestLocation:
    @pytest.mark.parametrize("text,loc", [
        ("Phnom Penh", "Phnom Penh"), ("ភ្នំពេញ", "Phnom Penh"), ("Toul Kork, PP", "Phnom Penh"),
        ("សៀមរាប", "Siem Reap"), ("Preah Sihanouk", "Sihanoukville"), ("Kampong Cham", "Kampong Cham"),
    ])
    def test_normalizes(self, text, loc):
        assert normalize_location(text) == loc

    def test_short_alias_needs_word_boundary(self):
        assert normalize_location("Apple store") is None  # 'pp' inside a word must not match

    def test_unknown(self):
        assert normalize_location("Somewhere") is None


class TestDates:
    NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)

    @pytest.mark.parametrize("text,delta", [
        ("2 days ago", timedelta(days=2)), ("3 hours ago", timedelta(hours=3)), ("yesterday", timedelta(days=1)),
        ("ម្សិលមិញ", timedelta(days=1)), ("៣ ថ្ងៃមុន", timedelta(days=3)), ("1 week ago", timedelta(weeks=1)),
    ])
    def test_relative(self, text, delta):
        assert parse_published_at(text, self.NOW) == self.NOW - delta

    def test_iso(self):
        assert parse_published_at("2026-09-25T08:00:00Z") == datetime(2026, 9, 25, 8, tzinfo=timezone.utc)

    def test_freshness(self):
        assert freshness_percent(self.NOW, 30, self.NOW) == 100
        assert freshness_percent(self.NOW - timedelta(days=15), 30, self.NOW) == 50
        assert freshness_percent(self.NOW - timedelta(days=90), 30, self.NOW) == 0
        assert freshness_percent(None, 30, self.NOW) == 50  # unknown is neutral, not rewarded


class TestHashes:
    def test_stable_hash_is_deterministic_and_order_sensitive(self):
        assert stable_hash("a", 1, {"x": 2}) == stable_hash("a", 1, {"x": 2})
        assert stable_hash("a", "b") != stable_hash("b", "a")

    def test_content_hash_ignores_case_and_whitespace(self):
        assert content_hash("Toyota  Camry", "Nice", "$1", "PP") == content_hash("toyota camry", " nice ", "$1", "pp")

    def test_khmer_text_is_nfc_normalized(self):
        assert normalize_text("ឡាន​លក់") == "ឡានលក់"

    def test_dhash_near_duplicates(self):
        def png(shift: int) -> bytes:
            im = Image.new("RGB", (200, 150), (40, 90, 200))
            for x in range(0, 200, 25):
                im.paste((255, 255, 255), (x + shift, 20, x + shift + 10, 120))
            buf = io.BytesIO()
            im.save(buf, "PNG")
            return buf.getvalue()

        a, b = dhash_hex(png(0)), dhash_hex(png(1))
        other = dhash_hex(png(12))
        assert hamming(a, b) <= 4
        assert hamming(a, other) > 4
