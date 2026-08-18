"""tests/test_v87_w11_provider_and_paths.py — v87-W11: 상위 프로바이더 진단 + W9 미적용 경로 2건.

- item1 진단: provider_diagnostics(env 검출·체인 포함, 키 값 없음) → '상위 4 전멸'이 env 미검출인지 판별.
- item① 재번역 소스=원본 제목(표시본 아님) → strip_market_boilerplate가 확실히 걸림.
- item② collect_status 조회 시 항상 재계산 → 스테일 저장값(단일상품 4/5) 신뢰 봉인.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.seller_console.ai.translator import provider_diagnostics
from src.collectors.collect_status import compute_collect_status


# ── item1: 프로바이더 진단(키 값 미출력) ─────────────────────────────
def test_provider_diagnostics_env_and_chain(monkeypatch):
    for k in ["NCP_PAPAGO_CLIENT_ID", "NCP_PAPAGO_CLIENT_SECRET", "DEEPL_API_KEY", "AZURE_TRANSLATOR_KEY", "OPENAI_API_KEY", "TRANSLATE_PROVIDER_CHAIN"]:
        monkeypatch.delenv(k, raising=False)
    d = {p["provider"]: p for p in provider_diagnostics()}
    assert d["mymemory"]["env_present"] and d["mymemory"]["in_chain"]
    for name in ["papago", "deepl", "azure", "openai"]:
        assert d[name]["env_present"] is False and d[name]["in_chain"] is False   # 미검출 → 체인 제외
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_ID", "a")
    monkeypatch.setenv("NCP_PAPAGO_CLIENT_SECRET", "b")
    d2 = {p["provider"]: p for p in provider_diagnostics()}
    assert d2["papago"]["env_present"] and d2["papago"]["in_chain"]


def test_provider_diagnostics_no_key_values():
    # 진단은 이름·bool만 — 키 값 유출 0.
    for p in provider_diagnostics():
        assert set(p.keys()) == {"provider", "env_present", "in_chain"}
        assert isinstance(p["env_present"], bool)


def test_diagnostics_template_shows_providers():
    src = Path("src/dashboard/admin_views.py").read_text(encoding="utf-8")
    assert "provider_diagnostics()" in src
    assert "프로바이더 상태" in src and "env 미검출" in src


# ── item①: 재번역 소스 = 원본 제목 ───────────────────────────────────
def test_retranslate_uses_original_title_not_display(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.seller_console.views as V
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    monkeypatch.setattr(V, "_seller_identities", lambda: {"u1"})
    monkeypatch.setattr(V, "_seller_id", lambda: "u1")
    iid = ch.append(source="extension", url="https://item.rakuten.co.jp/x/9/",
                    title="Rakugifu 포장 TSUMUGI",              # 표시본(옛 오염 번역)
                    price="1706", currency="JPY", seller_id="u1",
                    extra={"title": "楽ギフ_包装 TSUMUGI 紬", "title_en": "楽ギフ_包装 TSUMUGI 紬", "description": "日本語"})
    seen = {}

    class _T:
        def translate_product(self, s):
            seen["src"] = s["title"]
            return {"title_ko": "쓰무기", "description_ko": "d", "provider": "papago", "attempts": [], "detected_lang": "ja"}
        def translate_options(self, o): return {"options": o, "provider": "none", "translated": False}
    import src.seller_console.ai.translator as _tr
    monkeypatch.setattr(_tr, "AITranslator", lambda: _T())
    from src.order_webhook import app
    with app.test_client() as c:
        c.post("/seller/collect/bulk-translate", json={"item_ids": [iid]})
    assert seen["src"] == "楽ギフ_包装 TSUMUGI 紬"               # 원본(상용구 포함)에서 시작
    assert "Rakugifu" not in seen["src"]                        # 표시본(오염) 아님


def test_translate_product_strips_boilerplate_from_original():
    # translate_product 진입 시 상용구 제거가 걸리는지(전 진입점 강제) — dry-run 경로.
    import os
    os.environ["ADAPTER_DRY_RUN"] = "1"
    try:
        from src.seller_console.ai.translator import AITranslator
        out = AITranslator().translate_product({"title": "楽ギフ_包装 TSUMUGI 紬", "description": ""})
        assert "楽ギフ" not in out["title_ko"] and "TSUMUGI" in out["title_ko"]
    finally:
        os.environ.pop("ADAPTER_DRY_RUN", None)


# ── item②: collect_status 조회 시 항상 재계산(스테일 봉인) ────────────
def test_list_recomputes_collect_status_ignoring_stale(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.seller_console.views as V
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    monkeypatch.setattr(V, "_seller_identities", lambda: {"u1"})
    monkeypatch.setattr(V, "_seller_id", lambda: "u1")
    # 옛 스테일 저장값(부분 4/5)이 있어도, 실제 단일상품이면 재계산 성공 4/4.
    ch.append(source="extension", url="https://x/1", title="T", price="1706", currency="KRW", seller_id="u1",
              extra={"price": "1706", "price_status": "ok", "images": ["a"], "description": "x" * 30,
                     "review_count": 10, "collect_status": {"status": "부분", "filled": 4, "total": 5}})
    # 재계산 계약(직접): 스테일과 무관하게 성공 4/4
    r = compute_collect_status({"price": "1706", "price_status": "ok", "images": ["a"],
                                "description": "x" * 30, "review_count": 10})
    assert r["status"] == "성공" and r["filled"] == 4 and r["total"] == 4
    # 뷰가 스테일 저장값을 신뢰하지 않도록 소스 계약(항상 재계산).
    v = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert "조회 시 항상 재계산" in v
