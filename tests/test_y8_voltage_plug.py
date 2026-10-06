"""Y8 확장(오너 2026-10-05) — 옵션 값 속 전압·플러그 축 분리 + 국내 판매 필터 + 상세 맨 위 플러그 안내.

실측: `fixtures/providers/onebound_item_get_667810641388.json`(제습기 — 110V/220V × 미·영·호·국내 플러그 × 흑백)
대조: `onebound_item_get_652874751412.json`(소파 — 전압 토큰 없음 → 무반응).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

FX = Path(__file__).parent.parent / "fixtures" / "providers"
DEHUM = FX / "onebound_item_get_667810641388.json"
SOFA = FX / "onebound_item_get_652874751412.json"


def _extra(path):
    from src.collectors import taobao_provider_onebound as O
    p = O.normalize(json.loads(path.read_text(encoding="utf-8")))
    return {"options": copy.deepcopy(p["options"]), "skus": copy.deepcopy(p["skus"])}


def _pd(ex, **kw):
    return {"title": "미니 제습기", "title_ko": "미니 제습기", "title_src": "迷你除湿机", "price": "298", "currency": "CNY",
            "images": ["https://img.alicdn.com/a.jpg"], "options": ex["options"], "skus": ex["skus"],
            "description": "조용한 미니 제습기입니다.", **kw}


def test_notice_constants_exact():
    from src.seller_console import notice_texts as N
    assert N.PLUG_CN_SHORT == "220V · 중국식 플러그 — 변환 어댑터(돼지코) 필요"
    assert N.PLUG_CN_TITLE == "■ 플러그 안내"
    assert N.PLUG_CN_LINES == (
        "이 제품은 220V 전압에 맞지만 플러그가 중국 규격(납작한 2핀 또는 3핀)입니다.",
        "국내 콘센트에서 사용하려면 변환 어댑터(일명 돼지코)가 필요하며, 어댑터는 포함되어 있지 않습니다.",
        "※ 110V 전용 제품이 아니므로 변압기는 필요 없습니다.")
    assert N.PURCHASE_AGENT_NOTICE == ("본 제품은 해외 구매대행 상품으로 국내 KC 안전인증 표시가 없는 제품입니다. "
                                       "개인 사용 목적의 구매대행 특례에 따라 판매되며, 사용 중 발생하는 전기 안전 사항은 구매자가 확인해야 합니다.")


@pytest.mark.parametrize("value,voltage,plug,rest", [
    ("白色110V台湾美国日本加拿大", "110V", "A", "白色"),
    ("黑色220V英规香港澳门英国用", "220V", "G", "黑色"),
    ("白色220V澳规", "220V", "I", "白色"),
    ("黑色220V 国内用", "220V", "CN", "黑色"),
    ("银色110-220V欧规", "110-220V", "F/C", "银色"),
    ("白色100V日本", "100V", "A", "白色"),
    ("白色", None, None, "白色"),
    ("黑色宽电压国内用", "110-220V", "CN", "黑色"),        # 宽电压 = 겸용(숫자 없이)
    ("白色宽电压", "110-220V", None, "白色"),
    ("灰色宽电压110-220V欧规", "110-220V", "F/C", "灰色"),
])
def test_parse_tokens(value, voltage, plug, rest):
    from src.collectors import voltage_plug as V
    assert V.parse(value) == {"voltage": voltage, "plug": plug, "rest": rest}


def test_real_dehumidifier_split_and_verdicts():
    from src.collectors import voltage_plug as V
    ex = _extra(DEHUM)
    rec = V.apply(ex)
    assert rec["state"] == "split" and rec["sellable"] == 2 and rec["excluded"] == 6 and rec["plug_notice"] is True
    assert [o["name"] for o in ex["options"]] == ["颜色分类", "전압/플러그"]
    assert ex["options"][0]["values"] == ["白色", "黑色"]                                    # 색상 2값(남은 글자)
    assert sorted(ex["options"][1]["values"]) == ["110V A형", "220V", "220V G형", "220V I형"]
    ok = [k["spec"] for k in ex["skus"] if not k.get("sale_excluded")]
    assert ok == [["白色", "220V"], ["黑色", "220V"]]                                        # 白色220V国内用·黑色220V国内用
    why = sorted(k["sale_excluded"] for k in ex["skus"] if k.get("sale_excluded"))
    assert why == ["판매 제외: 110V 전용"] * 2 + ["판매 제외: 플러그 규격"] * 4
    assert [len(ex["options_src"][0]["values"]), len(ex["skus_src"])] == [8, 8]              # 원본 보관
    assert all(k["price"] == 298.0 for k in ex["skus"]) and V.apply(ex) is None             # 한 번만


def test_sofa_no_reaction():
    from src.collectors import voltage_plug as V
    ex = _extra(SOFA)
    before = copy.deepcopy(ex)
    assert V.apply(ex) is None and ex == before


def test_korea_market_drops_excluded_and_puts_notice_on_top():
    from src.collectors import voltage_plug as V
    from src.seller_console import notice_texts as N
    from src.seller_console.upload_dispatcher import UploadDispatcher
    ex = _extra(DEHUM)
    V.apply(ex)
    out, _loc = UploadDispatcher._payload_for_market(_pd(ex), "coupang")
    assert [k["spec"] for k in out["skus"]] == [["白色", "220V"], ["黑色", "220V"]] and len(out["skus_excluded"]) == 6
    assert out["options"][1]["values"] == ["220V"]                                          # 옵션명은 「220V」만
    desc = out["description"]
    assert desc.startswith(N.PLUG_CN_TITLE + "\n" + N.PLUG_CN_LINES[0])                     # 맨 위
    assert N.PURCHASE_AGENT_NOTICE in desc and desc.endswith("조용한 미니 제습기입니다.")
    assert "돼지코" not in out["title"] and not any("돼지코" in str(v) or "어댑터" in str(v)
                                                  for o in out["options"] for v in o["values"])
    html_in = _pd(ex, description_html='<img src="https://img.alicdn.com/d1.jpg"><p>본문</p>')
    h = UploadDispatcher._payload_for_market(html_in, "coupang")[0]["description_html"]
    assert h.startswith('<div class="kgp-plug-notice"><p><strong>■ 플러그 안내</strong></p>')
    assert h.index("kgp-plug-notice") < h.index("<img")                                    # 첫 이미지보다 위


def test_agent_notice_not_duplicated():
    from src.collectors import voltage_plug as V
    from src.seller_console import notice_texts as N
    from src.seller_console.upload_dispatcher import UploadDispatcher
    ex = _extra(DEHUM)
    V.apply(ex)
    out = UploadDispatcher._payload_for_market(_pd(ex, description="본문\n" + N.PURCHASE_AGENT_NOTICE), "coupang")[0]
    assert out["description"].count(N.PURCHASE_AGENT_NOTICE) == 1 and out["description"].startswith(N.PLUG_CN_TITLE)


def test_overseas_market_untouched():
    from src.collectors import voltage_plug as V
    from src.seller_console.upload_dispatcher import UploadDispatcher
    ex = _extra(DEHUM)
    V.apply(ex)
    out = UploadDispatcher._payload_for_market(_pd(ex), "shopify")[0]
    assert len(out["skus"]) == 8 and "플러그 안내" not in out["description"]


def test_no_voltage_token_no_notice():
    """전압 토큰이 없는 가전(USB 충전식 등) — 「国内用」이 있어도 안내 안 넣음."""
    from src.collectors import voltage_plug as V
    from src.seller_console.upload_dispatcher import UploadDispatcher
    ex = {"options": [{"name": "颜色分类", "values": ["白色国内用", "黑色国内用"]}],
          "skus": [{"spec": ["白色国内用"], "price": 10.0, "stock": 1, "sku_id": "1"},
                   {"spec": ["黑色国内用"], "price": 10.0, "stock": 1, "sku_id": "2"}]}
    V.apply(ex)
    assert not any(k.get("sale_excluded") or k.get("plug_notice") for k in ex["skus"])
    out = UploadDispatcher._payload_for_market(_pd(ex), "coupang")[0]
    assert "플러그 안내" not in out["description"]


def test_all_excluded_holds_then_override():
    from src.collectors import voltage_plug as V
    from src.seller_console.upload_dispatcher import UploadDispatcher, readiness_message
    ex = _extra(DEHUM)
    V.apply(ex)
    ex["skus"] = [k for k in ex["skus"] if k.get("sale_excluded")]
    ex["options"][1]["values"] = ["110V A형", "220V G형", "220V I형"]
    holds = [h for h in UploadDispatcher.readiness_holds(_pd(ex), "coupang") if h["fix"] == "voltage"]
    assert holds and holds[0]["short"] == "전압/플러그 불일치" and "판매 제외: 110V 전용" in holds[0]["line"]
    assert "「그래도 등록」" in readiness_message(holds)
    ov = _pd(ex, voltage_override={"at": "x", "by": "owner"})
    assert not [h for h in UploadDispatcher.readiness_holds(ov, "coupang") if h["fix"] == "voltage"]
    assert len(UploadDispatcher._payload_for_market(ov, "coupang")[0]["skus"]) == 6          # 그래도 등록 = 전부


def test_partial_exclusion_does_not_hold():
    from src.collectors import voltage_plug as V
    from src.seller_console.upload_dispatcher import UploadDispatcher
    ex = _extra(DEHUM)
    V.apply(ex)
    assert not [h for h in UploadDispatcher.readiness_holds(_pd(ex), "coupang") if h["fix"] == "voltage"]


def test_multitap_rule_stays_separate():
    """五孔/国标插座(멀티탭 자체)는 기존 소싱 제외 그대로 — 전압·플러그 규칙과 섞지 않는다."""
    from src.collectors import voltage_plug as V
    from src.seller_console.upload_dispatcher import UploadDispatcher
    ex = {"options": [{"name": "颜色", "values": ["白色220V国标插座", "黑色220V国标插座"]}],
          "skus": [{"spec": ["白色220V国标插座"], "price": 10.0, "stock": 1, "sku_id": "1"},
                   {"spec": ["黑色220V国标插座"], "price": 10.0, "stock": 1, "sku_id": "2"}]}
    V.apply(ex)
    pd = _pd(ex, title_src="排插", options_src=ex.get("options_src"))
    shorts = [h["short"] for h in UploadDispatcher.readiness_holds(pd, "coupang")]
    assert any("중국 표준 콘센트" in s for s in shorts) and "전압/플러그 불일치" not in shorts


def test_rule_pass_runs_split_and_m5_card(monkeypatch):
    """자동 경로(온바운드 → 병합 → 옵션 정규화)에서 분리되고, M5 카드에 회색 제외 줄 + 짧은 플러그 줄."""
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider_onebound as O
    from src.services import taobao_auto as A
    from src.seller_console import collect_history_store as S
    from src.db import image_translate_queue_pg as st
    monkeypatch.setenv("ONEBOUND_KEY", "kkk_test_key_1234")
    monkeypatch.setenv("ONEBOUND_SECRET", "sss_test_secret_5678")
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    monkeypatch.setattr(T, "fetch", lambda *a, **k: pytest.fail("mtop 호출 금지"))
    st.state_set(O._RAW + "667810641388", {})
    real_call = O.call
    monkeypatch.setattr(O, "call", lambda iid, refresh=False, no_cache=False, transport=None:
                        real_call(iid, refresh=refresh, no_cache=no_cache, transport=lambda u, p: (200, DEHUM.read_text(encoding="utf-8"))))
    seller = "owner-y8-volt"
    iid = S.append(source="share_text", url="https://item.taobao.com/item.htm?id=667810641388", seller_id=seller,
                   title="미니 제습기", price="", currency="",
                   extra={"title": "迷你除湿机", "title_ko": "미니 제습기", "item_id_taobao": "667810641388",
                          "enrich_state": "pending", "images": [], "uncollected": ["images", "options", "price"]})
    rec = A.run(seller, iid)
    assert rec["state"] == "done"
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert ex["voltage_split"]["state"] == "split" and ex["voltage_split"]["excluded"] == 6
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"] = seller
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert h.count('data-role="m5-sku-excluded"') == 3 and "판매 제외: 110V 전용" in h        # 5줄 중 제외 3(등록 2 먼저)
    assert 'data-role="m5-excluded-note"' in h and "국내 판매 제외 6개" in h
    assert "220V · 중국식 플러그 — 변환 어댑터(돼지코) 필요" in h
    d = c.get(f"/seller/collect/{iid}/auto-enrich").get_json()
    assert d["state"] == "done" and "동영상 없음" in d["line"] and "220V · 중국식 플러그" in d["line"]
    r = c.post(f"/seller/collect/{iid}/voltage-override", json={})
    assert r.status_code == 200 and json.loads(S.get(iid, seller_ids={seller})["extra_json"])["voltage_override"]["line"]


def test_wide_voltage_is_dual_and_sellable_with_notice():
    """D(오너 2026-10-06): 宽电压 = 110-220V 겸용 — 중국 플러그면 등록 가능 + 플러그 안내, 플러그 토큰 없으면 그대로."""
    from src.collectors import voltage_plug as V
    assert "宽电压" in dict(V.VOLT_WORDS)["110-220V"]
    assert V.verdict("110-220V", "CN") == {"sellable": True, "reason": "", "notice": True}
    ex = {"options": [{"name": "颜色分类", "values": ["白色宽电压国内用", "白色110V美规"]}],
          "skus": [{"spec": ["白色宽电压国内用"], "price": "100", "stock": 5},
                   {"spec": ["白色110V美规"], "price": "100", "stock": 5}]}
    rec = V.apply(ex)
    assert rec["state"] == "split" and rec["sellable"] == 1 and rec["excluded"] == 1 and rec["plug_notice"] is True
    assert ex["options"][-1]["values"][0] == "110-220V" and ex["skus"][0]["voltage"] == "110-220V"
