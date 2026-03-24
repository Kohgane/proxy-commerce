"""src/crm/segmentation.py — 고객 세분화 (RFM 분석).

외부 라이브러리 없이 RFM 분석 기반 고객 세그먼트를 계산한다.
세그먼트: VIP, LOYAL, AT_RISK, NEW, DORMANT

환경변수:
  CRM_ENABLED          — CRM 활성화 여부 (기본 "0")
  CRM_VIP_MIN_ORDERS   — VIP 최소 주문 횟수 (기본 "3")
  CRM_VIP_MIN_SPENT    — VIP 최소 누적 구매금액 KRW (기본 "1000000")
  CRM_AT_RISK_DAYS     — AT_RISK 기준 미구매 일수 (기본 "90")
  CRM_DORMANT_DAYS     — DORMANT 기준 미구매 일수 (기본 "180")
"""

import datetime
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 세그먼트 상수
SEG_VIP = "VIP"
SEG_LOYAL = "LOYAL"
SEG_AT_RISK = "AT_RISK"
SEG_NEW = "NEW"
SEG_DORMANT = "DORMANT"

SEGMENTS = (SEG_VIP, SEG_LOYAL, SEG_AT_RISK, SEG_NEW, SEG_DORMANT)

# 세그먼트 기준값 (환경변수로 오버라이드 가능)
_VIP_MIN_ORDERS = int(os.getenv("CRM_VIP_MIN_ORDERS", "3"))
_VIP_MIN_SPENT = float(os.getenv("CRM_VIP_MIN_SPENT", "1000000"))
_AT_RISK_DAYS = int(os.getenv("CRM_AT_RISK_DAYS", "90"))
_DORMANT_DAYS = int(os.getenv("CRM_DORMANT_DAYS", "180"))


class CustomerSegmentation:
    """고객 세분화 분석기 (RFM 기반)."""

    def __init__(
        self,
        profile_manager=None,
        vip_min_orders: Optional[int] = None,
        vip_min_spent: Optional[float] = None,
        at_risk_days: Optional[int] = None,
        dormant_days: Optional[int] = None,
    ):
        self._profile_manager = profile_manager
        self._vip_min_orders = vip_min_orders or int(os.getenv("CRM_VIP_MIN_ORDERS", "3"))
        self._vip_min_spent = vip_min_spent or float(os.getenv("CRM_VIP_MIN_SPENT", "1000000"))
        self._at_risk_days = at_risk_days or int(os.getenv("CRM_AT_RISK_DAYS", "90"))
        self._dormant_days = dormant_days or int(os.getenv("CRM_DORMANT_DAYS", "180"))

    def classify(self, customer: Dict[str, Any]) -> str:
        """단일 고객을 RFM 기준으로 세그먼트 분류한다.

        분류 우선순위:
          DORMANT > AT_RISK > VIP > LOYAL > NEW

        Args:
            customer: total_orders, total_spent_krw, first_order_date,
                      last_order_date 필드를 포함한 딕셔너리.

        Returns:
            세그먼트 문자열 (VIP/LOYAL/AT_RISK/NEW/DORMANT).
        """
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        total_orders = int(customer.get("total_orders", 0) or 0)
        total_spent = float(customer.get("total_spent_krw", 0) or 0)

        last_order_str = str(customer.get("last_order_date", "")).strip()
        first_order_str = str(customer.get("first_order_date", "")).strip()

        days_since_last = self._days_since(last_order_str, now)
        days_since_first = self._days_since(first_order_str, now)

        # DORMANT: 마지막 주문 DORMANT_DAYS+ 경과
        if days_since_last is not None and days_since_last >= self._dormant_days:
            return SEG_DORMANT

        # AT_RISK: 마지막 주문 AT_RISK_DAYS+ 경과, 이전 2회+ 구매
        if (
            days_since_last is not None
            and days_since_last >= self._at_risk_days
            and total_orders >= 2
        ):
            return SEG_AT_RISK

        # VIP: 최근 30일 내 3회+ 구매, 총 누적 VIP_MIN_SPENT+
        if (
            days_since_last is not None
            and days_since_last <= 30
            and total_orders >= self._vip_min_orders
            and total_spent >= self._vip_min_spent
        ):
            return SEG_VIP

        # LOYAL: 최근 60일 내 2회+ 구매
        if (
            days_since_last is not None
            and days_since_last <= 60
            and total_orders >= 2
        ):
            return SEG_LOYAL

        # NEW: 첫 주문 30일 이내
        if days_since_first is not None and days_since_first <= 30:
            return SEG_NEW

        # 기본값
        return SEG_LOYAL

    def segment_all_customers(
        self,
        customers: Optional[List[Dict[str, Any]]] = None,
        notify_changes: bool = True,
    ) -> Dict[str, List[str]]:
        """전체 고객을 세분화하고 결과를 반환한다.

        Args:
            customers: 고객 목록 (None이면 profile_manager에서 로드).
            notify_changes: 세그먼트 변경 시 알림 발송 여부.

        Returns:
            {segment: [email, ...]} 딕셔너리.
        """
        if customers is None:
            if self._profile_manager is not None:
                customers = self._profile_manager.get_all_customers()
            else:
                customers = []

        result: Dict[str, List[str]] = {seg: [] for seg in SEGMENTS}
        changed_to_vip = []
        changed_to_at_risk = []

        for c in customers:
            email = str(c.get("email", ""))
            new_segment = self.classify(c)
            old_segment = str(c.get("segment", ""))

            result[new_segment].append(email)

            if new_segment != old_segment:
                if new_segment == SEG_VIP:
                    changed_to_vip.append(email)
                elif new_segment == SEG_AT_RISK and old_segment not in (SEG_AT_RISK, SEG_DORMANT):
                    changed_to_at_risk.append(email)

                # 세그먼트 업데이트
                if self._profile_manager is not None:
                    self._profile_manager.update_segment(email, new_segment)

        if notify_changes:
            if changed_to_vip:
                self._notify_segment_change(SEG_VIP, changed_to_vip)
            if changed_to_at_risk:
                self._notify_segment_change(SEG_AT_RISK, changed_to_at_risk)

        return result

    def get_segment_summary(
        self,
        customers: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """세그먼트별 요약 통계를 반환한다.

        Returns:
            {segment: {count, avg_spent, avg_orders}} 딕셔너리.
        """
        if customers is None:
            if self._profile_manager is not None:
                customers = self._profile_manager.get_all_customers()
            else:
                customers = []

        groups: Dict[str, List[Dict[str, Any]]] = {seg: [] for seg in SEGMENTS}
        for c in customers:
            seg = self.classify(c)
            groups[seg].append(c)

        summary = {}
        for seg, members in groups.items():
            count = len(members)
            avg_spent = (
                round(sum(float(c.get("total_spent_krw", 0) or 0) for c in members) / count, 2)
                if count else 0.0
            )
            avg_orders = (
                round(sum(int(c.get("total_orders", 0) or 0) for c in members) / count, 2)
                if count else 0.0
            )
            summary[seg] = {
                "count": count,
                "avg_spent_krw": avg_spent,
                "avg_orders": avg_orders,
            }
        return summary

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _days_since(
        self, date_str: str, now: datetime.datetime
    ) -> Optional[int]:
        """날짜 문자열로부터 현재까지 경과 일수를 반환한다."""
        if not date_str:
            return None
        try:
            dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return max(0, (now - dt).days)
        except (ValueError, TypeError):
            return None

    def _notify_segment_change(self, segment: str, emails: List[str]) -> None:
        """세그먼트 변경 텔레그램 알림을 발송한다."""
        try:
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if not token or not chat_id:
                return
            icons = {SEG_VIP: "👑", SEG_AT_RISK: "⚠️"}
            icon = icons.get(segment, "📊")
            count = len(emails)
            preview = emails[:3]
            text = (
                f"{icon} *세그먼트 변경: {segment}*\n\n"
                f"고객 {count}명이 {segment} 세그먼트로 전환되었습니다.\n"
                + "\n".join(f"• {e}" for e in preview)
                + (f"\n... 외 {count - 3}명" if count > 3 else "")
            )
            import requests
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as exc:
            logger.warning("텔레그램 알림 실패: %s", exc)
