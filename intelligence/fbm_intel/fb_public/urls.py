"""Facebook URL canonicalization for public posts, comments and profiles.

Canonical form: https://www.facebook.com/<path> with every tracking / redirect / session parameter removed and
only the parameters needed to reopen the exact object kept (allowlist per URL type). Fragments are dropped.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

FB_HOST_RE = re.compile(r"^(?:[a-z0-9-]+\.)?facebook\.com$")
CANON_HOST = "www.facebook.com"

# Only these query parameters survive, per path. Everything else (__cft__, __tn__, mibextid, rdid, share_url,
# _rdc, _rdr, ref, notif_id, locale, sfnsn, paipv, eav, …) is tracking/session noise.
KEEP_PARAMS: dict[str, tuple[str, ...]] = {
    "/permalink.php": ("story_fbid", "id"),
    "/story.php": ("story_fbid", "id"),
    "/profile.php": ("id",),
    "/photo.php": ("fbid",),
    "/photo": ("fbid",),
}
COMMENT_PARAMS = ("comment_id", "reply_comment_id")

POST_PATTERNS = [
    re.compile(r"^/groups/(?P<group>[^/]+)/(?:posts|permalink)/(?P<id>[\w-]+)$"),
    re.compile(r"^/(?P<owner>[^/]+)/posts/(?P<id>[\w-]+)$"),
    re.compile(r"^/share/p/(?P<id>[\w-]+)$"),
]
NON_PROFILE_ROOTS = {"groups", "hashtag", "marketplace", "watch", "reel", "reels", "events", "search", "stories",
                     "photo", "photo.php", "permalink.php", "story.php", "l.php", "share", "login", "help", "policies",
                     "privacy", "settings", "notifications", "messages", "friends", "bookmarks", "pages", "gaming", "ads"}


class NotFacebookUrl(ValueError):
    pass


def _split(url: str):
    parts = urlsplit((url or "").strip())
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not FB_HOST_RE.match(host):
        raise NotFacebookUrl(f"not a facebook.com URL: {host or url[:40]!r}")
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path, parse_qsl(parts.query, keep_blank_values=False)


def _build(path: str, params: list[tuple[str, str]]) -> str:
    return urlunsplit(("https", CANON_HOST, path, urlencode(params), ""))


def canonicalize(url: str, *, keep_comment_params: bool = False) -> str:
    path, query = _split(url)
    keep = set(KEEP_PARAMS.get(path, ()))
    if keep_comment_params:
        keep |= set(COMMENT_PARAMS)
    order = list(KEEP_PARAMS.get(path, ())) + (list(COMMENT_PARAMS) if keep_comment_params else [])
    params = sorted(((k, v) for k, v in query if k in keep), key=lambda kv: order.index(kv[0]))
    return _build(path, params)


def canonical_post_url(url: str) -> str:
    return canonicalize(url)


def post_id(url: str) -> str | None:
    path, query = _split(url)
    q = dict(query)
    if path in ("/permalink.php", "/story.php"):
        return q.get("story_fbid")
    for pat in POST_PATTERNS:
        m = pat.match(path)
        if m:
            return m.group("id")
    return None


def is_group_post(url: str) -> bool:
    path, _ = _split(url)
    return path.startswith("/groups/")


def is_post_url(url: str) -> bool:
    try:
        return post_id(url) is not None
    except NotFacebookUrl:
        return False


def comment_ids(url: str) -> tuple[str | None, str | None]:
    """(comment_id, reply_comment_id) from a comment permalink."""
    _, query = _split(url)
    q = dict(query)
    return q.get("comment_id"), q.get("reply_comment_id")


def canonical_comment_url(post_canonical_url: str, comment_id: str | None, reply_comment_id: str | None) -> str | None:
    """Post URL + comment identifiers — reopens the exact public comment/reply."""
    if not comment_id:
        return None
    path, query = _split(post_canonical_url)
    params = [(k, v) for k, v in query]
    params.append(("comment_id", comment_id))
    if reply_comment_id:
        params.append(("reply_comment_id", reply_comment_id))
    return _build(path, params)


def canonical_profile_url(url: str | None) -> str | None:
    """Username or profile.php?id= form. Returns None for anything that is not a person/page link."""
    if not url:
        return None
    try:
        path, query = _split(url)
    except NotFacebookUrl:
        return None
    segs = [s for s in path.split("/") if s]
    if not segs:
        return None
    if path == "/profile.php":
        pid = dict(query).get("id")
        return _build("/profile.php", [("id", pid)]) if pid and pid.isdigit() else None
    if segs[0] == "people" and len(segs) >= 3 and segs[2].isdigit():  # /people/<Name>/<id>
        return _build("/profile.php", [("id", segs[2])])
    if len(segs) == 1 and segs[0].lower() not in NON_PROFILE_ROOTS and re.fullmatch(r"[A-Za-z0-9.\-]{2,80}", segs[0]):
        return _build("/" + segs[0].lower(), [])
    return None


def post_url_from_photo_set(photo_url: str, author_url: str | None) -> str | None:
    """Facebook's Posts search hides post permalinks, but a post's photos link to /photo?fbid=…&set=pcb.<POST_ID>.
    With the posting Page/profile link this rebuilds the exact post URL. Returns None if either part is missing."""
    try:
        path, query = _split(photo_url)
    except NotFacebookUrl:
        return None
    if path not in ("/photo", "/photo.php"):
        return None
    m = re.fullmatch(r"pcb\.(\d{5,25})", dict(query).get("set", ""))
    owner = canonical_profile_url(author_url)
    if not m or not owner:
        return None
    opath, oq = _split(owner)
    if opath == "/profile.php":
        return _build("/permalink.php", [("story_fbid", m.group(1)), ("id", dict(oq)["id"])])
    return _build(f"{opath}/posts/{m.group(1)}", [])


def group_post_url_from_photo_set(photo_url: str) -> str | None:
    """Group posts in Posts search have no permalink either, but their photos link to
    /photo?fbid=…&set=gm.<POST_ID>&idorvanity=<GROUP>, which is enough for /groups/<GROUP>/posts/<POST_ID>/."""
    try:
        path, query = _split(photo_url)
    except NotFacebookUrl:
        return None
    if path not in ("/photo", "/photo.php"):
        return None
    q = dict(query)
    m = re.fullmatch(r"(?:gm|pcb)\.(\d{5,25})", q.get("set", ""))
    group = q.get("idorvanity", "")
    if not m or not re.fullmatch(r"[A-Za-z0-9._-]{2,100}", group):
        return None
    return _build(f"/groups/{group}/posts/{m.group(1)}", [])
