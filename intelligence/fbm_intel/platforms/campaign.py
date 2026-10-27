"""What the worker is looking for: `campaign` in config/platforms_v1.json picks the search terms and the lead typing.

  rx300   — people who want to buy a Lexus RX300 (config/rx300_*.json, platforms/leads.py)
  rental  — people looking for a place to rent in Phnom Penh (config/rental_*.json, platforms/rental_leads.py)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@dataclass(frozen=True)
class Campaign:
    name: str
    label: str                    # alert headline, e.g. "🏠 Rental seeker"
    seeker_leads: tuple[str, ...]  # lead types that count as leads (best first)
    discovery_path: Path

    @property
    def focus(self) -> str:
        return self.seeker_leads[0]

    @property
    def rules(self) -> ModuleType:
        """Module with PostContext, classify_post, classify_comment, looks_organizational."""
        if self.name == "rental":
            from . import rental_leads
            return rental_leads
        from . import leads
        return leads


CAMPAIGNS = {
    "rx300": Campaign("rx300", "🚗 Best RX300 buyer", ("confirmed_rx300_buyer", "potential_rx300_fit"),
                      CONFIG_DIR / "rx300_discovery_v1.json"),
    "rental": Campaign("rental", "🏠 Rental seeker", ("rental_seeker", "potential_rental_seeker"),
                       CONFIG_DIR / "rental_discovery_v1.json"),
}
ALL_SEEKER_LEADS = tuple(t for c in CAMPAIGNS.values() for t in c.seeker_leads)


def current(cfg: dict | None = None) -> Campaign:
    if cfg is None:
        from .registry import load_config
        cfg = load_config()
    return CAMPAIGNS[cfg.get("campaign", "rx300")]
