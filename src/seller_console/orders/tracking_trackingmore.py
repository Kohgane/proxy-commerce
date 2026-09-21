"""src/seller_console/orders/tracking_trackingmore.py — TrackingMore v4 운송장 추적 (Phase 133).

SweetTracker 대체.
API 문서: https://api.trackingmore.com/v4
Header: Tracking-Api-Key: {TRACKINGMORE_API_KEY}
- 키 미설정 시 stub/noop
- ADAPTER_DRY_RUN=1 시 외부 호출 차단
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from .courier_catalog import get_trackingmore_courier_map, lookup_trackingmore_code

logger = logging.getLogger(__name__)

# 한국 택배사 코드 매핑 (TrackingMore 코드)
KOREA_COURIERS: dict = get_trackingmore_courier_map()


class TrackingMoreClient:
    """TrackingMore v4 API 클라이언트."""

    def __init__(self) -> None:
        self.api_key = os.getenv("TRACKINGMORE_API_KEY")
        self.active = bool(self.api_key)
        self.base = "https://api.trackingmore.com/v4"

    def _headers(self) -> dict:
        return {
            "Tracking-Api-Key": self.api_key or "",
            "Content-Type": "application/json",
        }

    def detect_courier(self, tracking_no: str) -> list:
        """택배사 자동 감지 — 코드 목록만(빈 목록 = 실패/미활성).

        **사유가 필요하면 `detect_detail`을 쓴다** — 이건 옛 호출부를 위한 얇은 껍데기다.
        """
        return self.detect_detail(tracking_no).get("codes") or []

    def detect_detail(self, tracking_no: str) -> dict:
        """택배사 자동 감지 — `{codes, raw, http_status, error}` (F44-p).

        ★ `detect_courier`는 실패를 **빈 목록**으로만 말했다. 빈 목록은
        「이 번호로는 못 찾겠다」와 「키가 없다」와 「429다」를 **같은 값**으로 뭉갠다.
        판별 프로브는 그 셋을 갈라 봐야 하므로 **응답 원문**까지 들고 나온다(F41 규율).

        본문은 마스킹 후 300자 — 공급사가 요청을 되울릴 수 있다.
        """
        if not self.active:
            return {"codes": [], "raw": "", "http_status": None,
                    "error": "TRACKINGMORE_API_KEY가 설정되지 않았습니다"}
        try:
            r = requests.post(
                f"{self.base}/couriers/detect",
                json={"tracking_number": tracking_no},
                headers=self._headers(),
                timeout=10,
            )
        except Exception as exc:
            logger.warning("TrackingMore 택배사 감지 실패 (%s): %s", tracking_no, exc)
            return {"codes": [], "raw": "", "http_status": None,
                    "error": f"호출 오류: {type(exc).__name__}"}

        from src.utils.secret_mask import mask_text
        body = mask_text(getattr(r, "text", "") or "", secrets=(self.api_key or "",))
        if r.status_code >= 400:
            logger.warning("TrackingMore 감지 HTTP %s: %s", r.status_code, body[:2000])
            return {"codes": [], "raw": body[:300] or "본문을 주지 않았습니다(빈 응답)",
                    "http_status": r.status_code,
                    "error": f"공급사가 거부했습니다 (HTTP {r.status_code})"}
        try:
            data = r.json().get("data") or []
        except Exception as exc:
            return {"codes": [], "raw": body[:300], "http_status": r.status_code,
                    "error": f"응답을 해석하지 못했습니다: {type(exc).__name__}"}
        codes = [str(c.get("courier_code") or "") for c in data if c.get("courier_code")]
        return {"codes": codes, "raw": body[:300], "http_status": r.status_code,
                "error": "" if codes else "후보가 없습니다(공급사가 빈 목록을 냈다)"}

    def register(self, tracking_no: str, courier_code: str, order_id: Optional[str] = None) -> dict:
        """운송장 등록 → 추적 시작.

        Returns:
            API 응답 또는 stub dict
        """
        if not self.active:
            return {"status": "stub", "reason": "TRACKINGMORE_API_KEY 미설정"}
        if os.getenv("ADAPTER_DRY_RUN") == "1":
            logger.info("ADAPTER_DRY_RUN=1 — TrackingMore 운송장 등록 차단: %s", tracking_no)
            return {"_dry_run": True, "tracking_number": tracking_no}

        payload = [
            {
                "tracking_number": tracking_no,
                "courier_code": courier_code,
                "order_number": order_id,
            }
        ]
        try:
            r = requests.post(
                f"{self.base}/trackings/create",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            logger.warning("TrackingMore 운송장 등록 실패 (%s): %s", tracking_no, exc)
            return {"status": "error", "reason": "운송장 등록 중 오류가 발생했습니다."}

    def get_status(self, tracking_no: str, courier_code: str) -> dict:
        """현재 배송 상태 조회.

        Returns:
            {
              "status": "pending"|"transit"|"pickup"|"delivered"|"undelivered"|"exception"|"expired"|"stub",
              "checkpoints": [...],
              "last_updated": "...",
              "is_delivered": bool,
            }
        """
        if not self.active:
            return {"status": "stub", "stage": "unknown", "is_delivered": False}
        try:
            r = requests.get(
                f"{self.base}/trackings/get",
                params={"tracking_numbers": tracking_no, "courier_code": courier_code},
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            if not data:
                return {"status": "not_found", "is_delivered": False}
            item = data[0]
            delivery_status = item.get("delivery_status", "pending")
            return {
                "status": delivery_status,
                "checkpoints": item.get("origin_info", {}).get("trackinfo", []),
                "last_updated": item.get("latest_event_time"),
                "is_delivered": delivery_status == "delivered",
            }
        except Exception as exc:
            logger.warning("TrackingMore 상태 조회 실패 (%s): %s", tracking_no, exc)
            return {"status": "error", "is_delivered": False, "reason": "상태 조회 중 오류가 발생했습니다."}

    def health_check(self) -> dict:
        """API 키 유효성 ping.

        Returns:
            {"status": "ok", "couriers": N} 또는 {"status": "missing"|"fail", ...}
        """
        if not self.active:
            return {"status": "missing", "hint": "TRACKINGMORE_API_KEY 환경변수 등록 필요"}
        try:
            r = requests.get(
                f"{self.base}/couriers/all",
                headers=self._headers(),
                timeout=5,
            )
            if r.status_code == 200:
                return {"status": "ok", "couriers": len(r.json().get("data", []))}
            return {"status": "fail", "code": r.status_code}
        except Exception as exc:
            logger.warning("TrackingMore 헬스 체크 실패: %s", exc)
            return {"status": "fail", "error": "TrackingMore 헬스 체크 오류"}


def get_courier_code(name: str) -> str:
    """택배사 이름 → TrackingMore 코드."""
    return lookup_trackingmore_code(name)
