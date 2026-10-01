"""Who wrote a comment: individual | business | unknown — decided in memory, never by visiting a personal profile.

The display name is used ONLY for this decision and is discarded for individuals. Business details (page name + URL)
are kept only when the account is clearly an organization: a platform business marker, or a name that reads as a
dealership/shop. Nothing here infers personal traits.
"""
from __future__ import annotations

from dataclasses import dataclass

ACCOUNT_TYPES = ("individual", "business", "unknown")


@dataclass(frozen=True)
class Account:
    type: str                         # individual | business | unknown
    business_page_name: str | None = None
    business_page_url: str | None = None


def classify_account(display_name: str | None, page_url: str | None, *, business_marker: bool = False,
                     has_profile: bool = True) -> Account:
    from ..platforms.leads import looks_organizational
    if business_marker or looks_organizational(display_name):
        name = (display_name or "").strip()[:300] or None
        return Account("business", name, page_url)
    return Account("individual" if has_profile else "unknown")
