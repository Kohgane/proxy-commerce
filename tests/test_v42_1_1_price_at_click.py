"""tests/test_v42_1_1_price_at_click.py — v42 1-1: 수집 클릭 시점 렌더 DOM 가격 직접 읽기 + 통화 감지.

증거: Temu 페이지에 61,144원이 렌더됐는데 드로어는 0.00 USD.
원인: og:price(스테일/USD) 우선 + '원' 통화 미감지 + USD 기본값.
수리: 렌더 DOM 현재가 최우선(scoped→meta→본문), ₩/원→KRW, USD 기본값 금지.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


# ── 확장 소스 계약 ──
def test_currency_map_has_won_krw():
    assert '"원": "KRW"' in CS and '"엔": "JPY"' in CS


def test_return_prefers_scoped_no_usd_default():
    # 반환이 og:price를 우선하지 않고 해결된 heuristicPrice/Currency를 그대로 씀 + USD 기본값 제거.
    assert "price: heuristicPrice," in CS
    assert "currency: heuristicCurrency," in CS
    assert 'currency: getMeta("product:price:currency") || heuristicCurrency || "USD"' not in CS


def test_scoped_price_computed_unconditionally():
    # og:price 유무와 무관하게 scoped를 먼저 계산(과거: !getMeta(...) 게이트).
    assert "const _scoped = _kgpScopedPrice();" in CS
    assert "if (!getMeta(\"product:price:amount\")) {" not in CS


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_parse_price_detects_won_and_symbols():
    s1 = CS.index("const _KGP_SYM_MAP")
    s2 = CS.index("function _kgpScopedPrice")
    script = CS[s1:s2] + r"""
    const out = {};
    for (const c of ['₩61,144','61,144원','$12.99','¥3,200','1,999 KRW','free shipping']) {
      out[c] = _kgpParsePrice(c);
    }
    console.log(JSON.stringify(out));
    """
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    o = json.loads(res.stdout)
    assert o["₩61,144"] == {"price": "61144", "currency": "KRW"}
    assert o["61,144원"] == {"price": "61144", "currency": "KRW"}   # Temu KR
    assert o["$12.99"] == {"price": "12.99", "currency": "USD"}
    assert o["¥3,200"]["currency"] == "JPY"
    assert o["free shipping"] is None                              # 가짜 가격 0


# ── 서버: USD 기본값 금지 ──
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def _clear():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()


def test_krw_price_stored_not_usd(client):
    _clear()
    r = client.post("/api/v1/collect/extension", json={
        "url": "https://www.temu.com/kr/g-601.html", "title": "접이식 차량용 책상",
        "price": "61144", "currency": "KRW"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    from src.seller_console import collect_history_store as ch
    row = ch.list_items(seller_ids={"u1"})[0]
    assert row.get("currency") == "KRW"
    assert (row.get("price") or "") == "61144"


def test_price_without_currency_marks_needs_check_not_usd(client):
    """가격은 있는데 통화 미상 → USD 임의 확정 금지, needs_check(정직)."""
    _clear()
    r = client.post("/api/v1/collect/extension", json={
        "url": "https://shop.example.com/p/9", "title": "무통화 상품",
        "price": "12345", "currency": ""})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    from src.seller_console import collect_history_store as ch
    row = ch.list_items(seller_ids={"u1"})[0]
    assert (row.get("currency") or "") == ""      # USD 스탬프 안 함
    ex = json.loads(row.get("extra_json") or "{}")
    assert ex.get("price_status") == "needs_check"
