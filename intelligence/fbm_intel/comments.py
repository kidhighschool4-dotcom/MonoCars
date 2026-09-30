"""Buyer-intent classification for comments on a listing post.

Three rule sets, all phrase-based (never a single isolated token):
  1. English phrases and Khmer-script phrases (matched on the original, case-folded text).
  2. Romanized Khmer / Cambodian Facebook chat spelling (config/buyer_intent_khmer_latin_v1.json), matched on a
     NORMALIZED copy built token-by-token so every match maps back to the exact original words.
  3. Negations — explicit "not interested", "ot jong tinh", seller ads, etc. — override any match.

The original comment is never modified; the normalized copy exists only for matching and auditing.
Privacy: commenter identity is never read here; phone numbers/emails/links are redacted before storage.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .normalize import fold, normalize_text, sha256_hex

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "buyer_intent_khmer_latin_v1.json"

# English + Khmer-script phrases (substring match with word boundaries for short Latin phrases).
SCRIPT_SIGNALS: dict[str, list[str]] = {
    "wants_to_buy": ["want to buy", "i'll take it", "i will take it", "i want it", "i'm interested", "im interested",
                     "interested", "i'll buy", "i will buy", "ខ្ញុំចង់ទិញ", "ចង់ទិញ", "ចាប់អារម្មណ៍"],
    "asks_availability": ["still available", "is it available", "available?", "sold yet", "នៅលក់ទេ", "នៅមានទេ"],
    "asks_price": ["how much", "last price", "final price", "best price", "can discount", "discount?",
                   "តម្លៃប៉ុន្មាន", "ប៉ុន្មាន", "ចុះថ្លៃ", "ចុះបានទេ", "តម្លៃចុងក្រោយ"],
    "asks_to_see": ["can i see", "test drive", "where can i see", "where is it", "location?", "មើលឡាន", "សាកឡាន",
                    "នៅឯណា", "មើលបានទេ"],
    "asks_contact": ["inbox me", "pm me", "dm me", "check inbox", "sent you a message", "ឆាតមក", "inbox មក"],
}
SCRIPT_NEGATIONS = ["not interested", "no longer interested", "already sold", "មិនចាប់អារម្មណ៍", "លក់ដាច់ហើយ",
                    "for rent", "ជួល", "i'm selling", "i am selling", "i also sell", "ខ្ញុំក៏លក់"]
SOLD_SELLER = re.compile(r"(?<![a-z])sold(?![a-z])(?!\s*(nov|nv|yet|te))", re.I)

_KHMER = re.compile(r"[ក-៿᧠-᧿]")
_KEEP_CHARS = re.compile(r"[^0-9a-zក-៿᧠-᧿$៛.,'-]")
_REPEAT = re.compile(r"([a-z])\1{2,}")                  # bonggg → bong, priceee → price
_PHONE = re.compile(r"(?:\+?855|0)[\s\-.]?\d{1,3}(?:[\s\-.]?\d{2,4}){2,3}|\b\d{8,11}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"https?://\S+|www\.\S+")
_MENTION = re.compile(r"(?<!\w)@[\w.]{2,}")


@dataclass(frozen=True)
class IntentConfig:
    version: str
    token_map: dict[str, str]
    patterns: dict[str, list[re.Pattern]]
    negations: list[re.Pattern]


@lru_cache(maxsize=4)
def load_config(path: str = str(CONFIG_PATH)) -> IntentConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return IntentConfig(
        version=raw["version"],
        token_map={k.casefold(): v for k, v in raw["token_map"].items()},
        patterns={cat: [re.compile(p) for p in pats] for cat, pats in raw["patterns"].items()},
        negations=[re.compile(p) for p in raw["negations"]],
    )


CLASSIFIER_VERSION = f"buyer-intent-rules-v2+{load_config().version}"


@dataclass
class IntentResult:
    signals: list[str]
    matched_phrases: list[str]          # exact ORIGINAL words that triggered each match
    normalized: str                     # normalized copy used for matching (never replaces the original)
    negated: bool
    negation_phrases: list[str] = field(default_factory=list)
    version: str = CLASSIFIER_VERSION

    @property
    def is_buyer(self) -> bool:
        return bool(self.signals) and not self.negated


def normalize_tokens(text: str, cfg: IntentConfig | None = None) -> list[tuple[str, str]]:
    """[(original_token, normalized_token)] — lowercase, de-decorated, repeated letters collapsed, chat spelling mapped.
    Khmer script, numbers, currency symbols and model names are preserved."""
    cfg = cfg or load_config()
    out: list[tuple[str, str]] = []
    for orig in normalize_text(unicodedata.normalize("NFC", text or "")).split(" "):
        t = orig.casefold()
        t = _KEEP_CHARS.sub(" ", t)                  # drop decorative punctuation/emoji, keep Khmer + digits + $/៛
        for piece in t.split():
            p = piece.strip(".,'-")
            if not _KHMER.search(p):
                p = _REPEAT.sub(r"\1", p)
            if not p:
                continue
            out.append((orig, cfg.token_map.get(p, p)))
    return out


def _script_matches(text: str) -> tuple[list[str], list[str]]:
    t = fold(text)
    signals, phrases = [], []
    for code, items in SCRIPT_SIGNALS.items():
        for ph in items:
            if re.fullmatch(r"[a-z' ?]+", ph):
                m = re.search(rf"(?<![a-z]){re.escape(ph)}(?![a-z])", t)
            else:
                m = re.search(re.escape(ph), t)
            if m:
                signals.append(code)
                phrases.append(text[m.start():m.end()] if fold(text) == t and len(text) == len(t) else ph)
                break
    return signals, phrases


def classify(text: str, cfg: IntentConfig | None = None) -> IntentResult:
    cfg = cfg or load_config()
    pairs = normalize_tokens(text, cfg)
    norm_tokens = [n for _, n in pairs]
    normalized = " ".join(norm_tokens)

    # char offset → token index, so a regex span on the normalized string maps back to original tokens
    starts, pos = [], 0
    for n in norm_tokens:
        starts.append(pos)
        pos += len(n) + 1

    def originals(span: tuple[int, int]) -> str:
        idx = [i for i, st in enumerate(starts) if st < span[1] and st + len(norm_tokens[i]) > span[0]]
        seen, words = set(), []
        for i in idx:
            if pairs[i][0] not in seen:  # a raw token like "man??" may yield one piece; don't repeat it
                seen.add(pairs[i][0])
                words.append(pairs[i][0])
        return " ".join(words)

    signals, phrases = _script_matches(text)
    for cat, pats in cfg.patterns.items():
        for pat in pats:
            m = pat.search(normalized)
            if m:
                if cat not in signals:
                    signals.append(cat)
                phrases.append(originals(m.span()))
                break

    neg_phrases = []
    folded = fold(text)
    for ph in SCRIPT_NEGATIONS:
        if ph in folded:
            neg_phrases.append(ph)
    if SOLD_SELLER.search(folded):
        neg_phrases.append("sold")
    for pat in cfg.negations:
        m = pat.search(normalized)
        if m:
            neg_phrases.append(originals(m.span()))

    return IntentResult(signals=signals, matched_phrases=list(dict.fromkeys(p for p in phrases if p)),
                        normalized=normalized, negated=bool(neg_phrases), negation_phrases=neg_phrases,
                        version=CLASSIFIER_VERSION)


def buyer_signals(text: str) -> list[str]:
    """Backwards-compatible helper: buyer-intent signal codes, or [] if none / negated."""
    r = classify(text)
    return r.signals if r.is_buyer else []


# ─── storage helpers ────────────────────────────────────────────────────────

@dataclass
class BuyerComment:
    comment_hash: str
    text_redacted: str
    signals: list[str]
    language: str
    matched_phrases: list[str] = field(default_factory=list)
    text_normalized: str = ""


def redact(text: str) -> str:
    t = _EMAIL.sub("[email]", text)
    t = _URL.sub("[link]", t)
    t = _PHONE.sub("[phone]", t)
    return _MENTION.sub("[mention]", t)


def _language(text: str) -> str:
    has_km = bool(_KHMER.search(text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    return "mixed" if has_km and has_latin else "km" if has_km else "en"


def classify_comments(raw_texts: list[str], max_comments: int = 200) -> list[BuyerComment]:
    """Return only buyer-intent comments, redacted and de-duplicated. Non-buyer comments are dropped."""
    out: dict[str, BuyerComment] = {}
    for raw in raw_texts[:max_comments]:
        text = normalize_text(raw)[:1000]
        r = classify(text)
        if not r.is_buyer:
            continue
        h = sha256_hex(fold(text))
        out.setdefault(h, BuyerComment(h, redact(text), r.signals, _language(text),
                                       [redact(p) for p in r.matched_phrases], redact(r.normalized)))
    return list(out.values())
