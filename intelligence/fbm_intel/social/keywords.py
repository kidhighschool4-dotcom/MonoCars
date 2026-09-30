"""Keyword variants from a product concept + location, in English, Khmer script and Romanized Khmer.

Deterministic and reviewable (no model call). Khmer terms come from a fixed dictionary that should be reviewed by a
fluent speaker; unknown concepts fall back to the English words plus the generic Khmer "car for sale" forms.
"""
from __future__ import annotations

from ..normalize import fold, normalize_text

KM_LOCATION = {"phnom penh": ("ភ្នំពេញ", "phnom penh"), "siem reap": ("សៀមរាប", "siem reap"),
               "battambang": ("បាត់ដំបង", "battambang"), "kandal": ("កណ្តាល", "kandal"),
               "sihanoukville": ("ព្រះសីហនុ", "sihanoukville"), "kampot": ("កំពត", "kampot")}
KM_CONCEPT = {"car": ("ឡាន", "lan"), "sedan": ("ឡាន sedan", "lan sedan"), "suv": ("ឡាន SUV", "lan suv"),
              "pickup": ("ឡានភីកអាប់", "lan pickup"), "used car": ("ឡានមួយទឹក", "lan muy tuk"),
              "motorbike": ("ម៉ូតូ", "moto"), "ev": ("ឡានអគ្គិសនី", "lan EV")}
SELL_KM, SELL_ROM = "លក់", "lok"


def keyword_variants(concept: str, location: str | None = None, limit: int = 12) -> list[dict]:
    c = fold(concept)
    loc_key = fold(location or "")
    loc_km, loc_rom = KM_LOCATION.get(loc_key, (location or "", location or ""))
    km_concept, rom_concept = next(((km, rom) for k, (km, rom) in sorted(KM_CONCEPT.items(), key=lambda x: -len(x[0]))
                                    if k in c), ("ឡាន", "lan"))
    loc_en = (location or "").strip()
    cands = [
        (f"{concept} for sale {loc_en}", "en"),
        (f"{km_concept} {SELL_KM} {loc_km}", "km"),
        (f"{rom_concept} {SELL_ROM} {loc_rom}", "romanized_km"),
        (f"{concept} {loc_en}", "en"),
        (f"{km_concept}{'' if km_concept.endswith(chr(0x1793)) else ' '}{SELL_KM}", "km"),
        (f"{concept} {SELL_KM} {loc_km}", "mixed"),
        (f"used {concept} cambodia", "en"),
        (f"{rom_concept} {SELL_ROM}", "romanized_km"),
    ]
    seen, out = set(), []
    for text, lang in cands:
        t = normalize_text(text)
        if t and fold(t) not in seen:
            seen.add(fold(t))
            out.append({"text": t, "language": lang})
    return out[:limit]
