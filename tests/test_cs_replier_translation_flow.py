from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_replier_uses_translation_for_ja_message(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "faq.jsonl"))
    monkeypatch.setenv("CS_AUTO_TRANSLATE", "1")
    monkeypatch.setenv("CS_TRANSLATE_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    from src.cs_bot.faq_store import FAQEntry, FAQStore
    from src.cs_bot.inbox_store import CSMessage
    from src.cs_bot.replier import suggest_reply

    store = FAQStore(str(tmp_path / "faq.jsonl"))
    store.create(
        FAQEntry(
            faq_id="faq1",
            category="shipping",
            language="ko",
            question="배송문의",
            keywords=["배송"],
            answer_template="안녕하세요 {{customer_name}}님 배송 중입니다.",
            priority=10,
        )
    )
    msg = CSMessage(
        message_id="m1",
        channel="telegram",
        direction="inbound",
        customer_id="c1",
        customer_name="太郎",
        body="いつ届きますか？",
        language="ja",
        category="shipping",
    )
    with patch("src.cs_bot.replier.get_or_translate_faq", return_value="こんにちは {{customer_name}} 様、発送済みです。"):
        out = suggest_reply(msg, store)
    assert "こんにちは" in out
    assert "太郎" in out
