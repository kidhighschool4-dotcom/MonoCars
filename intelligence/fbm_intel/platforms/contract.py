"""Common adapter contract (multi-platform discovery).

Every platform lives behind its own adapter that implements `PlatformAdapter`. Adapters only turn the platform's
normal public interface (official public API, public web page, or a visible logged-in browser) into the shared
`SocialPost` / `SocialComment` records; the worker owns scheduling, budgets, lead typing and persistence.

Rules every adapter follows (enforced by review + tests, restated here so they travel with the code):
- public content only; no private groups, followers-only content, paywalls or hidden/private endpoints;
- a CAPTCHA / challenge / login wall / restriction raises `Challenged` / `LoginRequired` / `AccessBlocked` — never bypassed;
- never message, follow, react or otherwise contact anyone;
- private individuals: no names, usernames or profile URLs are returned — only `PersonKeyer.key_for(platform, id)`;
  clearly organizational accounts may be returned as `Organization` (stored apart from buyer leads).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from ..fb_public.identity import PersonKeyer
from ..social.model import Evidence, SocialComment, SocialPost

Access = Literal["official_api", "public_web", "browser_session"]
HealthState = Literal["ok", "disabled", "misconfigured", "login_required", "challenged", "blocked", "rate_limited", "error"]
Completeness = Literal["complete", "partial_limit", "partial_timeout", "login_required", "access_blocked", "comments_unavailable"]


# ─── Errors (the worker maps each to a platform state; none of them stops other platforms) ───

class PlatformError(Exception):
    state: HealthState = "error"

    def __init__(self, detail: str, url: str | None = None):
        super().__init__(detail)
        self.detail = detail
        self.url = url


class Misconfigured(PlatformError):
    """Missing credentials / config (e.g. an API key). The adapter stays disabled until fixed."""
    state = "misconfigured"


class LoginRequired(PlatformError):
    state = "login_required"


class Challenged(PlatformError):
    """CAPTCHA / checkpoint / verification. Recorded and stopped; never solved automatically."""
    state = "challenged"


class AccessBlocked(PlatformError):
    """Restriction, ban, 403, or content behind an access control."""
    state = "blocked"


class RateLimited(PlatformError):
    state = "rate_limited"

    def __init__(self, detail: str, url: str | None = None, retry_after_s: float | None = None):
        super().__init__(detail, url)
        self.retry_after_s = retry_after_s


class BudgetExhausted(Exception):
    """A resource budget ran out: the worker saves the checkpoint and waits for the next allowed cycle."""

    def __init__(self, budget: str):
        super().__init__(budget)
        self.budget = budget


# ─── Shared value types ───

@dataclass
class Checkpoint:
    """Where a (platform, query) search left off. Opaque `cursor` is adapter-defined (page token, max id, offset…)."""
    query: str
    cursor: str | None = None
    page: int = 0
    seen: list[str] = field(default_factory=list)       # recent canonical URLs / ids, bounded by the worker
    exhausted: bool = False
    updated_at: str | None = None

    def mark(self) -> "Checkpoint":
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return self

    def to_dict(self) -> dict:
        return {"query": self.query, "cursor": self.cursor, "page": self.page, "seen": self.seen[-500:],
                "exhausted": self.exhausted, "updated_at": self.updated_at}

    @staticmethod
    def from_dict(d: dict | None, query: str) -> "Checkpoint":
        if not d:
            return Checkpoint(query=query)
        return Checkpoint(query=query, cursor=d.get("cursor"), page=int(d.get("page") or 0), seen=list(d.get("seen") or []),
                          exhausted=bool(d.get("exhausted")), updated_at=d.get("updated_at"))


@dataclass
class SearchItem:
    url: str                       # as found
    canonical_url: str
    query: str
    search_url: str | None         # the discovery page / API request (without credentials)
    source_id: str | None = None
    preview: dict = field(default_factory=dict)   # small raw fields the search already exposed (API payload bits)


@dataclass
class SearchPage:
    items: list[SearchItem]
    next_checkpoint: Checkpoint
    exhausted: bool = False


@dataclass
class Health:
    state: HealthState
    detail: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def ok(self) -> bool:
        return self.state == "ok"


@dataclass
class Organization:
    """A clearly organizational account (dealer, shop, page, channel of a business). Stored apart from buyer leads."""
    platform: str
    name: str
    url: str | None
    kind: Literal["dealer", "shop", "page", "channel", "marketplace_seller", "forum", "media", "other"]
    evidence: str                  # why we consider it organizational (self-description, platform business flag…)


@dataclass
class CommentBatch:
    comments: list[SocialComment]
    completeness: Completeness
    expansion_rounds: int = 0


@dataclass
class AdapterContext:
    """Everything an adapter may use. Budgets / screenshots are checked by the worker through `budget`."""
    config: dict                               # this platform's merged config block
    keyer: PersonKeyer
    budget: Any = None                         # fbm_intel.platforms.budget.Budget
    headed: bool = True                        # visible browser for browser_session adapters
    preview: bool = True                       # no database writes anywhere when True
    fixtures: Any = None                       # tests: install routes / fake transports


class PlatformAdapter(abc.ABC):
    """The contract. Subclasses set the class attributes and implement every abstract method."""

    name: str = ""                             # registry key / config key (e.g. "facebook_public_posts")
    platform: str = ""                         # SocialPost.platform value (e.g. "facebook")
    display_name: str = ""
    tier: int = 1
    access: Access = "public_web"
    adapter_version: str = ""
    supports_comments: bool = True
    content_type: str = ""                     # SocialPost.source_content_type
    required_env: tuple[str, ...] = ()         # credentials the adapter needs (names only)
    allowed_hosts: frozenset[str] = frozenset()

    def __init__(self, ctx: AdapterContext):
        self.ctx = ctx
        self.cfg = ctx.config
        self.keyer = ctx.keyer
        self._next_checkpoint: Checkpoint | None = None

    # discovery
    @abc.abstractmethod
    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage: ...

    @abc.abstractmethod
    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        """Open one public post and return it normalized (without comments), or None when it is not verifiably
        public / unavailable (the reason goes to `self.last_skip_reason`)."""

    @abc.abstractmethod
    def collect_comments(self, post: SocialPost) -> CommentBatch: ...

    @abc.abstractmethod
    def capture_evidence(self, item: SocialPost | SocialComment) -> Evidence | None:
        """Screenshot (names/avatars hidden) of a post or a comment; None when the platform has no rendered page."""

    @abc.abstractmethod
    def canonicalize_url(self, url: str) -> str | None:
        """Canonical public URL for this platform, or None when the URL is not one of its public post URLs."""

    @abc.abstractmethod
    def normalize_result(self, result: dict) -> SocialPost:
        """Raw platform record (API JSON / parsed page dict) → SocialPost."""

    def get_next_checkpoint(self) -> Checkpoint | None:
        return self._next_checkpoint

    @abc.abstractmethod
    def health_check(self) -> Health: ...

    def close(self) -> None:  # noqa: B027 - optional
        pass

    # helpers
    last_skip_reason: str | None = None

    def organization_for_post(self, post: SocialPost) -> Organization | None:  # noqa: ARG002
        """Override when the platform exposes a clear organizational author (business page, dealer channel…)."""
        return None

    def missing_env(self) -> list[str]:
        import os
        return [k for k in self.required_env if not os.environ.get(k)]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
