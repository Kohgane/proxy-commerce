"""재고 변동 알림 관리 모듈."""

import logging
from decimal import Decimal

from ..utils.telegram import send_tele
from ..utils.emailer import send_mail

logger = logging.getLogger(__name__)


class StockAlertManager:
    """재고 변동 알림 관리."""

    def __init__(self):
        """텔레그램/이메일 알림 설정."""

    # ── public API ──────────────────────────────────────────

    def notify_out_of_stock(self, products: list):
        """품절 알림 발송.

        products: [{'sku': str, 'title': str, 'vendor': str, ...}, ...]
        """
        if not products:
            return
        lines = [f"🚫 [품절 알림] {len(products)}건\n"]
        for i, p in enumerate(products):
            prefix = '└' if i == len(products) - 1 else '├'
            title = p.get('title') or p.get('sku', '')
            lines.append(f"{prefix} {p['sku']} {title} — 재고 0")
        lines.append("\n→ 카탈로그/Shopify/WooCommerce 자동 비활성화 완료")
        msg = '\n'.join(lines)
        self._send(msg)

    def notify_restock(self, products: list):
        """재입고 알림 발송.

        products: [{'sku': str, 'title': str, 'quantity': int, ...}, ...]
        """
        if not products:
            return
        lines = [f"📦 [재입고 알림] {len(products)}건"]
        for i, p in enumerate(products):
            prefix = '└' if i == len(products) - 1 else '├'
            title = p.get('title') or p.get('sku', '')
            qty = p.get('quantity') or '?'
            lines.append(f"{prefix} {p['sku']} {title} — 재고 {qty}")
        msg = '\n'.join(lines)
        self._send(msg)

    def notify_price_change(self, products: list):
        """가격 변동 알림 발송.

        products: [{'sku': str, 'title': str, 'old_price': str, 'new_price': str,
                    'currency': str, ...}, ...]
        """
        if not products:
            return
        lines = [f"💰 [가격 변동 알림] {len(products)}건"]
        for i, p in enumerate(products):
            prefix = '└' if i == len(products) - 1 else '├'
            title = p.get('title') or p.get('sku', '')
            currency = p.get('currency', '')
            old_p = p.get('old_price', '')
            new_p = p.get('new_price', '')
            pct_str = _format_pct_change(old_p, new_p)
            symbol = '¥' if currency == 'JPY' else ('€' if currency == 'EUR' else '')
            lines.append(
                f"{prefix} {p['sku']} {title}\n"
                f"  {symbol}{old_p} → {symbol}{new_p}{pct_str}\n"
                f"  → 판매가 재계산 필요"
            )
        msg = '\n'.join(lines)
        self._send(msg)

    def send_sync_summary(self, sync_result: dict):
        """동기화 완료 요약 발송."""
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
        total = sync_result.get('total_checked', 0)
        changes = sync_result.get('changes', [])
        out_cnt = sum(1 for c in changes if c.get('change') == 'out_of_stock')
        restock_cnt = sum(1 for c in changes if c.get('change') == 'restock')
        price_cnt = sum(1 for c in changes if c.get('change') == 'price_changed')
        shopify_upd = sync_result.get('shopify_updated', 0)
        woo_upd = sync_result.get('woo_updated', 0)

        msg = (
            f"✅ [재고 동기화 완료] {now}\n"
            f"총 확인: {total}건\n"
            f"변경: {len(changes)}건 (품절 {out_cnt}, 재입고 {restock_cnt}, 가격변동 {price_cnt})\n"
            f"스토어 업데이트: Shopify {shopify_upd}건, WooCommerce {woo_upd}건"
        )
        self._send(msg)

    # ── internal ─────────────────────────────────────────────

    def _send(self, msg: str):
        """텔레그램 + 이메일로 알림 발송."""
        try:
            send_tele(msg)
        except Exception as exc:
            logger.warning("Telegram alert failed: %s", exc)
        try:
            send_mail('[재고알림]', msg)
        except Exception as exc:
            logger.warning("Email alert failed: %s", exc)


# ── helpers ──────────────────────────────────────────────────

def _format_pct_change(old_price: str, new_price: str) -> str:
    """가격 변동률 문자열 반환. 계산 불가 시 빈 문자열."""
    try:
        old = Decimal(str(old_price))
        new = Decimal(str(new_price))
        if old == 0:
            return ''
        pct = ((new - old) / old * 100).quantize(Decimal('0.1'))
        sign = '+' if pct > 0 else ''
        return f" ({sign}{pct}%)"
    except Exception:
        return ''
