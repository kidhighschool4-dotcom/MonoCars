"""Adapter registry: platform name → adapter class, plus merged per-platform config.

Adapters register themselves with `@register`. `load_all()` imports every adapter module so the registry is complete;
a module that fails to import is recorded as a blocker for that platform only.
"""
from __future__ import annotations

import copy
import importlib
import json
import logging
from functools import lru_cache
from pathlib import Path

from .contract import PlatformAdapter

log = logging.getLogger("fbm_intel.platforms")
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "platforms_v1.json"

_REGISTRY: dict[str, type[PlatformAdapter]] = {}
IMPORT_ERRORS: dict[str, str] = {}

ADAPTER_MODULES = [
    "facebook_public_posts", "facebook_marketplace", "tiktok", "instagram", "reddit", "youtube", "x", "threads",
    "telegram", "pinterest", "bluesky", "mastodon", "forums", "khmer24", "kh_classifieds", "search_engine", "web_sites",
]


def register(cls: type[PlatformAdapter]) -> type[PlatformAdapter]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} has no name")
    _REGISTRY[cls.name] = cls
    return cls


def load_all() -> dict[str, type[PlatformAdapter]]:
    for mod in ADAPTER_MODULES:
        if mod in _REGISTRY or mod in IMPORT_ERRORS:
            continue
        try:
            importlib.import_module(f"fbm_intel.platforms.adapters.{mod}")
        except ModuleNotFoundError as e:
            if e.name and e.name.endswith(f"adapters.{mod}"):
                IMPORT_ERRORS[mod] = "adapter not implemented yet"
            else:
                IMPORT_ERRORS[mod] = f"import failed: {e}"
        except Exception as e:  # noqa: BLE001 - one broken adapter must not break the others
            IMPORT_ERRORS[mod] = f"import failed: {type(e).__name__}: {e}"
            log.warning("Adapter %s failed to import: %s", mod, e)
    return dict(_REGISTRY)


def get(name: str) -> type[PlatformAdapter]:
    load_all()
    if name not in _REGISTRY:
        raise KeyError(IMPORT_ERRORS.get(name, f"unknown platform {name!r}"))
    return _REGISTRY[name]


@lru_cache(maxsize=4)
def _raw_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_config(path: str | Path = CONFIG_PATH) -> dict:
    return copy.deepcopy(_raw_config(str(path)))


def platform_config(name: str, cfg: dict | None = None) -> dict:
    """The platform's block with global budgets folded in (platform keys win) and its schedule class resolved."""
    cfg = cfg or load_config()
    p = copy.deepcopy(cfg["platforms"].get(name, {}))
    budgets = {**cfg.get("budgets", {}), **p.get("budgets", {})}
    sched = cfg.get("schedule_classes", {}).get(p.get("schedule", "global_social"), {"interval_min": 60, "interval_max": 180})
    return {**p, "name": name, "budgets": budgets, "schedule_window": sched,
            "screenshot_min_score": p.get("screenshot_min_score", cfg.get("screenshot_min_score", 70)),
            "persist_policy": p.get("persist_policy", cfg.get("persist_policy", "buyers")),
            "ai_review": p.get("ai_review", cfg.get("ai_review", {"enabled": False}))}
