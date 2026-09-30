"""Pseudonymous person keys: HMAC-SHA256(server secret, canonical profile URL).

The canonical profile URL exists only in memory for the duration of this call. It is never persisted or logged,
and neither is any display name. Keys carry a version so the secret can be rotated.
"""
from __future__ import annotations

import hashlib
import hmac
import os

from .urls import canonical_profile_url


class PersonKeyer:
    def __init__(self, secret: str, version: str):
        if not secret or len(secret) < 32:
            raise ValueError("HMAC secret missing or too short (need >= 32 chars)")
        if not version:
            raise ValueError("key version required")
        self._secret = secret.encode()
        self.version = version

    @classmethod
    def from_env(cls) -> "PersonKeyer":
        version = os.environ.get("FB_COMMENTER_KEY_VERSION", "hmac-sha256-v1")
        suffix = version.rsplit("-", 1)[-1].upper()  # hmac-sha256-v1 → V1
        return cls(os.environ.get(f"FB_COMMENTER_HMAC_SECRET_{suffix}", ""), version)

    def key(self, raw_profile_url: str | None) -> str | None:
        canon = canonical_profile_url(raw_profile_url)
        if canon is None:
            return None
        return hmac.new(self._secret, canon.encode("utf-8"), hashlib.sha256).hexdigest()

    def key_for(self, platform: str, identifier: str | None) -> str | None:
        """Cross-platform form: HMAC(secret, "<platform>:<identifier>"). Platform in the input means the same
        handle on two platforms yields unrelated keys (no cross-platform identity matching)."""
        if not identifier:
            return None
        return hmac.new(self._secret, f"{platform}:{identifier}".encode("utf-8"), hashlib.sha256).hexdigest()

    def __repr__(self) -> str:  # never reveal the secret
        return f"PersonKeyer(version={self.version!r})"
