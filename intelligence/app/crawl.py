"""Crawl one keyword on one platform through the existing pipeline.

  python -m app.crawl --platform facebook --query "car sedan" --dry-run --headed
  python -m app.crawl --platform facebook --query "car sedan" --headed
  python -m app.crawl --platform facebook --surface posts --query "Camry for sale" --headed
  python -m app.crawl --platform fbm --query "camry"
  python -m app.crawl --platform facebook-public-posts --query "car sedan" --headed [--dry-run]

--dry-run  opens the search and prints the listing URLs + visible card fields only:
           no listing pages opened, nothing written to Supabase, no vision calls.
"""
from __future__ import annotations

import argparse
import json
import os
import logging
import re
import sys

from fbm_intel import versions
from fbm_intel.adapters import FbmAdapter
from fbm_intel.adapters.facebook import FacebookAdapter
from fbm_intel.browser import BlockedError, open_session
from fbm_intel.cli import _load, _provider
from fbm_intel.normalize import normalize_text
from fbm_intel.orchestrator import Pipeline, RunReport
from fbm_intel.schemas import SearchPlan, SearchQuery
from fbm_intel.settings import Settings

log = logging.getLogger("app.crawl")


def _adapter(a, st: Settings):
    if a.platform == "facebook":
        return FacebookAdapter(surface=a.surface, location_slug=a.location)
    return FbmAdapter(st.fbm_base_url)


def dry_run(a, st: Settings) -> int:
    adapter = _adapter(a, st)
    access = adapter.validate_access()
    log.info("Access check: %s — %s", "OK" if access.allowed else "BLOCKED", access.reason)
    if not access.allowed:
        return 2
    session = getattr(adapter, "session_path", None)
    with open_session(adapter.allowed_hosts, adapter.min_interval_s, headless=not a.headed,
                      storage_state=str(session) if session else None) as s:
        try:
            if hasattr(adapter, "confirm_logged_in"):
                adapter.confirm_logged_in(s)
            state = adapter.open_search(s, a.query)
            refs = adapter.collect_result_refs(s, state)
        except BlockedError as e:
            log.error("Facebook blocked or restricted the run: %s at %s — stopped.", e.status.value, e.url)
            return 3
        log.info("Opened %s — %d result(s)", s.page.url, len(refs))
        rows = [{"url": r.url, "id": r.source_listing_id,
                 "card": [normalize_text(x) for x in (r.hint_title or "").split("\n") if normalize_text(x)][:4]}
                for r in refs[: a.limit]]
        print(json.dumps({"dry_run": True, "platform": adapter.platform, "query": a.query, "search_url": state.url,
                          "results_found": len(refs), "shown": rows}, indent=2, ensure_ascii=False))
        if a.headed:
            s.page.wait_for_timeout(4000)  # let you see the results page
    return 0


def real_run(a, st: Settings) -> int:
    store, brief, profile = _load(st)
    adapter = _adapter(a, st)
    access = adapter.validate_access()
    log.info("Access check: %s — %s", "OK" if access.allowed else "BLOCKED", access.reason)
    if not access.allowed:
        return 2
    q = normalize_text(a.query)
    lang = "mixed" if re.search(r"[ក-៿]", q) and re.search(r"[A-Za-z]", q) else "km" if re.search(r"[ក-៿]", q) else "en"
    from datetime import datetime, timezone
    plan = SearchPlan(intent=profile.intent, queries=[SearchQuery(text=q, language=lang, category="generic", priority=100)],
                      planner_version="manual-cli-v1", generated_at=datetime.now(timezone.utc))
    terms = [t for t in store.save_search_terms(profile.id, plan, source="manual", approved_by="cli")
             if normalize_text(t["text"]).casefold() == q.casefold()]
    pipe = Pipeline(store, _provider(st), brief, profile)
    run = store.create_crawl_run(profile.id, versions.PIPELINE_VERSION)
    report = RunReport(crawl_run_id=run["id"])
    status = "completed"
    try:
        pipe.crawl(adapter, terms[:1], report, listing_budget=a.limit, headless=not a.headed)
        if report.blocked:
            status = "stopped_blocked"
            log.error("Facebook blocked or restricted the run: %s", "; ".join(report.blocked))
        pipe.evaluate_pending(report, report.captured_listing_ids)
        pipe.score_evaluated(report, report.captured_listing_ids)
        pipe.rank_profile(report)
    except Exception as e:
        store.finish_crawl_run(run["id"], "failed", report.counters.as_row(), f"{type(e).__name__}: {str(e)[:300]}")
        raise
    store.finish_crawl_run(run["id"], status, report.counters.as_row(), "; ".join(report.blocked) or None)
    print(json.dumps({"crawl_run_id": run["id"], "status": status, **report.counters.as_row(),
                      "evaluated": report.evaluated, "scored": report.scored, "ranking": report.ranking,
                      "search_pages": report.search_urls, "listings": report.listings_seen,
                      "images_captured": report.images_captured, "buyer_comments": report.buyer_comments,
                      "blocked": report.blocked}, indent=2, ensure_ascii=False, default=str))
    return 0 if status != "stopped_blocked" else 3


def public_posts(a, st: Settings) -> int:
    from fbm_intel.fb_public import collector
    from fbm_intel.fb_public.adapter import FacebookPublicPostsAdapter
    from fbm_intel.fb_public.identity import PersonKeyer
    from fbm_intel.fb_public.model import Limits
    from fbm_intel.fb_public.repo import FacebookPublicRepo

    keyer = PersonKeyer.from_env()
    limits = Limits(max_posts_per_query=a.limit, max_comments_per_post=a.max_comments,
                    max_replies_per_comment=a.max_replies, max_comment_expansion_rounds=a.max_rounds,
                    comment_load_timeout_seconds=a.comment_timeout)
    repo = None
    if not a.dry_run:
        owner = resolve_owner(st, a.owner_email)
        if not owner:
            log.error("Owner account %r not found — sign up on the site first (records need an owner_id).", a.owner_email)
            return 2
        repo = FacebookPublicRepo(st, owner, keyer)
    if not a.duration_min:
        rep = collector.run(FacebookPublicPostsAdapter(keyer, limits), a.query, repo=repo, headless=not a.headed,
                            dry_run=a.dry_run, debug=a.debug, buyer_only=a.buyer_only)
        print(json.dumps(rep.__dict__, indent=2, ensure_ascii=False, default=str))
        return 3 if rep.stopped else 0

    # Timed mode: cycle through approved queries one at a time until the time is up or Facebook objects.
    import time
    queries = [q.strip() for q in (a.queries or DEFAULT_BUYER_QUERIES) if q.strip()]
    deadline = time.monotonic() + a.duration_min * 60
    runs, buyers, stopped = [], [], None
    i = 0
    while time.monotonic() < deadline:
        q = queries[i % len(queries)]
        i += 1
        log.info("── Query %d: %r (%.0f min left)", i, q, (deadline - time.monotonic()) / 60)
        rep = collector.run(FacebookPublicPostsAdapter(keyer, limits), q, repo=repo, headless=not a.headed,
                            dry_run=a.dry_run, buyer_only=a.buyer_only)
        runs.append({"query": q, "results": rep.results, "verified_public": rep.verified_public,
                     "skipped": len(rep.skipped), "new_comments": rep.new_comments, "new_replies": rep.new_replies,
                     "buyer_comments": len(rep.buyer_comments), "stopped": rep.stopped})
        buyers += rep.buyer_comments
        if rep.stopped:
            stopped = rep.stopped
            log.error("Facebook blocked or restricted the run (%s) — ending the timed session now.", stopped)
            break
        if i >= len(queries) * a.max_cycles:
            log.info("All queries done %d time(s); stopping early.", a.max_cycles)
            break
        rest = min(a.pause_between_queries, max(0, deadline - time.monotonic()))
        log.info("Resting %.0f s before the next query", rest)
        time.sleep(rest)
    seen, unique = set(), []
    for b in buyers:
        k = b["comment_url"] or (b["post_url"], b["text"])
        if k not in seen:
            seen.add(k)
            unique.append(b)
    print(json.dumps({"duration_min": a.duration_min, "queries_run": len(runs), "stopped": stopped, "runs": runs,
                      "buyer_comments_found": len(unique), "buyer_comments": unique}, indent=2, ensure_ascii=False, default=str))
    return 3 if stopped else 0


DEFAULT_BUYER_QUERIES = [
    "car for sale", "sedan for sale", "ឡានលក់", "ឡាន sedan លក់", "Camry for sale", "Prius for sale",
    "Lexus RX for sale", "Highlander for sale", "ឡានមួយទឹក", "used car Phnom Penh",
]


def resolve_owner(st: Settings, email: str | None) -> str | None:
    import httpx
    if not email:
        return None
    h = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}"}
    users = httpx.get(f"{st.supabase_url}/auth/v1/admin/users", params={"per_page": 1000}, headers=h, timeout=30).json().get("users", [])
    return next((u["id"] for u in users if (u.get("email") or "").lower() == email.lower()), None)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="python -m app.crawl", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--platform", choices=["facebook", "facebook-public-posts", "fbm"], required=True)
    p.add_argument("--owner-email", default=os.environ.get("FB_DATA_OWNER_EMAIL"), help="FBM account that owns collected public data")
    p.add_argument("--max-comments", type=int, default=200, help="max_comments_per_post")
    p.add_argument("--max-replies", type=int, default=50, help="max_replies_per_comment")
    p.add_argument("--max-rounds", type=int, default=15, help="max_comment_expansion_rounds")
    p.add_argument("--comment-timeout", type=int, default=90, help="comment_load_timeout_seconds")
    p.add_argument("--surface", choices=["marketplace", "posts"], default="marketplace", help="Facebook surface")
    p.add_argument("--location", default="phnompenh", help="Facebook Marketplace location slug")
    p.add_argument("--query", default="car for sale", help="one keyword/phrase per run")
    p.add_argument("--limit", type=int, default=5, help="max listings to open (kept small on purpose)")
    p.add_argument("--headed", action="store_true", help="show the browser window")
    p.add_argument("--dry-run", action="store_true", help="search + list results only; no Supabase, no vision")
    p.add_argument("--debug", action="store_true", help="print an anonymous page-structure report (counts + URL shapes)")
    p.add_argument("--duration-min", type=int, default=0, help="timed mode: keep cycling through --queries for N minutes")
    p.add_argument("--queries", nargs="*", help="queries for timed mode (default: built-in car-buying list)")
    p.add_argument("--pause-between-queries", type=int, default=60, help="seconds to rest between queries")
    p.add_argument("--max-cycles", type=int, default=2, help="max passes over the query list in timed mode")
    p.add_argument("--buyer-only", action="store_true", help="keep only comments showing intent to buy (plus their parent)")
    a = p.parse_args(argv)
    a.limit = max(1, min(a.limit, 20))
    st = Settings.load()
    if a.platform == "facebook-public-posts":
        a.owner_email = a.owner_email or os.environ.get("FB_DATA_OWNER_EMAIL")
        return public_posts(a, st)
    return dry_run(a, st) if a.dry_run else real_run(a, st)


if __name__ == "__main__":
    sys.exit(main())
