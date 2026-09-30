"""Public-visibility verification. Conservative by design: anything not positively proven public is skipped.

Evidence Facebook shows next to a post's timestamp is an audience icon whose accessible label is e.g.
"Shared with Public" / "Public", or "Shared with Friends" / "Custom" / "Only me". Group posts show the
group's privacy ("Public group" / "Private group"). Being visible to the logged-in account is NOT evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

PUBLIC_AUDIENCE = {"public", "shared with public"}
RESTRICTED_AUDIENCE = {"friends", "shared with friends", "friends of friends", "shared with friends of friends",
                       "custom", "shared with custom", "only me", "shared with only me", "specific friends",
                       "friends except", "close friends", "your friends", "restricted"}


@dataclass(frozen=True)
class VisibilitySignals:
    url: str
    is_group_post: bool
    audience_labels: tuple[str, ...] = ()      # accessible labels / titles of audience icons in the post header
    group_privacy_texts: tuple[str, ...] = ()  # e.g. "Public group", "Private group"
    content_unavailable: bool = False          # "This content isn't available"


@dataclass(frozen=True)
class Visibility:
    status: str          # public_verified | unverified | private | restricted
    evidence: str | None
    skip_reason: str | None

    @property
    def verified(self) -> bool:
        return self.status == "public_verified"


def _norm(s: str) -> str:
    return " ".join((s or "").replace(" ", " ").split()).strip().casefold().rstrip(".:")


def verify(sig: VisibilitySignals) -> Visibility:
    if sig.content_unavailable:
        return Visibility("restricted", None, "content_unavailable")

    if sig.is_group_post:
        texts = {_norm(t) for t in sig.group_privacy_texts} | {_norm(l) for l in sig.audience_labels}
        # Facebook's audience icon on group posts reads "Shared with Public group" / "Shared with Private group"
        private = any("private group" in t for t in texts)
        public = any("public group" in t for t in texts)
        if private:
            return Visibility("private", None, "private_group")
        if public:
            return Visibility("public_verified", "group_privacy:Public group", None)
        return Visibility("unverified", None, "public_visibility_not_confirmed")

    labels = {_norm(l) for l in sig.audience_labels if _norm(l)}
    is_public = bool(labels & PUBLIC_AUDIENCE)
    is_restricted = any(l in RESTRICTED_AUDIENCE or l.startswith("shared with friends") for l in labels)
    if is_public and is_restricted:
        return Visibility("unverified", None, "public_visibility_not_confirmed")  # contradictory evidence
    if is_restricted:
        return Visibility("restricted", None, "not_public_audience")
    if is_public:
        label = next(l for l in sig.audience_labels if _norm(l) in PUBLIC_AUDIENCE)
        return Visibility("public_verified", f"audience_icon:{label.strip()}", None)
    return Visibility("unverified", None, "public_visibility_not_confirmed")
