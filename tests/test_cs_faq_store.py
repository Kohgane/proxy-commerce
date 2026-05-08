from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_faq_store_crud_and_persistence(tmp_path):
    from src.cs_bot.faq_store import FAQEntry, FAQStore

    path = tmp_path / "cs_faq.jsonl"
    store = FAQStore(str(path))
    created = store.create(
        FAQEntry(
            faq_id="faq_1",
            category="shipping",
            language="ko",
            question="배송 언제",
            keywords=["배송", "언제"],
            answer_template="{{customer_name}}님, {{eta}} 도착 예정입니다.",
        )
    )
    assert created.faq_id == "faq_1"
    assert store.get("faq_1") is not None

    created.answer_template = "업데이트"
    assert store.update(created) is True
    assert store.get("faq_1").answer_template == "업데이트"

    store2 = FAQStore(str(path))
    assert len(store2.list_all(enabled_only=False)) == 1
    assert store2.delete("faq_1") is True
    assert store2.get("faq_1") is None


def test_faq_search_by_keywords(tmp_path):
    from src.cs_bot.faq_store import FAQEntry, FAQStore

    store = FAQStore(str(tmp_path / "cs_faq.jsonl"))
    store.create(
        FAQEntry(
            faq_id="faq_shipping",
            category="shipping",
            language="ko",
            question="배송 문의",
            keywords=["배송", "운송장"],
            answer_template="운송장 안내",
            priority=1,
        )
    )
    rows = store.search_by_keywords("운송장 언제 오나요", language="ko")
    assert rows
    assert rows[0].faq_id == "faq_shipping"
