"""Server-side settings. Secrets come from the environment / MonoCars/.env.local and never leave this process."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # MonoCars/intelligence
APP_ROOT = ROOT.parent                              # MonoCars


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _openclaw_token_from_config() -> str:
    cfg = Path.home() / ".openclaw" / "openclaw.json"
    try:
        return json.loads(cfg.read_text())["gateway"]["auth"]["token"]
    except Exception:
        return ""


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    service_role_key: str
    openclaw_base_url: str
    openclaw_token: str
    openclaw_agent: str
    openclaw_backend_model: str
    fbm_base_url: str
    manual_url_hosts: frozenset[str]
    evidence_bucket: str = "listing-evidence"

    @staticmethod
    def load() -> "Settings":
        _load_env_file(APP_ROOT / ".env.local")
        _load_env_file(ROOT / ".env")
        url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        return Settings(
            supabase_url=url.rstrip("/"),
            service_role_key=key,
            openclaw_base_url=os.environ.get("OPENCLAW_BASE_URL", "http://127.0.0.1:18789"),
            openclaw_token=os.environ.get("OPENCLAW_GATEWAY_TOKEN") or _openclaw_token_from_config(),
            openclaw_agent=os.environ.get("OPENCLAW_VISION_AGENT", "listing-eval"),
            openclaw_backend_model=os.environ.get("OPENCLAW_VISION_MODEL", "openai/gpt-5.5"),
            fbm_base_url=os.environ.get("FBM_BASE_URL", "https://fbm-pied.vercel.app"),
            manual_url_hosts=frozenset(h.strip() for h in os.environ.get(
                "MANUAL_URL_HOSTS", "fbm-pied.vercel.app,khmer24.com").split(",") if h.strip()),
        )

    def require_supabase(self) -> None:
        if not self.supabase_url or not self.service_role_key:
            raise RuntimeError("Supabase URL / service-role key missing (MonoCars/.env.local)")
