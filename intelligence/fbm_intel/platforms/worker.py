"""Continuous multi-platform worker.

Each enabled platform runs on its own schedule (class window + random jitter) in its own thread, with its own
checkpoints, rate limit, failure counter and circuit breaker. A failing / challenged / misconfigured platform is
recorded and paused; the others keep running. Budgets stop a cycle cleanly: checkpoint saved, collected work kept.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from ..fb_public.identity import PersonKeyer
from ..social.model import SocialPost
from . import registry
from .budget import Budget
from .contract import (AdapterContext, BudgetExhausted, Checkpoint, Misconfigured, PlatformAdapter, PlatformError,
                       RateLimited, SearchItem)
from .discovery import queries_for
from .leads import PostContext, classify_comment, classify_post, looks_organizational
from .state import PlatformStatus, WorkerState, iso, now

log = logging.getLogger("fbm_intel.worker")
BUYER_LEADS = ("confirmed_rx300_buyer", "potential_rx300_fit")


@dataclass
class CycleResult:
    platform: str
    started_at: str
    finished_at: str | None = None
    state: str = "ok"                    # ok | budget_exhausted | <HealthState>
    detail: str = ""
    queries: list[dict] = field(default_factory=list)
    posts: int = 0
    comments: int = 0
    leads: dict = field(default_factory=lambda: {k: 0 for k in ("confirmed_rx300_buyer", "potential_rx300_fit",
                                                                   "seller_or_dealer", "irrelevant")})
    post_leads: dict = field(default_factory=dict)
    organizations: int = 0
    screenshots: int = 0
    skipped: list[dict] = field(default_factory=list)
    item_errors: list[dict] = field(default_factory=list)
    review: list[dict] = field(default_factory=list)      # leads to eyeball for false positives
    budget_exhausted: str | None = None
    alerts: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def keep_for_persist(post: SocialPost, policy: str, threshold: int, wanted: tuple = BUYER_LEADS) -> None:
    """'buyers': keep comments that are buyer leads or score ≥ threshold, plus the parents of kept replies.
    Dropped comment text is not stored; only counts with reasons."""
    if policy == "all":
        return
    if wanted == BUYER_LEADS:
        keep = {c.fingerprint for c in post.comments
                if c.intent.buyer_intent_score >= threshold or (c.lead is not None and c.lead.lead_type in BUYER_LEADS)}
    else:   # focused: only the wanted lead type (e.g. confirmed RX300 buyers)
        keep = {c.fingerprint for c in post.comments if c.lead is not None and c.lead.lead_type in wanted}
    keep |= {c.parent_fingerprint for c in post.comments if c.fingerprint in keep and c.parent_fingerprint}
    dropped = [c for c in post.comments if c.fingerprint not in keep]
    reasons: dict[str, int] = {}
    for c in dropped:
        k = c.lead.lead_type if c.lead is not None else "not_scored"
        reasons[k] = reasons.get(k, 0) + 1
    post.rejected_comment_count += len(dropped)
    post.rejection_reasons = {**post.rejection_reasons, **reasons}
    post.comments = [c for c in post.comments if c.fingerprint in keep]


def comment_date(c, post: SocialPost) -> datetime | None:
    """When the comment was written, if the platform showed it (a post date only gives a lower bound)."""
    return c.commented_at_observed


def apply_recency(post: SocialPost, rec: dict, at: datetime | None = None) -> None:
    """Old buyer comments are not leads: demoted to irrelevant (so not stored or alerted). Unknown dates are flagged."""
    max_days = rec.get("max_comment_age_days")
    if not max_days:
        return
    at = at or datetime.now(timezone.utc)
    published = post.published_at_observed
    for c in post.comments:
        L = c.lead
        if L is None or L.lead_type not in BUYER_LEADS:
            continue
        when = comment_date(c, post)
        if when is None and published is not None and at - published <= timedelta(days=max_days):
            continue  # unknown comment date, but the post itself is recent → the comment is too
        if when is None:
            L.needs_review = True
            if "date_unknown" not in L.reasons:
                L.reasons.append("date_unknown")
            continue
        age = (at - when).days
        if age > max_days:
            L.reasons.append(f"too_old:{age}d")
            L.lead_type = "irrelevant"


def type_leads(adapter: PlatformAdapter, post: SocialPost) -> None:
    org = post.organization or adapter.organization_for_post(post)
    post.organization = org
    ctx = PostContext(text=" ".join(filter(None, [post.post_title, post.document_title, post.post_text, " ".join(post.hashtags)])),
                      author_is_organization=bool(org), search_query=post.search_query or "")
    post.lead = classify_post(ctx)
    for c in post.comments:
        c.lead = classify_comment(c.comment_text, ctx, intent=c.intent, is_post_author=c.is_post_author,
                                  is_business=c.account_type == "business")


def run_cycle(name: str, *, cfg: dict, state: WorkerState, sink, keyer: PersonKeyer, headed: bool = True,
              fixtures=None, max_queries: int | None = None, adapter_factory=None, reviewer=None, notifier=None) -> CycleResult:
    """One cycle for one platform. Never raises for platform problems — they come back as CycleResult.state."""
    pcfg = registry.platform_config(name, cfg)
    res = CycleResult(platform=name, started_at=iso(now()))
    budget = Budget(name, pcfg["budgets"], state)
    try:
        cls = registry.get(name)
    except KeyError as e:
        res.state, res.detail = "misconfigured", str(e).strip("'\"")
        return res
    ctx = AdapterContext(config=pcfg, keyer=keyer, budget=budget, headed=headed, preview=getattr(sink, "preview", True),
                         fixtures=fixtures)
    pcfg["_reviewer"] = reviewer if pcfg.get("ai_review", {}).get("enabled") else None
    pcfg["_notifier"] = notifier
    try:
        if cls.access == "browser_session":
            with budget.browser_context():
                _run_with_adapter(cls, ctx, name, pcfg, state, sink, budget, res, max_queries, adapter_factory)
        else:
            _run_with_adapter(cls, ctx, name, pcfg, state, sink, budget, res, max_queries, adapter_factory)
    except BudgetExhausted as e:
        res.state, res.budget_exhausted, res.detail = "budget_exhausted", e.budget, f"budget reached: {e.budget}"
    except PlatformError as e:
        res.state, res.detail = e.state, e.detail + (f" at {e.url}" if e.url else "")
    except Exception as e:  # noqa: BLE001 - isolate the platform
        log.exception("%s cycle crashed", name)
        res.state, res.detail = "error", f"{type(e).__name__}: {e}"
    res.finished_at = iso(now())
    return res


def _run_with_adapter(cls, ctx, name, pcfg, state, sink, budget, res, max_queries, adapter_factory):
    adapter: PlatformAdapter = adapter_factory(ctx) if adapter_factory else cls(ctx)
    try:
        missing = adapter.missing_env()
        if missing:
            raise Misconfigured("missing credentials: " + ", ".join(missing))
        h = adapter.health_check()
        if not h.ok:
            err = PlatformError(h.detail or h.state)
            err.state = h.state
            raise err
        all_qs = queries_for(name, pcfg.get("discovery"), record_platform=adapter.platform)
        per_cycle = max_queries or pcfg["budgets"].get("max_queries_per_cycle") or len(all_qs)
        # rotate through the whole query list across cycles instead of repeating the first few
        rot = state.checkpoint(name, "__rotation__")
        start = int(rot.cursor or 0) % max(1, len(all_qs))
        qs = (all_qs[start:] + all_qs[:start])[:per_cycle]
        rot.cursor = str((start + per_cycle) % max(1, len(all_qs)))
        state.save_checkpoint(name, rot)
        revisit = timedelta(hours=float(pcfg.get("revisit_after_h", 12)))
        threshold = int(pcfg.get("screenshot_min_score", 70))
        for q in qs:
            budget.take("queries")
            cp = state.checkpoint(name, q.text)
            page = adapter.search(q.text, cp)
            qrep = {"query": q.text, "group": q.group, "language": q.language, "found": len(page.items), "collected": 0,
                    "search_url": page.items[0].search_url if page.items else None}
            res.queries.append(qrep)
            for item in page.items[: budget.max_posts_per_query]:
                canon = adapter.canonicalize_url(item.url) or item.canonical_url
                if state.seen_recently(name, canon, revisit):
                    continue
                try:
                    _collect_one(adapter, name, item, canon, pcfg, state, sink, budget, res, threshold)
                    qrep["collected"] += 1
                except (PlatformError, BudgetExhausted):
                    # resume THIS page next time; already-collected items are skipped via `seen`
                    cp.seen = list(dict.fromkeys(cp.seen + page.next_checkpoint.seen))
                    state.save_checkpoint(name, cp)
                    raise
                except Exception as e:  # noqa: BLE001 - one bad item never stops the cycle
                    log.warning("%s item %s failed: %s", name, canon, e)
                    res.item_errors.append({"url": canon, "error": f"{type(e).__name__}: {str(e)[:200]}"})
                    if len(res.item_errors) >= int(pcfg.get("max_item_errors", 5)):
                        raise PlatformError(f"too many item errors ({len(res.item_errors)})") from e
                page.next_checkpoint.seen.append(canon)
            state.save_checkpoint(name, page.next_checkpoint)
    finally:
        try:
            adapter.close()
        except Exception:  # noqa: BLE001
            pass


def _collect_one(adapter, name, item: SearchItem, canon, pcfg, state, sink, budget, res, threshold):
    budget.take("posts")
    post = adapter.collect_post(canon, item)
    if post is None:
        reason = adapter.last_skip_reason or "not_verified_public"
        res.skipped.append({"url": canon, "reason": reason})
        sink.record_skip(name, adapter.platform, canon, item.query, "unverified", reason)
        state.mark_seen(name, canon)
        return
    post.search_query = post.search_query or item.query
    post.search_url = post.search_url or item.search_url
    if adapter.supports_comments and post.comments_supported:
        batch = adapter.collect_comments(post)
        post.comments = batch.comments[: budget.max_comments_per_post]
        post.completeness_status = batch.completeness if len(batch.comments) <= budget.max_comments_per_post else "partial_limit"
        post.comment_expansion_rounds = batch.expansion_rounds
    else:
        post.completeness_status = "comments_unavailable"
    type_leads(adapter, post)
    _business_pages(adapter, post, state, budget)
    apply_recency(post, pcfg.get("recency", {}))
    _ai_second_opinion(post, pcfg.get("_reviewer"), budget)
    res.posts += 1
    res.comments += len(post.comments)
    budget.cycle["comments"] += len(post.comments)
    if state:
        state.add_usage(name, comments=len(post.comments))
    if post.organization:
        res.organizations += 1
    res.post_leads[post.lead.lead_type] = res.post_leads.get(post.lead.lead_type, 0) + 1
    for c in post.comments:
        res.leads[c.lead.lead_type] += 1
        if c.lead.lead_type in BUYER_LEADS or (c.lead.lead_type == "irrelevant" and c.intent.buyer_intent_score >= threshold):
            res.review.append({"post_url": post.canonical_post_url, "comment_url": c.canonical_comment_url, "text": c.comment_text[:300],
                               "lead_type": c.lead.lead_type, "confidence": c.lead.confidence, "reasons": c.lead.reasons,
                               "intent_score": c.intent.buyer_intent_score, "needs_review": c.lead.needs_review})
    # screenshots only for leads / high scores, within the per-cycle and daily storage budgets
    wanted = [c for c in post.comments if c.lead.lead_type in BUYER_LEADS or c.intent.buyer_intent_score >= threshold]
    if (wanted or post.lead.lead_type in BUYER_LEADS) and budget.try_take("screenshots"):
        post.screenshot = _safe_evidence(adapter, post, budget, res)
    for c in wanted:
        if not budget.try_take("screenshots"):
            break
        c.screenshot = _safe_evidence(adapter, c, budget, res)
    wanted = (pcfg["lead_focus"],) if pcfg.get("lead_focus") else BUYER_LEADS
    keep_for_persist(post, pcfg.get("persist_policy", "buyers"), threshold, wanted)
    has_buyer = any(c.lead is not None and c.lead.lead_type in wanted for c in post.comments) \
        or (post.lead is not None and post.lead.lead_type in wanted)
    if not has_buyer and pcfg.get("save_posts_without_buyers", False) is not True:
        state.mark_seen(name, canon)          # owner wants buyer comments, not seller posts: nothing stored
        return
    sink.save_post(name, post)
    if pcfg.get("_notifier") is not None:            # after saving, so the alert's lead is on the dashboard
        res.alerts += pcfg["_notifier"].consider(post)
    state.mark_seen(name, canon)


def _business_pages(adapter, post: SocialPost, state, budget: Budget, refresh_days: int = 30) -> None:
    """Public business pages only (account_type == business), once per page per window, within the screenshot budget.
    Personal profiles are never visited."""
    targets = [c for c in post.comments if c.account_type == "business" and c.business_page_url]
    org = post.organization
    for c in targets:
        if state.business_page_recent(c.business_page_url, timedelta(days=refresh_days)) or not budget.try_take("screenshots"):
            continue
        info = adapter.capture_business_page(c.business_page_url, c.account_type)
        state.mark_business_page(c.business_page_url)
        if info is not None:
            c.business_page_screenshot = info.screenshot
            budget.add_storage(len(info.screenshot.png) if info.screenshot else 0)
    if org is not None and org.url and org.screenshot is None and \
            not state.business_page_recent(org.url, timedelta(days=refresh_days)) and budget.try_take("screenshots"):
        info = adapter.capture_business_page(org.url, "business")
        state.mark_business_page(org.url)
        if info is not None:
            org.screenshot, org.category, org.sales_location, org.contact_channels = (
                info.screenshot, info.category, info.sales_location, info.contact_channels)


def _ai_second_opinion(post: SocialPost, reviewer, budget: Budget) -> None:
    """Borderline buyer leads only, within the AI budgets; advisory (see ai_review.py)."""
    if reviewer is None:
        return
    from .ai_review import apply_review
    for c in post.comments:
        if c.lead.lead_type in BUYER_LEADS and c.lead.needs_review:
            if not budget.try_take("ai_calls"):
                return
            apply_review(c.lead, reviewer.review(post.post_text or "", c.comment_text))


def _safe_evidence(adapter, item, budget, res):
    try:
        ev = adapter.capture_evidence(item)
    except PlatformError:
        raise
    except Exception as e:  # noqa: BLE001
        log.info("screenshot failed: %s", e)
        return None
    if ev is not None:
        budget.add_storage(len(ev.png))
        res.screenshots += 1
    return ev


# ─── Scheduling / circuit breaker ───────────────────────────────────────────

def next_run_after(pcfg: dict, jitter_fraction: float, at: datetime | None = None, rng: random.Random | None = None) -> datetime:
    rng = rng or random
    w = pcfg["schedule_window"]
    minutes = rng.uniform(w["interval_min"], w["interval_max"])
    minutes *= 1 + rng.uniform(-jitter_fraction, jitter_fraction)
    return (at or now()) + timedelta(minutes=max(1.0, minutes))


def apply_result(st: PlatformStatus, res: CycleResult, pcfg: dict, wcfg: dict, rng: random.Random | None = None) -> PlatformStatus:
    cb = wcfg.get("circuit_breaker", {})
    t = now()
    st.last_run_at, st.last_state, st.last_detail = iso(t), res.state, res.detail
    st.last_cycle = {k: v for k, v in res.as_dict().items() if k not in ("review",)}
    st.next_run_at = iso(next_run_after(pcfg, wcfg.get("jitter_fraction", 0.2), t, rng))
    if res.state in ("ok", "budget_exhausted"):
        st.last_success_at = iso(t)
        st.consecutive_failures = 0
        st.circuit_open_until = None
        return st
    st.consecutive_failures += 1
    st.total_failures += 1
    base = float(cb.get("base_cooldown_min", 30))
    if res.state == "challenged":
        cool = float(cb.get("challenge_cooldown_min", 360))
    elif res.state == "login_required":
        cool = float(cb.get("login_cooldown_min", 720))
    elif res.state == "misconfigured":
        cool = float(cb.get("misconfigured_cooldown_min", 24 * 60))
    elif res.state == "rate_limited":
        cool = base
    elif st.consecutive_failures >= int(cb.get("failure_threshold", 3)):
        cool = min(float(cb.get("max_cooldown_min", 720)), base * 2 ** (st.consecutive_failures - int(cb.get("failure_threshold", 3))))
    else:
        return st  # below the threshold: just retry on the normal schedule
    st.circuit_open_until = iso(t + timedelta(minutes=cool))
    st.next_run_at = max(st.next_run_at, st.circuit_open_until)
    return st


def is_excluded(name: str, cfg: dict) -> str | None:
    """Platforms the owner ruled out: never run, not even when named explicitly."""
    return cfg["platforms"].get(name, {}).get("excluded")


def is_enabled(name: str, cfg: dict, st: PlatformStatus) -> bool:
    if is_excluded(name, cfg):
        return False
    return st.enabled_override if st.enabled_override is not None else bool(cfg["platforms"].get(name, {}).get("enabled"))


class Worker:
    def __init__(self, *, cfg: dict, state: WorkerState, sink, keyer: PersonKeyer, platforms: list[str] | None = None,
                 headed: bool = True, max_parallel: int = 4, fixtures=None, rng: random.Random | None = None,
                 require_enabled: bool = False, reviewer=None, notifier=None):
        self.cfg, self.state, self.sink, self.keyer = cfg, state, sink, keyer
        self.require_enabled = require_enabled  # live: only enabled platforms; preview: the ones named explicitly
        self.reviewer = reviewer
        self.notifier = notifier
        self.only = platforms
        self.headed = headed
        self.fixtures = fixtures
        self.rng = rng or random.Random()
        self.pool = ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix="platform")
        self.running: dict[str, Future] = {}
        self.stop = threading.Event()
        self.results: list[CycleResult] = []

    def candidates(self) -> list[str]:
        names = self.only or list(self.cfg["platforms"])
        return [n for n in names if n in self.cfg["platforms"]]

    def due(self, at: datetime | None = None) -> list[str]:
        at = at or now()
        out = []
        for n in self.candidates():
            st = self.state.status(n)
            if n in self.running or not self._allowed(n, st):
                continue
            if st.circuit_open(at):
                continue
            if st.next_run_at and datetime.fromisoformat(st.next_run_at) > at:
                continue
            out.append(n)
        return out

    def _allowed(self, name: str, st: PlatformStatus) -> bool:
        if is_excluded(name, self.cfg):
            return False
        if self.require_enabled or not self.only:
            return is_enabled(name, self.cfg, st)
        return True

    def _run(self, name: str) -> CycleResult:
        log.info("▶ %s cycle starting", name)
        res = run_cycle(name, cfg=self.cfg, state=self.state, sink=self.sink, keyer=self.keyer, headed=self.headed,
                        fixtures=self.fixtures, reviewer=self.reviewer, notifier=self.notifier)
        st = apply_result(self.state.status(name), res, registry.platform_config(name, self.cfg), self.cfg.get("worker", {}), self.rng)
        self.state.save_status(st)
        if self.notifier is not None and res.state in ("challenged", "blocked") and \
                registry.get(name).access == "browser_session":
            self.notifier.status(f"paused:{name}", f"⏸ {name} paused: {res.detail[:160]}\nIt retries by itself around "
                                 f"{(st.next_run_at or '')[11:16]} UTC, or run: .venv/bin/python -m app.worker reset {name}",
                                 every_s=3600)
        self.sink.save_status(name, {"state": res.state, "detail": res.detail[:500], "consecutive_failures": st.consecutive_failures,
                                     "circuit_open_until": st.circuit_open_until, "last_success_at": st.last_success_at,
                                     "last_run_at": st.last_run_at, "next_run_at": st.next_run_at,
                                     "enabled": is_enabled(name, self.cfg, st), "last_cycle": st.last_cycle})
        log.info("■ %s: %s %s · posts=%d comments=%d leads=%s next=%s", name, res.state, res.detail[:120], res.posts,
                 res.comments, {k: v for k, v in res.leads.items() if v}, st.next_run_at)
        self.results.append(res)
        return res

    def run_once(self) -> list[CycleResult]:
        """One cycle for each selected platform (in parallel, isolated); used by preview mode."""
        futs = {n: self.pool.submit(self._run, n) for n in self.candidates() if self._allowed(n, self.state.status(n))}
        return [f.result() for f in futs.values()]

    def run_forever(self) -> None:
        tick = float(self.cfg.get("worker", {}).get("tick_s", 20))
        while not self.stop.is_set():
            for n, f in list(self.running.items()):
                if f.done():
                    self.running.pop(n)
            for n in self.due():
                self.running[n] = self.pool.submit(self._run, n)
            self.stop.wait(tick + self.rng.uniform(0, tick / 2))
        self.pool.shutdown(wait=True, cancel_futures=True)

    def shutdown(self) -> None:
        self.stop.set()


def ensure_checkpoint(cp: Checkpoint | None, query: str) -> Checkpoint:
    return cp if cp is not None else Checkpoint(query=query)
