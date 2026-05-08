from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_render_template_variables():
    from src.cs_bot.inbox_store import CSMessage
    from src.cs_bot.replier import render_template

    msg = CSMessage(message_id="1", channel="telegram", direction="inbound", customer_id="u", customer_name="김고객", order_no="5832")
    rendered = render_template("{{customer_name}} {{order_no}} {{tracking_no}} {{eta}}", msg, {"tracking_no": "TRK", "eta": "내일"})
    assert rendered == "김고객 5832 TRK 내일"


def test_suggest_reply_keyword_match_without_ai(tmp_path, monkeypatch):
    from src.cs_bot.faq_store import FAQEntry, FAQStore
    from src.cs_bot.inbox_store import CSMessage
    from src.cs_bot.replier import suggest_reply

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)

    store = FAQStore(str(tmp_path / "faq.jsonl"))
    store.create(
        FAQEntry(
            faq_id="faq_refund",
            category="refund",
            language="ko",
            question="환불 문의",
            keywords=["환불"],
            answer_template="{{customer_name}}님 환불 도와드릴게요.",
        )
    )
    msg = CSMessage(message_id="m", channel="telegram", direction="inbound", customer_id="1", customer_name="김", body="환불 가능한가요", language="ko", category="refund")
    draft = suggest_reply(msg, store)
    assert "김" in draft


def test_suggest_reply_ai_polish_mock(tmp_path, monkeypatch):
    from src.cs_bot.faq_store import FAQEntry, FAQStore
    from src.cs_bot.inbox_store import CSMessage
    from src.cs_bot import replier

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    store = FAQStore(str(tmp_path / "faq.jsonl"))
    store.create(FAQEntry(faq_id="f1", category="general", language="ko", question="문의", keywords=["문의"], answer_template="원문"))
    msg = CSMessage(message_id="m", channel="telegram", direction="inbound", customer_id="1", customer_name="김", body="문의", language="ko", category="general")

    with patch("src.cs_bot.replier.BudgetGuard.can_spend", return_value=True), patch("src.cs_bot.replier._call_openai_polish", return_value=("다듬은 답변", 0, 0)):
        assert replier.suggest_reply(msg, store) == "다듬은 답변"
