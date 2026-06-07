"""src/seller_console/orders/tracking.py — 운송장 추적 stub (Phase 129)."""
from __future__ import annotations

from .courier_catalog import get_courier_catalog, get_sweet_courier_map, lookup_sweet_code

COURIER_MAP = get_sweet_courier_map()
COURIER_NAME_MAP = {
    row["sweet_code"]: row["name"]
    for row in get_courier_catalog(include_dynamic=False)
    if row.get("sweet_code")
}


def get_courier_code(name: str) -> str:
    """택배사 이름 → 코드."""
    return lookup_sweet_code(name)


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
