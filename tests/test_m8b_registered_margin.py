"""M8 추가(오너 2026-10-10) — 7. 이미 등록된 마켓은 사전검증 「통과」가 아니라 「이미 등록됨 {번호}」(업로드 대상에서 빠짐) ·
8. 목표 마진율 정의 통일(출처 하나 · 환율 하나 · 줄에 분모·분자 적시 · 등록 때 재료 기록)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._pv_helper import prevalidate
from tests.test_m8_market_popup import UPLOADED, _item


def _client(seller, monkeypatch):
    """공유 사용자(가족) 세션 — 계정 코드 마켓(셰고가·고코스모스·쿠팡 계정)을 쓸 수 있는 문맥."""
    monkeypatch.setenv("FAMILY_EMAILS", f"{seller}@example.com")
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=seller, user_email=f"{seller}@example.com", user_role="seller")
    return c


# ── 7. 이미 등록됨 ─────────────────────────────────────────────────────────────────────────────

def test_7_registered_rows_skip_validation_and_show_number(monkeypatch):
    import src.seller_console.views as V
    from src.order_webhook import app
    iid = _item("m8b-reg")
    with app.test_request_context():
        from flask import session
        session["user_id"] = "m8b-reg"
        rows = V._pv_registered_rows(iid, ["smartstore:gocosmos", "smartstore:chezgoga", "coupang:gogane", "elevenst"])
    assert set(rows) == {"smartstore:gocosmos", "smartstore:chezgoga", "coupang:gogane"}
    r = rows["smartstore:gocosmos"]
    assert r["ok"] is False and r["registered_no"] == "13803531537" and r["error_code"] == "already_registered"
    assert r["message"] == "이미 등록됨 13803531537 · 다시 등록하려면 기록을 빼세요"


def test_7_prevalidate_job_marks_registered_and_still_checks_others(monkeypatch):
    import src.seller_console.views as V
    seen = []

    class D:
        def prevalidate(self, pd, markets):
            from src.seller_console.upload_dispatcher import PrevalidationResult
            seen.extend(markets)
            return [PrevalidationResult(market=markets[0], ok=True, message="사전검증 통과")]
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: D())
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    iid = _item("m8b-job")
    d = prevalidate(_client("m8b-job", monkeypatch), {"product": {"title": "x", "price": 1}, "item_id": iid,
                                         "markets": ["smartstore:gocosmos", "elevenst"]})
    by = {r["market"]: r for r in d["results"]}
    assert by["smartstore:gocosmos"]["registered_no"] == "13803531537" and by["smartstore:gocosmos"]["ok"] is False
    assert by["elevenst"]["ok"] is True
    assert seen == ["elevenst"]                                                    # 등록된 마켓은 재지 않는다


def test_7_cards_render_registered_and_exclude_from_upload():
    cp = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert 'data-role="prevalidate-registered"' in cp and 'data-role="pv-registered-open"' in cp
    assert 'data-role="m5-registered"' in m5 and 'data-ok="0"' in m5            # ok=false → 업로드 대상(통과)에서 빠짐
    assert "_validatedMarkets = results.filter(r => r.ok)" in cp


def test_7_single_record_can_be_removed_only_for_reregister(monkeypatch):
    iid = _item("m8b-rm")
    c = _client("m8b-rm", monkeypatch)
    url = f"/seller/collect/{iid}/upload-record/remove"
    r = c.post(url, json={"market": "smartstore:gocosmos", "product_id": "13742400001"})
    assert r.status_code == 409                                                   # Y7-K 그대로(중복 정리 전용)
    r = c.post(url, json={"market": "smartstore:gocosmos", "product_id": "13742400001", "purpose": "reregister"})
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and "다시 등록할 수 있어요" in d["message"] and "13803531537" in d["message"]
    from src.seller_console import collect_history_store as CH
    ex = json.loads(CH.get(iid, seller_ids={"m8b-rm"})["extra_json"])
    assert not any(u["market"] == "smartstore:gocosmos" for u in ex["uploaded"])
    gone = [u for u in ex["uploaded_removed"] if u["market"] == "smartstore:gocosmos"][0]
    assert gone["removed_reason"].startswith("다시 등록하려고")
    t = Path("src/seller_console/templates/_market_status.html").read_text(encoding="utf-8")
    assert "기록 빼기(다시 등록용)" in t and "data-armed" in t and "reregister" in t


# ── 8. 마진 정의 ───────────────────────────────────────────────────────────────────────────────

def test_8_one_margin_source(monkeypatch):
    from src.price import target_margin_pct
    monkeypatch.setenv("IMPORT_MARGIN_PCT", "35")
    assert target_margin_pct({}) == 35.0 and target_margin_pct({"target_margin_pct": 22}) == 22.0
    assert target_margin_pct({"target_margin_pct": ""}) == 35.0


def test_8_desktop_slider_defaults_to_server_margin(monkeypatch):
    monkeypatch.setenv("IMPORT_MARGIN_PCT", "35")
    iid = _item("m8b-slider")
    h = _client("m8b-slider", monkeypatch).get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    assert 'id="uploadMarginPct" min="5" max="50" value="35"' in h
    assert "목표 마진율(실수령 · 판매가 기준)" in h and 'data-role="margin-def"' in h


def test_8_single_price_uses_same_fx_as_combo_and_line(monkeypatch):
    """예전: 단일 판매가는 `_build_fx_rates()`(실시간 꺼짐이면 고정 185) · 조합 판매가·팝업 줄은 `sell_fx_rates`(실시간)."""
    from decimal import Decimal
    import src.price as P
    from src.seller_console.upload_dispatcher import UploadDispatcher, price_parts_for
    rates = dict(P._build_fx_rates(use_live=False))
    rates["CNYKRW"] = Decimal("200.45")
    monkeypatch.setattr(P, "sell_fx_rates", lambda: (dict(rates), {"CNY": {"rate": 200.45, "label": "실시간 환율"}}))
    monkeypatch.setenv("MARKET_COMMISSION_PCT_SMARTSTORE", "5.5")
    monkeypatch.setenv("IMPORT_MARGIN_PCT", "25")
    pd = {"price": 168, "price_original": 168, "currency": "CNY"}
    single = UploadDispatcher._ensure_sell_price_krw(pd, "smartstore")["sell_price_krw"]
    combo, _why = UploadDispatcher._landed_krw(pd, "smartstore")
    parts = price_parts_for(pd, "smartstore:gocosmos")
    assert parts["fx"] == 200.45
    assert single == int(round(combo)) == int(round(parts["sell_krw"]))      # 같은 입력 → 같은 숫자


def test_8_price_line_spells_out_numerator_and_denominator(monkeypatch):
    from src.price import sell_price_parts, MARGIN_TERMS
    monkeypatch.setenv("MARKET_COMMISSION_PCT_SMARTSTORE", "5.5")
    from decimal import Decimal as D
    p = sell_price_parts(168, "CNY", "smartstore", 25,
                         fx_rates={"CNYKRW": D("200.45"), "JPYKRW": D("9.0"), "USDKRW": D("1350"), "EURKRW": D("1470")})
    assert "마진 25%는 실수령(판매가 기준: " + MARGIN_TERMS["net"] + ")" in p["line"]
    assert "판매가 대비" in p["line"] and "원가 대비" in p["line"]
    r = p["ratios"]
    assert abs(r["net"] - 25) < 0.1                                            # 식이 목표를 정확히 남긴다(10원 올림 오차)
    assert r["gross_on_sell"] > r["net"] and r["markup_on_cost"] > r["gross_on_sell"]


def test_8_registration_records_price_snapshot_and_popup_shows_it(monkeypatch):
    import src.seller_console.views as V
    iid = _item("m8b-snap")
    c = _client("m8b-snap", monkeypatch)
    snap = {"sell_krw": 96650.0, "margin_pct": 35.0, "commission_pct": 5.5, "fx": 200.45, "fx_label": "실시간 환율",
            "line": "원가 168 CNY×200.45 = … · 마진 35%는 실수령(…)"}
    with c.session_transaction() as s:
        s["user_id"] = "m8b-snap"
    from src.order_webhook import app
    with app.test_request_context():
        from flask import session as S
        S["user_id"] = "m8b-snap"
        V._persist_upload_status(iid, {"results": [{"market": "smartstore:gocosmos", "success": True,
                                                    "external_product_id": "13742400999", "channel_product_no": "13803539999",
                                                    "price": snap}]})
    from src.seller_console import collect_history_store as CH
    ex = json.loads(CH.get(iid, seller_ids={"m8b-snap"})["extra_json"])
    rec = [u for u in ex["uploaded"] if u.get("product_id") == "13742400999"][0]
    assert rec["price"]["margin_pct"] == 35.0 and rec["price"]["fx"] == 200.45
    d = c.get(f"/seller/collect/{iid}/market-status?phase=db&market=smartstore:gocosmos").get_json()
    row = [r for r in d["rows"] if r["product_id"] == "13742400999"][0]
    assert row["registered_price"].startswith("원가 168 CNY×200.45")
    t = Path("src/seller_console/templates/_market_status.html").read_text(encoding="utf-8")
    assert "등록 때 판매가 구성" in t and "지금 다시 내면" in t
