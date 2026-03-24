"""src/crm/lifecycle.py — 고객 라이프사이클 자동화.

첫 구매 환영, 재구매 유도, VIP 혜택 알림, 이탈 방지 알림.
기존 src/notifications/ 패턴을 재사용한다.

환경변수:
  CRM_LIFECYCLE_ENABLED     — 라이프사이클 자동화 활성화 여부 (기본 "0")
  CRM_REPURCHASE_DAYS       — 재구매 유도 기준 일수 (기본 "30")
  TELEGRAM_BOT_TOKEN        — 텔레그램 봇 토큰
  TELEGRAM_CHAT_ID          — 텔레그램 채팅 ID
"""

import datetime
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPURCHASE_DAYS = int(os.getenv("CRM_REPURCHASE_DAYS", "30"))


class CustomerLifecycle:
    """고객 라이프사이클 자동화."""

    def __init__(self, profile_manager=None, segmentation=None):
        self._profile_manager = profile_manager
        self._segmentation = segmentation

    def is_enabled(self) -> bool:
        """라이프사이클 자동화 활성화 여부를 반환한다."""
        return os.getenv("CRM_LIFECYCLE_ENABLED", "0") == "1"

    def send_welcome(self, customer: Dict[str, Any]) -> bool:
        """첫 구매 고객에게 환영 알림을 발송한다.

        Args:
            customer: email, name 필드를 포함한 딕셔너리.

        Returns:
            발송 성공 여부.
        """
        if not self.is_enabled():
            return False

        email = str(customer.get("email", ""))
        name = str(customer.get("name", "고객")) or "고객"
        text = (
            f"🎉 *환영합니다, {name}님!*\n\n"
            f"첫 구매를 완료하셨습니다. "
            f"저희 서비스를 선택해 주셔서 진심으로 감사드립니다.\n"
            f"앞으로도 최고의 서비스를 제공하겠습니다."
        )
        return self._send_notification(email, text)

    def send_repurchase_nudge(
        self,
        customers: Optional[List[Dict[str, Any]]] = None,
        days: Optional[int] = None,
    ) -> List[str]:
        """마지막 구매 후 N일이 지난 고객에게 재구매 유도 알림을 발송한다.

        Args:
            customers: 고객 목록 (None이면 profile_manager에서 로드).
            days: 재구매 유도 기준 일수 (기본: 환경변수).

        Returns:
            알림을 발송한 이메일 목록.
        """
        if not self.is_enabled():
            return []

        if customers is None:
            if self._profile_manager is not None:
                customers = self._profile_manager.get_all_customers()
            else:
                return []

        threshold = days if days is not None else int(os.getenv("CRM_REPURCHASE_DAYS", "30"))
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        nudged = []

        for c in customers:
            last_order_str = str(c.get("last_order_date", "")).strip()
            if not last_order_str:
                continue
            try:
                last_order = datetime.datetime.fromisoformat(
                    last_order_str.replace("Z", "+00:00")
                )
                if last_order.tzinfo is None:
                    last_order = last_order.replace(tzinfo=datetime.timezone.utc)
                days_since = (now - last_order).days
                if days_since >= threshold:
                    email = str(c.get("email", ""))
                    name = str(c.get("name", "고객")) or "고객"
                    text = (
                        f"💝 *{name}님, 오랜만이에요!*\n\n"
                        f"마지막 구매 후 {days_since}일이 지났습니다. "
                        f"새로운 상품들이 입고되었으니 확인해 보세요!"
                    )
                    if self._send_notification(email, text):
                        nudged.append(email)
            except (ValueError, TypeError):
                continue

        return nudged

    def send_vip_benefit(
        self,
        customers: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """VIP 고객에게 전용 혜택 알림을 발송한다.

        Args:
            customers: 고객 목록 (None이면 VIP 세그먼트 고객 로드).

        Returns:
            알림을 발송한 이메일 목록.
        """
        if not self.is_enabled():
            return []

        if customers is None:
            if self._profile_manager is not None:
                customers = self._profile_manager.get_all_customers(segment="VIP")
            else:
                return []

        notified = []
        for c in customers:
            email = str(c.get("email", ""))
            name = str(c.get("name", "VIP 고객")) or "VIP 고객"
            text = (
                f"👑 *{name}님, VIP 전용 혜택 안내*\n\n"
                f"감사한 마음을 담아 VIP 고객님께 특별 혜택을 준비했습니다. "
                f"지금 바로 확인하세요!"
            )
            if self._send_notification(email, text):
                notified.append(email)

        return notified

    def send_at_risk_alert(
        self,
        customers: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """이탈 위험(AT_RISK) 고객에게 이탈 방지 알림을 발송한다.

        Args:
            customers: 고객 목록 (None이면 AT_RISK 세그먼트 고객 로드).

        Returns:
            알림을 발송한 이메일 목록.
        """
        if not self.is_enabled():
            return []

        if customers is None:
            if self._profile_manager is not None:
                customers = self._profile_manager.get_all_customers(segment="AT_RISK")
            else:
                return []

        notified = []
        for c in customers:
            email = str(c.get("email", ""))
            name = str(c.get("name", "고객")) or "고객"
            text = (
                f"💌 *{name}님, 보고 싶었어요!*\n\n"
                f"한동안 뵙지 못했네요. 특별 할인 혜택을 준비했으니 "
                f"다시 찾아주시면 감사하겠습니다."
            )
            if self._send_notification(email, text):
                notified.append(email)

        return notified

    def run_all(self) -> Dict[str, Any]:
        """모든 라이프사이클 자동화를 실행한다.

        Returns:
            {welcome, repurchase, vip_benefit, at_risk} 결과 딕셔너리.
        """
        if not self.is_enabled():
            return {"enabled": False}

        repurchase = self.send_repurchase_nudge()
        vip_benefit = self.send_vip_benefit()
        at_risk = self.send_at_risk_alert()

        return {
            "enabled": True,
            "repurchase_nudge_count": len(repurchase),
            "vip_benefit_count": len(vip_benefit),
            "at_risk_alert_count": len(at_risk),
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _send_notification(self, email: str, text: str) -> bool:
        """알림을 발송한다 (텔레그램 채널 사용).

        실제 이메일 발송 대신 텔레그램으로 운영자에게 알림.
        """
        try:
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if not token or not chat_id:
                logger.info("텔레그램 미설정 — 알림 건너뜀: %s", email)
                return False
            full_text = f"[CRM 알림 → {email}]\n\n{text}"
            import requests
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": full_text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("알림 발송 실패: email=%s error=%s", email, exc)
            return False
