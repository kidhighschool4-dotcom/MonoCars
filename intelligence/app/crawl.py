"""Crawl one keyword on one platform through the existing pipeline.

  python -m app.crawl --platform facebook --query "car sedan" --dry-run --headed
  python -m app.crawl --platform facebook --query "car sedan" --headed
  python -m app.crawl --platform facebook --surface posts --query "Camry for sale" --headed
  python -m app.crawl --platform fbm --query "camry"

--dry-run  opens the search and prints the listing URLs + visible card fields only:
           no listing pages opened, nothing written to Supabase, no vision calls.
"""
from __future__ import annotations

import argparse
import json
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


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="python -m app.crawl", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--platform", choices=["facebook", "fbm"], required=True)
    p.add_argument("--surface", choices=["marketplace", "posts"], default="marketplace", help="Facebook surface")
    p.add_argument("--location", default="phnompenh", help="Facebook Marketplace location slug")
    p.add_argument("--query", required=True, help="one keyword/phrase per run")
    p.add_argument("--limit", type=int, default=5, help="max listings to open (kept small on purpose)")
    p.add_argument("--headed", action="store_true", help="show the browser window")
    p.add_argument("--dry-run", action="store_true", help="search + list results only; no Supabase, no vision")
    a = p.parse_args(argv)
    a.limit = max(1, min(a.limit, 20))
    st = Settings.load()
    return dry_run(a, st) if a.dry_run else real_run(a, st)


if __name__ == "__main__":
    sys.exit(main())
