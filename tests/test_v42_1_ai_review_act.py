"""V42-1(오너 2026-10-28 20:08) — AI 검수 항목에 수락·편집·기각 동사(수락 = 상품명 바로 고침) · 사진 글자 대기엔 예상 시간 + 자동 재검증."""
from __future__ import annotations

import json
import os

import pytest

from src.services import ai_review as AR
from src.services import risk_gate as RG


def test_parse_items_structured_and_legacy():
    it = AR._parse_items({"items": [{"issue": "상품명에 전기자전거·스쿠터 혼용", "field": "title", "fix": "전기자전거 36V 접이식"},
                                    {"issue": "옵션에 용량 없음", "field": "option", "fix": "무시됨"},
                                    {"issue": "", "field": "title"}, "문자열 항목"]})
    assert [x["field"] for x in it] == ["title", "option", "none"]
    assert it[0]["fix"] == "전기자전거 36V 접이식" and it[1]["fix"] is None          # fix는 title만
    assert AR._parse_items({"lines": ["옛 형식"]}) == [{"issue": "옛 형식", "field": "none", "fix": None}]


def test_decide_accept_rewrites_title_and_records():
    ex = {"title_ko": "전기 스쿠터 전기자전거", "coupang_name": "전기 스쿠터 전기자전거", "pv_ready": {"ok": True},
          AR.KEY: {"status": "done", "items": [{"issue": "혼용", "field": "title", "fix": "전기자전거 36V 접이식"},
                                               {"issue": "옵션 부족", "field": "option", "fix": None}]}}
    r = AR.decide(ex, 0, "accept", by="u1")
    assert r["ok"] and r["changed"] == {"title_ko": "전기자전거 36V 접이식", "coupang_name": "전기자전거 36V 접이식"}
    assert ex["title_ko"] == "전기자전거 36V 접이식" and "pv_ready" not in ex           # 바뀌었으니 「준비 완료」는 다시
    d = ex[AR.KEY]["decisions"]["0"]
    assert d["action"] == "accept" and d["prev"]["title_ko"] == "전기 스쿠터 전기자전거"
    r2 = AR.decide(ex, 1, "accept")
    assert not r2["ok"] and "편집" in r2["why"]                                     # 자동으로 못 고치는 건 정직하게
    assert AR.decide(ex, 1, "reject")["ok"] and ex[AR.KEY]["decisions"]["1"]["action"] == "reject"
    assert not AR.decide(ex, 9, "reject")["ok"] and not AR.decide({}, 0, "accept")["ok"]


def test_card_carries_items_and_decisions():
    c = AR.card({"status": "done", "lines": ["a"], "items": [{"issue": "a", "field": "none", "fix": None}], "decisions": {"0": {"action": "reject"}}})
    assert c["items"][0]["issue"] == "a" and c["decisions"]["0"]["action"] == "reject"
    assert AR.card({"status": "done", "lines": ["옛"]})["items"] == [{"issue": "옛", "field": "none", "fix": None}]


def test_prompt_text_marks_price_as_internal():
    body = AR._text({"title_ko": "T", "price": "1849", "currency": "CNY", "images": []}, {})
    assert "약 " not in body and "CNY" not in body                                      # 우리 표기(약·원가 통화)를 AI가 짚지 않게
    assert "시스템 값" in AR._prompt("x") and '"items"' in AR._prompt("x")


def test_risk_wait_line_has_eta_and_auto_word():
    sc = RG.scan({"images": []}, pending_images=12, pending_eta_sec=200)
    assert sc["waiting"] == 12 and sc["waiting_eta_sec"] == 200
    hold = [h for h in RG.holds(sc) if h["code"] == "risk_wait"]
    assert hold and "약 4분" in hold[0]["line"] and "자동으로 다시" in hold[0]["line"]
    assert RG.card(sc)["waiting_eta_sec"] == 200
    assert RG.eta_word(0) == "" and RG.eta_word(30) == " · 약 30초"


@pytest.fixture()
def client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-v421"; s["user_email"] = "v421@test.local"; s["user_role"] = "seller"
        yield c


def test_route_accept_saves_and_returns_card(client):
    from src.seller_console import collect_history_store as CH
    uid = "u-v421"
    iid = CH.append(source="extension", url="https://item.taobao.com/item.htm?id=4210", title="t", image="", price="1", currency="CNY", seller_id=uid)
    iid = iid[0] if isinstance(iid, tuple) else iid
    CH.update(iid, seller_ids={uid}, extra_json=json.dumps({"title_ko": "전기 스쿠터 전기자전거",
        AR.KEY: {"status": "done", "items": [{"issue": "혼용", "field": "title", "fix": "전기자전거 36V 접이식"}]}}))
    r = client.post(f"/seller/collect/{iid}/ai-review-act", json={"idx": 0, "action": "accept"})
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["fields"]["title_ko"] == "전기자전거 36V 접이식"
    assert d["ai_review"]["decisions"]["0"]["action"] == "accept"
    ex = json.loads(CH.get(iid, seller_ids={uid})["extra_json"])
    assert ex["title_ko"] == "전기자전거 36V 접이식"                                    # 저장됐다
    r2 = client.post(f"/seller/collect/{iid}/ai-review-act", json={"idx": 0, "action": "nope"})
    assert r2.status_code == 400


def test_ui_block_has_verbs_and_auto_rerun():
    blk = open("src/seller_console/templates/_risk_block.html", encoding="utf-8").read()
    for s in ('data-role="ai-review-act"', 'data-action="accept"', 'data-action="reject"', 'data-role="ai-review-edit"', "/ai-review-act"):
        assert s in blk
    pv = open("src/seller_console/templates/collect_preview.html", encoding="utf-8").read()
    assert "kgpAiReviewHtml(window._kgpAiReview, _ITEM_ID)" in pv and "risk_wait" in pv and "_kgpPvAutoRerun" in pv
    css = open("src/static/app.css", encoding="utf-8").read()
    for cls in (".kgp-ai-field", ".kgp-ai-fix", ".kgp-ai-decided"):
        assert cls in css
