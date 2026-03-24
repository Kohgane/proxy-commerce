"""src/crm/customer_profile.py — 고객 프로필 관리.

Google Sheets 기반 고객 데이터 저장 및 업데이트.

환경변수:
  CRM_ENABLED       — CRM 활성화 여부 (기본 "0")
  CRM_SHEET_NAME    — 고객 워크시트명 (기본 "customers")
  GOOGLE_SHEET_ID   — Google Sheets ID
"""

import datetime
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("CRM_ENABLED", "0") == "1"
_SHEET_NAME = os.getenv("CRM_SHEET_NAME", "customers")
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

_HEADERS = [
    "email", "name", "total_orders", "total_spent_krw",
    "first_order_date", "last_order_date", "country",
    "segment", "tags", "updated_at",
]


class CustomerProfileManager:
    """고객 프로필 관리자."""

    def __init__(self, sheet_id: str = "", sheet_name: str = ""):
        self._sheet_id = sheet_id or _SHEET_ID
        self._sheet_name = sheet_name or _SHEET_NAME

    def is_enabled(self) -> bool:
        """CRM 기능 활성화 여부를 반환한다."""
        return os.getenv("CRM_ENABLED", "0") == "1"

    def get_profile(self, email: str) -> Optional[Dict[str, Any]]:
        """고객 이메일로 프로필을 조회한다.

        Args:
            email: 고객 이메일.

        Returns:
            고객 프로필 딕셔너리 또는 None.
        """
        customers = self._load()
        for c in customers:
            if str(c.get("email", "")).lower() == email.lower():
                return c
        return None

    def get_all_customers(
        self,
        segment: Optional[str] = None,
        country: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """고객 목록을 반환한다.

        Args:
            segment: 세그먼트 필터.
            country: 국가 필터.
        """
        customers = self._load()
        if segment:
            customers = [c for c in customers if c.get("segment", "") == segment]
        if country:
            customers = [
                c for c in customers
                if str(c.get("country", "")).upper() == country.upper()
            ]
        return customers

    def upsert_from_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """주문 데이터로 고객 프로필을 생성하거나 업데이트한다.

        Args:
            order_data: customer_email, customer_name, sell_price_krw,
                        order_date, country 필드를 포함한 딕셔너리.

        Returns:
            업데이트된 고객 프로필.
        """
        email = str(order_data.get("customer_email", "")).strip().lower()
        if not email:
            raise ValueError("customer_email is required")

        now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        order_date = str(order_data.get("order_date", now))
        order_total = float(order_data.get("sell_price_krw", 0) or 0)

        existing = self.get_profile(email)
        if existing:
            updated = dict(existing)
            updated["total_orders"] = int(existing.get("total_orders", 0) or 0) + 1
            updated["total_spent_krw"] = (
                float(existing.get("total_spent_krw", 0) or 0) + order_total
            )
            updated["last_order_date"] = order_date
            if order_data.get("customer_name"):
                updated["name"] = str(order_data["customer_name"])
            if order_data.get("country"):
                updated["country"] = str(order_data["country"])
            updated["updated_at"] = now
            self._update_profile(updated)
            return updated
        else:
            profile = {
                "email": email,
                "name": str(order_data.get("customer_name", "")),
                "total_orders": 1,
                "total_spent_krw": order_total,
                "first_order_date": order_date,
                "last_order_date": order_date,
                "country": str(order_data.get("country", "")),
                "segment": "NEW",
                "tags": "",
                "updated_at": now,
            }
            self._save_profile(profile)
            return profile

    def update_segment(self, email: str, segment: str) -> bool:
        """고객 세그먼트를 업데이트한다.

        Args:
            email: 고객 이메일.
            segment: 새 세그먼트.

        Returns:
            업데이트 성공 여부.
        """
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._sheet_name)
            records = ws.get_all_records()
            for idx, rec in enumerate(records, start=2):
                if str(rec.get("email", "")).lower() == email.lower():
                    seg_col = _HEADERS.index("segment") + 1
                    ws.update_cell(idx, seg_col, segment)
                    logger.info("세그먼트 업데이트: email=%s segment=%s", email, segment)
                    return True
        except Exception as exc:
            logger.warning("세그먼트 업데이트 실패: %s", exc)
        return False

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _load(self) -> List[Dict[str, Any]]:
        """Google Sheets에서 고객 목록을 로드한다."""
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._sheet_name)
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("고객 데이터 로드 실패: %s", exc)
            return []

    def _save_profile(self, profile: Dict[str, Any]) -> None:
        """새 고객 프로필을 Google Sheets에 저장한다."""
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._sheet_name)
            existing = ws.get_all_values()
            if not existing:
                ws.append_row(_HEADERS)
            ws.append_row([profile.get(h, "") for h in _HEADERS])
            logger.info("고객 프로필 저장: email=%s", profile.get("email"))
        except Exception as exc:
            logger.warning("고객 프로필 저장 실패: %s", exc)

    def _update_profile(self, profile: Dict[str, Any]) -> None:
        """기존 고객 프로필을 Google Sheets에서 업데이트한다."""
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._sheet_name)
            records = ws.get_all_records()
            email = str(profile.get("email", "")).lower()
            for idx, rec in enumerate(records, start=2):
                if str(rec.get("email", "")).lower() == email:
                    for col_idx, h in enumerate(_HEADERS, start=1):
                        ws.update_cell(idx, col_idx, profile.get(h, ""))
                    logger.info("고객 프로필 업데이트: email=%s", email)
                    return
        except Exception as exc:
            logger.warning("고객 프로필 업데이트 실패: %s", exc)
