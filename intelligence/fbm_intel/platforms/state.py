"""Persistent per-platform worker state (local SQLite, git-ignored under private/).

Per platform: enable override, failure counters, circuit breaker, last success / last run / next run, last health
state, per-query checkpoints, recently seen URLs (dedup) and daily resource usage. Thread-safe (one connection per
call, WAL mode) so platforms running in parallel never block each other for long.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .contract import Checkpoint

SCHEMA = """
CREATE TABLE IF NOT EXISTS platform_state (
  platform TEXT PRIMARY KEY,
  enabled_override INTEGER,              -- NULL = use config, 1/0 = operator override
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  total_failures INTEGER NOT NULL DEFAULT 0,
  circuit_open_until TEXT,
  last_success_at TEXT,
  last_run_at TEXT,
  next_run_at TEXT,
  last_state TEXT,
  last_detail TEXT,
  last_cycle_json TEXT
);
CREATE TABLE IF NOT EXISTS checkpoints (
  platform TEXT NOT NULL, query TEXT NOT NULL, data TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (platform, query)
);
CREATE TABLE IF NOT EXISTS seen_urls (
  platform TEXT NOT NULL, canonical_url TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
  PRIMARY KEY (platform, canonical_url)
);
CREATE TABLE IF NOT EXISTS notified (
  fingerprint TEXT PRIMARY KEY, platform TEXT NOT NULL, notified_at TEXT NOT NULL, delivered INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_usage (
  day TEXT NOT NULL, platform TEXT NOT NULL,
  posts INTEGER NOT NULL DEFAULT 0, comments INTEGER NOT NULL DEFAULT 0, screenshots INTEGER NOT NULL DEFAULT 0,
  ai_calls INTEGER NOT NULL DEFAULT 0, ai_cost_usd REAL NOT NULL DEFAULT 0, storage_bytes INTEGER NOT NULL DEFAULT 0,
  api_units INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, platform)
);
"""
USAGE_FIELDS = ("posts", "comments", "screenshots", "ai_calls", "ai_cost_usd", "storage_bytes", "api_units")


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def parse(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


@dataclass
class PlatformStatus:
    platform: str
    enabled_override: bool | None = None
    consecutive_failures: int = 0
    total_failures: int = 0
    circuit_open_until: str | None = None
    last_success_at: str | None = None
    last_run_at: str | None = None
    next_run_at: str | None = None
    last_state: str | None = None
    last_detail: str | None = None
    last_cycle: dict | None = None

    def circuit_open(self, at: datetime | None = None) -> bool:
        u = parse(self.circuit_open_until)
        return bool(u and u > (at or now()))

    def as_dict(self) -> dict:
        return asdict(self)


class WorkerState:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            yield c
            c.commit()
        finally:
            c.close()

    # ── platform status ──
    def status(self, platform: str) -> PlatformStatus:
        with self._conn() as c:
            r = c.execute("SELECT * FROM platform_state WHERE platform=?", (platform,)).fetchone()
        if not r:
            return PlatformStatus(platform)
        d = dict(r)
        eo = d.pop("enabled_override")
        cyc = d.pop("last_cycle_json")
        return PlatformStatus(**d, enabled_override=None if eo is None else bool(eo), last_cycle=json.loads(cyc) if cyc else None)

    def all_status(self) -> dict[str, PlatformStatus]:
        with self._conn() as c:
            names = [r[0] for r in c.execute("SELECT platform FROM platform_state")]
        return {n: self.status(n) for n in names}

    def save_status(self, st: PlatformStatus) -> None:
        with self._lock, self._conn() as c:
            c.execute("""INSERT INTO platform_state (platform, enabled_override, consecutive_failures, total_failures,
                         circuit_open_until, last_success_at, last_run_at, next_run_at, last_state, last_detail, last_cycle_json)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(platform) DO UPDATE SET enabled_override=excluded.enabled_override,
                           consecutive_failures=excluded.consecutive_failures, total_failures=excluded.total_failures,
                           circuit_open_until=excluded.circuit_open_until, last_success_at=excluded.last_success_at,
                           last_run_at=excluded.last_run_at, next_run_at=excluded.next_run_at, last_state=excluded.last_state,
                           last_detail=excluded.last_detail, last_cycle_json=excluded.last_cycle_json""",
                      (st.platform, None if st.enabled_override is None else int(st.enabled_override), st.consecutive_failures,
                       st.total_failures, st.circuit_open_until, st.last_success_at, st.last_run_at, st.next_run_at,
                       st.last_state, st.last_detail, json.dumps(st.last_cycle, default=str) if st.last_cycle else None))

    def set_enabled(self, platform: str, enabled: bool | None) -> None:
        st = self.status(platform)
        st.enabled_override = enabled
        if enabled:  # re-enabling resets the breaker so the operator's decision takes effect now
            st.circuit_open_until, st.consecutive_failures, st.next_run_at = None, 0, None
        self.save_status(st)

    def reset_circuit(self, platform: str) -> None:
        st = self.status(platform)
        st.circuit_open_until, st.consecutive_failures, st.next_run_at = None, 0, None   # run on the next tick
        self.save_status(st)

    # ── checkpoints ──
    def checkpoint(self, platform: str, query: str) -> Checkpoint:
        with self._conn() as c:
            r = c.execute("SELECT data FROM checkpoints WHERE platform=? AND query=?", (platform, query)).fetchone()
        return Checkpoint.from_dict(json.loads(r[0]) if r else None, query)

    def save_checkpoint(self, platform: str, cp: Checkpoint) -> None:
        cp.mark()
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO checkpoints VALUES (?,?,?,?) ON CONFLICT(platform, query) DO UPDATE SET data=excluded.data, "
                      "updated_at=excluded.updated_at", (platform, cp.query, json.dumps(cp.to_dict()), cp.updated_at))

    # ── dedup ──
    def seen_recently(self, platform: str, url: str, within: timedelta) -> bool:
        with self._conn() as c:
            r = c.execute("SELECT last_seen FROM seen_urls WHERE platform=? AND canonical_url=?", (platform, url)).fetchone()
        return bool(r and parse(r[0]) > now() - within)

    def mark_seen(self, platform: str, url: str) -> None:
        t = iso(now())
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO seen_urls VALUES (?,?,?,?) ON CONFLICT(platform, canonical_url) DO UPDATE SET last_seen=excluded.last_seen",
                      (platform, url, t, t))

    # ── best-buyer alerts ──
    def was_notified(self, fingerprint: str) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM notified WHERE fingerprint=?", (fingerprint,)).fetchone() is not None

    def mark_notified(self, fingerprint: str, platform: str, delivered: bool) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR IGNORE INTO notified VALUES (?,?,?,?)", (fingerprint, platform, iso(now()), int(delivered)))

    def notified_today(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM notified WHERE notified_at >= ?", (self.today(),)).fetchone()[0]

    # ── usage ──
    @staticmethod
    def today() -> str:
        return now().strftime("%Y-%m-%d")

    def add_usage(self, platform: str, **inc) -> None:
        cols = [k for k in inc if k in USAGE_FIELDS and inc[k]]
        if not cols:
            return
        with self._lock, self._conn() as c:
            c.execute("INSERT OR IGNORE INTO daily_usage (day, platform) VALUES (?,?)", (self.today(), platform))
            c.execute(f"UPDATE daily_usage SET {', '.join(f'{k}={k}+?' for k in cols)} WHERE day=? AND platform=?",
                      (*[inc[k] for k in cols], self.today(), platform))

    def usage(self, platform: str | None = None, day: str | None = None) -> dict:
        q = f"SELECT {', '.join(f'COALESCE(SUM({k}),0) AS {k}' for k in USAGE_FIELDS)} FROM daily_usage WHERE day=?"
        args: list = [day or self.today()]
        if platform:
            q += " AND platform=?"
            args.append(platform)
        with self._conn() as c:
            return dict(c.execute(q, args).fetchone())
