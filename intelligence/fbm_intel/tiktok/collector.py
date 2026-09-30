"""One TikTok run: keyword variants → public search UI → public videos → comments → score → persist."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..browser import BlockedError, open_persistent_session
from ..social.model import apply_persist_policy
from .adapter import AccessBlocked, LoginRequired, TikTokPublicVideosAdapter

log = logging.getLogger("fbm_intel.tiktok")
PROFILE_DIR = Path(__file__).resolve().parents[2] / "private" / "tiktok-profile"


@dataclass
class TikTokReport:
    phrases: list[str]
    search_urls: list[dict] = field(default_factory=list)
    videos: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    buyer_comments: list[dict] = field(default_factory=list)
    stopped: str | None = None
    errors: int = 0


def run(adapter: TikTokPublicVideosAdapter, phrases: list[str], *, repo=None, dry_run: bool = False,
        persist_policy: str = "all", max_videos_total: int = 20, session_factory=None, on_session=None) -> TikTokReport:
    rep = TikTokReport(phrases=phrases)
    factory = session_factory or (lambda: open_persistent_session(adapter.allowed_hosts, str(PROFILE_DIR),
                                                                  adapter.lim["page_load_interval_s"], headless=not adapter.headed))
    seen: set[str] = set()
    with factory() as s:
        if on_session:
            on_session(s)
        for phrase in phrases:
            try:
                found = adapter.search(s, phrase)
            except (AccessBlocked, BlockedError) as e:
                rep.stopped = f"access_blocked at {e.url}"
                log.error("TikTok blocked further access (%s) — stopping the TikTok run", rep.stopped)
                return rep
            except LoginRequired as e:
                rep.stopped = f"login_required: {e}"
                log.error("%s — stopping the TikTok run", rep.stopped)
                return rep
            except Exception as e:  # noqa: BLE001
                rep.errors += 1
                log.warning("Search %r failed (%s) — next phrase", phrase, type(e).__name__)
                continue
            rep.search_urls.append({"phrase": phrase, "search_url": found[0].search_url if found else None, "results": len(found)})
            for f in found:
                if f.canonical_url in seen or len(seen) >= max_videos_total:
                    continue
                seen.add(f.canonical_url)
                if dry_run:
                    rep.videos.append({"url": f.canonical_url, "phrase": phrase, "collected": False})
                    continue
                try:
                    post = adapter.collect_video(s, f)
                except (AccessBlocked, BlockedError) as e:
                    rep.stopped = f"access_blocked at {e.url}"
                    log.error("TikTok blocked further access (%s) — stopping the TikTok run", rep.stopped)
                    return rep
                except LoginRequired as e:
                    rep.stopped = f"login_required: {e}"
                    return rep
                except Exception as e:  # noqa: BLE001
                    rep.errors += 1
                    log.warning("Video %s failed (%s) — skipping", f.canonical_url, type(e).__name__)
                    continue
                if post is None:
                    rep.skipped.append({"url": f.canonical_url, "reason": "public_visibility_not_confirmed_or_unavailable"})
                    if repo and not dry_run:
                        repo.record_skip("tiktok", f.canonical_url, phrase, "unverified", "public_visibility_not_confirmed")
                    continue
                for c in post.comments:
                    if c.intent.buyer_intent_label != "not_buyer_intent":
                        rep.buyer_comments.append({"video": post.canonical_post_url, "text": c.comment_text[:200],
                                                   "score": c.intent.buyer_intent_score, "label": c.intent.buyer_intent_label,
                                                   "type": c.intent.intent_type, "phrases": c.intent.matched_phrases,
                                                   "screenshot": bool(c.screenshot)})
                apply_persist_policy(post, persist_policy, adapter.threshold)
                new = repo.save_post(post) if repo else (None, 0, 0)
                rep.videos.append({"url": post.canonical_post_url, "phrase": phrase, "search_url": post.search_url,
                                   "comments": post.comments_collected_count, "replies": post.replies_collected_count,
                                   "completeness": post.completeness_status, "hashtags": post.hashtags,
                                   "new_comments": new[1], "new_replies": new[2],
                                   "rejected_not_persisted": post.rejected_comment_count})
    return rep
