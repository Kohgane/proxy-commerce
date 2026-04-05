"""src/logistics/logistics_automation.py — 물류 자동화 (Phase 99)."""
from __future__ import annotations

import time
import uuid

from .cost_optimizer import CarrierSelector
from .logistics_models import CarrierInfo


class LogisticsAlertService:
    """물류 알림 서비스."""

    def __init__(self) -> None:
        self._alerts: list = []
        self._hub = None
        try:
            from ..realtime.realtime_hub import NotificationHub
            self._hub = NotificationHub()
        except Exception:
            pass

    def check_delivery_delays(self, deliveries: list) -> list:
        delayed = []
        now = time.time()
        for d in deliveries:
            eta = d.get("eta_minutes", 0) if isinstance(d, dict) else getattr(d, "eta_minutes", 0)
            updated = d.get("updated_at", now) if isinstance(d, dict) else getattr(d, "updated_at", now)
            status = d.get("status", "") if isinstance(d, dict) else getattr(d, "status", "")
            status_val = status.value if hasattr(status, "value") else str(status)
            if status_val not in ("delivered", "failed") and (now - updated) / 60 > eta + 30:
                delayed.append(d)
        return delayed

    def send_alert(self, alert_type: str, message: str, severity: str = "info") -> dict:
        alert = {
            "alert_id": str(uuid.uuid4()),
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
            "created_at": time.time(),
        }
        self._alerts.append(alert)
        if self._hub is not None:
            try:
                self._hub.broadcast(alert_type, alert)
            except Exception:
                pass
        return alert

    def get_alerts(self, alert_type: str | None = None) -> list:
        if alert_type is None:
            return list(self._alerts)
        return [a for a in self._alerts if a["alert_type"] == alert_type]


class LogisticsAutomation:
    """물류 자동화 처리기."""

    def __init__(self) -> None:
        self._selector = CarrierSelector()
        self._alert_svc = LogisticsAlertService()

    def auto_select_carrier(
        self, weight_kg: float, region: str, priority: str = "cost"
    ) -> CarrierInfo:
        return self._selector.recommend_carrier(weight_kg, region, priority)

    def auto_generate_waybill(self, delivery_id: str, carrier_id: str) -> dict:
        waybill_number = f"{carrier_id}-{uuid.uuid4().hex[:12].upper()}"
        return {
            "delivery_id": delivery_id,
            "carrier_id": carrier_id,
            "waybill_number": waybill_number,
            "generated_at": time.time(),
            "status": "generated",
        }

    def auto_update_delivery_status(
        self, delivery_id: str, tracking_number: str
    ) -> dict:
        # Mock 배송 상태 조회
        mock_status = "in_transit"
        mock_location = "서울 물류센터"
        return {
            "delivery_id": delivery_id,
            "tracking_number": tracking_number,
            "status": mock_status,
            "location": mock_location,
            "updated_at": time.time(),
        }

    def auto_reassign_failed_delivery(self, delivery_id: str) -> dict:
        new_agent_id = str(uuid.uuid4())
        return {
            "delivery_id": delivery_id,
            "action": "reassigned",
            "new_agent_id": new_agent_id,
            "reassigned_at": time.time(),
            "reason": "이전 배달 실패 후 자동 재배정",
        }

    def process_batch_deliveries(self, deliveries: list) -> list:
        results = []
        for delivery in deliveries:
            delivery_id = delivery.get("delivery_id", str(uuid.uuid4()))
            weight = delivery.get("weight_kg", 1.0)
            region = delivery.get("region", "서울")
            carrier = self.auto_select_carrier(weight, region)
            waybill = self.auto_generate_waybill(delivery_id, carrier.carrier_id)
            results.append({
                "delivery_id": delivery_id,
                "carrier": carrier.to_dict(),
                "waybill": waybill,
                "processed_at": time.time(),
            })
        return results
