"""Runs one public-posts crawl: search → verify → collect → persist, with safe stops and clear logging."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..adapters.facebook import SESSION_PATH, is_logged_in
from ..browser import BlockedError, BlockStatus, open_session
from .adapter import BLOCK_TO_REASON, FacebookPublicPostsAdapter, PartialPost

log = logging.getLogger("fbm_intel.fb_public")


@dataclass
class CrawlReport:
    query: str
    search_url: str | None = None
    results: int = 0
    verified_public: int = 0
    skipped: list[dict] = field(default_factory=list)
    posts: list[dict] = field(default_factory=list)
    new_comments: int = 0
    new_replies: int = 0
    stopped: str | None = None
    debug: dict | None = None
    buyer_comments: list[dict] = field(default_factory=list)
    error: str | None = None
    errors: int = 0


def run(adapter: FacebookPublicPostsAdapter, query: str, *, repo=None, headless: bool = True, session_path=SESSION_PATH,
        dry_run: bool = False, check_login: bool = True, on_session=None, debug: bool = False,
        buyer_only: bool = False) -> CrawlReport:
    rep = CrawlReport(query=query)
    if check_login and not session_path.exists():
        rep.stopped = "no_session: run python -m app.facebook_login"
        return rep
    with open_session(adapter.allowed_hosts, adapter.limits.page_load_interval_s, headless=headless,
                      storage_state=str(session_path) if check_login else None) as s:
        if on_session:  # test hook (e.g. route requests to local fixtures)
            on_session(s)
        try:
            if check_login:
                s.goto("https://www.facebook.com/", wait_until="domcontentloaded")
                s.page.wait_for_timeout(2500)
                if not is_logged_in(s.context, s.page):
                    raise BlockedError(BlockStatus.LOGIN_WALL, s.page.url)
                log.info("Facebook session loaded and logged in")
            rep.search_url = adapter.open_search(s, query)
            if debug:
                s.page.wait_for_timeout(5000)
                rep.debug = {"after_load": adapter.structure_report(s)}
                s.page.mouse.wheel(0, 1600)
                s.page.wait_for_timeout(4000)
                rep.debug["after_scroll"] = adapter.structure_report(s)
                rep.debug["timestamps"] = adapter.timestamp_report(s)
            results = adapter.collect_results(s)
        except BlockedError as e:
            rep.stopped = f"{e.status.value} at {e.url}"
            log.error("Facebook blocked or restricted the run: %s — stopped", rep.stopped)
            return rep
        except Exception as e:  # noqa: BLE001 — network timeout etc.: skip this query, don't end the session
            rep.error = f"{type(e).__name__}: {str(e).splitlines()[0][:150]}"
            log.warning("Search failed (%s) — skipping this query", rep.error)
            return rep
        rep.results = len(results)

        for r in results:
            if not r.visibility.verified:
                log.info("Skipped %s — %s (%s)", r.canonical_url, r.visibility.skip_reason, r.visibility.status)
                rep.skipped.append({"url": r.canonical_url, "visibility_status": r.visibility.status,
                                    "skip_reason": r.visibility.skip_reason})
                if repo and not dry_run:
                    repo.record_skip(r.canonical_url, query, r.visibility.status, r.visibility.skip_reason)
                continue
            if dry_run:
                rep.verified_public += 1
                rep.posts.append({"url": r.canonical_url, "evidence": r.visibility.evidence, "collected": False})
                continue
            try:
                post = adapter.collect_post(s, r, query)
            except PartialPost as pp:
                if repo:
                    repo.save_post(pp.post)
                rep.stopped = f"{pp.cause.status.value} at {pp.cause.url}"
                log.error("Facebook blocked or restricted the run while expanding comments: %s — stopped", rep.stopped)
                break
            except BlockedError as e:
                rep.stopped = f"{e.status.value} at {e.url}"
                log.error("Facebook blocked or restricted the run: %s — stopped", rep.stopped)
                break
            except Exception as e:  # noqa: BLE001 — transient (timeout, detached element): skip this post
                log.warning("Post %s failed (%s: %s) — skipping", r.canonical_url, type(e).__name__, str(e).splitlines()[0][:120])
                rep.errors += 1
                continue
            if post is None:  # visibility changed / unverified on the post page
                rep.skipped.append({"url": r.canonical_url, "visibility_status": r.visibility.status,
                                    "skip_reason": r.visibility.skip_reason})
                if repo:
                    repo.record_skip(r.canonical_url, query, r.visibility.status, r.visibility.skip_reason)
                continue
            rep.verified_public += 1
            if buyer_only:
                from .model import keep_buyer_intent
                post.comments = keep_buyer_intent(post.comments)
                for c in post.comments:
                    if c.buyer_intent:
                        rep.buyer_comments.append({"comment_url": c.canonical_comment_url or c.source_comment_url,
                                                   "post_url": post.canonical_post_url, "signals": c.buyer_intent_signals,
                                                   "matched_phrases": c.matched_phrases, "text": c.comment_text[:300],
                                                   "type": c.comment_type})
            new_c = new_r = 0
            if repo:
                _, new_c, new_r = repo.save_post(post)
            rep.new_comments += new_c
            rep.new_replies += new_r
            rep.posts.append({"url": post.canonical_post_url, "evidence": post.visibility_evidence,
                              "comments": post.comments_collected_count, "replies": post.replies_collected_count,
                              "complete": post.comments_complete, "incomplete_reason": post.comments_incomplete_reason,
                              "new_comments": new_c, "new_replies": new_r})
    return rep


__all__ = ["run", "CrawlReport", "BLOCK_TO_REASON"]
