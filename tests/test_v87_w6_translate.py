"""tests/test_v87_w6_translate.py — v87-W6 수집 번역 토글 + 번역 실패 정직 표시 + 계측.

## 오너 실기기 결함(재조사 금지)
① 수집 시 번역 토글의 실동작이 체감과 불일치. ② "번역 자체가 안 되는 경우가 많다"(쿼터 18/20 = 소진 아님).

## 근원
- 토글→payload→서버-존중 배선은 온전(popup kgp_translate → background translate:false → 서버 respect).
  체감 불일치의 실체는 **실패의 조용한 처리**: 번역 실패(openai-fallback) 시 원문 유지인데 응답이
  translated=True로 보고(폴백을 성공으로 오분류) + 실패 사유(translate_error)가 extra에 **미저장**.
- 실패 다발 근원: `_translate_openai` max_tokens=900 고정이 **긴 상세(일본어 721자)+제목+마켓카피 3종** JSON을
  잘라 json.loads 실패 → openai-fallback(원문 유지). = "됐다는데 원문"의 정체.

## 수리 (서버만 — 확장·번역쿼터 회계 무손대, AI 예산 존중)
- 계측: `_record_translate`/`get_translate_stats`(호출·성공·실패·사유별, 쿼터와 별개 읽기전용).
- 근원: max_tokens 길이비례(1000+입력, 캡 3000) + 타임아웃 길이대응.
- 정직 표시: extra에 translated/translate_error/translate_requested 저장 → 목록·드로어 3분(번역함/원문/실패+재시도).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.seller_console.ai import translator as T


TR = Path("src/seller_console/ai/translator.py").read_text(encoding="utf-8")
EXT = Path("src/api/extension_api.py").read_text(encoding="utf-8")
ROWS = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
PG = Path("src/db/collect_history_pg.py").read_text(encoding="utf-8")


# ── item 2 계측: 호출/성공/실패/사유별 ──────────────────────────────
def test_translate_stats_counts_calls_fails_reasons(monkeypatch):
    T.reset_translate_stats()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TRANSLATE_PROVIDER_CHAIN", "openai")   # v87-W7: openai만 격리(체인 무료 프로바이더 네트워크 회피)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import requests

    # 실패(잘린 JSON = max_tokens 잘림 시뮬) → openai-fallback + 원문 유지 + 계측.
    def _truncated(url, headers=None, json=None, timeout=None, data=None):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": '{"title_ko":"x","descripti'}}]}
        return R()
    monkeypatch.setattr(requests, "post", _truncated)
    tr = T.AITranslator(); tr.provider = "openai"
    res = tr.translate_product({"title": "TSUMUGI 紬", "description": "長い説明" * 100})
    assert res["provider"] == "openai-fallback" and res.get("error")
    assert res["title_ko"] == "TSUMUGI 紬"   # 원문 유지(실패)
    st = T.get_translate_stats()
    assert st["calls"] == 1 and st["fail"] == 1 and st["ok"] == 0
    assert sum(st["by_reason"].values()) == 1

    # 성공 1건 → ok 증가.
    def _ok(url, headers=None, json=None, timeout=None, data=None):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": '{"title_ko":"쓰무기","description_ko":"설명","copy_coupang":"a","copy_smartstore":"b","copy_11st":"c"}'}}]}
        return R()
    monkeypatch.setattr(requests, "post", _ok)
    tr.translate_product({"title": "x", "description": "y"})
    st2 = T.get_translate_stats()
    assert st2["calls"] == 2 and st2["ok"] == 1 and st2["fail"] == 1


def test_translate_max_tokens_is_length_aware():
    # 근원 수리: 고정 900 → 길이비례(1000+입력, 캡 3000) + 길이 대응 타임아웃.
    assert "_max_tokens = max(900, min(3000, 1000 + _in_len))" in TR
    assert "_timeout = 30 if _in_len > 400 else 15" in TR
    assert '"max_tokens": 900' not in TR   # 옛 고정값 잔존 0(번역 경로)


# ── item 1·2 저장: 번역 상태 정직 저장(폴백=실패, 토글 존중) ─────────────
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c, ext


def _extra(ext, item_id):
    from src.seller_console import collect_history_store as ch
    row = ch.get(item_id, seller_id="u1")
    ex = row.get("extra") or row.get("extra_json") or {}
    return json.loads(ex) if isinstance(ex, str) else ex


def _clear():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()


def test_failed_translation_stored_as_failure_not_silent(client, monkeypatch):
    c, ext = client
    _clear()
    # 번역이 실패(폴백)하는 상황 모킹.
    monkeypatch.setattr(ext, "_translate_payload", lambda p: {
        "title_ko": p.get("title", ""), "description_ko": p.get("description", ""),
        "provider": "openai-fallback", "translate_error": "번역 API 호출에 실패했어요"})
    r = c.post("/api/v1/collect/extension", json={
        "url": "https://item.rakuten.co.jp/x/1/", "title": "TSUMUGI 紬", "price": "1706", "currency": "JPY",
        "images": ["https://i/a.jpg"], "translate": True})
    j = r.get_json()
    assert j["translated"] is False           # 폴백을 성공으로 오분류하지 않음
    assert j["translate_error"]               # 사유 응답
    ex = _extra(ext, j["item_id"])
    assert ex["translated"] is False and ex["translate_error"] and ex["translate_requested"] is True


def test_successful_translation_marked_translated(client, monkeypatch):
    c, ext = client
    _clear()
    monkeypatch.setattr(ext, "_translate_payload", lambda p: {
        "title_ko": "쓰무기 레코드", "description_ko": "상세", "provider": "openai"})
    r = c.post("/api/v1/collect/extension", json={
        "url": "https://item.rakuten.co.jp/x/2/", "title": "TSUMUGI 紬", "price": "1706", "currency": "JPY",
        "images": ["https://i/a.jpg"], "translate": True})
    j = r.get_json()
    assert j["translated"] is True and not j.get("translate_error")
    ex = _extra(ext, j["item_id"])
    assert ex["translated"] is True and not ex["translate_error"]


def test_toggle_off_is_not_a_failure(client, monkeypatch):
    c, ext = client
    _clear()
    # translate:false → 번역 시도 자체 없음(사용자 선택). '원문 유지'는 실패 아님.
    called = {"n": 0}
    def _should_not_call(p):
        called["n"] += 1
        return {}
    monkeypatch.setattr(ext, "_translate_payload", _should_not_call)
    r = c.post("/api/v1/collect/extension", json={
        "url": "https://item.rakuten.co.jp/x/3/", "title": "TSUMUGI 紬", "price": "1706", "currency": "JPY",
        "images": ["https://i/a.jpg"], "translate": False})
    j = r.get_json()
    assert called["n"] == 0                    # 토글 OFF → 번역 파이프라인 미호출(존중)
    ex = _extra(ext, j["item_id"])
    assert ex["translate_requested"] is False and ex["translated"] is False and not ex["translate_error"]


# ── 표시 계약: 목록·드로어·views·PG ───────────────────────────────────
def test_list_row_shows_three_state_badges():
    assert "번역 실패" in ROWS and "다시 번역" in PREVIEW
    assert "원문(번역 안 함)" in ROWS
    assert "it.translate_error" in ROWS and "it.translate_requested is false" in ROWS


def test_views_exposes_translate_status_and_pg_projects_it():
    assert 'it["translated"]' in VIEWS and 'it["translate_error"]' in VIEWS and 'it["translate_requested"]' in VIEWS
    assert "'translated', extra_json->'translated'" in PG
    assert "'translate_error', extra_json->'translate_error'" in PG
