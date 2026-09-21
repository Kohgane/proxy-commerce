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
    """택배사 이름 → 코드. **모르면 빈 문자열**(F45 — 예전엔 조용히 `"00"`)."""
    return lookup_sweet_code(name)


def track(courier_code: str, tracking_no: str) -> dict:
    """운송장 추적. 현재 stub — SWEET_TRACKER_API_KEY 활성 시 실 추적."""
    import os
    if os.getenv("SWEET_TRACKER_API_KEY"):
        # 미래 실 추적 구현 예정
        pass
    # F45: 코드가 비어 있으면 **택배사를 못 찾은 것**이다 — 「알 수 없음」이라는
    #   이름으로 얼버무리지 않고, 그 사실을 사유로 말한다.
    code = str(courier_code or "")
    if not code:
        return {
            "courier_code": "",
            "courier_name": "",
            "tracking_no": tracking_no,
            "status": "택배사 미지원",
            "detail": "카탈로그에 없는 택배사입니다 — 목록에서 택배사를 골라 주세요.",
            "events": [],
        }
    return {
        "courier_code": code,
        "courier_name": COURIER_NAME_MAP.get(code, "알 수 없음"),
        "tracking_no": tracking_no,
        "status": "추적 미지원",
        "detail": "SWEET_TRACKER_API_KEY 등록 시 실시간 추적 가능",
        "events": [],
    }
