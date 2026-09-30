from fbm_intel.comments import buyer_signals, classify_comments, redact


def test_keeps_only_buyer_interest():
    texts = [
        "Is it still available? I want to buy",
        "តម្លៃប៉ុន្មាន? ខ្ញុំចង់ទិញ",
        "Nice car bro 🔥",
        "I also sell Camry cheaper, check my page",
        "not interested anymore",
        "Can I see it this weekend?",
        "Best dealer in town",          # 'deal' must not match inside 'dealer'
    ]
    kept = [c.text_redacted for c in classify_comments(texts)]
    assert kept == ["Is it still available? I want to buy", "តម្លៃប៉ុន្មាន? ខ្ញុំចង់ទិញ", "Can I see it this weekend?"]


def test_signals():
    assert set(buyer_signals("Is it still available? how much?")) == {"asks_availability", "asks_price"}
    assert buyer_signals("នៅលក់ទេ?") == ["asks_availability"]
    assert buyer_signals("inbox me the last price") == ["asks_price", "asks_contact"]
    assert buyer_signals("Sold, thanks") == []


def test_redacts_contact_details():
    assert redact("call 012 345 678 or +855 97 123 4567") == "call [phone] or [phone]"
    assert redact("mail a.b@example.com or see https://x.com/p @sok_ha") == "mail [email] or see [link] [mention]"


def test_dedupes_and_labels_language():
    out = classify_comments(["I want to buy", "i want  to buy", "ចង់ទិញ Camry"])
    assert len(out) == 2 and [c.language for c in out] == ["en", "mixed"]
