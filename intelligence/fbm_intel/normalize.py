"""Deterministic normalization: URLs, text, prices, locations, dates, hashes (§8.5, §16.1)."""
from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

KHR_PER_USD = 4100  # approximate; only used to normalize Riel prices for ranking

TRACKING_PARAMS = {"fbclid", "gclid", "ref", "ref_src", "igshid", "mc_cid", "mc_eid", "_ga"}


def normalize_text(text: str | None) -> str:
    """NFC-normalize and collapse whitespace. Keeps Khmer intact."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("​", "")  # zero-width space is common in Khmer typing
    return re.sub(r"\s+", " ", text).strip()


def fold(text: str | None) -> str:
    """Case-insensitive comparison key."""
    return normalize_text(text).casefold()


def canonicalize_url(url: str) -> str:
    """Lowercase scheme/host, drop fragments, default ports, tracking params and trailing slash."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme: {parts.scheme!r}")
    if not parts.hostname:
        raise ValueError("URL has no host")
    host = parts.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    query.sort()
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunsplit(("https", netloc, path, urlencode(query), ""))


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def stable_hash(*parts: object) -> str:
    """Idempotency key helper (§14.1): order-sensitive, JSON-stable."""
    return sha256_hex(json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False))


def content_hash(title: str | None, description: str | None, price: str | None, location: str | None) -> str:
    return stable_hash(fold(title), fold(description), fold(price), fold(location))


# ─── Price ──────────────────────────────────────────────────────────────────

_KHMER_DIGITS = str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789")
_NUM = r"(\d{1,3}(?:[,\s]\d{3})+|\d+)(?:\.(\d+))?\s*([kKmM]|ពាន់|លាន)?"


def parse_price_usd(text: str | None) -> int | None:
    """Parse '$12,800', '12800 USD', '12.8k$', '៛52,480,000', '52 លានរៀល' → whole USD.

    Returns None when no unambiguous price is present (e.g. 'Call for price', 'តម្លៃចរចា').
    """
    if not text:
        return None
    t = normalize_text(text).translate(_KHMER_DIGITS)
    is_khr = bool(re.search(r"៛|រៀល|\bkhr|\briel", t, re.IGNORECASE))
    m = re.search(_NUM, t)
    if not m:
        return None
    whole = re.sub(r"[,\s]", "", m.group(1))
    value = float(f"{whole}.{m.group(2)}") if m.group(2) else float(whole)
    mult = (m.group(3) or "").lower()
    if mult == "k" or mult == "ពាន់":
        value *= 1_000
    elif mult == "m" or mult == "លាន":
        value *= 1_000_000
    if is_khr:
        value /= KHR_PER_USD
    if value <= 0 or value > 5_000_000:
        return None
    return int(round(value))


# ─── Location ───────────────────────────────────────────────────────────────

PROVINCES: dict[str, list[str]] = {
    "Phnom Penh": ["phnom penh", "pp", "ភ្នំពេញ"],
    "Kandal": ["kandal", "កណ្តាល", "កណ្ដាល"],
    "Siem Reap": ["siem reap", "siemreap", "សៀមរាប"],
    "Battambang": ["battambang", "បាត់ដំបង"],
    "Sihanoukville": ["sihanoukville", "preah sihanouk", "kampong som", "ព្រះសីហនុ"],
    "Kampot": ["kampot", "កំពត"],
    "Kampong Cham": ["kampong cham", "កំពង់ចាម"],
    "Takeo": ["takeo", "តាកែវ"],
    "Kep": ["kep", "កែប"],
    "Kampong Speu": ["kampong speu", "កំពង់ស្ពឺ"],
    "Banteay Meanchey": ["banteay meanchey", "poipet", "បន្ទាយមានជ័យ"],
}


def normalize_location(text: str | None) -> str | None:
    t = fold(text)
    if not t:
        return None
    for canonical, aliases in PROVINCES.items():
        for alias in aliases:
            if len(alias) <= 3:
                if re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", t):
                    return canonical
            elif alias in t:
                return canonical
    return None


# ─── Dates ──────────────────────────────────────────────────────────────────

def parse_published_at(text: str | None, now: datetime | None = None) -> datetime | None:
    """ISO timestamps or relative English/Khmer phrases ('2 days ago', 'ម្សិលមិញ')."""
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    t = fold(text).translate(_KHMER_DIGITS)
    try:
        dt = datetime.fromisoformat(t.replace("z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    if t in ("today", "just now", "ថ្ងៃនេះ"):
        return now
    if t in ("yesterday", "ម្សិលមិញ"):
        return now - timedelta(days=1)
    units = {
        "minute": timedelta(minutes=1), "min": timedelta(minutes=1), "នាទី": timedelta(minutes=1),
        "hour": timedelta(hours=1), "hr": timedelta(hours=1), "ម៉ោង": timedelta(hours=1),
        "day": timedelta(days=1), "ថ្ងៃ": timedelta(days=1),
        "week": timedelta(weeks=1), "សប្តាហ៍": timedelta(weeks=1), "សប្ដាហ៍": timedelta(weeks=1),
        "month": timedelta(days=30), "ខែ": timedelta(days=30),
    }
    m = re.search(r"(\d+)\s*([a-zក-៹]+)", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2).rstrip("s")
        for key, delta in units.items():
            if unit.startswith(key):
                return now - n * delta
    return None


def freshness_percent(published_at: datetime | None, max_age_days: int | None, now: datetime | None = None) -> int:
    """100 = brand new, decays linearly to 0 at max_age_days. Unknown date → neutral 50."""
    if published_at is None:
        return 50
    now = now or datetime.now(timezone.utc)
    age_days = max(0.0, (now - published_at).total_seconds() / 86400)
    horizon = max_age_days or 60
    return max(0, min(100, round(100 * (1 - age_days / horizon))))


# ─── Images ─────────────────────────────────────────────────────────────────

def dhash_hex(png_bytes: bytes, size: int = 8) -> str:
    """64-bit difference hash for near-duplicate screenshots."""
    from PIL import Image

    with Image.open(io.BytesIO(png_bytes)) as im:
        g = im.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
        px = list(g.tobytes())  # mode 'L' → one byte per pixel
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")
