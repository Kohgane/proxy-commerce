"""R2(오너 2026-10-05 역직구) — Qoo10 재팬 뼈대: env 「미설정」 · 명세 미확인이면 호출 안 함 · 수출 가격 엔진 · ko→ja 번역 체인."""
from __future__ import annotations

import pytest

QENV = ("QOO10_API_KEY", "QOO10_USER_ID", "QOO10_PASSWORD", "QOO10_CERT_KEY", "QOO10_FEE_PCT",
        "EXPORT_SHIP_KRW_PER_KG_JP", "EXPORT_MARGIN_PCT")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in QENV:
        monkeypatch.delenv(k, raising=False)


def test_status_unset_then_cert_needed_then_ready(monkeypatch):
    from src.markets import qoo10 as Q
    st = Q.status()
    assert st["state"] == "미설정" and st["missing"] == ["QOO10_API_KEY", "QOO10_USER_ID", "QOO10_PASSWORD"]
    for k in ("QOO10_API_KEY", "QOO10_USER_ID", "QOO10_PASSWORD"):
        monkeypatch.setenv(k, "x")
    assert Q.status()["state"] == "cert_needed"
    monkeypatch.setenv("QOO10_CERT_KEY", "secret-cert")
    st = Q.status()
    assert st["state"] == "ready" and "secret-cert" not in str(st)


def test_calls_refuse_until_spec_confirmed(monkeypatch):
    from src.markets import qoo10 as Q
    with pytest.raises(Q.Qoo10NotReady, match="미설정"):
        Q.call("new_goods", {})
    monkeypatch.setenv("QOO10_CERT_KEY", "c")
    with pytest.raises(Q.Qoo10NotReady, match="추측 금지"):
        Q.call("new_goods", {"x": 1}, transport=lambda u, p: {"ok": True})
    with pytest.raises(Q.Qoo10NotReady, match="메서드명 미확인"):
        Q.call("orders", {})
    gaps = Q.spec_gaps()
    assert any("베이스 URL 미확인" in g for g in gaps) and any("ItemsBasic.SetNewGoods 파라미터 이름 미확인" in g for g in gaps)
    # 명세가 확정되면(가이드 확인 뒤 표를 채움) 그 파라미터만 보낸다
    monkeypatch.setitem(Q.QAPI_BASE, "confirmed", True)
    monkeypatch.setitem(Q.METHODS, "new_goods", dict(Q.METHODS["new_goods"], params_confirmed=True, params=["ItemTitle"]))
    sent = []
    Q.call("new_goods", {"ItemTitle": "t"}, transport=lambda u, p: sent.append((u, p)) or {"ok": True})
    assert sent == [("https://api.qoo10.jp/GMKT.INC.Front.QAPIService/ebayjapan.qapi/ItemsBasic.SetNewGoods", {"ItemTitle": "t"})]
    with pytest.raises(Q.Qoo10NotReady, match="명세에 없는 파라미터 Bogus"):
        Q.call("new_goods", {"Bogus": 1}, transport=lambda u, p: {})


def test_export_price_needs_fee_ship_weight_fx(monkeypatch):
    from src.pricing import export_price as P
    fx = {"JPY": 9.0}
    assert P.quote(30000, market="qoo10", weight_kg=1.0, fx_rates=fx)["why"] == "수수료 미설정 — 가격 산정 보류(QOO10_FEE_PCT)"
    monkeypatch.setenv("QOO10_FEE_PCT", "10")
    assert "EXPORT_SHIP_KRW_PER_KG_JP" in P.quote(30000, market="qoo10", weight_kg=1.0, fx_rates=fx)["why"]
    monkeypatch.setenv("EXPORT_SHIP_KRW_PER_KG_JP", "8000")
    assert P.quote(30000, market="qoo10", weight_kg=None, fx_rates=fx)["why"].startswith("무게 미확인")
    assert P.quote(30000, market="qoo10", weight_kg=1.0, fx_rates={})["why"].startswith("환율 없음(JPY)")
    q = P.quote(30000, market="qoo10", weight_kg=1.5, fx_rates=fx)
    # (30,000 + 12,000) ÷ (1 − 0.10 − 0.27) = 66,667원 → ÷ 9 = 7,408엔(올림)
    assert q["state"] == "ok" and q["krw"] == 66667 and q["price"] == 7408 and q["currency"] == "JPY"
    assert q["duty_free"] is True and "1만 엔 이하(소액 면세 대상 가능)" in q["line"]
    q2 = P.quote(90000, market="qoo10", weight_kg=1.5, fx_rates=fx)
    assert q2["price"] > 10000 and q2["duty_free"] is False and "1만 엔 초과" in q2["line"]
    monkeypatch.setenv("EXPORT_MARGIN_PCT", "95")
    assert "100%를 넘어요" in P.quote(30000, market="qoo10", weight_kg=1.0, fx_rates=fx)["why"]


def test_ko_to_ja_chain_keeps_korean_when_no_translator(monkeypatch):
    from src.services import export_translate as E
    for k in ("NCP_PAPAGO_CLIENT_ID", "NCP_PAPAGO_CLIENT_SECRET", "DEEPL_API_KEY", "AZURE_TRANSLATOR_KEY"):
        monkeypatch.delenv(k, raising=False)
    r = E.to_ja(["빈백 소파", "1인용"])
    assert r["translated"] is False and r["texts"] == ["빈백 소파", "1인용"] and [a["provider"] for a in r["attempts"]] == ["papago", "deepl", "azure"]
    tbl = {"빈백 소파": "ビーズソファ", "1인용": "1人用", "색상": "カラー", "그레이": "グレー", "상세": "詳細"}

    def _fail(t):
        raise RuntimeError("HTTP 429")
    monkeypatch.setattr(E, "CHAIN", (("papago", _fail), ("deepl", lambda t: [tbl.get(x, x) for x in t])))
    p = E.product_to_ja({"title_ko": "빈백 소파", "description_ko": "상세",
                         "options": [{"name": "颜色", "name_ko": "색상", "values": ["灰"], "values_ko": ["그레이"]}]})
    assert p["translated"] and p["provider"] == "deepl" and p["title_ja"] == "ビーズソファ"
    assert p["options_ja"] == [{"name": "カラー", "values": ["グレー"]}] and p["attempts"][0]["error"].endswith("HTTP 429")


def test_build_goods_lists_holds():
    from src.markets import qoo10 as Q
    g = Q.build_goods({"id": "i1", "images": []}, ja={"translated": False, "attempts": [{"provider": "papago", "error": "키 없음"}]},
                      price={"state": "unknown", "why": "수수료 미설정 — 가격 산정 보류(QOO10_FEE_PCT)"})
    assert g["holds"] == ["일본어 번역 안 됨 — papago: 키 없음", "판매가 없음 — 수수료 미설정 — 가격 산정 보류(QOO10_FEE_PCT)", "이미지 0장"]


def test_diag_page_shows_status_gaps_and_quote(monkeypatch):
    monkeypatch.setenv("QOO10_FEE_PCT", "10")
    monkeypatch.setenv("EXPORT_SHIP_KRW_PER_KG_JP", "8000")
    from src.seller_console import data_aggregator as D
    monkeypatch.setattr(D, "get_fx_rates", lambda: {"JPY": 9.0})
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/qoo10", query_string={"cost": "30000", "kg": "1.5"}).get_data(as_text=True)
    assert 'data-role="qoo10-status"' in h and "미설정 — QOO10_API_KEY · QOO10_USER_ID · QOO10_PASSWORD" in h
    assert "ItemsBasic.SetNewGoods 파라미터 이름 미확인" in h and "7,408 JPY" in h
