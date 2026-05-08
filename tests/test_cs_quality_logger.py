from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_log_reply_quality_and_similarity(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_REPLY_QUALITY_FALLBACK_PATH", str(tmp_path / "quality.jsonl"))
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "faq.jsonl"))
    from src.cs_bot.faq_store import FAQEntry, FAQStore
    from src.cs_bot.inbox_store import CSMessage
    from src.cs_bot.quality_logger import log_reply_quality, get_low_quality_faqs

    store = FAQStore(str(tmp_path / "faq.jsonl"))
    store.create(FAQEntry(faq_id="f1", category="general", language="ko", question="q", keywords=["q"], answer_template="원문"))

    msg = CSMessage(
        message_id="m1",
        channel="telegram",
        direction="inbound",
        customer_id="c1",
        customer_name="kim",
        matched_faq_id="f1",
        language="ko",
        category="general",
    )
    log_reply_quality(msg, "안녕하세요", "완전히 다른 문장", accepted=False)
    low = get_low_quality_faqs(threshold=0.9)
    assert low
    assert low[0][0].faq_id == "f1"
    assert 0.0 <= low[0][1] <= 1.0
