"""src/promotions/engine.py — 프로모션/할인 엔진.

Google Sheets 기반 프로모션 규칙 관리.
4가지 할인 타입 (PERCENTAGE, FIXED_AMOUNT, BUY_X_GET_Y, FREE_SHIPPING).

환경변수:
  PROMOTIONS_ENABLED  — 프로모션 활성화 여부 (기본 "0")
  PROMO_STACK_MODE    — 할인 중첩 모드 "best" 또는 "stack" (기본 "best")
  PROMO_SHEET_NAME    — 프로모션 워크시트명 (기본 "promotions")
  GOOGLE_SHEET_ID     — Google Sheets ID
"""

import datetime
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("PROMOTIONS_ENABLED", "0") == "1"
_STACK_MODE = os.getenv("PROMO_STACK_MODE", "best")
_SHEET_NAME = os.getenv("PROMO_SHEET_NAME", "promotions")
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# 프로모션 타입 상수
TYPE_PERCENTAGE = "PERCENTAGE"
TYPE_FIXED_AMOUNT = "FIXED_AMOUNT"
TYPE_BUY_X_GET_Y = "BUY_X_GET_Y"
TYPE_FREE_SHIPPING = "FREE_SHIPPING"

PROMO_TYPES = (TYPE_PERCENTAGE, TYPE_FIXED_AMOUNT, TYPE_BUY_X_GET_Y, TYPE_FREE_SHIPPING)

_HEADERS = [
    "promo_id", "name", "type", "value", "min_order_krw",
    "start_date", "end_date", "skus", "categories", "countries",
    "buy_x", "get_y", "active", "usage_count", "total_discount_krw",
]


class PromotionEngine:
    """프로모션/할인 엔진."""

    def __init__(self, sheet_id: str = "", sheet_name: str = ""):
        self._sheet_id = sheet_id or _SHEET_ID
        self._sheet_name = sheet_name or _SHEET_NAME

    def is_enabled(self) -> bool:
        """프로모션 기능 활성화 여부를 반환한다."""
        return os.getenv("PROMOTIONS_ENABLED", "0") == "1"

    # ------------------------------------------------------------------
    # 프로모션 CRUD
    # ------------------------------------------------------------------

    def create_promotion(self, promo_data: Dict[str, Any]) -> Dict[str, Any]:
        """새 프로모션을 생성한다.

        Args:
            promo_data: name, type, value, start_date, end_date 등 포함.

        Returns:
            생성된 프로모션 딕셔너리.

        Raises:
            ValueError: 필수 필드 누락 또는 유효하지 않은 타입.
        """
        self._validate_promo(promo_data)
        promo = {
            "promo_id": str(uuid.uuid4())[:8],
            "name": str(promo_data.get("name", "")),
            "type": str(promo_data.get("type", "")).upper(),
            "value": float(promo_data.get("value", 0)),
            "min_order_krw": float(promo_data.get("min_order_krw", 0)),
            "start_date": str(promo_data.get("start_date", "")),
            "end_date": str(promo_data.get("end_date", "")),
            "skus": str(promo_data.get("skus", "")),
            "categories": str(promo_data.get("categories", "")),
            "countries": str(promo_data.get("countries", "")),
            "buy_x": int(promo_data.get("buy_x", 0)),
            "get_y": int(promo_data.get("get_y", 0)),
            "active": "1",
            "usage_count": 0,
            "total_discount_krw": 0,
        }
        self._save_promo(promo)
        return promo

    def get_promotions(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """프로모션 목록을 반환한다.

        Args:
            active_only: True이면 활성 + 유효 기간 내 프로모션만 반환.
        """
        rows = self._load_promos()
        if active_only:
            now = datetime.datetime.now(tz=datetime.timezone.utc)
            result = []
            for p in rows:
                if str(p.get("active", "0")) != "1":
                    continue
                if not self._is_in_period(p, now):
                    continue
                result.append(p)
            return result
        return rows

    def update_promotion(
        self, promo_id: str, updates: Dict[str, Any]
    ) -> bool:
        """프로모션을 수정한다.

        Args:
            promo_id: 프로모션 ID.
            updates: 업데이트할 필드 딕셔너리.

        Returns:
            업데이트 성공 여부.
        """
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._sheet_name)
            records = ws.get_all_records()
            for idx, rec in enumerate(records, start=2):
                if str(rec.get("promo_id", "")) == promo_id:
                    for field, val in updates.items():
                        if field in _HEADERS:
                            col = _HEADERS.index(field) + 1
                            ws.update_cell(idx, col, val)
                    logger.info("프로모션 업데이트: promo_id=%s", promo_id)
                    return True
        except Exception as exc:
            logger.warning("프로모션 업데이트 실패: %s", exc)
        return False

    def get_promo_stats(self, promo_id: str) -> Optional[Dict[str, Any]]:
        """프로모션 성과 통계를 반환한다.

        Args:
            promo_id: 프로모션 ID.
        """
        promos = self._load_promos()
        for p in promos:
            if str(p.get("promo_id", "")) == promo_id:
                return {
                    "promo_id": promo_id,
                    "name": p.get("name", ""),
                    "usage_count": int(p.get("usage_count", 0) or 0),
                    "total_discount_krw": float(p.get("total_discount_krw", 0) or 0),
                    "active": str(p.get("active", "0")) == "1",
                }
        return None

    # ------------------------------------------------------------------
    # 할인 계산
    # ------------------------------------------------------------------

    def calculate_discount(
        self,
        order_data: Dict[str, Any],
        promotions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """주문에 적용 가능한 할인을 계산한다.

        Args:
            order_data: order_total_krw, skus, country, quantity 등 포함.
            promotions: 적용 대상 프로모션 목록 (None이면 활성 프로모션 로드).

        Returns:
            {discount_krw, free_shipping, applied_promos, stack_mode} 딕셔너리.
        """
        if promotions is None:
            promotions = self.get_promotions(active_only=True)

        applicable = self._filter_applicable(order_data, promotions)
        if not applicable:
            return {
                "discount_krw": 0,
                "free_shipping": False,
                "applied_promos": [],
                "stack_mode": _STACK_MODE,
            }

        stack_mode = os.getenv("PROMO_STACK_MODE", _STACK_MODE)
        discounts = [self._compute_discount(order_data, p) for p in applicable]
        free_shipping = any(
            p.get("type", "").upper() == TYPE_FREE_SHIPPING for p in applicable
        )

        if stack_mode == "stack":
            total_discount = sum(d for d in discounts if d > 0)
        else:
            total_discount = max(discounts) if discounts else 0

        return {
            "discount_krw": round(total_discount, 2),
            "free_shipping": free_shipping,
            "applied_promos": [p.get("promo_id", "") for p in applicable],
            "stack_mode": stack_mode,
        }

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _validate_promo(self, data: Dict[str, Any]) -> None:
        """프로모션 데이터를 검증한다."""
        required = ("name", "type")
        missing = [f for f in required if not data.get(f)]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        promo_type = str(data.get("type", "")).upper()
        if promo_type not in PROMO_TYPES:
            raise ValueError(f"Invalid promotion type: {promo_type}. Must be one of {PROMO_TYPES}")

    def _is_in_period(
        self, promo: Dict[str, Any], now: datetime.datetime
    ) -> bool:
        """프로모션이 유효 기간 내에 있는지 확인한다."""
        start_str = str(promo.get("start_date", "")).strip()
        end_str = str(promo.get("end_date", "")).strip()
        try:
            if start_str:
                start = datetime.datetime.fromisoformat(start_str)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=datetime.timezone.utc)
                if now < start:
                    return False
            if end_str:
                end = datetime.datetime.fromisoformat(end_str)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=datetime.timezone.utc)
                if now > end:
                    return False
        except (ValueError, TypeError):
            pass
        return True

    def _filter_applicable(
        self,
        order_data: Dict[str, Any],
        promotions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """주문에 적용 가능한 프로모션을 필터링한다."""
        order_total = float(order_data.get("order_total_krw", 0) or 0)
        order_skus = order_data.get("skus", [])
        if isinstance(order_skus, str):
            order_skus = [s.strip() for s in order_skus.split(",") if s.strip()]
        order_country = str(order_data.get("country", "")).strip().upper()

        result = []
        for p in promotions:
            # 최소 주문 금액 체크
            min_order = float(p.get("min_order_krw", 0) or 0)
            if order_total < min_order:
                continue
            # SKU 제한 체크
            promo_skus_raw = str(p.get("skus", "")).strip()
            if promo_skus_raw:
                promo_skus = [s.strip() for s in promo_skus_raw.split(",") if s.strip()]
                if promo_skus and not any(s in promo_skus for s in order_skus):
                    continue
            # 국가 제한 체크
            promo_countries_raw = str(p.get("countries", "")).strip()
            if promo_countries_raw and order_country:
                promo_countries = [c.strip().upper() for c in promo_countries_raw.split(",") if c.strip()]
                if promo_countries and order_country not in promo_countries:
                    continue
            result.append(p)
        return result

    def _compute_discount(
        self, order_data: Dict[str, Any], promo: Dict[str, Any]
    ) -> float:
        """프로모션의 할인 금액을 계산한다."""
        promo_type = str(promo.get("type", "")).upper()
        order_total = float(order_data.get("order_total_krw", 0) or 0)
        value = float(promo.get("value", 0) or 0)

        if promo_type == TYPE_PERCENTAGE:
            return order_total * (value / 100)
        elif promo_type == TYPE_FIXED_AMOUNT:
            return min(value, order_total)
        elif promo_type == TYPE_BUY_X_GET_Y:
            # 단가 기반으로 Y개 무료 할인 계산
            qty = int(order_data.get("quantity", 0) or 0)
            buy_x = int(promo.get("buy_x", 0) or 0)
            get_y = int(promo.get("get_y", 0) or 0)
            if buy_x > 0 and qty >= buy_x:
                unit_price = order_total / qty if qty > 0 else 0
                free_qty = (qty // buy_x) * get_y
                return unit_price * free_qty
            return 0
        elif promo_type == TYPE_FREE_SHIPPING:
            return 0  # 무료 배송은 discount_krw가 아닌 free_shipping 플래그로 처리
        return 0

    def _save_promo(self, promo: Dict[str, Any]) -> None:
        """프로모션을 Google Sheets에 저장한다."""
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._sheet_name)
            existing = ws.get_all_values()
            if not existing:
                ws.append_row(_HEADERS)
            ws.append_row([promo.get(h, "") for h in _HEADERS])
            logger.info("프로모션 저장: promo_id=%s", promo.get("promo_id"))
        except Exception as exc:
            logger.warning("프로모션 저장 실패: %s", exc)

    def _load_promos(self) -> List[Dict[str, Any]]:
        """Google Sheets에서 프로모션 목록을 로드한다."""
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._sheet_name)
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("프로모션 로드 실패: %s", exc)
            return []
