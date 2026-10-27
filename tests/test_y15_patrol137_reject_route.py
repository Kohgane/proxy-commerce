"""순찰 137(오너 2026-10-27 22:20 「4번 — 반려 사유 상세 + 조치」) — 반려 사유 전문 수집·자동 조치 라우팅 계약."""
from __future__ import annotations

import json

import pytest

from src.services import reject_route as RR
from src.services import oneshot_ops as OO


class _Up:
    def __init__(self, hist, product=None, approve_ok=True, modify_ok=True):
        self.hist, self.product, self.approve_ok, self.modify_ok = hist, product, approve_ok, modify_ok
        self.calls = []

    def get_status_histories(self, sid):
        return self.hist

    def request_approval(self, sid):
        self.calls.append(("approve", sid))
        return {"success": self.approve_ok, **({} if self.approve_ok else {"error": "쿠팡 거부 원문"})}

    def get_product(self, sid):
        return self.product or {"sellerProductId": sid, "items": [{"itemName": "a", "images": []}]}

    def modify_product(self, body):
        self.calls.append(("modify", body))
        return {"success": self.modify_ok, **({} if self.modify_ok else {"error": "수정 거부 원문"})}

    def rebuild_images_for_resubmit(self, images):
        return {"ok": bool(images), "images": [{"imageOrder": i, "vendorPath": u} for i, u in enumerate(images)],
                "dropped": [], "unknown": [], "reason": "" if images else "없음"}


_LONG = "대표이미지는 최대 10M, 최소 500*500, 최대 5000*5000 … " + "상세 설명 " * 120


def _hist(comment=_LONG, status="승인반려"):
    return {"data": [{"statusName": "승인대기중", "comment": "", "createdAt": "2026-10-27T01:00:00"},
                     {"statusName": status, "comment": comment, "createdAt": "2026-10-27T02:00:00"}]}


def test_collect_keeps_full_comment_and_timeline():
    d = RR.collect_coupang(_Up(_hist()), "1")
    assert d["comment"] == _LONG.strip()[:RR.COMMENT_MAX] and len(d["comment"]) > 500     # 500자 자르기 없음
    assert len(d["timeline"]) == 2 and d["timeline"][-1]["status"] == "승인반려"
    assert d["status_raw"] == "승인반려"


def test_collect_error_is_verbatim():
    assert RR.collect_coupang(_Up({"error": "HTTP 400 DEFAULT"}), "1")["error"] == "HTTP 400 DEFAULT"


def test_naver_has_no_reason_api_and_says_so():
    d = RR.collect_naver({"status_raw": "REJECTION", "link": "https://x"})
    assert d["comment"] == "" and "판매자센터" in d["api_reason"]


def _detail(comment, market="coupang:gogane"):
    return {"comment": comment, "status_raw": "승인반려", "sid": "99", "sig": RR._sig(market, comment, "승인반려")}


def test_route_image_spec_resubmits_images(monkeypatch):
    from src.services import coupang_image_check as CIC
    from src.services import image_translate_store as ITS
    from src.seller_console import collect_history_store as store
    monkeypatch.setattr(CIC, "auto_rep_pick", lambda ex, **k: {"changed": True, "picked_idx": 1})
    monkeypatch.setattr(ITS, "effective_images", lambda ex, **k: ["https://a/1.jpg", "https://a/2.jpg"])
    monkeypatch.setattr(store, "merge_extra", lambda *a, **k: True)
    up = _Up(_hist())
    r = RR.route("i1", "u1", {"images": ["x"]}, "coupang:gogane", _detail(_LONG), up=up)
    assert r["kind"] == "image_spec" and r["applied"] is True and r["action"] == "resubmit_images"
    assert [c[0] for c in up.calls] == ["modify", "approve"]
    assert up.calls[0][1]["items"][0]["images"][0]["vendorPath"] == "https://a/1.jpg"   # 조회 원문 위에 사진만


def test_route_saved_pending_requests_approval():
    up = _Up(_hist())
    r = RR.route("i1", "u1", {}, "coupang:gogane", _detail("임시저장"), up=up)
    assert r["kind"] == "saved_pending" and r["applied"] and up.calls == [("approve", "99")]


def test_route_trademark_and_unknown_go_to_owner():
    up = _Up(_hist())
    r = RR.route("i1", "u1", {}, "coupang:gogane", _detail("상표권 침해 소지"), up=up)
    assert r["kind"] == "trademark" and r["needs_owner"] and not up.calls
    r2 = RR.route("i1", "u1", {}, "coupang:gogane", _detail("알 수 없는 새 문구"), up=up)
    assert r2["kind"] == "unknown" and r2["needs_owner"] and r2["comment"] == "알 수 없는 새 문구"


def test_route_option_kinds_requeue_prevalidate():
    got = []
    r = RR.route("i1", "u1", {}, "coupang:gogane", _detail("유효하지 않은 구매 옵션 값 혹은 단위 입니다."), up=_Up(_hist()),
                 enqueue=lambda row: got.append(row) or True)
    assert r["kind"] == "option_unit" and r["action"] == "prevalidate_queued" and got[0]["op"] == "prevalidate"


def test_same_sig_rejection_stops_after_one_auto_action():
    d = _detail("임시저장")
    ex = {"review_detail": {"coupang:gogane": {"routed": {"sig": d["sig"], "action": "request_approval", "at": "2026-10-27T03:00"}}}}
    up = _Up(_hist())
    r = RR.route("i1", "u1", ex, "coupang:gogane", d, up=up)
    assert r["needs_owner"] and not r["applied"] and not up.calls and "다시 반려" in r["reason"]


def test_run_saves_review_detail(monkeypatch):
    from src.services import ocr_compare_diag as D
    from src.services import coupang_detail_refresh as CDR
    from src.seller_console import collect_history_store as store
    item = {"id": "i1", "title": "t", "extra_json": json.dumps({"uploaded": [{"market": "coupang:gogane", "account": "gogane", "product_id": "99"}]})}
    monkeypatch.setattr(D, "_item", lambda iid: (item, "u1"))
    saved = {}

    def _merge(iid, apply, seller_ids=None):
        fresh = json.loads(item["extra_json"]); apply(fresh); saved.update(fresh); return True
    monkeypatch.setattr(store, "merge_extra", _merge)
    up = _Up(_hist("임시저장"))
    r = RR.run("i1", "coupang:gogane", make_up=lambda acc: up)
    assert r["ok"] and r["applied"] and r["kind"] == "saved_pending" and r["saved"]
    rd = saved["review_detail"]["coupang:gogane"]
    assert rd["comment"] == "임시저장" and rd["routed"]["action"] == "request_approval" and len(rd["timeline"]) == 2


def test_op_registered_and_review_status_requeues_on_reject():
    assert "reject_route" in OO.OPS
    src = open("src/services/oneshot_ops.py", encoding="utf-8").read()
    assert '"op": "reject_route"' in src and 'row.get("state") == "rejected"' in src
    assert OO._row_key({"op": "reject_route", "item_id": "i", "market": "coupang:gogane"}) != \
        OO._row_key({"op": "reject_route", "item_id": "i", "market": "coupang:woojoo"})
