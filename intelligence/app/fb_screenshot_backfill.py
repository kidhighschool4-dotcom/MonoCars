"""Screenshots for Facebook posts collected before screenshot capture existed.

  python -m app.fb_screenshot_backfill [--limit 20] [--headed]

For each stored public post without a screenshot: open it with the saved owner session, expand comments, hide names
and avatars, take the post screenshot + one per stored buyer comment, upload to the private bucket and fill
screenshot_path. Stops on any checkpoint / login wall / restriction. Reads nothing new and stores no new comments.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from fbm_intel.adapters.facebook import SESSION_PATH, is_logged_in
from fbm_intel.browser import BlockedError, open_session
from fbm_intel.fb_public.adapter import _POST_JS, FacebookPublicPostsAdapter
from fbm_intel.fb_public.identity import PersonKeyer
from fbm_intel.fb_public.model import Limits, PublicComment, PublicPost
from fbm_intel.fb_public.repo import FacebookPublicRepo
from fbm_intel.settings import Settings
from fbm_intel.social.repo import upload_evidence

log = logging.getLogger("fb_backfill")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args(argv)
    st = Settings.load()
    from app.crawl import resolve_owner
    owner = resolve_owner(st, os.environ.get("FB_DATA_OWNER_EMAIL"))
    if not owner or not SESSION_PATH.exists():
        print("Need FB_DATA_OWNER_EMAIL and a Facebook session (python -m app.facebook_login).")
        return 2
    repo = FacebookPublicRepo(st, owner, PersonKeyer.from_env())
    posts = repo._req("GET", "facebook_public_posts", params={
        "owner_id": f"eq.{owner}", "screenshot_path": "is.null", "select": "id,canonical_post_url",
        "order": "captured_at.desc", "limit": str(a.limit)}) or []
    print(f"{len(posts)} post(s) without a screenshot")
    ad = FacebookPublicPostsAdapter(repo.keyer, Limits(page_load_interval_s=8))
    done = shots = 0
    with open_session(ad.allowed_hosts, 8, headless=not a.headed, storage_state=str(SESSION_PATH)) as s:
        s.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        s.page.wait_for_timeout(2500)
        if not is_logged_in(s.context, s.page):
            print("Facebook session expired — run: python -m app.facebook_login")
            return 2
        for p in posts:
            buyers = repo._req("GET", "facebook_public_comments", params={
                "post_id": f"eq.{p['id']}", "buyer_intent": "is.true", "screenshot_path": "is.null",
                "select": "id,comment_text,comment_fingerprint"}) or []
            try:
                s.goto(p["canonical_post_url"], wait_until="domcontentloaded")
                s.page.wait_for_timeout(3500)
                ad.check(s)
                ad.expand_comments(s)
                s.page.evaluate(_POST_JS)            # marks the post region used for the post screenshot
            except BlockedError as e:
                print(f"Stopped: Facebook showed {e.status.value} at {e.url}")
                break
            except Exception as e:  # noqa: BLE001
                log.warning("Skipped %s (%s)", p["canonical_post_url"], type(e).__name__)
                continue
            fake = PublicPost(source_post_id=None, source_post_url=p["canonical_post_url"], canonical_post_url=p["canonical_post_url"],
                              author_key=None, author_key_version=None, post_text=None, published_at_observed=None,
                              visibility_status="public_verified", visibility_evidence="", search_query="",
                              captured_at=None, content_hash="")
            by_id = {}
            for b in buyers:
                c = PublicComment(fingerprint=b["comment_fingerprint"], parent_fingerprint=None, comment_type="comment",
                                  source_comment_id=None, source_comment_url=None, canonical_comment_url=None,
                                  commenter_key=None, commenter_key_version=None, comment_text=b["comment_text"],
                                  commented_at_observed=None, content_hash="", buyer_intent=True)
                fake.comments.append(c)
                by_id[b["id"]] = c
            ad.capture_evidence(s, fake)
            path = upload_evidence(repo.http, st.supabase_url, repo._h, "facebook", fake.screenshot)
            if path:
                repo._req("PATCH", "facebook_public_posts", params={"id": f"eq.{p['id']}"}, body={"screenshot_path": path})
                shots += 1
            for cid, c in by_id.items():
                cp = upload_evidence(repo.http, st.supabase_url, repo._h, "facebook", c.screenshot)
                if cp:
                    repo._req("PATCH", "facebook_public_comments", params={"id": f"eq.{cid}"}, body={"screenshot_path": cp})
                    shots += 1
            done += 1
            log.info("%s: post %s, %d/%d buyer comment shot(s)", p["canonical_post_url"], "✓" if path else "✗",
                     sum(c.screenshot is not None for c in by_id.values()), len(by_id))
    print(f"Done: {done} post(s) visited, {shots} screenshot(s) saved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
