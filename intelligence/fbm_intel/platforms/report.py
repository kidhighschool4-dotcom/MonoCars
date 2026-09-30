"""Per-platform preview / status report (JSON + Markdown)."""
from __future__ import annotations

import json
from pathlib import Path

from . import registry
from .worker import CycleResult

STATE_HINT = {
    "ok": "ran", "budget_exhausted": "stopped at a budget (checkpoint saved)", "misconfigured": "not configured",
    "login_required": "needs a manual login", "challenged": "CAPTCHA / verification shown", "blocked": "access blocked",
    "rate_limited": "rate limited", "error": "failed",
}


def build(results: list[CycleResult], run_dir: Path | None = None) -> dict:
    registry.load_all()
    rows = []
    for r in results:
        cls = registry._REGISTRY.get(r.platform)
        rows.append({
            "platform": r.platform, "tier": getattr(cls, "tier", None), "access": getattr(cls, "access", None),
            "state": r.state, "detail": r.detail, "queries": len(r.queries), "posts": r.posts, "comments": r.comments,
            "leads": r.leads, "post_leads": r.post_leads, "organizations": r.organizations, "screenshots": r.screenshots,
            "skipped": len(r.skipped), "skip_reasons": _count(x["reason"] for x in r.skipped),
            "item_errors": r.item_errors[:10], "query_detail": r.queries, "review": r.review[:50],
        })
    rep = {"platforms": rows, "import_errors": dict(registry.IMPORT_ERRORS)}
    if run_dir:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (run_dir / "report.md").write_text(markdown(rep), encoding="utf-8")
    return rep


def _count(xs) -> dict:
    out: dict = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out


def markdown(rep: dict) -> str:
    L = ["# Multi-platform preview", "", "| Platform | Tier | Access | Result | Posts | Comments | RX300 buyers | Potential fits | Sellers | Skipped |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["platforms"]:
        L.append(f"| {r['platform']} | {r['tier']} | {r['access']} | {STATE_HINT.get(r['state'], r['state'])}"
                 f"{': ' + r['detail'][:80] if r['detail'] else ''} | {r['posts']} | {r['comments']} | "
                 f"{r['leads'].get('confirmed_rx300_buyer', 0)} | {r['leads'].get('potential_rx300_fit', 0)} | "
                 f"{r['leads'].get('seller_or_dealer', 0)} | {r['skipped']} |")
    for r in rep["platforms"]:
        if not r["review"]:
            continue
        L += ["", f"## {r['platform']} — leads to check for false positives", ""]
        for x in r["review"]:
            flag = " ⚠ review" if x.get("needs_review") else ""
            L.append(f"- **{x['lead_type']}** ({x['confidence']}, intent {x['intent_score']}){flag}: “{x['text'][:160]}” "
                     f"— {', '.join(x['reasons'][:4])} · {x.get('comment_url') or x['post_url']}")
    if rep.get("import_errors"):
        L += ["", "## Adapters not loaded", ""] + [f"- {k}: {v}" for k, v in rep["import_errors"].items()]
    return "\n".join(L) + "\n"


def print_table(rep: dict) -> None:
    w = max([len(r["platform"]) for r in rep["platforms"]] + [8])
    print(f"{'platform':<{w}}  tier  result              posts  comments  rx300  fit  seller  skipped  detail")
    for r in rep["platforms"]:
        L = r["leads"]
        print(f"{r['platform']:<{w}}  {str(r['tier']):<4}  {r['state']:<18}  {r['posts']:>5}  {r['comments']:>8}  "
              f"{L.get('confirmed_rx300_buyer', 0):>5}  {L.get('potential_rx300_fit', 0):>3}  {L.get('seller_or_dealer', 0):>6}  "
              f"{r['skipped']:>7}  {r['detail'][:90]}")
