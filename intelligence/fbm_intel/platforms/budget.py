"""Resource budgets: per-cycle limits for one platform plus daily limits shared by all platforms.

When a budget runs out, `take()` raises BudgetExhausted; the worker saves the checkpoint, keeps everything already
collected, and waits for the next allowed cycle (or the next UTC day for daily limits).
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

from .contract import BudgetExhausted
from .state import WorkerState

_BROWSER_SLOTS: dict[int, threading.BoundedSemaphore] = {}
_SLOTS_LOCK = threading.Lock()


def browser_semaphore(n: int) -> threading.BoundedSemaphore:
    with _SLOTS_LOCK:
        if n not in _BROWSER_SLOTS:
            _BROWSER_SLOTS[n] = threading.BoundedSemaphore(max(1, n))
        return _BROWSER_SLOTS[n]


class Budget:
    def __init__(self, platform: str, limits: dict, state: WorkerState | None = None):
        self.platform = platform
        self.limits = limits
        self.state = state
        self.cycle = {"screenshots": 0, "ai_calls": 0, "posts": 0, "comments": 0, "queries": 0, "storage_bytes": 0}
        self.exhausted: str | None = None

    # ── per-cycle ──
    def _cycle_limit(self, kind: str) -> int | None:
        return {"screenshots": self.limits.get("max_screenshots_per_cycle"),
                "ai_calls": self.limits.get("max_ai_classifications_per_cycle"),
                "queries": self.limits.get("max_queries_per_cycle"),
                "posts": self.limits.get("max_posts_per_cycle")}.get(kind)

    def can(self, kind: str, n: int = 1) -> bool:
        lim = self._cycle_limit(kind)
        if lim is not None and self.cycle.get(kind, 0) + n > lim:
            return False
        if kind == "ai_calls" and self.state:
            cost = self.limits.get("ai_cost_per_classification_usd", 0.01) * n
            if self.state.usage()["ai_cost_usd"] + cost > self.limits.get("max_daily_ai_cost_usd", 1e9):
                return False
        if kind in ("screenshots", "storage_bytes") and self.state:
            if self.state.usage()["storage_bytes"] >= self.limits.get("max_daily_storage_mb", 1e9) * 1024 * 1024:
                return False
        return True

    def take(self, kind: str, n: int = 1) -> None:
        if not self.can(kind, n):
            self.exhausted = self.exhausted or kind
            raise BudgetExhausted(kind)
        self.cycle[kind] = self.cycle.get(kind, 0) + n
        if self.state and kind in ("screenshots", "ai_calls", "posts", "comments"):
            extra = {"ai_cost_usd": self.limits.get("ai_cost_per_classification_usd", 0.01) * n} if kind == "ai_calls" else {}
            self.state.add_usage(self.platform, **{kind: n}, **extra)

    def try_take(self, kind: str, n: int = 1) -> bool:
        """Soft version for optional work (e.g. a screenshot): returns False instead of stopping the cycle."""
        try:
            self.take(kind, n)
            return True
        except BudgetExhausted:
            return False

    def add_storage(self, nbytes: int) -> None:
        self.cycle["storage_bytes"] += nbytes
        if self.state:
            self.state.add_usage(self.platform, storage_bytes=nbytes)

    def add_api_units(self, units: int) -> None:
        if self.state:
            self.state.add_usage(self.platform, api_units=units)

    def api_units_today(self) -> int:
        return int(self.state.usage(self.platform)["api_units"]) if self.state else 0

    @property
    def max_posts_per_query(self) -> int:
        return int(self.limits.get("max_posts_per_query", 10))

    @property
    def max_comments_per_post(self) -> int:
        return int(self.limits.get("max_comments_per_post", 200))

    @contextmanager
    def browser_context(self):
        """At most `max_browser_contexts` browsers open at once across all platforms."""
        sem = browser_semaphore(int(self.limits.get("max_browser_contexts", 2)))
        sem.acquire()
        try:
            yield
        finally:
            sem.release()
