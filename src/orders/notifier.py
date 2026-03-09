"""주문 알림 통합 모듈 — 텔레그램, 이메일, Notion으로 구매 태스크 발송."""

import os
import logging

logger = logging.getLogger(__name__)


class OrderNotifier:
    """주문 라우팅 결과를 알림 채널로 발송."""

    # ── 공개 API ────────────────────────────────────────────

    def notify_new_order(self, routed_order: dict):
        """새 주문 라우팅 결과를 모든 활성 채널로 알림.

        routed_order: OrderRouter.route_order() 반환값
        """
        telegram_msg = self._format_telegram_message(routed_order)

        if os.getenv('TELEGRAM_ENABLED', '1') == '1':
            try:
                from ..utils.telegram import send_tele
                send_tele(telegram_msg)
            except Exception as exc:
                logger.warning("Telegram notification failed: %s", exc)

        if os.getenv('EMAIL_ENABLED', '0') == '1':
            try:
                from ..utils.emailer import send_mail
                order_number = routed_order.get('order_number', '')
                send_mail(
                    subject=f'[구매요청] 신규 주문 태스크 {order_number}',
                    body=telegram_msg,
                )
            except Exception as exc:
                logger.warning("Email notification failed: %s", exc)

        notion_tasks = self._format_notion_tasks(routed_order)
        order_id = routed_order.get('order_id')
        for task_data in notion_tasks:
            try:
                from ..utils.notion import create_task_if_env
                create_task_if_env(
                    title=task_data['title'],
                    url=task_data['src_url'],
                    sku=task_data['sku'],
                    order_id=order_id,
                )
            except Exception as exc:
                logger.warning("Notion task creation failed for SKU %s: %s", task_data.get('sku'), exc)

    def notify_tracking_update(
        self,
        order_id,
        sku: str,
        tracking_number: str,
        carrier: str,
    ):
        """송장 업데이트 알림 (배대지 → 고객 발송 시)."""
        msg = (
            f'📦 [송장 등록]\n'
            f'주문 ID: {order_id}\n'
            f'SKU: {sku}\n'
            f'택배사: {carrier}\n'
            f'송장번호: {tracking_number}'
        )

        if os.getenv('TELEGRAM_ENABLED', '1') == '1':
            try:
                from ..utils.telegram import send_tele
                send_tele(msg)
            except Exception as exc:
                logger.warning("Telegram tracking notification failed: %s", exc)

    # ── 내부 포맷터 ─────────────────────────────────────────

    def _format_telegram_message(self, routed_order: dict) -> str:
        """텔레그램 메시지 포맷팅. 마크다운 형식, 이모지 포함, 벤더별 구분."""
        order_number = routed_order.get('order_number', '')
        order_id = routed_order.get('order_id', '')
        customer = routed_order.get('customer', {})
        customer_name = customer.get('name', '')
        customer_email = customer.get('email', '')
        summary = routed_order.get('summary', {})
        tasks = routed_order.get('tasks', [])

        lines = [
            '🛒 [신규 주문 구매요청]',
            f'주문번호: {order_number}  (ID: {order_id})',
            f'고객: {customer_name} <{customer_email}>',
            f'총 태스크: {summary.get("total_tasks", 0)}개',
            '',
        ]

        # 벤더별로 그룹화하여 출력
        by_vendor: dict[str, list[dict]] = {}
        for task in tasks:
            v = task.get('vendor', 'UNKNOWN')
            by_vendor.setdefault(v, []).append(task)

        for vendor, vtasks in by_vendor.items():
            lines.append(f'▶ {vendor} ({len(vtasks)}건)')
            for task in vtasks:
                qty = task.get('quantity', 1)
                price = task.get('buy_price', 0)
                currency = task.get('buy_currency', '')
                lines.append(f'  • [{task["sku"]}] {task.get("title", "")}')
                lines.append(f'    수량: {qty} / 구매가: {price:,.0f} {currency}')
                lines.append(f'    구매처: {task.get("src_url", "(미등록)")}')
                lines.append(f'    배대지: {task.get("forwarder_address", "")}')
                lines.append(f'    지시: {task.get("instructions", "")}')
            lines.append('')

        by_vendor_summary = summary.get('by_vendor', {})
        by_forwarder_summary = summary.get('by_forwarder', {})
        lines.append(f'벤더별: {by_vendor_summary}')
        lines.append(f'배대지별: {by_forwarder_summary}')

        return '\n'.join(lines)

    def _format_notion_tasks(self, routed_order: dict) -> list[dict]:
        """Notion 태스크 생성용 데이터 포맷팅.

        각 태스크별로 개별 Notion 페이지 생성.
        Notion 속성: Name, Order ID, SKU, Vendor, Status(신규), Source URL, Forwarder
        """
        order_id = routed_order.get('order_id', '')
        order_number = routed_order.get('order_number', '')
        result = []
        for task in routed_order.get('tasks', []):
            sku = task.get('sku', '')
            vendor = task.get('vendor', '')
            result.append({
                'title': f'구매요청 {sku} (주문 {order_number})',
                'sku': sku,
                'vendor': vendor,
                'src_url': task.get('src_url', ''),
                'forwarder': task.get('forwarder', ''),
                'order_id': order_id,
                'status': '신규',
            })
        return result
