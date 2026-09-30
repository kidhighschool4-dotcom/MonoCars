"""Regression tests for Romanized Khmer / Cambodian Facebook chat buyer intent (buyer-intent-khmer-latin-v1)."""
import pytest

from fbm_intel.comments import classify, classify_comments, load_config, normalize_tokens

SHOULD_MATCH = {
    # the spec's examples
    "domlai man b": "asks_price",
    "how much b": "asks_price",
    "lan nov te bong": "asks_availability",
    "jg tinh b": "wants_to_buy",
    "interested b inbox mok": "wants_to_buy",
    "location na b": "asks_to_see",
    "ach tov mer lan ban te": "asks_to_see",
    "year man km man b": "asks_vehicle_details",
    "final price man bong": "asks_price",
    "som lek telegram b": "asks_contact",
    # realistic spelling variations
    "Domlai ponman b??": "asks_price",
    "tomlai man bro": "asks_price",
    "tamlai man b": "asks_price",
    "THLAI MAN BONGGG": "asks_price",
    "priceee man b": "asks_price",
    "price ponman b": "asks_price",
    "jos tlai ban te b": "asks_price",
    "ach jos tlai ban te": "asks_price",
    "som domlai": "asks_price",
    "mean nov te b": "asks_availability",
    "nov mean te b": "asks_availability",
    "nv te bong": "asks_availability",
    "available te b": "asks_availability",
    "sold nv?": "asks_availability",
    "chong tinh b": "wants_to_buy",
    "knhom jong tinh": "wants_to_buy",
    "nyom jg ting": "wants_to_buy",
    "chab arom": "wants_to_buy",
    "jab arum b": "wants_to_buy",
    "take b": "wants_to_buy",
    "yom len": "wants_to_buy",
    "kg interested": "wants_to_buy",
    "chat mok b": "asks_contact",
    "pm mok": "asks_contact",
    "telegram mean te": "asks_contact",
    "send detail mok": "asks_contact",
    "nov na b": "asks_to_see",
    "ti tang na b": "asks_to_see",
    "showroom nov na": "asks_to_see",
    "mel lan nov na": "asks_to_see",
    "chnam man b": "asks_vehicle_details",
    "komlat man": "asks_vehicle_details",
    "run ban man km": "asks_vehicle_details",
    "masin yax mex b": "asks_vehicle_details",
    "mean bok te": "asks_vehicle_details",
    "document krob te": "asks_vehicle_details",
    "pong tax te b": "asks_vehicle_details",
    "auto or manual?": "asks_vehicle_details",
    "benzin or hybrid": "asks_vehicle_details",
}

SHOULD_NOT_MATCH = [
    "nice lan b", "haha bong", "tag bong", "price high nas", "ot jong tinh", "ort jong tinh b", "min jong tinh",
    "not interested", "khnhom mean lan sell der", "no need b", "bought already", "expensive, not buying",
    "just asking for friend: domlai man b", "I also sell Camry cheaper, check my page", "lan saat nas b 🔥",
    "b", "lan", "price", "bong", "man", "Sold, thanks everyone",
]


@pytest.mark.parametrize("text,signal", list(SHOULD_MATCH.items()))
def test_matches(text, signal):
    r = classify(text)
    assert r.is_buyer and signal in r.signals, (text, r)
    assert r.matched_phrases, "must record which original phrase triggered it"


@pytest.mark.parametrize("text", SHOULD_NOT_MATCH)
def test_does_not_match(text):
    assert not classify(text).is_buyer, (text, classify(text))


def test_negation_overrides_and_is_recorded():
    r = classify("ot jong tinh te b, domlai man?")
    assert r.signals and r.negated and not r.is_buyer
    assert "ot jong tinh" in r.negation_phrases[0]


def test_matched_phrases_are_original_words():
    r = classify("Domlai PONMAN b?? inbox mok")
    assert r.matched_phrases == ["Domlai PONMAN", "inbox mok"]  # exact original casing/spelling


def test_normalization_rules():
    toks = [n for _, n in normalize_tokens("BONGGG  priceee!!! man?? ឡាន Camry 2019 $18,500 jg tinh")]
    assert toks == ["bong", "price", "howmuch", "lan", "camry", "2019", "$18,500", "jong", "tinh"]


def test_original_never_replaced_and_both_kept():
    [c] = classify_comments(["Domlai man b? call 012 345 678"])
    assert c.text_redacted == "Domlai man b? call [phone]"          # original text (redacted), unchanged spelling
    assert c.text_normalized == "price howmuch bong call [phone]" or c.text_normalized.startswith("price howmuch bong")
    assert c.signals == ["asks_price"] and c.matched_phrases


def test_khmer_script_still_works():
    assert classify("តម្លៃប៉ុន្មាន? ខ្ញុំចង់ទិញ").is_buyer
    assert not classify("មិនចាប់អារម្មណ៍ទេ").is_buyer


def test_config_is_versioned():
    assert load_config().version == "buyer-intent-khmer-latin-v1"
