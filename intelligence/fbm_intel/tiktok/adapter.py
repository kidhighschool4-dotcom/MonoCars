"""TikTokPublicVideosAdapter — public TikTok videos via the normal web UI (owner-approved Playwright approach).

Collects only what the page renders: canonical video URL, document title, caption/hashtags, displayed time and
counts, public comments/replies and their displayed timestamps, and screenshots. Never reads hidden/private
endpoints, never types a password, never solves or bypasses a CAPTCHA. All selectors come from
config/tiktok_adapter_v1.json (several strategies per field).
"""
from __future__ import annotations

import io
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ..browser import BlockedError, BlockStatus, BrowserSession
from ..fb_public.identity import PersonKeyer
from ..fb_public.model import parse_fb_time
from ..normalize import normalize_text, sha256_hex
from ..social.model import Evidence, SocialComment, SocialPost, make_comment
from .urls import author_identifier, canonical_video_url, is_video_url, search_url, video_id

log = logging.getLogger("fbm_intel.tiktok")
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "tiktok_adapter_v1.json"
DIAG_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "tiktok-diagnostics"
HASHTAG_RE = re.compile(r"#[\wក-៿]+")


class LoginRequired(Exception):
    pass


class AccessBlocked(BlockedError):
    def __init__(self, url: str, why: str):
        super().__init__(BlockStatus.CAPTCHA, url)
        self.why = why


def load_config(path: Path = CONFIG_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


_FIND_JS = """(sels) => { for (const s of sels) { try { const el = document.querySelector(s); if (el) return s; } catch (e) {} } return null; }"""

_COMMENTS_JS = """(cfg) => {
  const q = (root, sels) => { for (const s of sels) { try { const r = Array.from(root.querySelectorAll(s)); if (r.length) return r; } catch (e) {} } return []; };
  const q1 = (root, sels) => q(root, sels)[0] || null;
  // union of all text strategies (level-1 comments AND level-2 replies), in document order, de-duplicated
  const seen = new Set(); const texts = [];
  for (const s of cfg.comment_text) { try { document.querySelectorAll(s).forEach(e => { if (!seen.has(e)) { seen.add(e); texts.push(e); } }); } catch (e) {} }
  texts.sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);
  let lastTop = null;
  return texts.map(t => {
    let item = null;
    for (const s of cfg.comment_item) { try { item = t.closest(s); } catch (e) {} if (item) break; }
    item = item || t.parentElement?.parentElement || t;
    const e2e = t.getAttribute('data-e2e') || '';
    const clone = t.cloneNode(true);
    clone.querySelectorAll('a').forEach(a => a.replaceWith('[mention]'));   // @tags → [mention]
    const author = q1(item, cfg.comment_author_link);
    const time = q1(item, cfg.comment_time);
    const level = /level-2/.test(e2e) || /reply/i.test(item.getAttribute('data-e2e') || '') ? 2 : 1;
    const text = (clone.textContent || '').trim();
    const timeText = time ? (time.textContent || '').trim() : null;
    const authorHref = author ? author.getAttribute('href') : null;
    const selfKey = JSON.stringify([level, text, timeText, authorHref]);
    const parentKey = level === 2 ? lastTop : null;         // nearest preceding top-level comment ON THE PAGE
    if (level === 1) lastTop = selfKey;
    return {
      level, key: selfKey, parent_key: parentKey,
      text,
      author_href: author ? author.getAttribute('href') : null,     // transient: hashed in Python, never stored
      time: time ? (time.textContent || '').trim() : null,
      comment_id: item.getAttribute('data-comment-id') || item.id || null,
      visible: !!(item.offsetWidth || item.offsetHeight || item.getClientRects().length),
    };
  }).filter(c => c.visible);
}"""

_SCROLL_JS = """(sels) => {
  let el = null;
  for (const s of sels) { try { el = document.querySelector(s); } catch (e) {} if (el) break; }
  const scrollable = n => n && n.scrollHeight > n.clientHeight + 10 && /(auto|scroll)/.test(getComputedStyle(n).overflowY);
  let n = el; for (let i = 0; i < 6 && n && !scrollable(n); i++) n = n.parentElement;
  if (!scrollable(n)) return {scrolled: false, at_end: true};
  const before = n.scrollTop; n.scrollTop = n.scrollTop + n.clientHeight * 0.9;
  return {scrolled: n.scrollTop > before, at_end: n.scrollTop + n.clientHeight >= n.scrollHeight - 4};
}"""


@dataclass
class Found:
    url: str
    canonical_url: str
    search_phrase: str
    search_url: str


class TikTokPublicVideosAdapter:
    platform = "tiktok"
    allowed_hosts = {"tiktok.com", "tiktokcdn.com", "tiktokcdn-us.com", "ttwstatic.com", "tiktokv.com", "byteoversea.com", "ibytedtos.com"}

    def __init__(self, keyer: PersonKeyer, cfg: dict | None = None, *, headed: bool = False, screenshot_threshold: int | None = None):
        self.cfg = cfg or load_config()
        self.version = self.cfg["version"]
        self.sel = self.cfg["selectors"]
        self.lim = self.cfg["limits"]
        self.markers = self.cfg["text_markers"]
        self.keyer = keyer
        self.headed = headed
        self.threshold = screenshot_threshold if screenshot_threshold is not None else self.cfg["screenshot_threshold"]

    # ── page state ──
    def page_state(self, s: BrowserSession) -> str:
        """ok | login_required | access_blocked | private | unavailable"""
        try:
            body = (s.page.inner_text("body", timeout=3000) or "")[:6000].casefold()
        except Exception:  # noqa: BLE001
            body = ""
        title = (s.page.title() or "").casefold()
        if any(m in body or m in title for m in self.markers["challenge"]) or \
                s.page.locator("iframe[src*='captcha'], [id*='captcha'], [class*='captcha']").count():
            return "access_blocked"
        if any(m in body for m in self.markers["private"]):
            return "private"
        if any(m in body for m in self.markers["unavailable"]):
            return "unavailable"
        if any(m in body for m in self.markers["login_prompt"]) and not self._has(s, "video_desc") and not self._has(s, "search_result_link"):
            return "login_required"
        return "ok"

    def _has(self, s: BrowserSession, field: str) -> bool:
        return bool(s.page.evaluate(_FIND_JS, self.sel[field]))

    def _first_text(self, s: BrowserSession, field: str) -> str | None:
        found = s.page.evaluate(_FIND_JS, self.sel[field])
        if not found:
            return None
        try:
            return normalize_text(s.page.locator(found).first.inner_text(timeout=3000)) or None
        except Exception:  # noqa: BLE001
            return None

    def guard(self, s: BrowserSession) -> None:
        st = self.page_state(s)
        if st == "access_blocked":
            self.diagnose(s, "access_blocked")
            raise AccessBlocked(s.page.url, "challenge_or_automation_block")
        if st == "login_required":
            self.wait_for_manual_login(s)

    def wait_for_manual_login(self, s: BrowserSession) -> None:
        """Pause for the human to log in in the visible window. Never automated."""
        if not self.headed:
            raise LoginRequired("TikTok asks for login — run with --headed and log in manually (python -m app.tiktok_login)")
        log.warning("TikTok is asking for login. Please log in yourself in the browser window (waiting up to %d min)…",
                    self.lim["login_wait_min"])
        deadline = time.monotonic() + self.lim["login_wait_min"] * 60
        while time.monotonic() < deadline:
            time.sleep(3)
            if any(c.get("name") == "sessionid" for c in s.context.cookies("https://www.tiktok.com")) and \
                    self.page_state(s) != "login_required":
                log.info("Login detected; continuing")
                return
        raise LoginRequired("login not completed in time")

    def diagnose(self, s: BrowserSession, reason: str) -> None:
        """Sanitized diagnostics: page structure without text or links, plus a screenshot."""
        try:
            DIAG_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            html = s.page.evaluate("""() => { const c = document.body.cloneNode(true);
                c.querySelectorAll('script,style,img,video,svg').forEach(n => n.remove());
                c.querySelectorAll('*').forEach(n => { for (const t of Array.from(n.childNodes)) if (t.nodeType === 3) t.textContent = t.textContent.trim() ? '·' : '';
                  for (const a of Array.from(n.attributes)) if (!['data-e2e','role','aria-label','class','id'].includes(a.name)) n.removeAttribute(a.name); });
                return c.innerHTML.slice(0, 400000); }""")
            (DIAG_DIR / f"{stamp}-{reason}.html").write_text(html, encoding="utf-8")
            s.page.screenshot(path=str(DIAG_DIR / f"{stamp}-{reason}.png"))
            log.info("Saved sanitized diagnostics to %s", DIAG_DIR)
        except Exception:  # noqa: BLE001
            pass

    # ── search ──
    def search(self, s: BrowserSession, phrase: str) -> list[Found]:
        url = search_url(self.cfg["search_url"], phrase)
        log.info("Opening TikTok search: %r → %s", phrase, url)
        s.goto(url, wait_until="domcontentloaded")
        s.page.wait_for_timeout(self.lim["settle_ms"])
        self.guard(s)
        found: dict[str, Found] = {}
        for _ in range(3):
            for sel in self.sel["search_result_link"]:
                try:
                    hrefs = s.page.eval_on_selector_all(sel, "els => els.map(e => e.href)")
                except Exception:  # noqa: BLE001
                    continue
                for h in hrefs:
                    if is_video_url(h):
                        c = canonical_video_url(h)
                        found.setdefault(c, Found(h, c, phrase, url))
                if found:
                    break
            if len(found) >= self.lim["max_results_per_query"]:
                break
            s.page.mouse.wheel(0, 1400)
            s.page.wait_for_timeout(self.lim["scroll_pause_ms"])
            self.guard(s)
        res = list(found.values())[: self.lim["max_results_per_query"]]
        log.info("Search %r: %d public video result(s) visible", phrase, len(res))
        if not res:
            self.diagnose(s, "no_search_results")
        return res

    # ── video ──
    def _screenshot_region(self, s: BrowserSession, fields: list[str]) -> Evidence | None:
        boxes = []
        for f in fields:
            found = s.page.evaluate(_FIND_JS, self.sel[f])
            if found:
                b = s.page.locator(found).first.bounding_box()
                if b and b["width"] > 0 and b["height"] > 0:
                    boxes.append(b)
        if not boxes:
            return None
        x0, y0 = min(b["x"] for b in boxes), min(b["y"] for b in boxes)
        x1, y1 = max(b["x"] + b["width"] for b in boxes), max(b["y"] + b["height"] for b in boxes)
        vp = s.page.viewport_size or {"width": 1280, "height": 900}
        clip = {"x": max(0, x0), "y": max(0, y0), "width": min(vp["width"], x1) - max(0, x0), "height": min(vp["height"], y1) - max(0, y0)}
        if clip["width"] <= 0 or clip["height"] <= 0:
            return None
        png = s.page.screenshot(clip=clip)
        return _evidence(png, "post")

    def open_comments(self, s: BrowserSession) -> bool:
        if s.page.evaluate(_FIND_JS, self.sel["comment_text"]):
            return True
        btn = s.page.evaluate(_FIND_JS, self.sel["comments_button"])
        if btn:
            try:
                s.page.locator(btn).first.click(timeout=5000)
                s.page.wait_for_timeout(self.lim["scroll_pause_ms"])
            except Exception:  # noqa: BLE001
                pass
        return bool(s.page.evaluate(_FIND_JS, self.sel["comment_text"]))

    def expand_and_read(self, s: BrowserSession) -> tuple[list[dict], str, int]:
        """Scroll the comment container and click 'view replies' until done. Returns (raw, completeness, rounds)."""
        reply_re = re.compile(self.markers["reply_expand"], re.I)
        deadline = time.monotonic() + self.lim["comment_time_limit_s"]
        seen: dict[tuple, dict] = {}
        no_new = rounds = 0
        while True:
            self.guard(s)
            for c in s.page.evaluate(_COMMENTS_JS, self.sel):
                seen.setdefault(c["key"], c)
            if len(seen) >= self.lim["max_comments_per_post"]:
                return list(seen.values()), "partial_limit", rounds
            if time.monotonic() > deadline:
                return list(seen.values()), "partial_timeout", rounds
            if rounds >= self.lim["max_expansion_rounds"]:
                return list(seen.values()), "partial_limit", rounds
            rounds += 1
            before = len(seen)
            clicked = 0
            for sel in self.sel["reply_expand_button"]:
                try:
                    for b in s.page.locator(sel).all()[:30]:
                        if clicked >= 10:
                            break
                        txt = normalize_text(b.inner_text(timeout=500))
                        if txt and reply_re.match(txt) and b.is_visible():
                            b.click(timeout=3000)
                            clicked += 1
                            s.page.wait_for_timeout(600)
                except Exception:  # noqa: BLE001
                    continue
            scroll = s.page.evaluate(_SCROLL_JS, self.sel["comment_list"])
            s.page.wait_for_timeout(self.lim["scroll_pause_ms"])
            for c in s.page.evaluate(_COMMENTS_JS, self.sel):
                seen.setdefault(c["key"], c)
            if len(seen) == before and clicked == 0:
                # 'complete' only when the list visibly reached its end and nothing is left to expand
                if scroll.get("at_end"):
                    return list(seen.values()), "complete", rounds
                # an attempt only "fails" when scrolling made no progress (the platform stopped loading)
                if not scroll.get("scrolled"):
                    no_new += 1
                    if no_new >= self.lim["no_new_comment_attempts"]:
                        return list(seen.values()), "partial_limit", rounds
            else:
                no_new = 0

    def collect_video(self, s: BrowserSession, f: Found) -> SocialPost | None:
        log.info("Opening video %s", f.canonical_url)
        s.goto(f.canonical_url, wait_until="domcontentloaded")
        s.page.wait_for_timeout(self.lim["settle_ms"])
        self.guard(s)
        state = self.page_state(s)
        if state in ("private", "unavailable"):
            log.info("Skipped %s — %s", f.canonical_url, state)
            return None
        desc = self._first_text(s, "video_desc")
        if not desc and not self._has(s, "video_region"):
            log.info("Skipped %s — public_visibility_not_confirmed (no rendered public video)", f.canonical_url)
            self.diagnose(s, "unverified_video")
            return None
        final = canonical_video_url(s.page.url) if is_video_url(s.page.url) else f.canonical_url
        published = self._first_text(s, "publish_time")
        engagement = {k: self._first_text(s, f"{k}_count") for k in ("like", "comment", "share")}
        post = SocialPost(
            platform="tiktok", source_content_type="tiktok_video", source_post_id=video_id(final),
            source_post_url=s.page.url.split("#")[0], canonical_post_url=final,
            document_title=normalize_text(s.page.title()) or None, post_title=None, post_text=desc,
            hashtags=sorted(set(HASHTAG_RE.findall(desc or ""))), published_text_displayed=published,
            published_at_observed=parse_fb_time(published.split("·")[-1].strip()) if published else None,
            engagement={k: v for k, v in engagement.items() if v}, visibility_status="public_verified",
            visibility_evidence="public_video_page_rendered", search_query=f.search_phrase, search_url=f.search_url,
            captured_at=datetime.now(timezone.utc), adapter_version=self.version,
            content_hash=sha256_hex((desc or "").casefold()),
        )
        post.screenshot = self._screenshot_region(s, ["video_region", "video_desc"])

        disabled = s.page.evaluate(_FIND_JS, self.sel["comments_disabled"][:1])
        if disabled or not self.open_comments(s):
            post.completeness_status = "comments_unavailable"
            return post
        raw, status, rounds = self.expand_and_read(s)
        post.completeness_status, post.comment_expansion_rounds = status, rounds
        post.comments = self._build(raw, final)
        self._screenshot_buyer_comments(s, post)
        log.info("Video %s: %d comments, %d replies, %s", final, post.comments_collected_count, post.replies_collected_count, status)
        return post

    def _build(self, raw: list[dict], post_url: str) -> list[SocialComment]:
        out: list[SocialComment] = []
        by_key: dict[str, SocialComment] = {}
        replies: dict[str, int] = {}
        counter: dict = {}
        # top-level first so every reply can find its parent regardless of load order
        for r in sorted(raw, key=lambda x: x["level"]):
            is_reply = r["level"] == 2
            parent = by_key.get(r.get("parent_key")) if is_reply else None
            if is_reply and parent is None:
                continue
            if is_reply and replies.get(parent.fingerprint, 0) >= self.lim["max_replies_per_comment"]:
                continue
            ident = author_identifier(r["author_href"])
            key = self.keyer.key_for("tiktok", ident)
            c = make_comment(platform="tiktok", post_url=post_url, raw_text=r["text"], is_reply=is_reply, parent=parent,
                             commenter_key=key, key_version=self.keyer.version, displayed_timestamp=r["time"],
                             commented_at=parse_fb_time(r["time"]), source_comment_id=r["comment_id"],
                             source_comment_url=None, occurrence_counter=counter)
            if c is None or any(x.fingerprint == c.fingerprint for x in out):
                continue
            out.append(c)
            by_key[r["key"]] = c
            if is_reply:
                replies[parent.fingerprint] = replies.get(parent.fingerprint, 0) + 1
        return out

    def _screenshot_buyer_comments(self, s: BrowserSession, post: SocialPost) -> None:
        """Screenshot only comments above the threshold, with the commenter's name/avatar hidden first."""
        targets = [c for c in post.comments if c.intent.buyer_intent_score >= self.threshold]
        if not targets:
            return
        s.page.add_style_tag(content="a[href^='/@'], a[href^='/@'] *, [data-e2e*='avatar'], [data-e2e*='username'] "
                                     "{ visibility: hidden !important; }")
        for c in targets:
            try:
                snippet = max(re.split(r"\[(?:mention|phone|email|link)\]", c.comment_text), key=len).strip()[:60]
                if len(snippet) < 2:
                    continue
                loc = s.page.get_by_text(snippet, exact=False).first
                item = loc.locator("xpath=ancestor::div[2]")
                png = item.screenshot(timeout=4000)
                c.screenshot = _evidence(png, "comment")
            except Exception:  # noqa: BLE001
                continue


def _evidence(png: bytes, kind: str) -> Evidence:
    with Image.open(io.BytesIO(png)) as im:
        w, h = im.size
    return Evidence(png=png, checksum_sha256=sha256_hex(png), width=w, height=h, kind=kind)
