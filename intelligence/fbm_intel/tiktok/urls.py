"""TikTok URL canonicalization. Canonical video URL: https://www.tiktok.com/@<creator>/video/<id> (no query/fragment)."""
from __future__ import annotations

import re
from urllib.parse import quote, urlsplit

VIDEO_RE = re.compile(r"^/@(?P<creator>[A-Za-z0-9._]{2,24})/(?:video|photo)/(?P<id>\d{8,25})/?$")
HOST_RE = re.compile(r"^(?:www\.|m\.|vm\.|vt\.)?tiktok\.com$")


class NotTikTokUrl(ValueError):
    pass


def parse_video(url: str) -> tuple[str, str] | None:
    """(creator, video_id) or None."""
    p = urlsplit((url or "").strip())
    if p.scheme not in ("http", "https") or not HOST_RE.match((p.hostname or "").lower()):
        return None
    m = VIDEO_RE.match(p.path)
    return (m.group("creator").lower(), m.group("id")) if m else None


def canonical_video_url(url: str) -> str:
    parsed = parse_video(url)
    if not parsed:
        raise NotTikTokUrl(f"not a TikTok video URL: {url[:80]!r}")
    creator, vid = parsed
    return f"https://www.tiktok.com/@{creator}/video/{vid}"


def video_id(url: str) -> str | None:
    parsed = parse_video(url)
    return parsed[1] if parsed else None


def is_video_url(url: str) -> bool:
    return parse_video(url) is not None


def author_identifier(href: str | None) -> str | None:
    """Stable transient identifier from a comment author link ('/@handle' → 'handle'). Never stored."""
    if not href:
        return None
    path = urlsplit(href).path if "://" in href else href.split("?")[0]
    m = re.match(r"^/@([A-Za-z0-9._]{2,24})/?$", path)
    return m.group(1).lower() if m else None


def search_url(template: str, query: str) -> str:
    return template.format(query=quote(query))
