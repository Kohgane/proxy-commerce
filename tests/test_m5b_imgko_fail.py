"""M5 후속(오너 2026-10-07, 실사용 1호) — 이미지 번역 실패를 숨기지 않는다 + 쿠팡 노출 미리보기 실패 사유.

실측: 텐센트 계정 연체 정지 → 상세 사진 중국어 번역 0건, 카드엔 아무 표시 없음.
사유 코드: tencent_auth / tencent_balance / tencent_qps / breaker_open / cap_reached (+ tencent_image · tencent_other).
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    monkeypatch.setenv("FAMILY_EMAILS", "mom@example.com")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)


@pytest.mark.parametrize("cls,code,msg,want", [
    ("TencentCloudSDKException", "AuthFailure.SecretIdNotFound", "secret id not found", "tencent_auth"),
    ("TencentCloudSDKException", "FailedOperation.ServiceIsolate", "账号欠费", "tencent_balance"),
    ("TencentCloudSDKException", "ResourceUnavailable.InArrears", "The account is in Arrears", "tencent_balance"),
    ("TencentCloudSDKException", "FailedOperation.NoFreeAmount", "", "tencent_balance"),
    ("TencentCloudSDKException", "LimitExceeded", "超过了每秒频率上限", "tencent_qps"),
    ("RateQueueTooLong", "", "줄이 깁니다", "tencent_qps"),
    ("TencentCloudSDKException", "FailedOperation.DecodeErr", "", "tencent_image"),
    ("FetchFailed", "", "이미지를 내려받지 못했습니다(HTTPError · HTTP 403)", "tencent_image"),
    ("TencentCloudSDKException", "InternalError", "boom", "tencent_other"),
])
def test_failure_code_from_raw_strings(cls, code, msg, want):
    from src.services import image_translate_tencent as tc
    assert tc.failure_code(cls, code, msg) == want
    assert want in tc.FAILURE_LABELS


def test_recent_calls_ring_keeps_last_10():
    from src.services import image_translate_tencent as tc
    for i in range(12):
        tc._remember({"ok": i % 2 == 0, "error_class": "" if i % 2 == 0 else "TencentCloudSDKException",
                      "error_code": "" if i % 2 == 0 else "FailedOperation.ServiceIsolate",
                      "error_message": f"m{i}", "ms": i})
    rows = tc.recent_calls()
    assert len(rows) == 10 and rows[0]["message"] == "m11" and rows[0]["kind"] == "tencent_balance"
    assert rows[1]["ok"] is True and rows[1]["kind"] == ""
    tc._remember({"ok": False, "error_class": "NotConfigured"})                 # 미연결은 호출이 아니다
    assert tc.recent_calls()[0]["message"] == "m11"


def _item(seller="m5b-img", extra=None):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "슬립 원피스", "images": ["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/b.jpg"],
          "detail_images": ["https://img.alicdn.com/d1.jpg"], "price": "328", "currency": "CNY"}
    ex.update(extra or {})
    return S.append(source="share_text", url="https://item.taobao.com/item.htm?id=1", seller_id=seller,
                    title="슬립 원피스", price="328", currency="CNY", extra=ex)


FAILED = {"detail_images_ko": [{"idx": 0, "kind": "detail", "status": "failed", "at": "2026-10-07T01:39:00Z",
                                "error_class": "TencentCloudSDKException", "error_code": "FailedOperation.ServiceIsolate",
                                "error_message": "账号欠费，服务已被隔离"}]}


def test_item_failure_reads_page_failure_then_breaker_then_cap(monkeypatch):
    from src.services import image_translate_auto as A
    from src.db import image_translate_queue_pg as q
    monkeypatch.setattr(A, "kick", lambda: None)                               # 실제 워커는 돌리지 않는다
    f = A.item_failure("i1", FAILED)
    assert f["code"] == "tencent_balance" and "ServiceIsolate" in f["raw"] and f["failed"] == 1
    assert A.item_failure("i1", {}) == {}                                      # 실패도 대기도 없으면 배지 없음
    q.enqueue("u", "i2", [("detail", 0)])
    A.pause("번역 실패 20장 누적 — 원인을 확인한 뒤 「재개」")
    f = A.item_failure("i2", {})
    assert f["code"] == "breaker_open" and "20장" in f["raw"]
    A.resume()
    monkeypatch.setattr(A, "daily_cap", lambda: 0)
    f = A.item_failure("i2", {})
    assert f["code"] == "cap_reached" and "오늘" in f["raw"]


def _client(**sess):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(sess)
    return c


def test_exposure_json_carries_badge_and_does_not_hold():
    iid = _item(extra=FAILED)
    d = _client(user_id="m5b-img").get(f"/seller/collect/{iid}/coupang-exposure").get_json()
    assert d["ok"] and d["imgko_fail"]["code"] == "tencent_balance" and "ServiceIsolate" in d["imgko_fail"]["raw"]
    assert all("a.jpg" in u or "b.jpg" in u for u in [s["url"] for s in d["strip"]])   # 원본 그대로 나감
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"title": "슬립 원피스", "price": "328", "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"], **FAILED}
    assert not [h for h in UploadDispatcher.readiness_holds(pd, "coupang") if "번역" in h.get("short", "") and "이미지" in h.get("short", "")]


def test_exposure_failure_reason_is_json_not_html(monkeypatch):
    import src.seller_console.views as V
    iid = _item()
    monkeypatch.setattr(V, "coupang_exposure_data", lambda item: (_ for _ in ()).throw(TimeoutError("OCR 15초 초과")))
    r = _client(user_id="m5b-img").get(f"/seller/collect/{iid}/coupang-exposure")
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] is False and "TimeoutError" in d["error"] and "OCR 15초 초과" in d["error"]


def test_retry_requeues_failed_pages_and_resume_is_shared_only(monkeypatch):
    from src.services import image_translate_auto as A
    from src.db import image_translate_queue_pg as q
    monkeypatch.setattr(A, "kick", lambda: None)
    monkeypatch.setattr(A, "enqueue_after_enrich", lambda *a, **k: 0)
    iid = _item(seller="m5b-img", extra=FAILED)
    q.enqueue("m5b-img", iid, [("detail", 0)])
    job = q.lease_next()
    q.finish(job["id"], "failed", "FailedOperation.ServiceIsolate")
    A.pause("번역 실패 20장 누적")
    d = _client(user_id="m5b-img", user_email="stranger@example.com").post(f"/seller/collect/{iid}/image-translate/retry").get_json()
    assert d["ok"] and d["requeued"] == 1 and d["paused"] and "관리자가 재개" in d["message"]
    assert q.counts(iid)["queued"] == 1 and A.pause_state().get("paused")
    q.finish(q.lease_next()["id"], "failed", "x")
    d = _client(user_id="m5b-img", user_email="mom@example.com").post(f"/seller/collect/{iid}/image-translate/retry").get_json()
    assert d["requeued"] == 1 and d["resumed"] and not A.pause_state().get("paused") and "다시 돌렸어요" in d["message"]


def test_card_template_shows_badge_and_retry():
    from pathlib import Path
    h = Path("src/seller_console/templates/_coupang_exposure.html").read_text(encoding="utf-8")
    for must in ("cpx-imgko-fail", "이미지 번역 실패: ", "cpx-imgko-retry", "/image-translate/retry", "불러오지 못했어요 — "):
        assert must in h, must


def test_diagnostics_lists_recent_tencent_calls():
    from src.services import image_translate_tencent as tc
    tc._remember({"ok": False, "error_class": "TencentCloudSDKException", "error_code": "FailedOperation.ServiceIsolate",
                  "error_message": "账号欠费", "ms": 120})
    h = _client(user_id="owner-diag", user_role="admin").get("/admin/diagnostics").get_data(as_text=True)
    assert 'data-role="tencent-recent"' in h and "FailedOperation.ServiceIsolate" in h and "tencent_balance" in h
    assert 'data-role="alicdn-probe"' in h and "ALICDN_PROBE=0" in h
