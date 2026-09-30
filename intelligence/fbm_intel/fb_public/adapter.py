"""FacebookPublicPostsAdapter — Facebook Posts search (not Marketplace), public posts only.

Browser actions are limited to: open the search, tick the "Public posts" filter if Facebook offers one, scroll a
few times, open verified-public post permalinks, and click comment-expansion controls ("View more comments",
"View N replies", "See more", comment sort → "All comments"). It never likes, comments, messages, follows, or
opens anyone's profile. Author links are read from the page only to compute an HMAC key and then discarded.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

from ..browser import BlockedError, BlockStatus, BrowserSession, detect_block
from ..normalize import normalize_text, sha256_hex
from .identity import PersonKeyer
from .model import ADAPTER_VERSION, Limits, PublicPost, RawComment, build_comments, parse_fb_time
from .urls import (canonical_post_url, canonical_profile_url, is_group_post, is_post_url, post_id,
                   post_url_from_photo_set)
from .visibility import Visibility, VisibilitySignals, verify

log = logging.getLogger("fbm_intel.fb_public")

EXPAND_RE = re.compile(
    r"^(?:(?:view|see)\s+(?:more|previous|all\s+\d+|\d+(?:\s+more)?)\s+(?:comments?|repl(?:y|ies))"
    r"|\d+\s+repl(?:y|ies)|see more|view more comments|view previous comments|view more replies)$", re.I)
TIME_LABEL_PY = (r"(?i)^(\d+\s*(s|m|h|d|w|y|mins?|hrs?|minutes?|hours?|days?|weeks?|months?|years?)(\s+ago)?"
                 r"|an? (second|minute|hour|day|week|month|year) ago|just now|yesterday.*|[A-Z][a-z]+ \d{1,2}(, \d{4})?( at .*)?)$")
BLOCK_TO_REASON = {BlockStatus.LOGIN_WALL: "login_wall", BlockStatus.CHECKPOINT: "checkpoint",
                   BlockStatus.CAPTCHA: "captcha", BlockStatus.BOT_CHALLENGE: "captcha",
                   BlockStatus.RATE_LIMITED: "rate_limit", BlockStatus.ACCOUNT_RESTRICTED: "checkpoint",
                   BlockStatus.ACCESS_DENIED: "checkpoint"}

# Facebook's search feed items are the children of [role=feed] (not always role=article).
TIME_LABEL_JS = r"/^(\\d+\\s*(s|m|h|d|w|y|mins?|hrs?|minutes?|hours?|days?|weeks?|months?|years?)(\\s+ago)?|an? (second|minute|hour|day|week|month|year) ago|just now|yesterday.*|[A-Z][a-z]+ \\d{1,2}(, \\d{4})?( at .*)?)$/i"

_SEARCH_JS = """() => {
  const feed = document.querySelector('[role="feed"]');
  const items = feed ? Array.from(feed.children)
      : Array.from(document.querySelectorAll('[role="article"]')).filter(a => !a.parentElement.closest('[role="article"]'));
  const timeRe = """ + TIME_LABEL_JS + """;
  return items.map((it, i) => {
    const labels = Array.from(it.querySelectorAll('[aria-label],[title],svg title'))
      .map(e => (e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent || '').trim())
      .filter(t => t && t.length < 60);
    const txt = it.innerText || '';
    const timeLinks = Array.from(it.querySelectorAll('a')).filter(a => timeRe.test((a.getAttribute('aria-label') || a.innerText || '').trim()));
    return {
      index: i, empty: txt.trim().length === 0,
      links: Array.from(it.querySelectorAll('a[href]')).map(x => x.href),
      time_links: timeLinks.map(a => a.getAttribute('href') ? a.href : null),
      time_label: timeLinks.length ? (timeLinks[0].getAttribute('aria-label') || timeLinks[0].innerText || '').trim() : null,
      labels,
      group_texts: labels.filter(t => /\\b(public|private) group\\b/i.test(t))
        .concat(txt.split('\\n').filter(t => /\\b(public|private) group\\b/i.test(t))).slice(0, 5),
      unavailable: /content isn.t available/i.test(txt),
    };
  });
}"""

_STRUCTURE_JS = r"""() => {
  const shape = h => { try { const u = new URL(h, location.href);
      if (!/facebook[.]com$/.test(u.hostname)) return 'external';
      const segs = u.pathname.split('/').filter(Boolean).map(s => /^\d+$/.test(s) ? '<num>' : /^pfbid/.test(s) ? '<pfbid>'
        : ['groups','posts','permalink','photo','watch','reel','story.php','permalink.php','profile.php','marketplace','search','hashtag','videos','events','people','share','p'].includes(s) ? s : '<name>');
      const q = Array.from(u.searchParams.keys()).filter(k => !k.startsWith('__')).sort().join(',');
      return '/' + segs.join('/') + (q ? '?' + q : '');
    } catch (e) { return 'bad'; } };
  const count = sel => document.querySelectorAll(sel).length;
  const shapes = {};
  document.querySelectorAll('a[href]').forEach(a => { const k = a.getAttribute('href') === '#' ? '#' : shape(a.href); shapes[k] = (shapes[k] || 0) + 1; });
  const top = Object.entries(shapes).sort((a, b) => b[1] - a[1]).slice(0, 40);
  return {
    title_len: document.title.length, path: location.pathname,
    feeds: count('[role="feed"]'), articles: count('[role="article"]'), mains: count('[role="main"]'),
    feed_children: (document.querySelector('[role="feed"]') || {children: []}).children.length,
    aria_posinset: count('[aria-posinset]'), hash_links: count('a[href="#"]'),
    svg_titles: Array.from(new Set(Array.from(document.querySelectorAll('svg title')).map(t => t.textContent.trim()).filter(t => t.length < 30))).slice(0, 30),
    aria_labels_short: Array.from(new Set(Array.from(document.querySelectorAll('[aria-label]')).map(e => e.getAttribute('aria-label')).filter(t => t && t.length < 25 && !/\s\S+\s\S+\s/.test(t)))).slice(0, 40),
    link_shapes: top,
  };
}"""

_TIMESTAMP_JS = r"""() => {
  const timeRe = __TIME_RE__;
  const shape = h => { if (!h) return null; try { const u = new URL(h, location.href);
      const segs = u.pathname.split('/').filter(Boolean).map(s => /^\d+$/.test(s) ? '<num>' : /^pfbid/.test(s) ? '<pfbid>'
        : ['groups','posts','permalink','photo','watch','reel','story.php','permalink.php','profile.php','videos','share','p','commerce','listing'].includes(s) ? s : '<name>');
      return u.hostname.replace(/^[a-z]+\./,'*.') + '/' + segs.join('/') + '?' + Array.from(u.searchParams.keys()).filter(k => !k.startsWith('__')).sort().join(',');
    } catch (e) { return 'bad'; } };
  const feed = document.querySelector('[role="feed"]');
  return (feed ? Array.from(feed.children) : []).map((it, i) => {
    const anchors = Array.from(it.querySelectorAll('a'));
    const tl = anchors.filter(a => timeRe.test((a.getAttribute('aria-label') || a.innerText || '').trim()));
    const spans = Array.from(it.querySelectorAll('span')).filter(sp => timeRe.test((sp.getAttribute('aria-label') || sp.innerText || '').trim())).length;
    return { i, text_len: (it.innerText || '').length, anchors: anchors.length, time_links: tl.length, time_spans: spans,
             time_link_shapes: tl.slice(0, 3).map(a => a.getAttribute('href') === null ? 'NO_HREF' : shape(a.href)),
             has_aria_label_time_on: tl.slice(0,2).map(a => a.getAttribute('aria-label') ? 'aria' : 'text') };
  });
}"""

_POST_JS = """() => {
  const isComment = a => /^(comment|reply) by /i.test(a.getAttribute('aria-label') || '');
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  // Real Facebook: the post may sit in one of several dialogs or in main, and the audience icon is NOT inside a
  // role=article. Pick the region that actually holds the post (message / comments), then read it minus comments.
  const regions = Array.from(document.querySelectorAll('[role="dialog"]')).concat(Array.from(document.querySelectorAll('[role="main"]')));
  const score = r => (r.querySelector('[data-ad-preview="message"],[data-ad-comet-preview="message"],[data-testid="post-message"]') ? 100 : 0)
                   + Array.from(r.querySelectorAll('[role="article"]')).filter(isComment).length
                   + (Array.from(r.querySelectorAll('svg title')).some(t => /^shared with/i.test(t.textContent.trim())) ? 10 : 0);
  const scope = regions.filter(visible).sort((a, b) => score(b) - score(a))[0] || document.body;
  const inComment = el => { const a = el.closest('[role="article"]'); return !!(a && isComment(a)); };
  const labels = Array.from(scope.querySelectorAll('[aria-label],[title],svg title')).filter(e => !inComment(e))
    .map(e => (e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent || '').trim())
    .filter(t => t && t.length < 60);
  const postLinks = Array.from(scope.querySelectorAll('a[href]')).filter(e => !inComment(e))
    .map(x => ({href: x.href, text: (x.innerText || x.getAttribute('aria-label') || '').trim().slice(0, 40)}));
  const msg = scope.querySelector('[data-ad-preview="message"],[data-ad-comet-preview="message"],[data-testid="post-message"]');
  const postText = msg ? msg.innerText : Array.from(scope.querySelectorAll('div[dir="auto"]'))
      .filter(e => !inComment(e) && !e.closest('a')).map(e => e.innerText).slice(0, 20).join('\\n');
  const txt = Array.from(scope.querySelectorAll('span,div')).filter(e => !inComment(e) && e.children.length === 0)
      .map(e => e.textContent).filter(t => /\\b(public|private) group\\b/i.test(t)).slice(0, 5);
  const comments = Array.from(scope.querySelectorAll('[role="article"]')).filter(a => isComment(a) && visible(a));
  return {
    labels, post_links: postLinks, post_text: postText, group_texts: txt,
    unavailable: /content isn.t available|this content is no longer available/i.test(document.body.innerText || ''),
    comments: comments.map(c => {
      const mine = el => el.closest('[role="article"]') === c;
      const links = Array.from(c.querySelectorAll('a[href]')).filter(mine)
        .map(x => ({href: x.href, text: (x.innerText || '').trim().slice(0, 20)}));
      const body = Array.from(c.querySelectorAll('div[dir="auto"]')).filter(e => mine(e) && !e.closest('a'))
        .map(e => e.innerText).join('\\n');
      const parentEl = c.parentElement.closest('[role="article"]');
      return {
        kind: /^reply by /i.test(c.getAttribute('aria-label') || '') ? 'reply' : 'comment',
        links, text: body, parent_index: parentEl && isComment(parentEl) ? comments.indexOf(parentEl) : null,
      };
    }),
  };
}"""


@dataclass
class SearchResult:
    url: str
    canonical_url: str
    visibility: Visibility


class FacebookPublicPostsAdapter:
    platform = "facebook"
    allowed_hosts = {"facebook.com", "fbcdn.net", "facebook.net", "fbsbx.com"}

    def __init__(self, keyer: PersonKeyer, limits: Limits = Limits(), search_base: str = "https://www.facebook.com"):
        self.keyer = keyer
        self.limits = limits
        self.search_base = search_base.rstrip("/")

    # ── guards ──
    def check(self, s: BrowserSession) -> None:
        b = detect_block(s.page)
        if b != BlockStatus.NONE:
            raise BlockedError(b, s.page.url)

    # ── search ──
    def search_url(self, query: str) -> str:
        return f"{self.search_base}/search/posts/?q={quote(normalize_text(query))}"

    def open_search(self, s: BrowserSession, query: str) -> str:
        url = self.search_url(query)
        log.info("Opening Facebook Posts search (not Marketplace): %s", url)
        s.goto(url, wait_until="domcontentloaded")
        s.page.wait_for_timeout(self.limits.settle_ms)
        self.apply_public_filter(s)
        return url

    def apply_public_filter(self, s: BrowserSession) -> bool:
        pat = re.compile(r"^public posts$", re.I)
        for role in ("switch", "checkbox", "radio"):
            ctl = s.page.get_by_role(role, name=pat)
            if ctl.count():
                try:
                    if ctl.first.get_attribute("aria-checked") != "true":
                        ctl.first.click(timeout=5000)
                        s.page.wait_for_timeout(self.limits.settle_ms)
                    log.info("Applied Facebook's 'Public posts' filter")
                    return True
                except Exception as e:  # noqa: BLE001
                    log.info("Could not apply 'Public posts' filter (%s); relying on per-post verification", type(e).__name__)
                    return False
        log.info("No 'Public posts' filter offered; every result is verified individually")
        return False

    def structure_report(self, s: BrowserSession) -> dict:
        """Anonymous DOM structure (counts + URL shapes only) for fixing selectors. No names, text or real URLs."""
        return s.page.evaluate(_STRUCTURE_JS)

    def timestamp_report(self, s: BrowserSession) -> list[dict]:
        """Per feed item: how many timestamp-like links, and the anonymized shape of their href after hover."""
        hovered = self._reveal_permalinks(s)
        rows = s.page.evaluate(_TIMESTAMP_JS.replace("__TIME_RE__", TIME_LABEL_JS))
        return [{"hovered_total": hovered}] + rows

    def _reveal_permalinks(self, s: BrowserSession) -> int:
        """Facebook fills in a post's timestamp href only on hover. Hover each timestamp link once (read-only)."""
        hovered = 0
        items = s.page.locator("[role='feed'] > div")
        n = min(items.count(), self.limits.max_posts_per_query * 3)
        for i in range(n):
            for a in items.nth(i).locator("a").all()[:40]:
                label = (a.get_attribute("aria-label") or "").strip()
                if not label or not re.match(TIME_LABEL_PY, label):
                    continue
                try:
                    a.hover(timeout=3000)
                    s.page.wait_for_timeout(250)
                    hovered += 1
                except Exception:  # noqa: BLE001
                    pass
                break
        return hovered

    def collect_results(self, s: BrowserSession) -> list[SearchResult]:
        results: dict[str, SearchResult] = {}
        no_link = 0
        for i in range(self.limits.max_search_scrolls + 1):
            self._reveal_permalinks(s)
            no_link = 0
            for r in s.page.evaluate(_SEARCH_JS):
                if r["empty"]:
                    continue
                url = next((h for h in r["time_links"] if h and is_post_url(h)), None) \
                    or next((h for h in r["links"] if is_post_url(h)), None)
                if not url:
                    # Posts search hides permalinks; rebuild from photo set=pcb.<post id> + the posting Page link
                    author = next((h for h in r["links"] if canonical_profile_url(h)), None)
                    url = next((u for u in (post_url_from_photo_set(h, author) for h in r["links"]) if u), None)
                if not url:
                    no_link += 1
                    continue
                canon = canonical_post_url(url)
                if canon in results:
                    continue
                vis = verify(VisibilitySignals(url=canon, is_group_post=is_group_post(canon),
                                               audience_labels=tuple(r["labels"]), group_privacy_texts=tuple(r["group_texts"]),
                                               content_unavailable=r["unavailable"]))
                results[canon] = SearchResult(url, canon, vis)
            if len(results) >= self.limits.max_posts_per_query or i == self.limits.max_search_scrolls:
                break
            before = len(results)
            s.page.mouse.wheel(0, 1600)
            s.page.wait_for_timeout(self.limits.scroll_pause_ms)
            self.check(s)
            if len(results) == before and i > 0:
                break
        found = list(results.values())[: self.limits.max_posts_per_query]
        log.info("Posts search results: %d with a post link (%d verified public); %d result blocks had no post permalink "
                 "(no exact post link in the search result, e.g. group sale posts — skipped)", len(found), sum(r.visibility.verified for r in found), no_link)
        return found

    # ── post ──
    def expand_comments(self, s: BrowserSession) -> tuple[bool, str | None, int]:
        """Click expansion controls until none remain or a limit/timeout is hit. Returns (complete, reason, rounds)."""
        deadline = time.monotonic() + self.limits.comment_load_timeout_seconds
        self._switch_to_all_comments(s)
        rounds = 0
        while rounds < self.limits.max_comment_expansion_rounds:
            self.check(s)
            if time.monotonic() > deadline:
                return False, "timeout", rounds
            if s.page.locator("[role='article'][aria-label^='Comment by']:visible, [role='article'][aria-label^='Reply by']:visible").count() \
                    >= self.limits.max_comments_per_post:
                return False, "configured_limit_reached", rounds
            buttons = [b for b in s.page.get_by_role("button").all()
                       if b.is_visible() and EXPAND_RE.match(normalize_text(self._text(b)))]
            if not buttons:
                return True, None, rounds
            rounds += 1
            before = self._visible_articles(s)
            for b in buttons[: self.limits.max_clicks_per_round]:
                try:
                    b.click(timeout=4000)
                    s.page.wait_for_timeout(self.limits.expansion_click_pause_ms)
                except Exception:  # noqa: BLE001 — element went away after an earlier click
                    continue
            if self._visible_articles(s) == before and not self._any_see_more(s):
                return False, "facebook_stopped_loading", rounds
        return False, "configured_limit_reached", rounds

    @staticmethod
    def _visible_articles(s: BrowserSession) -> int:
        return s.page.evaluate("() => Array.from(document.querySelectorAll('[role=\"article\"]'))"
                               ".filter(e => e.offsetWidth || e.offsetHeight || e.getClientRects().length).length")

    @staticmethod
    def _text(loc) -> str:
        try:
            return loc.inner_text(timeout=1000)
        except Exception:  # noqa: BLE001
            return ""

    def _any_see_more(self, s: BrowserSession) -> bool:
        return any(b.is_visible() and EXPAND_RE.match(normalize_text(self._text(b))) for b in s.page.get_by_role("button").all())

    def _switch_to_all_comments(self, s: BrowserSession) -> None:
        sort = s.page.get_by_role("button", name=re.compile(r"^(most relevant|top comments)$", re.I))
        if not sort.count():
            return
        try:
            sort.first.click(timeout=4000)
            s.page.wait_for_timeout(1500)
            opt = s.page.get_by_role("menuitem", name=re.compile(r"^all comments", re.I))
            if opt.count():
                opt.first.click(timeout=4000)
                s.page.wait_for_timeout(2500)
                log.info("Comment order switched to 'All comments'")
        except Exception:  # noqa: BLE001
            pass

    def collect_post(self, s: BrowserSession, result: SearchResult, query: str) -> PublicPost | None:
        """Open a verified-public post, re-verify on the post page, expand and collect comments."""
        log.info("Opening public post %s", result.canonical_url)
        s.goto(result.canonical_url, wait_until="domcontentloaded")
        s.page.wait_for_timeout(self.limits.settle_ms)
        final_canon = canonical_post_url(s.page.url) if is_post_url(s.page.url) else result.canonical_url
        data = s.page.evaluate(_POST_JS)
        vis = verify(VisibilitySignals(url=final_canon, is_group_post=is_group_post(final_canon),
                                       audience_labels=tuple(data["labels"]), group_privacy_texts=tuple(data["group_texts"]),
                                       content_unavailable=data["unavailable"]))
        if not vis.verified:
            log.info("Skipped %s on the post page: %s (%s)", final_canon, vis.skip_reason, vis.status)
            result.visibility = Visibility(vis.status if vis.status != "public_verified" else "unverified", None,
                                           "visibility_changed" if vis.status in ("private", "restricted") else vis.skip_reason)
            return None

        author_href = next((l["href"] for l in data["post_links"] if canonical_profile_url(l["href"])), None)
        time_text = next((l["text"] for l in data["post_links"] if is_post_url(l["href"])), None)
        text = normalize_text(data["post_text"])[:20000] or None
        post = PublicPost(
            source_post_id=post_id(final_canon), source_post_url=s.page.url.split("#")[0], canonical_post_url=final_canon,
            author_key=self.keyer.key(author_href), author_key_version=self.keyer.version if self.keyer.key(author_href) else None,
            post_text=text, published_at_observed=parse_fb_time(time_text), visibility_status=vis.status,
            visibility_evidence=vis.evidence or "", search_query=normalize_text(query), captured_at=datetime.now(timezone.utc),
            content_hash=sha256_hex((text or "").casefold()),
        )
        try:
            complete, reason, rounds = self.expand_comments(s)
        except BlockedError as e:
            post.comments_complete, post.comments_incomplete_reason = False, BLOCK_TO_REASON.get(e.status, "unknown")
            raise PartialPost(post, e) from e
        data = s.page.evaluate(_POST_JS)  # re-read after expansion
        raw = []
        for c in data["comments"]:
            permalink = next((l["href"] for l in c["links"] if "comment_id=" in l["href"] and is_post_url(l["href"])), None)
            author = next((l["href"] for l in c["links"] if canonical_profile_url(l["href"])), None)
            time_txt = next((l["text"] for l in c["links"] if l["href"] == permalink), None)
            raw.append(RawComment(kind=c["kind"], text=c["text"], permalink=permalink, author_href=author,
                                  time_text=time_txt, dom_parent=c["parent_index"]))
        comments, truncated = build_comments(raw, final_canon, self.keyer, self.limits)
        post.comments = comments
        post.comment_expansion_rounds = rounds
        if truncated and complete:
            complete, reason = False, "configured_limit_reached"
        post.comments_complete, post.comments_incomplete_reason = complete, (None if complete else reason or "unknown")
        log.info("Post %s: %d comments, %d replies, complete=%s%s", final_canon, post.comments_collected_count,
                 post.replies_collected_count, complete, "" if complete else f" ({post.comments_incomplete_reason})")
        return post


class PartialPost(Exception):
    """A block happened mid-post; carries what was verified so far so it can be saved as incomplete."""

    def __init__(self, post: PublicPost, cause: BlockedError):
        super().__init__(str(cause))
        self.post = post
        self.cause = cause
