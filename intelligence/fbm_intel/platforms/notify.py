"""Best-buyer alerts: the worker stays quiet and only messages the owner when it finds a top RX300 buyer.

"Best buyer" (config `alerts` in platforms_v1.json): a confirmed_rx300_buyer comment (or buyer post) with high lead
confidence and a strong intent score, low spam, not the post's author, and not flagged for review. Each comment is
alerted at most once (fingerprint kept in worker state), with a daily cap.

Delivery: Telegram DM to the owner through their own bot (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID, falling back to the
OpenClaw bot + heartbeat chat in ~/.openclaw/openclaw.json) and a macOS notification. The alert contains the public
comment text and links only — never names.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx

from ..social.model import SocialPost
from .state import WorkerState

log = logging.getLogger("fbm_intel.alerts")
PLATFORM_LABEL = {"facebook": "Facebook", "facebook_marketplace": "FB Marketplace", "tiktok": "TikTok", "instagram": "Instagram",
                  "reddit": "Reddit", "youtube": "YouTube", "x": "X", "threads": "Threads", "telegram": "Telegram",
                  "pinterest": "Pinterest", "bluesky": "Bluesky", "mastodon": "Mastodon", "forum": "Forum",
                  "classifieds": "Classifieds", "web": "Web"}
SIGNAL = {"asks_price": "asks the price", "wants_to_buy": "wants to buy", "makes_offer": "makes an offer",
          "asks_availability": "asks if still available", "asks_contact": "wants contact", "asks_to_see": "wants to see it",
          "asks_delivery": "asks about delivery", "asks_vehicle_details": "asks details"}
DEFAULTS = {"max_age_days": 30, "min_confidence": 85, "min_intent_score": 70, "max_spam_score": 30, "allow_needs_review": False,
            "max_per_day": 15, "telegram": True, "macos": True}


def telegram_target() -> tuple[str | None, str | None]:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        return token, chat
    try:
        c = json.loads((Path.home() / ".openclaw" / "openclaw.json").read_text())
        return c["channels"]["telegram"]["botToken"], str(c["agents"]["defaults"]["heartbeat"]["to"])
    except Exception:  # noqa: BLE001
        return None, None


class TelegramSender:
    def __init__(self, token: str, chat_id: str, transport: httpx.BaseTransport | None = None):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id
        self.client = httpx.Client(transport=transport, timeout=20)

    def send(self, text: str) -> bool:
        try:
            r = self.client.post(self.url, json={"chat_id": self.chat_id, "text": text[:4000], "disable_web_page_preview": True})
            return r.status_code == 200
        except httpx.HTTPError as e:
            log.warning("Telegram alert failed: %s", type(e).__name__)  # never log the URL (it contains the token)
            return False


class MacSender:
    def send(self, text: str) -> bool:
        if sys.platform != "darwin":
            return False
        first = text.splitlines()[0][:100].replace('"', "'")
        body = " ".join(text.splitlines()[1:3])[:180].replace('"', "'").replace("\\", "")
        try:
            subprocess.run(["osascript", "-e", f'display notification "{body}" with title "{first}" sound name "Glass"'],
                           check=False, timeout=10, capture_output=True)
            return True
        except Exception:  # noqa: BLE001
            return False


class BestBuyerNotifier:
    def __init__(self, state: WorkerState, config: dict | None = None, senders: list | None = None):
        self.state = state
        self.cfg = {**DEFAULTS, **(config or {})}
        if senders is None:
            senders = []
            if self.cfg["telegram"]:
                token, chat = telegram_target()
                if token and chat:
                    senders.append(TelegramSender(token, chat))
            if self.cfg["macos"]:
                senders.append(MacSender())
        self.senders = senders
        self.sent: list[str] = []

    def is_recent(self, c, post: SocialPost | None) -> bool:
        from datetime import datetime, timedelta, timezone
        limit = timedelta(days=self.cfg["max_age_days"])
        now = datetime.now(timezone.utc)
        if c.commented_at_observed is not None:
            return now - c.commented_at_observed <= limit
        # no comment date: only if the post itself is from within the window (the comment can't be older)
        return post is not None and post.published_at_observed is not None and now - post.published_at_observed <= limit

    def is_best(self, c, post: SocialPost | None = None) -> bool:
        L, i = c.lead, c.intent
        return (self.is_recent(c, post) and L is not None and L.lead_type == "confirmed_rx300_buyer" and L.confidence >= self.cfg["min_confidence"]
                and i.buyer_intent_score >= self.cfg["min_intent_score"] and i.spam_score <= self.cfg["max_spam_score"]
                and not c.is_post_author and (self.cfg["allow_needs_review"] or not L.needs_review))

    def consider(self, post: SocialPost) -> int:
        n = 0
        for c in post.comments:
            if not self.is_best(c, post) or self.state.was_notified(c.fingerprint):
                continue
            if self.state.notified_today() >= self.cfg["max_per_day"]:
                log.info("Daily best-buyer alert cap reached")
                return n
            text = format_alert(post, c)
            ok = any([s.send(text) for s in self.senders]) if self.senders else False
            logging.getLogger("fbm_intel.alerts.sent").info("\n%s\n", text)   # the only thing a quiet terminal shows
            self.state.mark_notified(c.fingerprint, post.platform, delivered=ok)
            self.sent.append(text)
            n += 1
        return n


def format_alert(post: SocialPost, c) -> str:
    L, i = c.lead, c.intent
    what = ", ".join(SIGNAL.get(s, s.replace("_", " ")) for s in i.matched_signals[:3]) or "buyer intent"
    use = {"taxi": " · taxi use", "family": " · family car"}.get(L.use_case or "", "")
    link = c.canonical_comment_url or c.source_comment_url
    lines = [
        f"🚗 Best RX300 buyer · {PLATFORM_LABEL.get(post.platform, post.platform)}",
        f"“{c.comment_text[:280]}”",
        f"{what}{use} · confidence {L.confidence} · intent {i.buyer_intent_score}",
        f"Post: {post.canonical_post_url}",
        f"Comment: {link}" if link else "Comment: on the post above",
        f"Commented: {c.displayed_timestamp or (c.commented_at_observed.date().isoformat() if c.commented_at_observed else 'date not shown')}"
        + (f" · post {post.published_text_displayed}" if post.published_text_displayed else ""),
        f"Found by search “{post.search_query}”",
    ]
    if post.post_title or post.post_text:
        lines.insert(2, "On: " + (post.post_title or post.post_text or "")[:120].replace("\n", " "))
    return "\n".join(lines)
