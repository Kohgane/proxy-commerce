"""배송 지연/예외 감지 — 임계값 기반 이상 감지."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import DeliveryAnomaly


# 상태별 지연 임계값 (시간 단위)
DELAY_THRESHOLDS = {
    'picked_up': 24,            # 픽업 후 24h 미진행 → 경고
    'in_transit': 48,           # 배송 중 48h 초과 → 경고
    'in_transit_critical': 72,  # 72h 초과 → 심각
    'out_for_delivery': 12,     # 배송 출발 후 12h 초과 → 경고
}


class DeliveryDelayDetector:
    """배송 지연 감지기."""

    def __init__(self) -> None:
        # tracking_no → 상태 진입 시각
        self._status_since: Dict[str, Dict[str, str]] = {}
        self._anomalies: List[DeliveryAnomaly] = []

    def record_status(self, tracking_no: str, status: str, timestamp: str = None) -> None:
        """상태 진입 시각 기록."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        if tracking_no not in self._status_since:
            self._status_since[tracking_no] = {}
        # 새로운 상태만 기록 (이미 기록된 상태는 유지)
        if status not in self._status_since[tracking_no]:
            self._status_since[tracking_no][status] = ts

    def check_delays(self, tracking_no: str, current_status: str, order_id: str = '') -> List[DeliveryAnomaly]:
        """지연 여부 검사. 새로 감지된 이상 목록 반환."""
        new_anomalies: List[DeliveryAnomaly] = []
        statuses = self._status_since.get(tracking_no, {})

        for status, since_str in statuses.items():
            threshold_h = None
            severity = 'low'

            if status == 'in_transit':
                elapsed_h = self._elapsed_hours(since_str)
                if elapsed_h >= DELAY_THRESHOLDS['in_transit_critical']:
                    threshold_h = DELAY_THRESHOLDS['in_transit_critical']
                    severity = 'high'
                elif elapsed_h >= DELAY_THRESHOLDS['in_transit']:
                    threshold_h = DELAY_THRESHOLDS['in_transit']
                    severity = 'medium'
            elif status == 'out_for_delivery':
                elapsed_h = self._elapsed_hours(since_str)
                if elapsed_h >= DELAY_THRESHOLDS['out_for_delivery']:
                    threshold_h = DELAY_THRESHOLDS['out_for_delivery']
                    severity = 'medium'
            elif status == 'picked_up' and current_status == 'picked_up':
                elapsed_h = self._elapsed_hours(since_str)
                if elapsed_h >= DELAY_THRESHOLDS['picked_up']:
                    threshold_h = DELAY_THRESHOLDS['picked_up']
                    severity = 'low'

            if threshold_h is not None:
                # 중복 감지 방지
                existing_keys = {(a.tracking_no, a.anomaly_type, a.severity) for a in self._anomalies}
                key = (tracking_no, 'delayed', severity)
                if key not in existing_keys:
                    anomaly = DeliveryAnomaly(
                        tracking_no=tracking_no,
                        anomaly_type='delayed',
                        detected_at=datetime.now(timezone.utc).isoformat(),
                        severity=severity,
                        order_id=order_id,
                    )
                    self._anomalies.append(anomaly)
                    new_anomalies.append(anomaly)

        return new_anomalies

    def get_all_anomalies(self) -> List[DeliveryAnomaly]:
        """감지된 전체 이상 목록 반환."""
        return list(self._anomalies)

    def _elapsed_hours(self, since_str: str) -> float:
        """시작 시각으로부터 경과 시간(시간) 계산."""
        try:
            since = datetime.fromisoformat(since_str)
            now = datetime.now(timezone.utc)
            # timezone-aware 처리
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            delta = now - since
            return delta.total_seconds() / 3600
        except Exception:
            return 0.0
