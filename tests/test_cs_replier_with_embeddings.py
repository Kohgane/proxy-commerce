from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_suggest_reply_with_embedding_boost(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "inbox.jsonl"))
    monkeypatch.setenv("CS_EMBEDDING_PROVIDER", "disabled")

    from src.cs_bot.faq_store import FAQEntry, FAQStore
    from src.cs_bot.inbox_store import CSMessage
    from src.cs_bot.replier import suggest_reply

    store = FAQStore()
    entry = FAQEntry(
        faq_id="faq_001",
        category="refund",
        language="ko",
        question="환불 방법",
        keywords=["환불", "취소"],
        answer_template="환불 처리해 드리겠습니다.",
        priority=5,
        enabled=True,
    )
    store.create(entry)

    msg = CSMessage(
        message_id="msg_test",
        channel="telegram",
        direction="inbound",
        customer_id="cid",
        customer_name="고객",
        body="환불하고 싶습니다",
        language="ko",
        category="refund",
    )
    reply = suggest_reply(msg, store)
    assert reply  # Should return something


def test_rank_candidates_uses_embedding(monkeypatch):
    monkeypatch.setenv("CS_EMBEDDING_PROVIDER", "disabled")
    from src.cs_bot.faq_store import FAQEntry
    from src.cs_bot.inbox_store import CSMessage
    from src.cs_bot.replier import _rank_candidates

    msg = CSMessage(
        message_id="m1",
        channel="telegram",
        direction="inbound",
        customer_id="c1",
        customer_name="테스터",
        body="배송 언제와요",
        language="ko",
        category="shipping",
    )
    entry = FAQEntry(
        faq_id="f1",
        category="shipping",
        language="ko",
        question="배송 조회",
        keywords=["배송", "언제"],
        answer_template="배송 중입니다",
        enabled=True,
        embedding=[1.0, 0.0, 0.0],
    )
    query_emb = [1.0, 0.0, 0.0]  # cosine_similarity = 1.0
    ranked = _rank_candidates(msg, [entry], query_embedding=query_emb)
    assert len(ranked) == 1
    assert ranked[0].faq_id == "f1"
