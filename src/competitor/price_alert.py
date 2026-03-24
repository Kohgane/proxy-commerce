"""src/competitor/price_alert.py — 경쟁사 가격 변동 알림.

경쟁사 가격 변동을 감지하여 텔레그램/Slack 알림을 발송한다.

환경변수:
  PRICE_ALERT_THRESHOLD_PCT — 알림 임계값 % (기본 5)
  COMPETITOR_TRACKING_ENABLED — 활성화 여부
"""

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_THRESHOLD_PCT = float(os.getenv('PRICE_ALERT_THRESHOLD_PCT', '5'))
_ENABLED = os.getenv('COMPETITOR_TRACKING_ENABLED', '0') == '1'


class PriceAlert:
    """경쟁사 가격 변동 알림 관리자."""

    def __init__(self):
        self._prev_prices: dict = {}  # {(sku, competitor): price_krw}

    def _get_tracker(self):
        from .price_tracker import CompetitorPriceTracker
        return CompetitorPriceTracker()

    def _send_telegram(self, text: str):
        try:
            from ..utils.telegram import send_tele
            send_tele(text)
        except Exception as exc:
            logger.warning("텔레그램 알림 실패: %s", exc)

    def _send_slack(self, text: str):
        try:
            from ..notifications.channels.slack_notifier import SlackNotifier
            notifier = SlackNotifier()
            notifier.send(text)
        except Exception as exc:
            logger.warning("슬랙 알림 실패: %s", exc)

    def check_price_changes(self) -> list:
        """경쟁사 가격 변동을 감지하고 알림을 발송한다.

        Returns:
            변동 감지된 항목 리스트
        """
        if not _ENABLED:
            logger.debug("경쟁사 추적 비활성화 — 가격 변동 체크 건너뜀")
            return []

        tracker = self._get_tracker()
        rows = tracker._get_all_rows()
        changes = []

        for row in rows:
            sku = str(row.get('our_sku', ''))
            comp_name = str(row.get('competitor_name', ''))
            comp_price = float(row.get('competitor_price') or 0)
            currency = str(row.get('competitor_currency', 'KRW'))

            if not sku or comp_price <= 0:
                continue

            try:
                comp_price_krw = tracker._convert_to_krw(comp_price, currency)
            except Exception:
                comp_price_krw = comp_price

            key = (sku, comp_name)
            prev_price_krw = self._prev_prices.get(key)

            if prev_price_krw is not None and prev_price_krw > 0:
                change_pct = (comp_price_krw - prev_price_krw) / prev_price_krw * 100
                if abs(change_pct) >= _THRESHOLD_PCT:
                    direction = '📈 상승' if change_pct > 0 else '📉 하락'
                    changes.append({
                        'our_sku': sku,
                        'competitor_name': comp_name,
                        'prev_price_krw': round(prev_price_krw),
                        'new_price_krw': round(comp_price_krw),
                        'change_pct': round(change_pct, 2),
                        'direction': direction,
                        'detected_at': datetime.utcnow().isoformat(),
                    })

            self._prev_prices[key] = comp_price_krw

        if changes:
            self._send_alerts(changes)

        return changes

    def _send_alerts(self, changes: list):
        """변동 알림을 Telegram + Slack으로 발송한다."""
        lines = [f"*💰 경쟁사 가격 변동 감지 ({len(changes)}건)*\n"]
        for c in changes[:10]:
            lines.append(
                f"• `{c['our_sku']}` [{c['competitor_name']}] "
                f"{c['direction']} {c['change_pct']:+.1f}% "
                f"({c['prev_price_krw']:,}원 → {c['new_price_krw']:,}원)"
            )
        if len(changes) > 10:
            lines.append(f"_... 외 {len(changes) - 10}건_")

        message = '\n'.join(lines)
        self._send_telegram(message)
        self._send_slack(message)

    def send_daily_summary(self) -> str:
        """일일 가격 비교 서머리를 발송한다."""
        if not _ENABLED:
            return ''

        tracker = self._get_tracker()

        overpriced = tracker.get_overpriced_items(threshold_pct=10)
        underpriced = tracker.get_underpriced_items(threshold_pct=10)

        lines = [
            "*📊 일일 경쟁사 가격 서머리*\n",
            f"• 우리가 더 비싼 상품: *{len(overpriced)}개* (가격 경쟁력 문제)",
            f"• 우리가 더 저렴한 상품: *{len(underpriced)}개* (마진 개선 기회)",
        ]

        if overpriced:
            lines.append("\n🚨 가격 경쟁력 부족 (상위 3개):")
            for item in overpriced[:3]:
                lines.append(
                    f"  • `{item['our_sku']}`: +{item['price_diff_pct']:.1f}% 높음"
                )

        summary = '\n'.join(lines)
        self._send_telegram(summary)
        self._send_slack(summary)
        return summary
