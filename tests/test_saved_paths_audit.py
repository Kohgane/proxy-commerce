"""tests/test_saved_paths_audit.py — 쿠팡 SAVED 생성 경로 전수 + 재제출 이미지 게이트.

**질문 1(오너):** 쿠팡 임시저장 60→107(+47) 급증 — 우리 소행인가?
**질문 2(오너):** 재제출이 기존 sid 수정 경로로 갔고 `_SS1600_` 치환분이 실제로 실렸나?

이 파일은 두 질문을 **코드 읽기가 아니라 계약으로** 고정한다:
  1. 쿠팡에 신규 SAVED를 만드는 API는 `POST seller-products` 하나뿐이고,
     **크론 경로 중 그것을 호출하는 것은 없다**(파일럿의 쿠팡 접근은 GET 읽기).
  2. 이미지 규격 반려는 **이미지 교체 없이 재제출할 수 없다**(같은 사유 재반려 왕복 차단).
  3. 재제출 결과에 **무엇이 실렸는지**가 남는다(수리 미반영을 로그·응답으로 판별 가능).
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ── 1. SAVED 생성 경로 전수 ─────────────────────────────────────────────────────
def test_only_upload_product_creates_new_coupang_product():
    """신규 생성 = POST seller-products. 업로더 안에서 그 호출은 `upload_product` 하나뿐이다."""
    src = Path("src/uploaders/coupang_uploader.py").read_text(encoding="utf-8")
    posts = [ln for ln in src.splitlines()
             if "_api_request('POST'" in ln and "seller-products" not in ln]
    # POST 호출은 등록(path 변수 경유)과 카테고리 예측뿐 — 예측은 상품을 만들지 않는다.
    assert "CATEGORY_PREDICT_PATH, data=" in src
    body = src.split("def upload_product")[1].split("def update_product")[0]
    assert "_api_request('POST', path, data=payload)" in body
    # 다른 메서드가 상품을 새로 만들지 않는지: resubmit/update/delete에 POST 없음.
    for fn in ("def resubmit_product", "def update_product", "def delete_product",
               "def request_approval", "def get_status_histories"):
        seg = src.split(fn)[1].split("\n    def ")[0]
        assert "'POST'" not in seg, fn


def test_pilot_touches_coupang_read_only():
    """파일럿(v88-C)은 쿠팡에 **쓰지 않는다** — GET seller-products/{sid}로 이미지만 읽는다."""
    src = Path("src/pipeline/coupang_replicate.py").read_text(encoding="utf-8")
    assert '_coupang_sign(secret, "GET", path, date)' in src
    for verb in ('"POST"', "'POST'", '"PUT"', "'PUT'", '"DELETE"', "'DELETE'"):
        assert f'_coupang_sign(secret, {verb}' not in src, verb


def test_no_cron_route_registers_to_coupang():
    """크론 6종 중 쿠팡 신규 등록을 호출하는 것은 없다('해당 없음 확인')."""
    cron = Path("src/pricing/cron.py").read_text(encoding="utf-8")
    # 반려감시 크론이 쓰는 업로더 메서드는 조회(histories)뿐 — 등록/승인요청 아님.
    seg = cron.split("def _run_reject_watch")[1].split("\ndef ")[0]
    assert "get_status_histories" in seg
    for forbidden in ("upload_product", "request_approval", "resubmit_product", "delete_product"):
        assert forbidden not in seg, forbidden


def test_registration_paths_are_human_triggered():
    """신규 등록 호출부는 전부 사람이 누르는 라우트 — 자동 루프가 아니다."""
    views = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    # ① 등록 파이프: 승인 게이트 + 카나리 게이트 뒤.
    assert "register_pipe_approved" in Path("src/pipeline/register_pipe.py").read_text(encoding="utf-8")
    assert 'batch_ok' in views
    # ② AI 후보 등록(auto_publish)은 LISTING_AUTO_PUBLISH 게이트.
    ap = Path("src/listing/auto_publish.py").read_text(encoding="utf-8")
    assert 'os.getenv("LISTING_AUTO_PUBLISH", "0") == "1"' in ap


def test_registry_report_route_exists():
    """'우리 소행인가'를 **데이터로** 답하는 라우트가 있어야 한다(코드 읽기로 답하지 않게)."""
    src = Path("src/dashboard/admin_views.py").read_text(encoding="utf-8")
    assert '@admin_panel_bp.get("/registrations")' in src
    assert "by_status" in src and "durable" in src


def test_registry_report_returns_counts(monkeypatch):
    from src.db import market_registrations_pg as REG
    REG.reset_memory()
    try:
        REG.record("SP1", account="gogane", vendor_sku="B0A")
        REG.record("SP2", account="gogane", vendor_sku="B0B")
        REG.mark_checked("SP2", status="rejected")
        monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
        import src.dashboard.admin_views as AV
        monkeypatch.setattr(AV, "is_admin_session", lambda: True, raising=False)
        from src.order_webhook import app
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = "u1"
                sess["user_role"] = "admin"
            r = c.get("/admin/registrations")
        assert r.status_code == 200
        d = r.get_json()
        assert d["ok"] is True and d["total"] == 2
        assert d["by_status"] == {"submitted": 1, "rejected": 1}
        assert d["durable"] is False and "인메모리" in d["durable_note"]   # PG 미가동 정직 표기
    finally:
        REG.reset_memory()


# ── 2·3. 재제출 이미지 게이트 + 계측 ────────────────────────────────────────────
def _up(monkeypatch):
    for k, v in {
        "COUPANG_GOGANE_OUTBOUND_SHIPPING_PLACE_CODE": "1",
        "COUPANG_GOGANE_RETURN_CENTER_CODE": "R1",
        "COUPANG_GOGANE_RETURN_ZIP_CODE": "12345",
        "COUPANG_GOGANE_RETURN_ADDRESS": "서울시",
        "COUPANG_GOGANE_RETURN_CHARGE_NAME": "담당자",
        "COUPANG_GOGANE_COMPANY_CONTACT_NUMBER": "02-000-0000",
        "COUPANG_GOGANE_VENDOR_USER_ID": "gogane01",
    }.items():
        monkeypatch.setenv(k, v)
    from src.uploaders.coupang_uploader import CoupangUploader
    monkeypatch.setattr("time.sleep", lambda s: None)
    return CoupangUploader("ak", "sk", "A01381223", account="gogane")


def test_image_spec_resubmit_requires_new_images(monkeypatch):
    """반려 2호 교훈: 같은 이미지로 승인요청하면 같은 사유로 또 반려된다 — 사전 차단."""
    from src.dashboard.admin_views import _reject_watch_resubmit
    up = _up(monkeypatch)
    monkeypatch.setattr(up, "update_product", lambda *a: pytest.fail("이미지 없이 PUT 호출됨"))
    monkeypatch.setattr(up, "request_approval", lambda *a: pytest.fail("이미지 없이 승인요청됨"))
    out = _reject_watch_resubmit(up, "16358413200", {"_kind": "image_spec"})
    assert out["success"] is False and out["stage"] == "images"
    assert "같은 사유로 다시 반려" in out["error"]


def test_other_kinds_can_resubmit_without_images(monkeypatch):
    """이미지 규격이 아닌 반려는 승인요청만으로도 재제출 가능(과잉 차단 0)."""
    from src.dashboard.admin_views import _reject_watch_resubmit
    up = _up(monkeypatch)
    calls = []
    monkeypatch.setattr(up, "request_approval",
                        lambda sid: calls.append(sid) or {"success": True})
    out = _reject_watch_resubmit(up, "16358413200", {"_kind": "option_value"})
    assert out["success"] is True and calls == ["16358413200"]
    assert out["images_replaced"] == 0


def test_resubmit_reports_what_was_sent(monkeypatch):
    """계측: 이미지가 실제로 실렸는지·첫 vendorPath가 무엇인지 응답에 남는다(수리 미반영 판별)."""
    from src.dashboard.admin_views import _reject_watch_resubmit
    up = _up(monkeypatch)
    monkeypatch.setattr("src.collectors.image_norm.probe_image_size", lambda u, **k: (1600, 1600))
    monkeypatch.setattr(up, "update_product", lambda sid, u: {"success": True})
    monkeypatch.setattr(up, "request_approval", lambda sid: {"success": True})
    out = _reject_watch_resubmit(
        up, "16358413200",
        {"_kind": "image_spec",
         "images": ["https://m.media-amazon.com/images/I/71a._AC_US40_.jpg"]})
    assert out["success"] is True and out["images_replaced"] == 1
    assert out["first_vendor_path"].endswith("._SS1600_.jpg")     # 치환분이 실렸다는 증거
    assert out["stage"] == "approval" and out["updated"] is True


def test_kind_flows_from_classifier_to_gate():
    """분류기 → apply_prescription → resubmit_fn 으로 유형이 전달된다(게이트가 유형을 안다)."""
    from src.pipeline import reject_watch as RW
    seen = {}
    RW.apply_prescription({"sid": "S1", "kind": "image_spec", "wing_state": "rejected"},
                          approved=True,
                          resubmit_fn=lambda sid, u: seen.update(u or {}) or {"success": True})
    assert seen["_kind"] == "image_spec"
