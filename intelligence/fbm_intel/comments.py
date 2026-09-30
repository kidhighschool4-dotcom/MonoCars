"""Buyer-interest comments on a listing post.

Keeps ONLY comments that show someone wants to buy the car. Everything else is discarded.
Privacy (architecture §3, §17): commenter names/profiles are never collected, and phone numbers,
emails, links and @mentions inside the text are redacted before anything is stored.
Deterministic rules (English + Khmer); the version is stored with every row.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import fold, normalize_text, sha256_hex

CLASSIFIER_VERSION = "buyer-intent-rules-v1"

# signal code → phrases (casefolded). Khmer phrases are common marketplace wording; review with a native speaker.
BUYER_SIGNALS: dict[str, list[str]] = {
    "wants_to_buy": ["want to buy", "i'll take it", "i will take it", "i want it", "i'm interested", "im interested",
                     "interested", "i'll buy", "i will buy", "deal", "ខ្ញុំចង់ទិញ", "ចង់ទិញ", "យក", "ចាប់អារម្មណ៍"],
    "asks_availability": ["still available", "is it available", "available?", "sold yet", "នៅលក់ទេ", "នៅទេ", "នៅមានទេ"],
    "asks_price": ["how much", "price?", "last price", "final price", "best price", "can discount", "discount?",
                   "តម្លៃប៉ុន្មាន", "ប៉ុន្មាន", "ចុះថ្លៃ", "ចុះបានទេ", "តម្លៃចុងក្រោយ"],
    "asks_to_see": ["can i see", "test drive", "where can i see", "where is it", "location?", "មើលឡាន", "សាកឡាន",
                    "នៅឯណា", "មើលបានទេ"],
    "asks_contact": ["inbox", "pm me", "dm me", "check inbox", "sent you a message", "ឆាតមក", "inbox មក"],
}

# Phrases that negate interest or come from the seller side — never counted as buyer interest.
NEGATIVE = ["not interested", "no longer interested", "sold", "already sold", "មិនចាប់អារម្មណ៍", "លក់ដាច់ហើយ",
            "for rent", "ជួល", "i'm selling", "i am selling", "i also sell", "ខ្ញុំក៏លក់"]

_PHONE = re.compile(r"(?:\+?855|0)[\s\-.]?\d{1,3}(?:[\s\-.]?\d{2,4}){2,3}|\b\d{8,11}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"https?://\S+|www\.\S+")
_MENTION = re.compile(r"(?<!\w)@[\w.]{2,}")


@dataclass
class BuyerComment:
    comment_hash: str
    text_redacted: str
    signals: list[str]
    language: str


def redact(text: str) -> str:
    t = _EMAIL.sub("[email]", text)
    t = _URL.sub("[link]", t)
    t = _PHONE.sub("[phone]", t)
    return _MENTION.sub("[mention]", t)


def _language(text: str) -> str:
    has_km = bool(re.search(r"[ក-៿]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    return "mixed" if has_km and has_latin else "km" if has_km else "en"


def buyer_signals(text: str) -> list[str]:
    t = fold(text)
    if not t or any(n in t for n in NEGATIVE):
        return []
    found = []
    for code, phrases in BUYER_SIGNALS.items():
        for p in phrases:
            # short Latin words need word boundaries ('deal' must not match 'dealer'); Khmer has no spaces
            if re.fullmatch(r"[a-z' ]+", p) and len(p) <= 8:
                if re.search(rf"(?<![a-z]){re.escape(p)}(?![a-z])", t):
                    found.append(code)
                    break
            elif p in t:
                found.append(code)
                break
    return found


def classify_comments(raw_texts: list[str], max_comments: int = 200) -> list[BuyerComment]:
    """Return only buyer-interest comments, redacted and de-duplicated. Non-buyer comments are dropped."""
    out: dict[str, BuyerComment] = {}
    for raw in raw_texts[:max_comments]:
        text = normalize_text(raw)[:1000]
        signals = buyer_signals(text)
        if not signals:
            continue
        h = sha256_hex(fold(text))
        out.setdefault(h, BuyerComment(h, redact(text), signals, _language(text)))
    return list(out.values())
