"""fbm-intel command line.

  fbm-intel init                         load brief + profile, store seed search terms (reviewed vocabulary)
  fbm-intel plan [--llm]                 show the seed plan, or generate an LLM plan (stored unapproved)
  fbm-intel approve-plan --by NAME       approve the pending LLM plan after a human has reviewed the Khmer terms
  fbm-intel run [--planner seed|llm] [--limit N]   crawl → capture → prefilter → vision → score → rank
  fbm-intel submit-url URL               manual URL capture + evaluation (§13 fallback)
  fbm-intel reprocess                    re-apply prefilter after a policy change, then evaluate/score/rank
  fbm-intel rank                         re-run deterministic ranking only
  fbm-intel status                       pipeline counts + latest ranking
  fbm-intel grant-admin EMAIL            let a user open /admin/intelligence (sets app_metadata.role=admin)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import versions
from .adapters import FbmAdapter, ManualUrlAdapter, ResultRef
from .browser import BlockedError, open_session
from .orchestrator import Pipeline, RunReport
from .planner import llm_plan, seed_plan
from .schemas import ProductBrief, SearchProfile
from .settings import ROOT, Settings
from .store import SupabaseStore
from .vision import OpenClawVisionProvider

CONFIG = ROOT / "config" / "default.json"


def _load(settings: Settings, config: Path = CONFIG) -> tuple[SupabaseStore, ProductBrief, SearchProfile]:
    cfg = json.loads(config.read_text())
    store = SupabaseStore(settings)
    brief = store.upsert_brief(ProductBrief.model_validate(cfg["product_brief"]))
    profile = store.upsert_profile(SearchProfile.model_validate(cfg["search_profile"]), brief.id)
    return store, brief, profile


def _provider(settings: Settings) -> OpenClawVisionProvider:
    return OpenClawVisionProvider(settings.openclaw_base_url, settings.openclaw_token, settings.openclaw_agent,
                                  settings.openclaw_backend_model)


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_init(a, st: Settings) -> None:
    store, brief, profile = _load(st)
    plan = seed_plan(profile, brief)
    terms = store.save_search_terms(profile.id, plan, source="seed", approved_by="seed-vocabulary")
    _print({"product_brief": brief.id, "search_profile": profile.id, "seed_terms": len(terms),
            "planner_version": plan.planner_version})


def cmd_plan(a, st: Settings) -> None:
    store, brief, profile = _load(st)
    if not a.llm:
        _print([q.model_dump() for q in seed_plan(profile, brief).queries])
        return
    plan = llm_plan(profile, brief, base_url=st.openclaw_base_url, token=st.openclaw_token, agent=st.openclaw_agent,
                    backend_model=st.openclaw_backend_model)
    store.save_search_terms(profile.id, plan, source="planner", approved_by=None)
    _print({"stored_unapproved": len(plan.queries), "planner_version": plan.planner_version,
            "queries": [q.model_dump() for q in plan.queries], "negative_terms": plan.negative_terms,
            "next": "review the Khmer terms, then: fbm-intel approve-plan --by <your name>"})


def cmd_approve(a, st: Settings) -> None:
    store, _, profile = _load(st)
    rows = store.update("search_terms", {"search_profile_id": profile.id, "planner_version": versions.PLANNER_VERSION},
                        {"approved_by": a.by, "approved_at": datetime.now(timezone.utc).isoformat()})
    _print({"approved": len(rows)})


def cmd_run(a, st: Settings) -> None:
    store, brief, profile = _load(st)
    planner_version = versions.PLANNER_VERSION if a.planner == "llm" else versions.SEED_PLANNER_VERSION
    terms = store.approved_terms(profile.id, planner_version)
    if not terms:
        sys.exit(f"no approved search terms for {planner_version}; run `fbm-intel init` (seed) or plan+approve (llm)")
    pipe = Pipeline(store, _provider(st), brief, profile)
    run = store.create_crawl_run(profile.id, versions.PIPELINE_VERSION)
    report = RunReport(crawl_run_id=run["id"])
    status = "completed"
    try:
        pipe.crawl(FbmAdapter(st.fbm_base_url), terms, report, listing_budget=a.limit)
        if report.blocked:
            status = "stopped_blocked"
        pipe.evaluate_pending(report)
        pipe.score_evaluated(report)
        pipe.rank_profile(report)
        if report.counters.errors or report.vision_errors:
            status = "completed_with_errors" if status == "completed" else status
    except Exception as e:
        status = "failed"
        store.finish_crawl_run(run["id"], status, report.counters.as_row(), f"{type(e).__name__}: {str(e)[:300]}")
        raise
    store.finish_crawl_run(run["id"], status, report.counters.as_row(), "; ".join(report.blocked) or None)
    _print({"crawl_run_id": run["id"], "status": status, **report.counters.as_row(), "evaluated": report.evaluated,
            "vision_errors": report.vision_errors, "scored": report.scored, "ranking": _ranking_with_url(store, report.ranking),
            "images_captured": report.images_captured, "new_buyer_comments": report.buyer_comments,
            "blocked": report.blocked, "search_pages": report.search_urls, "listings": report.listings_seen})


def _ranking_with_url(store: SupabaseStore, ranking: dict | None) -> dict | None:
    if not ranking or not ranking.get("selected"):
        return ranking
    sel = store.select("listings", {"id": f"eq.{ranking['selected']}", "select": "title_raw,source_url"})
    return {**ranking, "selected_title": sel[0]["title_raw"], "selected_url": sel[0]["source_url"]} if sel else ranking


def cmd_submit_url(a, st: Settings) -> None:
    store, brief, profile = _load(st)
    adapter = ManualUrlAdapter(set(st.manual_url_hosts))
    url = adapter.check_url(a.url)
    pipe = Pipeline(store, _provider(st), brief, profile)
    run = store.create_crawl_run(profile.id, versions.PIPELINE_VERSION)
    report = RunReport(crawl_run_id=run["id"])
    status = "completed"
    try:
        with open_session(adapter.allowed_hosts, adapter.min_interval_s) as s:
            ref = ResultRef(url=url)
            listing_id = pipe.capture_one(adapter, s, ref, report)
        pipe.evaluate_pending(report, [listing_id] if listing_id else [])
        pipe.score_evaluated(report, [listing_id] if listing_id else [])
    except BlockedError as e:
        status = "stopped_blocked"
        report.counters.blocks += 1
        report.blocked.append(f"manual_url: {e.status.value}")
    store.finish_crawl_run(run["id"], status, report.counters.as_row(), "; ".join(report.blocked) or None)
    _print({"crawl_run_id": run["id"], "status": status, "captured": report.captured_listing_ids,
            "evaluated": report.evaluated, "scored": report.scored, "blocked": report.blocked})


def cmd_reprocess(a, st: Settings) -> None:
    """Re-apply the prefilter under the current profile/brief versions, then evaluate, score and rank."""
    store, brief, profile = _load(st)
    pipe = Pipeline(store, _provider(st), brief, profile)
    report = RunReport()
    n = pipe.reprefilter(report)
    pipe.evaluate_pending(report)
    pipe.score_evaluated(report)
    pipe.rank_profile(report)
    _print({"reprefiltered": n, "still_rejected": report.counters.prefilter_rejected,
            "duplicates": report.counters.duplicates, "evaluated": report.evaluated,
            "vision_errors": report.vision_errors, "scored": report.scored, "ranking": report.ranking})


def cmd_rank(a, st: Settings) -> None:
    store, brief, profile = _load(st)
    _print(Pipeline(store, _provider(st), brief, profile).rank_profile(RunReport()))


def cmd_status(a, st: Settings) -> None:
    store, _, profile = _load(st)
    rows = store.select("listings", {"select": "lifecycle_status"})
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["lifecycle_status"]] = counts.get(r["lifecycle_status"], 0) + 1
    last = store.select("ranking_runs", {"search_profile_id": f"eq.{profile.id}", "order": "created_at.desc", "limit": "1"})
    open_tasks = store.select("review_tasks", {"status": "eq.open", "select": "id"})
    ranking = None
    if last:
        r = last[0]
        members = store.select("ranking_members", {"ranking_run_id": f"eq.{r['id']}", "order": "rank_position.asc",
                                                   "select": "rank_position,composite_score,qualified,selected,"
                                                             "listings(title_raw,price_text_raw,source_url,lifecycle_status,"
                                                             "photos:listing_assets(id,asset_kind),listing_comments(text_redacted))"})
        ranking = {"status": r["status"], "policy": r["policy_version"], "minimum_score": r["minimum_acceptable_score"],
                   "created_at": r["created_at"],
                   "candidates": [{"rank": m["rank_position"], "score": m["composite_score"], "selected": m["selected"],
                                   "qualified": m["qualified"], "title": m["listings"]["title_raw"],
                                   "price": m["listings"]["price_text_raw"], "state": m["listings"]["lifecycle_status"],
                                   "url": m["listings"]["source_url"],
                                   "photo_screenshot": any(a["asset_kind"] == "primary_image" for a in m["listings"]["photos"]),
                                   "buyer_comments": [c["text_redacted"] for c in m["listings"]["listing_comments"]]}
                                  for m in members]}
    _print({"listings_by_state": counts, "open_review_tasks": len(open_tasks), "latest_ranking": ranking})


def cmd_grant_admin(a, st: Settings) -> None:
    store = SupabaseStore(st)
    h = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}"}
    users = store.http.get(f"{st.supabase_url}/auth/v1/admin/users", params={"per_page": 1000}, headers=h).json().get("users", [])
    user = next((u for u in users if (u.get("email") or "").lower() == a.email.lower()), None)
    if not user:
        sys.exit("no user with that email — sign up on the site first")
    meta = {**(user.get("app_metadata") or {}), "role": "admin"}
    r = store.http.put(f"{st.supabase_url}/auth/v1/admin/users/{user['id']}", headers=h, json={"app_metadata": meta})
    r.raise_for_status()
    _print({"admin": a.email, "note": "sign out and back in so the new role is in your session"})


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="fbm-intel", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    pl = sub.add_parser("plan"); pl.add_argument("--llm", action="store_true")
    ap = sub.add_parser("approve-plan"); ap.add_argument("--by", required=True)
    rn = sub.add_parser("run"); rn.add_argument("--planner", choices=["seed", "llm"], default="seed"); rn.add_argument("--limit", type=int)
    su = sub.add_parser("submit-url"); su.add_argument("url")
    sub.add_parser("reprocess")
    sub.add_parser("rank")
    sub.add_parser("status")
    ga = sub.add_parser("grant-admin"); ga.add_argument("email")
    a = p.parse_args(argv)
    st = Settings.load()
    {"init": cmd_init, "plan": cmd_plan, "approve-plan": cmd_approve, "run": cmd_run, "submit-url": cmd_submit_url, "reprocess": cmd_reprocess,
     "rank": cmd_rank, "status": cmd_status, "grant-admin": cmd_grant_admin}[a.cmd](a, st)


if __name__ == "__main__":
    main()
