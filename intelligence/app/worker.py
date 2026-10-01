"""Multi-platform worker CLI.

  python -m app.worker list                              adapters, tier, access, credentials, blockers
  python -m app.worker preview --platforms telegram,youtube [--max-queries 2] [--headless]
                                                          one cycle per platform, NO database writes → artifacts/preview/<run>/
  python -m app.worker status                             per-platform state, failures, circuit breaker, last success, next run
  python -m app.worker enable <platform> | disable <platform> | reset <platform>
  python -m app.worker run --live [--platforms …]         continuous operation (enabled platforms only; needs approval + migration)
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from fbm_intel.fb_public.identity import PersonKeyer
from fbm_intel.platforms import registry
from fbm_intel.platforms.report import build, print_table
from fbm_intel.platforms.sinks import PreviewSink, SupabaseSink
from fbm_intel.platforms.state import WorkerState
from fbm_intel.platforms.worker import Worker, is_enabled
from fbm_intel.settings import ROOT, Settings

log = logging.getLogger("app.worker")


def _state(cfg: dict, preview: bool) -> WorkerState:
    p = ROOT / cfg["worker"]["state_path"]
    return WorkerState(p.with_name(p.stem + "_preview" + p.suffix) if preview else p)


def cmd_list(cfg: dict) -> int:
    classes = registry.load_all()
    for name in cfg["platforms"]:
        cls = classes.get(name)
        if not cls:
            print(f"{name:<22} not loaded: {registry.IMPORT_ERRORS.get(name, '?')}")
            continue
        ad = cls.__new__(cls)
        missing = [k for k in cls.required_env if not os.environ.get(k)]
        print(f"{name:<22} tier {cls.tier}  {cls.access:<15} comments={'yes' if cls.supports_comments else 'no ':<3} "
              f"enabled={cfg['platforms'][name].get('enabled')}  {'missing: ' + ', '.join(missing) if missing else ''}")
        del ad
    return 0


def cmd_status(cfg: dict) -> int:
    st = _state(cfg, preview=False)
    print(f"{'platform':<22} {'enabled':<8} {'state':<16} fails  circuit-open-until          last-success                next-run")
    for name in cfg["platforms"]:
        s = st.status(name)
        print(f"{name:<22} {str(is_enabled(name, cfg, s)):<8} {str(s.last_state or '-'):<16} {s.consecutive_failures:>5}  "
              f"{str(s.circuit_open_until or '-'):<27} {str(s.last_success_at or '-'):<27} {s.next_run_at or '-'}")
        if s.last_detail and s.last_state not in ("ok", None):
            print(f"{'':<22} └ {s.last_detail[:140]}")
    return 0


def _quiet_logging(path: Path) -> None:
    """Terminal: only errors that stop a platform for good + alerts (printed by the notifier). Everything → log file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    root.setLevel(logging.INFO)
    alert = logging.StreamHandler()
    alert.setLevel(logging.INFO)
    alert.addFilter(lambda r: r.name == "fbm_intel.alerts.sent")
    alert.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(alert)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="python -m app.worker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("status")
    for c in ("enable", "disable", "reset"):
        sub.add_parser(c).add_argument("platform", help='a platform name, or "all"')
    pv = sub.add_parser("preview")
    pv.add_argument("--platforms", required=True, help="comma-separated, e.g. telegram,youtube")
    pv.add_argument("--max-queries", type=int, default=None, help="queries per platform this cycle")
    pv.add_argument("--headless", action="store_true", help="browser platforms: no visible window (challenges then stop the platform)")
    rn = sub.add_parser("run")
    rn.add_argument("--live", action="store_true", help="required: continuous operation writing to Supabase")
    rn.add_argument("--platforms", default=None)
    rn.add_argument("--owner-email", default=None)
    rn.add_argument("--headless", action="store_true")
    rn.add_argument("--verbose", action="store_true", help="show all progress in the terminal (default: only best-buyer alerts)")
    pv.add_argument("--alerts", action="store_true", help="also send best-buyer alerts during the preview")
    sub.add_parser("test-alert", help="send one sample best-buyer alert to check Telegram / macOS delivery")
    a = ap.parse_args(argv)

    st_settings = Settings.load()
    cfg = registry.load_config()
    if a.cmd == "list":
        return cmd_list(cfg)
    if a.cmd == "status":
        return cmd_status(cfg)
    if a.cmd == "test-alert":
        from fbm_intel.platforms.notify import BestBuyerNotifier
        n = BestBuyerNotifier(_state(cfg, preview=True), cfg.get("alerts"))
        text = "🚗 FBM test alert\nThis is how a best RX300 buyer alert will look.\nPost: https://fbm-pied.vercel.app/admin/social"
        ok = [type(x).__name__ + (" ✓" if x.send(text) else " ✗") for x in n.senders]
        print("Sent via: " + (", ".join(ok) if ok else "no channel configured (set TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)"))
        return 0
    if a.cmd in ("enable", "disable", "reset") and a.platform == "all":
        s = _state(cfg, preview=False)
        for name, block in cfg["platforms"].items():
            if block.get("excluded"):
                print(f"{name}: skipped (excluded — {block['excluded']})")
            elif a.cmd == "reset":
                s.reset_circuit(name)
            else:
                s.set_enabled(name, a.cmd == "enable")
                print(f"{name}: {a.cmd}d")
        return 0
    if a.cmd in ("enable", "disable", "reset"):
        if a.platform not in cfg["platforms"]:
            print(f"unknown platform {a.platform}")
            return 2
        if a.cmd == "enable" and cfg["platforms"][a.platform].get("excluded"):
            print(f"{a.platform} is excluded: {cfg['platforms'][a.platform]['excluded']}")
            return 2
        s = _state(cfg, preview=False)
        if a.cmd == "reset":
            s.reset_circuit(a.platform)
        else:
            s.set_enabled(a.platform, a.cmd == "enable")
        print(f"{a.platform}: {'reset — runs on the next tick' if a.cmd == 'reset' else a.cmd + 'd'}")
        return 0

    try:
        keyer = PersonKeyer.from_env()
    except ValueError as e:
        print(f"Pseudonymous key secret not usable ({e}) — set FB_COMMENTER_HMAC_SECRET_V1 in .env.local")
        return 2

    if a.cmd == "preview":
        names = [p.strip() for p in a.platforms.split(",") if p.strip()]
        unknown = [n for n in names if n not in cfg["platforms"]]
        if unknown:
            print("unknown platform(s): " + ", ".join(unknown))
            return 2
        if a.max_queries:
            cfg["budgets"]["max_queries_per_cycle"] = a.max_queries
        sink = PreviewSink(ROOT / cfg["worker"]["preview_dir"])
        from fbm_intel.platforms.ai_review import reviewer_from_settings
        from fbm_intel.platforms.notify import BestBuyerNotifier
        pstate = _state(cfg, preview=True)
        w = Worker(cfg=cfg, state=pstate, sink=sink, keyer=keyer, platforms=names, headed=not a.headless,
                   reviewer=reviewer_from_settings(st_settings) if cfg.get("ai_review", {}).get("enabled") else None,
                   notifier=BestBuyerNotifier(pstate, cfg.get("alerts")) if a.alerts else None)
        results = w.run_once()
        w.pool.shutdown(wait=True)
        rep = build(results, sink.dir)
        print()
        print_table(rep)
        print(f"\nPreview written to {sink.dir} (report.md, report.json, <platform>.jsonl, shots/). Nothing was written to the database.")
        return 0

    if a.cmd == "run":
        from fbm_intel.platforms.ai_review import reviewer_from_settings
        if not a.live:
            print("Refusing to start continuous operation without --live (preview first: python -m app.worker preview …).")
            return 2
        st_settings.require_supabase()
        from app.crawl import resolve_owner
        owner = resolve_owner(st_settings, a.owner_email or os.environ.get("FB_DATA_OWNER_EMAIL"))
        if not owner:
            print("Owner account not found (set FB_DATA_OWNER_EMAIL).")
            return 2
        from fbm_intel.platforms.notify import BestBuyerNotifier
        names = [p.strip() for p in a.platforms.split(",")] if a.platforms else None
        live_state = _state(cfg, preview=False)
        notifier = BestBuyerNotifier(live_state, cfg.get("alerts"))
        from fbm_intel.platforms.notify import set_challenge_hook
        set_challenge_hook(notifier.challenge)
        w = Worker(cfg=cfg, state=live_state, sink=SupabaseSink(st_settings, owner), keyer=keyer,
                   platforms=names, headed=not a.headless, require_enabled=True, notifier=notifier,
                   reviewer=reviewer_from_settings(st_settings) if cfg.get("ai_review", {}).get("enabled") else None)
        signal.signal(signal.SIGINT, lambda *_: w.shutdown())
        signal.signal(signal.SIGTERM, lambda *_: w.shutdown())
        enabled = [n for n in w.candidates() if is_enabled(n, cfg, w.state.status(n))]
        if not a.verbose:
            _quiet_logging(ROOT / "artifacts" / "worker.log")
        print(f"Worker running quietly for: {', '.join(enabled) or 'no enabled platforms'}.\n"
              f"You'll only hear from it when it finds a best RX300 buyer ({', '.join(type(x).__name__ for x in notifier.senders) or 'no alert channel!'}). "
              f"Full log: artifacts/worker.log · status: python -m app.worker status")
        w.run_forever()
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
