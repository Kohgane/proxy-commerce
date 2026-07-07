"""tests/test_v45_recollect.py — 수집 UX: 신규/중복 단일 토스트 + 다시 수집(덮어쓰기) 가격 갱신.

오너: 중복이면 '이미 수집한 상품 — 이력 열기' 하나만(완료 토스트 동시 출력 금지), 신규면
'수집 완료 — 이력에서 확인' 하나만. 중복 배지에 '다시 수집(덮어쓰기)' → 가격·이미지 갱신.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

CS = None


@pytest.fixture(autouse=True)
def _clean_env():
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    yield


@pytest.fixture
def client():
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def _post(client, payload):
    return client.post("/api/v1/collect/extension", data=json.dumps(payload),
                       content_type="application/json", headers={"Authorization": "Bearer tok_test"})


def test_recollect_overwrites_price(client):
    from src.seller_console import collect_history_store as ch
    # 저장소 비움(테스트 격리)
    try: ch._in_memory.clear()
    except Exception: pass
    url = "https://www.temu.com/kr/goods.html?goods_id=999888"
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="cat1"), \
         patch("src.api.extension_api._notify_telegram"):
        # 1) 최초 수집(잘못된 9 KRW로 저장됐다고 가정)
        r1 = _post(client, {"url": url, "title": "접이식 책상", "price": "9", "currency": "KRW"})
        assert r1.get_json().get("ok") is True and not r1.get_json().get("duplicate")
        # 2) 같은 URL 재수집(force 없음) → 중복
        r2 = _post(client, {"url": url, "title": "접이식 책상", "price": "9", "currency": "KRW"})
        assert r2.get_json().get("duplicate") is True
        # 3) 다시 수집(덮어쓰기) → 실가 20,605로 갱신, 새 행 안 만듦
        r3 = _post(client, {"url": url, "title": "접이식 책상", "price": "20605", "currency": "KRW", "force": True})
        d3 = r3.get_json()
        assert d3.get("ok") is True and d3.get("updated") is True
        assert d3.get("item_id") == r2.get_json().get("item_id")   # 같은 항목(중복 행 0)
    # 저장된 가격이 20605로 갱신됐는지
    items = ch.list_items(seller_ids={"u1"})
    matching = [it for it in items if it.get("url") == url]
    assert len(matching) == 1                         # 중복 행 없음
    assert str(matching[0].get("price")) == "20605"   # 덮어쓰기 반영


def test_extension_single_toasts_and_recollect_button():
    global CS
    from pathlib import Path
    CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    # 신규/중복 단일 메시지
    assert "수집 완료 — 이력에서 확인" in CS
    assert "이미 수집한 상품 — 이력에서 확인" in CS
    # 다시 수집(덮어쓰기) 버튼 + force 전송
    assert "다시 수집(덮어쓰기)" in CS
    assert "meta.force = true" in CS
    # 갱신 결과 단일 메시지 + silent 축하(완료/중복 동시출력 금지)
    assert "가격·이미지를 갱신" in CS
    assert "kgpCelebrate(1, true)" in CS
