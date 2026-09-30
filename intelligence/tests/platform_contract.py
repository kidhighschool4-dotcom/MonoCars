"""Shared checks every platform adapter's tests call (contract conformance + privacy)."""
from __future__ import annotations

import inspect

from fbm_intel.fb_public.identity import PersonKeyer
from fbm_intel.platforms.contract import AdapterContext, PlatformAdapter
from fbm_intel.platforms.registry import platform_config
from fbm_intel.social.model import CONTENT_TYPES, PLATFORMS, SocialPost

KEYER = PersonKeyer("k" * 64, "hmac-sha256-v1")
REQUIRED = ("search", "collect_post", "collect_comments", "capture_evidence", "canonicalize_url", "normalize_result",
            "get_next_checkpoint", "health_check", "close")


def make_ctx(name: str, fixtures=None, **cfg_overrides) -> AdapterContext:
    cfg = platform_config(name)
    cfg.update(cfg_overrides)
    return AdapterContext(config=cfg, keyer=KEYER, fixtures=fixtures, headed=False, preview=True)


def assert_contract(cls: type[PlatformAdapter]) -> None:
    assert issubclass(cls, PlatformAdapter)
    assert cls.name and cls.platform in PLATFORMS and cls.content_type in CONTENT_TYPES, cls
    assert cls.tier in (1, 2, 3) and cls.access in ("official_api", "public_web", "browser_session")
    assert cls.adapter_version and cls.allowed_hosts
    for m in REQUIRED:
        assert callable(getattr(cls, m, None)), f"{cls.__name__}.{m} missing"
        assert not getattr(getattr(cls, m), "__isabstractmethod__", False), f"{cls.__name__}.{m} still abstract"
    assert not inspect.isabstract(cls), f"{cls.__name__} has abstract methods left"


def assert_post_valid(post: SocialPost, platform: str) -> None:
    assert post.platform == platform and post.source_content_type in CONTENT_TYPES
    assert post.visibility_status == "public_verified" and post.visibility_evidence
    assert post.canonical_post_url.startswith("https://")
    assert post.adapter_version and post.content_hash
    for c in post.comments:
        assert c.comment_text and c.fingerprint
        assert (c.comment_type == "reply") == (c.parent_fingerprint is not None)
        assert (c.commenter_key is None) == (c.commenter_key_version is None)


def assert_no_identity_leak(post: SocialPost, forbidden: list[str]) -> None:
    """Names / usernames / profile URLs of private individuals must not appear anywhere in stored fields."""
    blob = " ".join(str(x) for x in [
        post.post_text, post.post_title, post.document_title if not post.organization else "", post.author_key,
        *[f"{c.comment_text} {c.commenter_key} {c.source_comment_url} {c.canonical_comment_url}" for c in post.comments]])
    for f in forbidden:
        assert f not in blob, f"leaked {f!r}"
