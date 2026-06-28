"""tests/test_v38_collect_no_fake_success.py — v38 P0: 수집 가짜 성공 박멸(영속 저장 확인).

핵심: '수집 완료' 토스트는 서버가 **영속 저장(durable)** 을 확인했을 때만 떠야 한다.
시트가 설정됐는데 쓰기에 실패해 인메모리로만 폴백되면(멀티워커서 안 보임) 정직한 실패(502).
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    # 확장 흐름 모사: 토큰 검증을 u1로(실제 PAT 인증 대체)
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def _clear_mem():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()


def test_single_collect_appears_in_same_user_list(client):
    # 정상 경로: 수집 성공(ok:true) → 같은 user 스코프 목록에 즉시 1건
    _clear_mem()
    r = client.post("/api/v1/collect/extension",
                    json={"url": "https://temu.com/p/abc", "title": "Temu 테스트 상품",
                          "price": "9.99", "currency": "USD"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    from src.seller_console import collect_history_store as ch
    items = ch.list_items(seller_ids={"u1"})
    assert len(items) == 1 and items[0]["title"] == "Temu 테스트 상품"


def test_non_durable_save_is_honest_failure_not_fake_success(client, monkeypatch):
    # 가짜 성공 박멸: 시트 설정됐는데 쓰기 실패 → 인메모리 폴백 → 502 정직 실패(ok:false)
    _clear_mem()
    import src.seller_console.collect_history_store as ch
    monkeypatch.setattr(ch, "_SHEET_ID", "fake-sheet-id")

    def _boom():
        raise RuntimeError("sheet write down")
    monkeypatch.setattr(ch, "_get_worksheet", _boom)

    r = client.post("/api/v1/collect/extension",
                    json={"url": "https://temu.com/p/zzz", "title": "비영속 상품", "price": "1"})
    body = r.get_json()
    assert r.status_code == 502, f"비영속 저장인데 성공 처리됨(가짜 성공): {body}"
    assert body["ok"] is False


def test_durable_save_returns_flag():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    item_id, durable = ch.append(return_durable=True, source="extension",
                                 url="https://x.com", title="t", seller_id="u1")
    assert item_id and durable is True   # 시트 미설정 = 단일테넌트 의도(영속 간주)
