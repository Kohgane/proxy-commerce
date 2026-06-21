"""tests/test_translation_usage.py — 번역 무료 20회 + 초과 차단 (Phase 246, v3 P1-4)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    from src.seller_console import collect_history_store as chs
    from src.seller_console import translation_usage as tu
    chs._in_memory.clear()
    tu._in_memory.clear()
    monkeypatch.setenv("TRANSLATION_FREE_LIMIT", "3")  # 테스트는 무료 3회로
    monkeypatch.delenv("TRANSLATION_UNLIMITED", raising=False)
    yield
    chs._in_memory.clear()
    tu._in_memory.clear()


def _real_translator():
    inst = MagicMock()
    inst.translate_product.return_value = {"title_ko": "번역됨", "description_ko": "설명", "provider": "openai"}
    return MagicMock(return_value=inst)


def _stub_translator():
    inst = MagicMock()
    inst.translate_product.return_value = {"title_ko": "x", "description_ko": "y", "provider": "stub"}
    return MagicMock(return_value=inst)


def test_usage_counter_increments_and_remaining():
    from src.seller_console import translation_usage as tu
    assert tu.remaining("s1") == 3
    tu.increment("s1", 2)
    assert tu.get_used("s1") == 2
    assert tu.remaining("s1") == 1


def test_bulk_translate_blocks_over_free_limit(client):
    """무료 3회 → 4개 요청 시 3개만 번역, 1개 차단."""
    from src.seller_console import collect_history_store as chs
    ids = [chs.append(source="manual", url=f"https://x/{i}", title=f"t{i}", seller_id="default") for i in range(4)]
    with patch("src.seller_console.ai.translator.AITranslator", _real_translator()):
        r = client.post("/seller/collect/bulk-translate", json={"item_ids": ids})
    data = r.get_json()
    assert data["ok"] is True
    assert data["translated"] == 3
    assert data["blocked"] == 1
    assert data["free_remaining"] == 0
    assert "무료 번역" in (data["message"] or "")


def test_bulk_translate_stub_does_not_consume_free(client):
    """번역기 stub(키 없음)이면 무료 차감/차단 없음(정직)."""
    from src.seller_console import collect_history_store as chs
    from src.seller_console import translation_usage as tu
    ids = [chs.append(source="manual", url=f"https://x/{i}", title=f"t{i}", seller_id="default") for i in range(5)]
    with patch("src.seller_console.ai.translator.AITranslator", _stub_translator()):
        r = client.post("/seller/collect/bulk-translate", json={"item_ids": ids})
    data = r.get_json()
    assert data["translated"] == 0
    assert data["blocked"] == 0
    assert tu.get_used("default") == 0  # 차감 없음
    assert data["free_remaining"] == 3


def test_unlimited_env_bypasses_limit(client):
    from src.seller_console import collect_history_store as chs
    ids = [chs.append(source="manual", url=f"https://x/{i}", title=f"t{i}", seller_id="default") for i in range(5)]
    with patch.dict(os.environ, {"TRANSLATION_UNLIMITED": "1"}), \
         patch("src.seller_console.ai.translator.AITranslator", _real_translator()):
        r = client.post("/seller/collect/bulk-translate", json={"item_ids": ids})
    data = r.get_json()
    assert data["translated"] == 5
    assert data["blocked"] == 0


def test_history_page_shows_free_balance(client):
    from src.seller_console import collect_history_store as chs
    chs.append(source="manual", url="https://x/1", title="t", seller_id="default")
    html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "무료 번역" in html
    assert "translRemain" in html
