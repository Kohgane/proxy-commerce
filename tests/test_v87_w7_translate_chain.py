"""tests/test_v87_w7_translate_chain.py — v87-W7 번역 다중 프로바이더 체인 + 병기 + 초안 폴백.

## 오너 정책(불변)
- 상세 = 원문 + 한국어 병기 허용. 제목 = 원문 유지 허용. KO/EN 혼재 금지는 콘솔 UI 언어 한정(상품 문안 병기 예외).
- 번역 프로바이더 체인: 무료 → 저가/키필요 → OpenAI 순차 폴백(하나 실패하면 다음).

## 이 파일이 못박는 것
1. 체인 순서(무료 우선·env 오버라이드)·MyMemory 무키 프로바이더·폴백+attempts·translated에 mymemory 포함.
2. compose_bilingual(한국어+구분선+원문, 중복 제거) + collect_upload 병기 합성 + 드로어 미리보기.
4. 무키 폴백 초안: 원문 상세 라인 통째 보존(숫자 조각 리스트 금지).
5. 확장 업데이트 채널 안내(버전 배너+다운로드).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.seller_console.ai.translator as T
from src.seller_console.ai.translator import AITranslator, compose_bilingual, _detect_src_lang


# ── item1 체인 ───────────────────────────────────────────────────────
def test_provider_chain_free_first_and_override(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    monkeypatch.delenv("TRANSLATE_PROVIDER_CHAIN", raising=False)
    monkeypatch.delenv("TRANSLATE_DISABLE_MYMEMORY", raising=False)
    assert AITranslator()._provider_chain() == ["mymemory"]          # 무키 → 무료만
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    assert AITranslator()._provider_chain() == ["mymemory", "openai"]  # 무료 우선 → OpenAI 폴백
    monkeypatch.setenv("TRANSLATE_PROVIDER_CHAIN", "openai,mymemory")
    assert AITranslator()._provider_chain() == ["openai", "mymemory"]  # 오버라이드(품질 우선)


def test_detect_src_lang():
    assert _detect_src_lang("TSUMUGI 紬 レコード") == "ja"
    assert _detect_src_lang("쓰무기") == "ko"
    assert _detect_src_lang("木制唱片盒") == "zh-CN"
    assert _detect_src_lang("Wooden case") == "en"


def test_chain_falls_over_and_records_attempts(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    monkeypatch.delenv("TRANSLATE_PROVIDER_CHAIN", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import requests

    def _mm_fail(url, params=None, timeout=None):
        class R:
            def raise_for_status(self): raise RuntimeError("429 quota")
            def json(self): return {}
        return R()

    def _openai_ok(url, headers=None, json=None, timeout=None, data=None):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": '{"title_ko":"쓰무기","description_ko":"상세","copy_coupang":"a","copy_smartstore":"b","copy_11st":"c"}'}}]}
        return R()
    monkeypatch.setattr(requests, "get", _mm_fail)
    monkeypatch.setattr(requests, "post", _openai_ok)
    res = AITranslator().translate_product({"title": "TSUMUGI 紬", "description": "日本語"})
    assert res["provider"] == "openai"                       # mymemory 실패 → openai 성공
    prov = [a["provider"] for a in res["attempts"]]
    assert prov == ["mymemory", "openai"]
    assert res["attempts"][0]["ok"] is False and res["attempts"][1]["ok"] is True


def test_all_providers_fail_is_honest_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.delenv("TRANSLATE_PROVIDER_CHAIN", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    res = AITranslator().translate_product({"title": "x", "description": "y"})
    # 전부 실패 → 마지막 프로바이더의 -fallback 보존 + translate_error(정직 실패), 원문 유지.
    assert res["provider"].endswith("-fallback") and res.get("translate_error")
    assert res["title_ko"] == "x"
    assert all(a["ok"] is False for a in res["attempts"])


def test_extension_api_stores_attempts_and_mymemory_translated(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    monkeypatch.setattr(ext, "_translate_payload", lambda p: {
        "title_ko": "쓰무기", "description_ko": "상세", "provider": "mymemory",
        "attempts": [{"provider": "mymemory", "ok": True, "error": ""}]})
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    with app.test_client() as c:
        r = c.post("/api/v1/collect/extension", json={
            "url": "https://item.rakuten.co.jp/x/9/", "title": "TSUMUGI 紬", "price": "1706", "currency": "JPY",
            "images": ["https://i/a.jpg"], "translate": True})
        j = r.get_json()
    assert j["translated"] is True and j["translation_provider"] == "mymemory"
    row = ch.get(j["item_id"], seller_id="u1")
    ex = json.loads(row["extra_json"]) if isinstance(row.get("extra_json"), str) else (row.get("extra") or {})
    assert ex["translated"] is True and ex["translation_attempts"] == [{"provider": "mymemory", "ok": True, "error": ""}]


# ── item1(W7a) AI 초안: 키 미설정 vs 키 있으나 호출 실패 3분 ─────────────
def test_draft_status_distinguishes_no_key_vs_openai_error(monkeypatch):
    from src.seller_console.ai.translator import AITranslator as A
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import requests
    # 키 있으나 호출 실패 → openai_error + 사유(키 미설정으로 오귀인 금지).
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = A().generate_description({"title": "T", "specs": [["サイズ", "30cm"]], "description": "素材:木"})
    assert out["provider"] == "stub" and out["draft_status"] == "openai_error" and out["draft_error"]
    # 키 부재 → no_openai_key.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out2 = A().generate_description({"title": "T", "specs": [["サイズ", "30cm"]], "description": "素材:木"})
    assert out2["provider"] == "stub" and out2["draft_status"] == "no_openai_key" and not out2["draft_error"]


def test_ai_draft_ui_message_is_three_way():
    t = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "draft_status === 'openai_error'" in t
    assert "AI 키는 설정돼 있지만 호출에 실패" in t          # 키 있으나 실패
    assert "설정되지 않아" in t                              # 키 부재


def test_ai_draft_endpoint_returns_draft_status():
    v = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert '"draft_status": res.get("draft_status"' in v and '"draft_error": res.get("draft_error"' in v


def test_chain_attempts_record_elapsed_ms():
    tr = Path("src/seller_console/ai/translator.py").read_text(encoding="utf-8")
    assert '"ms": int((_time.time() - _t0) * 1000)' in tr


# ── item2 병기 ───────────────────────────────────────────────────────
def test_compose_bilingual():
    assert compose_bilingual("한국어", "日本語") == "한국어\n\n───────── 원문 (Original) ─────────\n日本語"
    assert compose_bilingual("x", "x") == "x"           # 같으면 하나만(중복 없음)
    assert compose_bilingual("한국어", "") == "한국어"     # 원문 없으면 번역만
    assert compose_bilingual("", "원문") == "원문"


def test_collect_upload_composes_bilingual_from_stored_original(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.seller_console.views as V
    # 저장된 원문(일본어)을 재읽어 병기 합성하는지 — 디스패처는 캡처만.
    monkeypatch.setattr(V, "_get_owned_item", lambda iid: {"extra_json": json.dumps({"description": "日本語の説明"})})
    captured = {}

    class _FakeResult:
        def to_dict(self): return {"markets": {}}

    class _FakeDisp:
        def dispatch(self, product, markets):
            captured["desc"] = product.get("description"); return _FakeResult()
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _FakeDisp())
    monkeypatch.setattr(V, "_persist_upload_status", lambda *a, **k: None)
    import src.seller_console.market_credentials as mc

    class _Env:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(mc, "seller_market_env", lambda *a, **k: _Env())
    monkeypatch.setattr(V, "_seller_id", lambda: "u1")
    from src.order_webhook import app
    with app.test_client() as c:
        c.post("/seller/collect/upload", json={
            "product": {"description": "한국어 번역본", "title": "T", "price": "1000"},
            "markets": ["coupang"], "item_id": "it1"})
    assert "日本語の説明" in captured["desc"] and "한국어 번역본" in captured["desc"]   # 병기본이 마켓으로
    assert "원문 (Original)" in captured["desc"]


def test_drawer_has_bilingual_preview_and_provider():
    t = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "마켓 전송 미리보기" in t and "원문 (Original)" in t
    assert "번역 프로바이더" in t and "translation_attempts" in t


# ── item4 초안 무키 폴백: 원문 라인 통째 보존 ──────────────────────────
def test_stub_draft_preserves_whole_original_lines(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    monkeypatch.setenv("TRANSLATE_DISABLE_MYMEMORY", "1")
    out = AITranslator().generate_description({
        "title": "TSUMUGI", "category": "GEN", "keywords": ["レコード"], "brand": "TSUMUGI",
        "specs": [["サイズ", "30cm"]],
        "description": "素材: 天然木（オーク）\nサイズ: 約30×30×5cm\n重量: 1.2kg\nお気に入りに追加\n1"})
    txt = out["text"]
    assert "■ 원문 상세" in txt
    assert "素材: 天然木（オーク）" in txt and "重量: 1.2kg" in txt   # 원문 라인 통째
    assert "お気に入りに追加" not in txt                            # UI 쓰레기 제외
    # 숫자 조각(단독 '1') 금지.
    assert "\n1\n" not in ("\n" + txt + "\n")


# ── item5 확장 업데이트 채널 안내 ──────────────────────────────────────
def test_extension_install_shows_version_channel():
    t = Path("src/seller_console/templates/extension_install.html").read_text(encoding="utf-8")
    assert "최신 확장 버전" in t and "최신 확장 내려받기" in t
    assert "/seller/extension/download" in t
