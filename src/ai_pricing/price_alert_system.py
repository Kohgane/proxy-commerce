"""src/ai_pricing/price_alert_system.py — 가격 알림 시스템 (Phase 97)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)


class PriceAlertSystem:
    """가격 변경/경쟁사 변동/마진 위험 알림 시스템.

    기존 NotificationHub를 활용하여 텔레그램/이메일/Slack으로 알림을 발송한다.
    """

    def __init__(self, min_margin_pct: float = 0.15) -> None:
        self._min_margin = min_margin_pct
        self._alerts: List[Dict] = []
        self._daily_report_data: List[Dict] = []

    # ── 알림 생성 ─────────────────────────────────────────────────────────

    def alert_price_change(
        self,
        sku: str,
        old_price: float,
        new_price: float,
        strategy: str = '',
        auto_applied: bool = False,
    ) -> Dict:
        """가격 변경 알림을 생성하고 발송한다."""
        change_pct = ((new_price - old_price) / old_price * 100) if old_price else 0.0
        direction = '▲' if new_price > old_price else '▼'
        alert = {
            'type': 'price_change',
            'sku': sku,
            'old_price': old_price,
            'new_price': new_price,
            'change_pct': round(change_pct, 2),
            'direction': direction,
            'strategy': strategy,
            'auto_applied': auto_applied,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._alerts.append(alert)
        self._daily_report_data.append(alert)
        msg = (
            f'💰 가격 변경 [{sku}]\n'
            f'{direction} {old_price:,.0f} → {new_price:,.0f}원 ({change_pct:+.1f}%)\n'
            f'전략: {strategy} | 자동적용: {"✅" if auto_applied else "⏳ 승인대기"}'
        )
        self._notify(msg)
        return alert

    def alert_competitor_change(
        self,
        competitor_id: str,
        sku: str,
        old_price: float,
        new_price: float,
        change_pct: float,
    ) -> Dict:
        """경쟁사 가격 변동 알림을 생성한다."""
        direction = '급등' if change_pct > 0 else '급락'
        alert = {
            'type': 'competitor_price_change',
            'competitor_id': competitor_id,
            'sku': sku,
            'old_price': old_price,
            'new_price': new_price,
            'change_pct': round(change_pct, 2),
            'direction': direction,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._alerts.append(alert)
        msg = (
            f'🔔 경쟁사 가격 {direction} [{sku}]\n'
            f'{competitor_id}: {old_price:,.0f} → {new_price:,.0f} ({change_pct:+.1f}%)'
        )
        self._notify(msg)
        return alert

    def alert_margin_risk(
        self,
        sku: str,
        current_price: float,
        cost: float,
        current_margin: float,
    ) -> Dict:
        """마진 위험 알림을 생성한다."""
        alert = {
            'type': 'margin_risk',
            'sku': sku,
            'current_price': current_price,
            'cost': cost,
            'current_margin': round(current_margin, 4),
            'min_margin': self._min_margin,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._alerts.append(alert)
        msg = (
            f'⚠️ 마진 위험 [{sku}]\n'
            f'현재 마진: {current_margin * 100:.1f}% (최소 기준: {self._min_margin * 100:.0f}%)\n'
            f'판가: {current_price:,.0f}원 | 원가: {cost:,.0f}원'
        )
        self._notify(msg)
        return alert

    # ── 일일 리포트 ───────────────────────────────────────────────────────

    def generate_daily_report(self) -> str:
        """일일 가격 리포트를 생성한다."""
        data = self._daily_report_data
        price_changes = [d for d in data if d.get('type') == 'price_change']
        increases = [d for d in price_changes if d.get('change_pct', 0) > 0]
        decreases = [d for d in price_changes if d.get('change_pct', 0) < 0]
        avg_change = (
            sum(d['change_pct'] for d in price_changes) / len(price_changes)
            if price_changes else 0.0
        )
        report = (
            f'📊 일일 가격 최적화 리포트\n'
            f'─────────────────────\n'
            f'총 가격 변경: {len(price_changes)}건\n'
            f'  ▲ 인상: {len(increases)}건\n'
            f'  ▼ 인하: {len(decreases)}건\n'
            f'평균 변동률: {avg_change:+.2f}%\n'
            f'생성: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}'
        )
        # 리포트 생성 후 초기화
        self._daily_report_data.clear()
        self._notify(report)
        return report

    def get_alerts(
        self,
        alert_type: str = None,
        limit: int = 50,
    ) -> List[Dict]:
        """알림 목록을 반환한다."""
        alerts = self._alerts
        if alert_type:
            alerts = [a for a in alerts if a.get('type') == alert_type]
        return alerts[-limit:]

    def clear_alerts(self) -> None:
        """알림 목록을 초기화한다."""
        self._alerts.clear()

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────

    def _notify(self, message: str) -> None:
        """NotificationHub를 통해 알림을 발송한다."""
        logger.info('[PriceAlert] %s', message.replace('\n', ' | '))
        try:
            from ..notifications.hub import NotificationHub
            hub = NotificationHub()
            hub.send('order', message)
        except Exception as exc:
            logger.debug('알림 발송 건너뜀: %s', exc)
