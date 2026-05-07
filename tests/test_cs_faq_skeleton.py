from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_cs_faq_page_200_and_create(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        get_resp = client.get("/seller/cs/faq")
        assert get_resp.status_code == 200
        post_resp = client.post("/seller/cs/faq", data={"keyword": "배송", "answer": "배송은 2~3일", "locale": "ko"})
        assert post_resp.status_code == 200
        html = post_resp.get_data(as_text=True)
        assert "배송" in html


def test_cs_faq_model_serialization():
    from src.cs_bot.models import FaqItem

    item = FaqItem(faq_id="faq_1", keyword="환불", answer="환불은 3영업일", locale="ko")
    payload = item.to_dict()
    restored = FaqItem.from_dict(payload)
    assert restored.faq_id == "faq_1"
    assert restored.keyword == "환불"
    assert restored.answer == "환불은 3영업일"

