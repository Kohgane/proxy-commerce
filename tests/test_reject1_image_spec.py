"""tests/test_reject1_image_spec.py — 승인반려 1호: 이미지 규격(유형①) 정본 처방.

쿠팡 반려 원문(2026-08-25, Fellow Stagg 16358413200):
  "[B0GS4698H2]: 대표이미지는 최대 10M, 최소 500*500, 최대 5000*5000. 기타이미지(DETAIL) 동일."

실측 근원: 사이즈 토큰 치환 규칙이 **확장(JS)에만 있고 서버에 없었다** → 서버 수집 경로로 온
`._AC_US40_`(40px) 썸네일이 그대로 등록에 나갔다.

계약:
  1. 아마존 URL 사이즈 토큰 → `_SS1600_` 치환(정본·오너 지시). 치환 불가 형식은 원본 유지.
  2. px 게이트: 500 미만 제외 · 대표 전멸이면 등록 차단. **측정 불가는 제외하지 않는다**(정직).
  3. 재제출: 이미지 교체 PUT → PUT approvals. 규격 통과 0장이면 재제출 중단.
  4. P4 분류기가 이 반려 원문을 유형①로 분류하고 처방을 매핑한다.
"""
from __future__ import annotations

import pytest

from src.collectors.image_norm import (
    MIN_PX,
    normalize_image_url,
    normalize_image_urls,
    screen_images,
)

# 반려 1호 실 원문(전문 고정 — 회귀 시 이 문자열이 잡는다).
REJECT1_COMMENT = ("[B0GS4698H2]: 대표이미지는 최대 10M, 최소 500*500, 최대 5000*5000. "
                   "기타이미지(DETAIL) 동일.")


# ── 1. URL 정규화(정본: _SS1600_ 치환) ──────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    # 사이즈 토큰 치환 — 반려를 부른 그 형태들.
    ("https://m.media-amazon.com/images/I/71abc._AC_US40_.jpg",
     "https://m.media-amazon.com/images/I/71abc._SS1600_.jpg"),
    ("https://m.media-amazon.com/images/I/71abc._SL160_.jpg",
     "https://m.media-amazon.com/images/I/71abc._SS1600_.jpg"),
    ("https://m.media-amazon.com/images/I/71abc._AC_SX466_SY466_.jpg",
     "https://m.media-amazon.com/images/I/71abc._SS1600_.jpg"),
    # 토큰 없는 원본 → 대형본 토큰 삽입.
    ("https://m.media-amazon.com/images/I/71abc.jpg",
     "https://m.media-amazon.com/images/I/71abc._SS1600_.jpg"),
    # 쿼리스트링 제거(정본 — 쿠팡이 거부).
    ("https://m.media-amazon.com/images/I/71abc._AC_US40_.jpg?v=2",
     "https://m.media-amazon.com/images/I/71abc._SS1600_.jpg"),
])
def test_amazon_size_token_replaced_with_ss1600(raw, expected):
    assert normalize_image_url(raw) == expected


def test_amazon_de_uses_same_cdn_rule():
    """amazon.de도 같은 CDN 규칙(오너 지시) — 로케일 무관."""
    u = "https://images-eu.ssl-images-amazon.com/images/I/91xyz._AC_US40_.jpg"
    assert normalize_image_url(u).endswith("91xyz._SS1600_.jpg")


def test_non_amazon_url_left_alone():
    """남의 CDN 규칙은 추측하지 않는다 — 원본 유지(발명 0)."""
    u = "https://cdn.temu.com/goods/abc_120x120.jpg"
    assert normalize_image_url(u) == u
    # 쿼리스트링만 제거.
    assert normalize_image_url(u + "?x=1") == u


def test_normalize_list_dedups_after_replacement():
    """치환하면 같아지는 URL들은 1장으로 접힌다(썸네일+원본 중복 방지)."""
    out = normalize_image_urls([
        "https://m.media-amazon.com/images/I/71a._AC_US40_.jpg",
        "https://m.media-amazon.com/images/I/71a._SL160_.jpg",
        "https://m.media-amazon.com/images/I/71b.jpg",
        "",
    ])
    assert out == ["https://m.media-amazon.com/images/I/71a._SS1600_.jpg",
                   "https://m.media-amazon.com/images/I/71b._SS1600_.jpg"]


# ── 2. px 게이트 ────────────────────────────────────────────────────────────────
_A = "https://m.media-amazon.com/images/I/71a._SS1600_.jpg"
_B = "https://m.media-amazon.com/images/I/71b._SS1600_.jpg"
_SMALL = "https://m.media-amazon.com/images/I/71s._SS1600_.jpg"


def test_undersized_images_dropped():
    sizes = {_A: (1600, 1600), _SMALL: (40, 40)}
    out = screen_images([_A, _SMALL], probe_fn=lambda u: sizes.get(u))
    assert out["ok"] is True and out["images"] == [_A]
    assert out["dropped"][0]["size"] == "40x40" and f"{MIN_PX}px 미만" in out["dropped"][0]["reason"]


def test_oversized_images_dropped():
    out = screen_images([_A, _B], probe_fn=lambda u: (6000, 6000) if u == _B else (1600, 1600))
    assert out["images"] == [_A] and "5000px 초과" in out["dropped"][0]["reason"]


def test_all_undersized_blocks_registration():
    """대표이미지가 전멸하면 등록 차단 — 규격 미달로 카나리 태우지 않는다."""
    out = screen_images([_SMALL], probe_fn=lambda u: (40, 40))
    assert out["ok"] is False and out["images"] == []
    assert "등록 중단" in out["reason"] and "40x40" in out["reason"]


def test_unmeasurable_images_are_kept_not_dropped():
    """측정 불가는 '미달'이 아니다 — 확인 실패를 단정으로 바꾸지 않는다(정직)."""
    out = screen_images([_A], probe_fn=lambda u: None)
    assert out["ok"] is True and out["images"] == [_A]
    assert out["unknown"] == [_A] and out["dropped"] == []


def test_probe_exception_treated_as_unknown():
    def _boom(u):
        raise RuntimeError("네트워크 차단")
    out = screen_images([_A], probe_fn=_boom)
    assert out["ok"] is True and out["unknown"] == [_A]


def test_empty_images_is_honest_failure():
    out = screen_images([], probe_fn=lambda u: (1600, 1600))
    assert out["ok"] is False and "이미지 0장" in out["reason"]


# ── 업로더 배선 ────────────────────────────────────────────────────────────────
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
    return CoupangUploader("ak", "sk", "A01381223", account="gogane", overseas_purchased=True)


_PRODUCT = {"title": "Fellow Stagg 주전자", "price": 894000, "category_id": 1001,
            "sku": "B0GS4698H2", "brand": "Fellow", "origin": "미국",
            "images": ["https://m.media-amazon.com/images/I/71a._AC_US40_.jpg"]}


def test_payload_images_are_normalized(monkeypatch):
    """페이로드 vendorPath가 대형본 — 반려를 부른 40px URL이 그대로 나가지 않는다."""
    up = _up(monkeypatch)
    imgs = up._build_product_payload(_PRODUCT)["items"][0]["images"]
    assert imgs[0]["vendorPath"] == "https://m.media-amazon.com/images/I/71a._SS1600_.jpg"
    assert imgs[0]["imageType"] == "REPRESENTATION"


def test_upload_blocked_when_all_images_undersized(monkeypatch):
    up = _up(monkeypatch)
    monkeypatch.setattr("src.collectors.image_norm.probe_image_size", lambda u, **k: (40, 40))
    monkeypatch.setattr(up, "_api_request",
                        lambda *a, **k: pytest.fail("규격 미달인데 API 호출됨"))
    res = up.upload_product(dict(_PRODUCT))
    assert res["success"] is False and res["held"] is True
    assert "이미지 규격 미달" in res["error"]


def test_upload_proceeds_when_images_ok(monkeypatch):
    """규격 통과면 다음 게이트로 — 과잉 차단 0."""
    up = _up(monkeypatch)
    monkeypatch.setattr("src.collectors.image_norm.probe_image_size", lambda u, **k: (1600, 1600))
    monkeypatch.setattr(up, "predict_category", lambda *a, **k: "")   # 다음 게이트에서 정직 중단
    res = up.upload_product({**_PRODUCT, "category_id": ""})           # 폴백 카테고리도 없음
    assert "카테고리 예측 실패" in res["error"]


def test_image_screen_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("COUPANG_IMAGE_SCREEN", "0")
    up = _up(monkeypatch)
    assert up.image_screen_enabled is False
    monkeypatch.setattr("src.collectors.image_norm.probe_image_size",
                        lambda u, **k: pytest.fail("게이트 껐는데 실측 호출됨"))
    monkeypatch.setattr(up, "predict_category", lambda *a, **k: "")
    out = up.upload_product({**_PRODUCT, "category_id": ""})
    assert "카테고리 예측 실패" in out["error"]                          # 이미지 게이트는 안 걸림


# ── 3. 이미지 교체 재제출 ───────────────────────────────────────────────────────
def test_rebuild_images_for_resubmit(monkeypatch):
    up = _up(monkeypatch)
    monkeypatch.setattr("src.collectors.image_norm.probe_image_size", lambda u, **k: (1600, 1600))
    out = up.rebuild_images_for_resubmit(["https://m.media-amazon.com/images/I/71a._AC_US40_.jpg"])
    assert out["ok"] is True
    assert out["images"][0]["vendorPath"].endswith("._SS1600_.jpg")


def test_rebuild_blocks_when_nothing_passes(monkeypatch):
    up = _up(monkeypatch)
    monkeypatch.setattr("src.collectors.image_norm.probe_image_size", lambda u, **k: (40, 40))
    out = up.rebuild_images_for_resubmit(["https://m.media-amazon.com/images/I/71s._AC_US40_.jpg"])
    assert out["ok"] is False and "등록 중단" in out["reason"]


def test_admin_resubmit_replaces_images_then_approves(monkeypatch):
    from src.dashboard.admin_views import _reject_watch_resubmit
    up = _up(monkeypatch)
    monkeypatch.setattr("src.collectors.image_norm.probe_image_size", lambda u, **k: (1600, 1600))
    order, sent = [], {}
    monkeypatch.setattr(up, "update_product",
                        lambda sid, u: (order.append("update"), sent.update(u))[0] or {"success": True})
    monkeypatch.setattr(up, "request_approval",
                        lambda sid: order.append("approval") or {"success": True})
    out = _reject_watch_resubmit(
        up, "16358413200",
        {"images": ["https://m.media-amazon.com/images/I/71a._AC_US40_.jpg"]})
    assert out["success"] is True and order == ["update", "approval"]     # 순서 정본
    assert sent["items"][0]["images"][0]["vendorPath"].endswith("._SS1600_.jpg")
    assert "images" not in sent                                          # 원본 키는 전송 안 함


def test_admin_resubmit_stops_when_images_undersized(monkeypatch):
    """미달 이미지로 재제출하면 같은 사유로 또 반려된다 — 여기서 멈춘다."""
    from src.dashboard.admin_views import _reject_watch_resubmit
    up = _up(monkeypatch)
    monkeypatch.setattr("src.collectors.image_norm.probe_image_size", lambda u, **k: (40, 40))
    monkeypatch.setattr(up, "update_product", lambda *a: pytest.fail("규격 미달인데 PUT 호출됨"))
    monkeypatch.setattr(up, "request_approval", lambda *a: pytest.fail("규격 미달인데 승인요청됨"))
    out = _reject_watch_resubmit(up, "16358413200",
                                 {"images": ["https://m.media-amazon.com/images/I/71s._AC_US40_.jpg"]})
    assert out["success"] is False and out["stage"] == "images"


# ── 4. P4 분류기 — 실 반려 원문 ─────────────────────────────────────────────────
def test_reject1_comment_classified_as_image_spec():
    from src.pipeline import reject_watch as RW
    cl = RW.classify_rejection(REJECT1_COMMENT, title="Fellow Stagg 주전자")
    assert cl["kind"] == "image_spec"
    assert cl["prescription"] == "reupload"
    assert "재제출" in cl["prescription_ko"]


def test_reject1_scan_end_to_end():
    from src.pipeline import reject_watch as RW
    hist = {"data": [{"statusName": "승인반려", "comment": REJECT1_COMMENT}]}
    scan = RW.scan_rejections([{"sid": "16358413200", "title": "Fellow Stagg", "account": "gogane"}],
                              history_fn=lambda sid, acct: hist)
    row = scan["rows"][0]
    assert row["kind"] == "image_spec" and row["wing_state"] == "rejected"
    assert row["actionable"] is True
    assert scan["by_kind"] == {"image_spec": 1} and scan["actionable"] == 1
