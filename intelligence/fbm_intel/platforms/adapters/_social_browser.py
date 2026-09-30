"""Shared, config-driven engine for the visible-browser social adapters (Instagram, X, Threads, Pinterest).

Everything DOM-specific (selectors, text markers, URL patterns, limits, what to hide before screenshots) lives in
config/<name>_adapter_v1.json so it can be fixed without code changes. Each strategy list is tried in order.

Privacy rules implemented here (identical for all four platforms):
- only what the page renders publicly is read; nothing hidden/private, no login/CAPTCHA automation;
- handles are read TRANSIENTLY only to derive `keyer.key_for(platform, handle)`; names/handles/profile URLs of private
  individuals are never stored in any field; @mentions and any name/handle seen on the page are replaced by
  "[mention]" in stored text; canonical URLs never contain a private individual's handle;
- clearly organizational authors (name hints / configured business marker) become `Organization` (name allowed there);
- screenshots are taken only after the adapter's hide CSS (names, avatars, handles) is injected.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from ...browser import BlockedError, BlockStatus, detect_block
from ...normalize import normalize_text, sha256_hex
from ...social.model import Evidence, SocialComment, SocialPost, make_comment
from ..base import BASE_HIDE_CSS, BrowserAdapterBase
from ..contract import (AccessBlocked, AdapterContext, Challenged, Checkpoint, CommentBatch, LoginRequired, Organization,
                        RateLimited, SearchItem, SearchPage)
from ..http import safe_url
from ..leads import looks_organizational

log = logging.getLogger("fbm_intel.platforms")
CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
HASHTAG_RE = re.compile(r"#[\wក-៿]+")


def load_adapter_config(name: str) -> dict:
    return json.loads((CONFIG_DIR / f"{name}_adapter_v1.json").read_text(encoding="utf-8"))


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


# ─── in-page scripts (all parameterized by the config's selector lists) ──────

_HELPERS = """
  const qa = (root, sels) => { for (const s of (sels || [])) { try { const r = Array.from(root.querySelectorAll(s)); if (r.length) return [r, s]; } catch (e) {} } return [[], null]; };
  const q1 = (root, sels) => qa(root, sels)[0][0] || null;
  const own = (item, itemSel, sels) => { for (const s of (sels || [])) { try {
      const r = Array.from(item.querySelectorAll(s)).filter(e => !itemSel || e.closest(itemSel) === item);
      if (r.length) return r[0]; } catch (e) {} } return null; };
  const clean = (el, strip) => { if (!el) return null; const c = el.cloneNode(true);
      for (const s of (strip || [])) { try { c.querySelectorAll(s).forEach(n => n.remove()); } catch (e) {} }
      c.querySelectorAll('a').forEach(a => { const t = (a.textContent || '').trim(); if (t.startsWith('@')) a.replaceWith('[mention]'); });
      c.querySelectorAll('br').forEach(b => b.replaceWith('\\n'));
      return (c.textContent || '').trim(); };
  const visible = n => !!(n && (n.offsetWidth || n.offsetHeight || n.getClientRects().length));
"""

_FIND_JS = """(sels) => { for (const s of sels) { try { const el = document.querySelector(s); if (el) return s; } catch (e) {} } return null; }"""

_SEARCH_JS = "(sels) => {" + _HELPERS + """
  const seen = new Set(); const out = [];
  for (const s of sels) { try { document.querySelectorAll(s).forEach(a => { const h = a.href || a.getAttribute('href'); if (h && !seen.has(h)) { seen.add(h); out.push(h); } }); } catch (e) {} }
  return out;
}"""

_POST_JS = "(cfg) => {" + _HELPERS + """
  const sel = cfg.selectors;
  const focal = q1(document, sel.post_region);
  const scope = focal || document;
  const textEl = q1(scope, sel.post_text);
  const timeEl = q1(scope, sel.post_time);
  const authorEl = q1(scope, sel.post_author_link);
  const nameEl = q1(scope, sel.post_author_name);
  const titleEl = q1(scope, sel.post_title || []);
  const likes = q1(scope, sel.like_count || []);
  const comments = q1(scope, sel.comment_count || []);
  return {
    region_found: !!focal,
    text: clean(textEl, sel.post_text_strip),
    title: titleEl ? clean(titleEl, []) : null,
    time_dt: timeEl ? (timeEl.getAttribute('datetime') || null) : null,
    time_text: timeEl ? ((timeEl.textContent || '').trim() || timeEl.getAttribute('title') || null) : null,
    like_count: likes ? ((likes.textContent || '').trim() || likes.getAttribute('aria-label')) : null,
    comment_count: comments ? ((comments.textContent || '').trim() || comments.getAttribute('aria-label')) : null,
    author_href: authorEl ? authorEl.getAttribute('href') : null,       // transient: hashed in Python, never stored
    author_name: nameEl ? (nameEl.textContent || '').trim() : null,     // transient unless organizational
    org_marker: !!q1(scope, sel.org_marker || []),
    doc_title: document.title || null,
  };
}"""

_COMMENTS_JS = "(cfg) => {" + _HELPERS + """
  const sel = cfg.selectors;
  const focal = q1(document, sel.post_region);
  const cap = q1(focal || document, sel.post_text);
  const [items0, itemSel] = qa(document, sel.comment_item);
  // the focal post (and the caption row some platforms render as the first "comment") is not a comment
  const items = items0.filter(it => !(focal && (it === focal || it.contains(focal))) && !(cap && it.contains(cap)) && visible(it));
  const isReplyMarked = it => (sel.reply_marker || []).some(s => { try { return it.matches(s) || !!it.closest(s); } catch (e) { return false; } });
  const info = new Map();
  for (const it of items) {
    const t = own(it, itemSel, sel.comment_text);
    const a = own(it, itemSel, sel.comment_author_link);
    const n = own(it, itemSel, sel.comment_author_name);
    const tm = own(it, itemSel, sel.comment_time);
    const pl = own(it, itemSel, sel.comment_permalink || []);
    const text = clean(t, sel.comment_text_strip);
    const timeText = tm ? ((tm.textContent || '').trim() || null) : null;
    const authorHref = a ? a.getAttribute('href') : null;
    info.set(it, {text, time: timeText, time_dt: tm ? tm.getAttribute('datetime') : null, author_href: authorHref,
                  author_name: n ? (n.textContent || '').trim() : null, permalink: pl ? pl.getAttribute('href') : null,
                  org_marker: !!own(it, itemSel, sel.org_marker || [])});
  }
  let lastTop = null; const out = [];
  for (const it of items) {
    const d = info.get(it);
    let anc = it.parentElement ? it.parentElement.closest(itemSel) : null;
    while (anc && !info.has(anc)) anc = anc.parentElement ? anc.parentElement.closest(itemSel) : null;
    let depth = 0; for (let p = anc; p; p = p.parentElement ? p.parentElement.closest(itemSel) : null) if (info.has(p)) depth++;
    let parent = anc;
    if (!parent && isReplyMarked(it)) { parent = lastTop; depth = parent ? 1 : 0; }
    const key = JSON.stringify([depth, d.text, d.time, d.author_href, d.permalink]);
    d.key = key; d.depth = depth;
    if (depth === 0) lastTop = it;
    out.push({...d, parent_key: null, _p: parent});
  }
  return out.map(o => { const p = o._p; delete o._p; o.parent_key = p && info.get(p) ? info.get(p).key : null; return o; })
            .filter(o => o.text);
}"""

_SCROLL_JS = """(sels) => {
  let el = null;
  for (const s of (sels || [])) { try { el = document.querySelector(s); } catch (e) {} if (el) break; }
  const scrollable = n => n && n.scrollHeight > n.clientHeight + 10 && /(auto|scroll)/.test(getComputedStyle(n).overflowY);
  let n = el; for (let i = 0; i < 6 && n && !scrollable(n); i++) n = n.parentElement;
  if (scrollable(n)) {
    const before = n.scrollTop; n.scrollTop = n.scrollTop + n.clientHeight * 0.9;
    return {scrolled: n.scrollTop > before, at_end: n.scrollTop + n.clientHeight >= n.scrollHeight - 4};
  }
  const se = document.scrollingElement || document.documentElement;
  const before = se.scrollTop; window.scrollBy(0, window.innerHeight * 0.9);
  return {scrolled: se.scrollTop > before, at_end: se.scrollTop + window.innerHeight >= se.scrollHeight - 4};
}"""

_LABEL_JS = """e => (e.innerText || '').trim() || e.getAttribute('aria-label') ||
  (e.querySelector('[aria-label]') ? e.querySelector('[aria-label]').getAttribute('aria-label') : '')"""

_MARK_COMMENT_JS = "(args) => {" + _HELPERS + """
  const [cfg, commentId, snippet] = args; const sel = cfg.selectors;
  document.querySelectorAll('[data-fbm-target]').forEach(n => n.removeAttribute('data-fbm-target'));
  const focal = q1(document, sel.post_region);
  const cap = q1(focal || document, sel.post_text);
  const [items] = qa(document, sel.comment_item);
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  let best = null;
  for (const it of items) {
    if ((focal && (it === focal || it.contains(focal))) || (cap && it.contains(cap))) continue;
    let ok = false;
    if (commentId) ok = Array.from(it.querySelectorAll('a[href]')).some(a => (a.getAttribute('href') || '').includes(commentId));
    if (!ok && snippet) ok = norm(it.textContent).includes(norm(snippet));
    if (ok && (!best || (it.textContent || '').length < (best.textContent || '').length)) best = it;
  }
  if (best) best.setAttribute('data-fbm-target', '1');
  return !!best;
}"""


class SocialBrowserAdapter(BrowserAdapterBase):
    """Subclasses set the contract class attributes + `config_name`, and may override `post_url_parts`."""

    config_name: str = ""
    org_kind: str = "page"

    def __init__(self, ctx: AdapterContext):
        super().__init__(ctx)
        base = load_adapter_config(self.config_name or self.name)
        over = dict(self.cfg.get("adapter") or {})
        if self.cfg.get("limits"):
            over["limits"] = {**over.get("limits", {}), **self.cfg["limits"]}
        self.acfg = _deep_merge(base, over)
        self.sel = self.acfg["selectors"]
        self.lim = self.acfg["limits"]
        self.markers = self.acfg["text_markers"]
        self.login_url = self.acfg.get("login", {}).get("url")
        hide = ", ".join(self.acfg.get("hide_selectors", []))
        self.hide_css = BASE_HIDE_CSS + (f"\n{hide} {{ visibility: hidden !important; }}" if hide else "")
        self._post_patterns = [re.compile(p) for p in self.acfg["post_url"]["path_patterns"]]
        self._handle_re = re.compile(self.acfg["handle_regex"])
        self._current_url: str | None = None
        self._nav: dict[str, str] = {}
        self._people: set[str] = set()          # transient names/handles seen on the current page (scrub only)
        self._post_author: str | None = None    # transient handle of the current post's author

    # ── limits ──
    @property
    def max_posts(self) -> int:
        b = self.ctx.budget
        return int(b.max_posts_per_query) if b is not None else int(self.lim["max_results_per_query"])

    @property
    def max_comments(self) -> int:
        b = self.ctx.budget
        return int(b.max_comments_per_post) if b is not None else int(self.lim["max_comments_per_post"])

    # ── URLs ──
    def post_url_parts(self, url: str) -> tuple[str, str] | None:
        """(kind, id) for a public post URL of this platform, else None."""
        try:
            p = urlsplit(url if "://" in url else "https://" + url.lstrip("/"))
        except ValueError:
            return None
        host = (p.hostname or "").lower()
        if not any(host == h or host.endswith("." + h) for h in self.acfg["post_url"]["hosts"]):
            return None
        for pat in self._post_patterns:
            m = pat.match(p.path)
            if m:
                return m.groupdict().get("kind") or "post", m.group("id")
        return None

    def canonicalize_url(self, url: str) -> str | None:
        parts = self.post_url_parts(url)
        if not parts:
            return None
        kind, pid = parts
        tpl = self.acfg["post_url"]["canonical"]
        tpl = tpl.get(kind, tpl.get("post")) if isinstance(tpl, dict) else tpl
        return tpl.format(id=pid)

    def handle_from_href(self, href: str | None) -> str | None:
        if not href:
            return None
        path = urlsplit(href).path if "://" in href else href.split("?")[0]
        m = self._handle_re.match(path)
        if not m:
            return None
        h = m.group(1).casefold()
        return None if h in {x.casefold() for x in self.acfg.get("reserved_paths", [])} else h

    def search_url_for(self, query: str) -> str | None:
        """Return the discovery URL for a query or None (with last_skip_reason) when this query can't be searched."""
        s = self.acfg["search"]
        q = query.strip()
        if q.startswith("#") and s.get("hashtag_url"):
            tag = q[1:]
            if re.fullmatch(s.get("hashtag_valid_regex", r"[\w]+"), tag):
                return s["hashtag_url"].format(tag=quote(tag.casefold()))
            if not s.get("keyword_url"):
                self.last_skip_reason = "hashtag_not_valid_in_url_form"
                return None
        if s.get("keyword_url") and s.get("use_keyword_search", True):
            return s["keyword_url"].format(query=quote(q))
        self.last_skip_reason = "keyword_search_not_configured"
        return None

    # ── page state ──
    def _body(self) -> str:
        try:
            return (self.s.page.inner_text("body", timeout=3000) or "")[:8000].casefold()
        except Exception:  # noqa: BLE001
            return ""

    def _has(self, field: str) -> bool:
        sels = self.sel.get(field) or []
        return bool(sels) and bool(self.s.page.evaluate(_FIND_JS, sels))

    def _markers(self, kind: str, body: str | None = None) -> bool:
        body = self._body() if body is None else body
        title = (self.s.page.title() or "").casefold()
        return any(m.casefold() in body or m.casefold() in title for m in self.markers.get(kind, []))

    def is_challenged(self) -> bool:
        if self.s is None:
            return False
        url = (self.s.page.url or "").casefold()
        if any(m in url for m in self.markers.get("challenge_url", [])):
            return True
        if self._markers("challenge"):
            return True
        try:
            if any(self.s.page.locator(sel).count() for sel in self.sel.get("challenge", [])):
                return True
            return detect_block(self.s.page) in (BlockStatus.CAPTCHA, BlockStatus.BOT_CHALLENGE, BlockStatus.CHECKPOINT)
        except Exception:  # noqa: BLE001
            return False

    def is_login_wall(self) -> bool:
        if self.s is None:
            return False
        url = (self.s.page.url or "").casefold()
        if any(m in url for m in self.markers.get("login_url", [])):
            return True
        if not self._markers("login_prompt"):
            return False
        return not any(self._has(f) for f in ("post_text", "search_result_link", "comment_item"))

    def page_state(self) -> str:
        """ok | private | unavailable"""
        body = self._body()
        if self._markers("private", body):
            return "private"
        if self._markers("unavailable", body):
            return "unavailable"
        return "ok"

    def _goto(self, url: str, as_url: str | None = None) -> None:
        s = self.session()
        try:
            s.goto(url, wait_until="domcontentloaded")
        except BlockedError as e:
            if e.status == BlockStatus.LOGIN_WALL:
                raise LoginRequired(f"login wall — run: python -m app.platform_login {self.name}", url) from e
            if e.status == BlockStatus.RATE_LIMITED:
                raise RateLimited("platform rate limit page", url) from e
            if e.status in (BlockStatus.ACCESS_DENIED, BlockStatus.ACCOUNT_RESTRICTED):
                raise AccessBlocked(f"{e.status.value} — stopping this platform", url) from e
            # CAPTCHA / bot challenge / checkpoint: fall through to guard() (human solves it, or we stop)
            if not self.ctx.headed:
                raise Challenged(f"{e.status.value}; run headed to solve it yourself", url) from e
        s.page.wait_for_timeout(int(self.lim["settle_ms"]))
        self.guard()
        self._current_url = as_url or url

    # ── search ──
    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        cursor = json.loads(checkpoint.cursor) if checkpoint.cursor else {}
        self.last_skip_reason = None
        url = self.search_url_for(query)
        if url is None:
            nxt = Checkpoint(query=query, cursor=checkpoint.cursor, page=checkpoint.page, seen=list(checkpoint.seen),
                             exhausted=True)
            self._next_checkpoint = nxt
            log.info("%s: query %r skipped — %s", self.name, query, self.last_skip_reason)
            return SearchPage(items=[], next_checkpoint=nxt, exhausted=True)
        self._goto(url)
        seen = set(checkpoint.seen)
        stop_at = cursor.get("newest_id")
        found: dict[str, SearchItem] = {}
        order: list[str] = []
        rounds, hit_known, no_growth = 0, False, 0
        while True:
            before = len(order)
            for h in self.s.page.evaluate(_SEARCH_JS, self.sel["search_result_link"]):
                canon = self.canonicalize_url(h)
                if not canon or canon in found:
                    continue
                pid = self.post_url_parts(h)[1]
                self._nav[canon] = h           # transient: the URL as found (may contain a handle), never stored
                order.append(canon)
                found[canon] = SearchItem(url=canon, canonical_url=canon, query=query, search_url=safe_url(url), source_id=pid)
                if stop_at and pid == stop_at:
                    hit_known = True
            fresh = [c for c in order if c not in seen]
            if len(fresh) >= self.max_posts or hit_known or rounds >= int(self.lim["max_search_scrolls"]):
                break
            no_growth = no_growth + 1 if len(order) == before else 0
            if no_growth >= 2:
                break
            rounds += 1
            self.s.page.evaluate(_SCROLL_JS, [])
            self.s.page.wait_for_timeout(int(self.lim["scroll_pause_ms"]))
            self.guard()
        items = [found[c] for c in order if c not in seen][: self.max_posts]
        newest = found[order[0]].source_id if order else cursor.get("newest_id")
        nxt = Checkpoint(query=query, page=checkpoint.page + 1, seen=list(checkpoint.seen),
                         cursor=json.dumps({"newest_id": newest, "last_id": items[-1].source_id if items else cursor.get("last_id"),
                                            "scroll_rounds": rounds}))
        self._next_checkpoint = nxt
        log.info("%s search %r: %d new public result(s) after %d scroll(s)", self.name, query, len(items), rounds)
        return SearchPage(items=items, next_checkpoint=nxt, exhausted=not items)

    # ── post ──
    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        self.last_skip_reason = None
        canon = self.canonicalize_url(url)
        if not canon:
            self.last_skip_reason = "not_a_public_post_url"
            return None
        self._goto(self._nav.get(canon, canon), as_url=canon)
        state = self.page_state()
        if state != "ok":
            self.last_skip_reason = self.acfg.get("skip_reasons", {}).get(state, state)
            log.info("%s: skipped %s — %s", self.name, canon, self.last_skip_reason)
            return None
        raw = self.s.page.evaluate(_POST_JS, {"selectors": self.sel})
        if not raw.get("region_found") and not raw.get("text"):
            self.last_skip_reason = "public_visibility_not_confirmed"
            return None
        kind, pid = self.post_url_parts(canon)
        raw.update(canonical_url=canon, kind=kind, id=pid, final_url=self.s.page.url,
                   search_query=item.query if item else "", search_url=item.search_url if item else None)
        return self.normalize_result(raw)

    def _content_type(self, kind: str) -> str:
        return self.acfg.get("content_types", {}).get(kind, self.content_type)

    def _scrub(self, text: str | None) -> str | None:
        """Replace any name/handle seen on this page (transient) with [mention]."""
        if not text:
            return text
        for p in sorted(self._people, key=len, reverse=True):
            if len(p) >= 3:
                text = re.sub(r"@?" + re.escape(p), "[mention]", text, flags=re.I)
        return text

    def _parse_dt(self, iso: str | None) -> datetime | None:
        if not iso:
            return None
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def normalize_result(self, raw: dict) -> SocialPost:
        handle = self.handle_from_href(raw.get("author_href"))
        name = normalize_text(raw.get("author_name") or "") or None
        self._post_author = handle
        self._people = {x for x in (handle, name) if x}
        is_org = bool(raw.get("org_marker")) or looks_organizational(name) or looks_organizational(handle)
        text = normalize_text(raw.get("text") or "") or None
        if not is_org:
            text = self._scrub(text)
        text = text[:20000] if text else None
        title = normalize_text(raw.get("doc_title") or "") or None
        if title and not is_org:
            title = self._scrub(title)
        canon = raw["canonical_url"]
        ptitle = normalize_text(raw.get("title") or "") or None
        ptitle = ptitle if is_org else self._scrub(ptitle)
        engagement = {k: normalize_text(raw[f"{k}_count"]) for k in ("like", "comment") if raw.get(f"{k}_count")}
        post = SocialPost(
            platform=self.platform, source_content_type=self._content_type(raw.get("kind", "post")), source_post_id=raw.get("id"),
            source_post_url=canon, canonical_post_url=canon, document_title=title,
            post_title=ptitle,
            post_text=text, hashtags=sorted(set(HASHTAG_RE.findall(text or ""))),
            published_text_displayed=normalize_text(raw.get("time_text") or "") or None,
            published_at_observed=self._parse_dt(raw.get("time_dt")), engagement=engagement,
            visibility_status="public_verified", visibility_evidence=self.acfg["visibility_evidence"],
            search_query=raw.get("search_query") or "", search_url=raw.get("search_url"), captured_at=datetime.now(timezone.utc),
            adapter_version=self.adapter_version, content_hash=sha256_hex((text or "").casefold()),
            completeness_status="comments_unavailable", comments_supported=self.supports_comments)
        if is_org and (name or handle):
            profile = self.acfg.get("profile_url")
            post.organization = Organization(
                platform=self.platform, name=name or handle, url=profile.format(handle=handle) if profile and handle else None,
                kind=self.org_kind, evidence="platform business/organization marker shown" if raw.get("org_marker")
                else "account name reads as a business")
        elif handle:
            post.author_key = self.keyer.key_for(self.platform, handle)
            post.author_key_version = self.keyer.version
        return post

    def organization_for_post(self, post: SocialPost) -> Organization | None:
        return post.organization

    # ── comments ──
    def _ensure_on(self, url: str) -> None:
        if self.s is None or self._current_url != url:
            self._goto(self._nav.get(url, url), as_url=url)

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        if not self.supports_comments:
            return CommentBatch([], "comments_unavailable")
        self._ensure_on(post.canonical_post_url)
        if self._has("comments_disabled"):
            return CommentBatch([], "comments_unavailable")
        if not self._has("comment_item") and self._has("comments_button"):
            try:
                self.s.page.locator(self.s.page.evaluate(_FIND_JS, self.sel["comments_button"])).first.click(timeout=4000)
                self.s.page.wait_for_timeout(int(self.lim["scroll_pause_ms"]))
            except Exception:  # noqa: BLE001
                pass
        if not self._has("comment_item") and not self._has("comment_list"):
            return CommentBatch([], "comments_unavailable")
        raw, status, rounds = self._expand_and_read()
        comments = self._build(raw, post.canonical_post_url)
        if len(comments) > self.max_comments:
            comments, status = comments[: self.max_comments], "partial_limit"
        log.info("%s %s: %d comment(s)/reply(ies), %s", self.name, post.canonical_post_url, len(comments), status)
        return CommentBatch(comments, status, rounds)

    def _read(self, seen: dict) -> None:
        for c in self.s.page.evaluate(_COMMENTS_JS, {"selectors": self.sel}):
            seen.setdefault(c["key"], c)

    def _expand_and_read(self) -> tuple[list[dict], str, int]:
        expand_re = re.compile(self.markers["expand"], re.I)
        deadline = time.monotonic() + float(self.lim["comment_time_limit_s"])
        seen: dict[str, dict] = {}
        rounds = no_new = 0
        while True:
            self.guard()
            self._read(seen)
            if len(seen) >= self.max_comments:
                return list(seen.values()), "partial_limit", rounds
            if time.monotonic() > deadline:
                return list(seen.values()), "partial_timeout", rounds
            if rounds >= int(self.lim["max_expansion_rounds"]):
                return list(seen.values()), "partial_limit", rounds
            rounds += 1
            before, clicked = len(seen), 0
            for sel in self.sel.get("expand_button", []):
                try:
                    handles = self.s.page.query_selector_all(sel)[:60]   # stable handles: clicked buttons may vanish
                except Exception:  # noqa: BLE001
                    continue
                for b in handles:
                    if clicked >= 10:
                        break
                    try:
                        label = normalize_text(b.evaluate(_LABEL_JS) or "")
                        if label and expand_re.search(label) and b.is_visible():
                            b.click(timeout=3000)
                            clicked += 1
                            self.s.page.wait_for_timeout(int(self.lim["click_pause_ms"]))
                    except Exception:  # noqa: BLE001 - detached / covered button: skip it
                        continue
            scroll = self.s.page.evaluate(_SCROLL_JS, self.sel.get("comment_list", []))
            self.s.page.wait_for_timeout(int(self.lim["scroll_pause_ms"]))
            self._read(seen)
            if len(seen) == before and clicked == 0:
                if scroll.get("at_end"):
                    return list(seen.values()), "complete", rounds
                if not scroll.get("scrolled"):
                    no_new += 1
                    if no_new >= int(self.lim["no_new_comment_attempts"]):
                        return list(seen.values()), "partial_limit", rounds
            else:
                no_new = 0

    def _build(self, raw: list[dict], post_url: str) -> list[SocialComment]:
        for r in raw:
            h = self.handle_from_href(r.get("author_href"))
            r["_handle"] = h
            self._people |= {x for x in (h, normalize_text(r.get("author_name") or "")) if x}
        out: list[SocialComment] = []
        by_key: dict[str, SocialComment] = {}
        replies: dict[str, int] = {}
        counter: dict = {}
        tpl = self.acfg.get("comment_url")
        id_re = re.compile(self.acfg["comment_id_regex"]) if self.acfg.get("comment_id_regex") else None
        post_id = self.post_url_parts(post_url)[1] if self.post_url_parts(post_url) else ""
        for r in sorted(raw, key=lambda x: x["depth"]):
            is_reply = r["depth"] > 0
            parent = by_key.get(r.get("parent_key")) if is_reply else None
            if is_reply and parent is None:
                continue
            if is_reply and replies.get(parent.fingerprint, 0) >= int(self.lim["max_replies_per_comment"]):
                continue
            handle = r["_handle"]
            key = self.keyer.key_for(self.platform, handle) if handle else None
            cid = None
            if id_re and r.get("permalink"):
                m = id_re.search(r["permalink"])
                cid = m.group(1) if m else None
            if cid and cid == post_id:
                continue  # the focal post itself
            curl = tpl.format(id=cid, post_id=post_id) if tpl and cid else None
            c = make_comment(platform=self.platform, post_url=post_url, raw_text=self._scrub(r["text"]) or "", is_reply=is_reply,
                             parent=parent, commenter_key=key, key_version=self.keyer.version if key else None,
                             displayed_timestamp=r.get("time"), commented_at=self._parse_dt(r.get("time_dt")),
                             source_comment_id=cid, source_comment_url=curl, occurrence_counter=counter)
            if c is None or any(x.fingerprint == c.fingerprint for x in out):
                continue
            c.is_post_author = bool(handle and handle == self._post_author)
            out.append(c)
            by_key[r["key"]] = c
            if is_reply:
                replies[parent.fingerprint] = replies.get(parent.fingerprint, 0) + 1
        return out

    # ── evidence ──
    def capture_evidence(self, item: SocialPost | SocialComment) -> Evidence | None:
        if self.s is None:
            return None
        if isinstance(item, SocialPost):
            self._ensure_on(item.canonical_post_url)
            found = self.s.page.evaluate(_FIND_JS, self.sel["post_region"])
            return self.screenshot_locator(self.s.page.locator(found).first, "post") if found else None
        snippet = max(re.split(r"\[(?:mention|phone|email|link)\]", item.comment_text), key=len).strip()[:50]
        if len(snippet) < 2 and not item.source_comment_id:
            return None
        if not self.s.page.evaluate(_MARK_COMMENT_JS, [{"selectors": self.sel}, item.source_comment_id, snippet]):
            return None
        return self.screenshot_locator(self.s.page.locator("[data-fbm-target='1']").first, "comment")
