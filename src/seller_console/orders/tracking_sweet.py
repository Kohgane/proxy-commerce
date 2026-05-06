"""src/seller_console/orders/tracking_sweet.py — SweetTracker 운송장 자동 추적 (Phase 130).

.. deprecated:: Phase 133
   SweetTracker는 TrackingMore로 교체되었습니다.
   신규 코드는 tracking_trackingmore.py를 사용하세요.
   이 모듈은 백워드 호환성을 위해 유지됩니다.

SWEETTRACKER_API_KEY 활성 시 실 API 호출, 미설정 시 stub 반환.
ADAPTER_DRY_RUN=1 시 API 호출 차단.

SweetTracker API: https://info.sweettracker.co.kr/api/v1/trackingInfo
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_BASE_URL = "https://info.sweettracker.co.kr/api/v1"

# 택배사 코드 매핑 (스윗트래커 표준)
COURIER_CODE_MAP: dict = {
    "CJ대한통운": "04",
    "CJ": "04",
    "한진택배": "05",
    "한진": "05",
    "롯데택배": "08",
    "롯데": "08",
    "우체국": "01",
    "로젠택배": "06",
    "로젠": "06",
    "대신택배": "22",
    "경동택배": "23",
    "일양로지스": "18",
    "합동택배": "32",
    "천일택배": "24",
}


def _api_active() -> bool:
    return bool(os.getenv("SWEETTRACKER_API_KEY"))


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


def get_tracking_info(tracking_no: str, courier_code: str) -> dict:
    """운송장 추적 정보 조회.

    Args:
        tracking_no: 운송장 번호
        courier_code: 택배사 코드 (COURIER_CODE_MAP 참고)

    Returns:
        추적 결과 dict:
        {
          "tracking_no": str,
          "courier_code": str,
          "courier_name": str,
          "status": str,
          "events": [{"time": str, "location": str, "description": str}, ...],
          "is_delivered": bool,
          "stub": bool,
        }
    """
    if _dry_run():
        logger.info("ADAPTER_DRY_RUN=1 — SweetTracker 추적 차단: %s", tracking_no)
        return _stub_response(tracking_no, courier_code, reason="dry_run")

    if not _api_active():
        logger.debug("SWEETTRACKER_API_KEY 미설정 — stub 반환")
        return _stub_response(tracking_no, courier_code, reason="key_missing")

    api_key = os.getenv("SWEETTRACKER_API_KEY", "")
    try:
        import requests
        resp = requests.get(
            f"{_BASE_URL}/trackingInfo",
            params={"t_key": api_key, "t_code": courier_code, "t_invoice": tracking_no},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        events = [
            {
                "time": ev.get("time", ""),
                "location": ev.get("where", ""),
                "description": ev.get("kind", ""),
            }
            for ev in data.get("trackingDetails", [])
        ]
        return {
            "tracking_no": tracking_no,
            "courier_code": courier_code,
            "courier_name": data.get("companyName", ""),
            "status": data.get("lastStateDetail", "조회 중"),
            "events": events,
            "is_delivered": data.get("complete", False),
            "stub": False,
        }
    except Exception as exc:
        logger.warning("SweetTracker 추적 실패 (%s): %s", tracking_no, exc)
        return _stub_response(tracking_no, courier_code, reason=str(exc))


def get_courier_code(name: str) -> str:
    """택배사 이름 → 스윗트래커 코드."""
    return COURIER_CODE_MAP.get(name, "00")


def _stub_response(tracking_no: str, courier_code: str, reason: str = "") -> dict:
    """stub 응답 반환."""
    reverse_map = {v: k for k, v in COURIER_CODE_MAP.items()}
    courier_name = reverse_map.get(courier_code, "알 수 없음")
    return {
        "tracking_no": tracking_no,
        "courier_code": courier_code,
        "courier_name": courier_name,
        "status": "추적 미지원 (stub)",
        "events": [],
        "is_delivered": False,
        "stub": True,
        "reason": reason,
    }
