"""src/seller_console/orders/tracking.py — 운송장 추적 stub (Phase 129)."""
from __future__ import annotations

COURIER_MAP = {
    "CJ": "04",
    "한진": "05",
    "롯데": "08",
    "우체국": "01",
    "로젠": "06",
    "CJ대한통운": "04",
}
COURIER_NAME_MAP = {v: k for k, v in COURIER_MAP.items()}


def get_courier_code(name: str) -> str:
    """택배사 이름 → 코드."""
    return COURIER_MAP.get(name, "00")


def track(courier_code: str, tracking_no: str) -> dict:
    """운송장 추적. 현재 stub — SWEET_TRACKER_API_KEY 활성 시 실 추적."""
    import os
    if os.getenv("SWEET_TRACKER_API_KEY"):
        # 미래 실 추적 구현 예정
        pass
    return {
        "courier_code": courier_code,
        "courier_name": COURIER_NAME_MAP.get(courier_code, "알 수 없음"),
        "tracking_no": tracking_no,
        "status": "추적 미지원",
        "detail": "SWEET_TRACKER_API_KEY 등록 시 실시간 추적 가능",
        "events": [],
    }
