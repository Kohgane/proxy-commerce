"""src/bot/virtual_inventory_commands.py — 가상 재고 봇 커맨드 (Phase 113)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _pool():
    from src.virtual_inventory.virtual_stock import VirtualStockPool
    return VirtualStockPool()


def cmd_vstock(sku: str) -> str:
    """/vstock <sku> — 상품 가상 재고 조회."""
    from .formatters import format_message

    sku = sku.strip()
    if not sku:
        return format_message('error', 'SKU를 입력해주세요.\n사용법: /vstock <sku>')
    try:
        from src.virtual_inventory.virtual_stock import VirtualStockPool
        pool = VirtualStockPool()
        vs = pool.get_virtual_stock(sku)
        if vs is None:
            return format_message('warning', f'가상 재고 없음: `{sku}`')
        lines = [
            f'📦 *가상 재고: `{sku}`*\n',
            f'• 총 가용: {vs.total_available}개',
            f'• 예약: {vs.reserved}개',
            f'• 판매 가능: {vs.sellable}개',
            f'• 소싱처 수: {len(vs.sources)}개',
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vstock 오류: %s", exc)
        return format_message('error', f'조회 실패: {exc}')


def cmd_vstock_all() -> str:
    """/vstock_all — 전체 가상 재고 요약."""
    from .formatters import format_message

    try:
        from src.virtual_inventory.virtual_stock import VirtualStockPool
        pool = VirtualStockPool()
        stocks = pool.get_all_virtual_stocks()
        if not stocks:
            return format_message('info', '등록된 가상 재고 없음')
        lines = [f'📦 *전체 가상 재고 ({len(stocks)}종)*\n']
        for vs in stocks[:20]:
            lines.append(f'• [{vs.product_id}] 가용={vs.total_available} / 판매={vs.sellable}')
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vstock_all 오류: %s", exc)
        return format_message('error', f'조회 실패: {exc}')


def cmd_vstock_low() -> str:
    """/vstock_low — 재고 부족 상품 목록."""
    from .formatters import format_message

    try:
        from src.virtual_inventory.virtual_stock import VirtualStockPool
        pool = VirtualStockPool()
        stocks = pool.get_all_virtual_stocks()
        low = [vs for vs in stocks if 0 < vs.sellable <= 3]
        if not low:
            return format_message('info', '재고 부족 상품 없음')
        lines = [f'⚠️ *재고 부족 ({len(low)}종)*\n']
        for vs in low:
            lines.append(f'• [{vs.product_id}] 판매 가능: {vs.sellable}개')
        return format_message('warning', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vstock_low 오류: %s", exc)
        return format_message('error', f'조회 실패: {exc}')


def cmd_vstock_out() -> str:
    """/vstock_out — 재고 소진 상품 목록."""
    from .formatters import format_message

    try:
        from src.virtual_inventory.virtual_stock import VirtualStockPool
        pool = VirtualStockPool()
        stocks = pool.get_all_virtual_stocks()
        out = [vs for vs in stocks if vs.sellable == 0]
        if not out:
            return format_message('info', '재고 소진 상품 없음')
        lines = [f'❌ *재고 소진 ({len(out)}종)*\n']
        for vs in out:
            lines.append(f'• [{vs.product_id}]')
        return format_message('error', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vstock_out 오류: %s", exc)
        return format_message('error', f'조회 실패: {exc}')


def cmd_vstock_alerts() -> str:
    """/vstock_alerts — 재고 알림 목록."""
    from .formatters import format_message

    try:
        from src.virtual_inventory.stock_alerts import VirtualStockAlertService
        svc = VirtualStockAlertService()
        summary = svc.get_alert_summary()
        lines = [
            '🔔 *재고 알림 요약*\n',
            f'• 전체: {summary.get("total", 0)}개',
            f'• 미확인: {summary.get("unacknowledged", 0)}개',
        ]
        for sev, cnt in summary.get('by_severity', {}).items():
            lines.append(f'• {sev}: {cnt}개')
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vstock_alerts 오류: %s", exc)
        return format_message('error', f'알림 조회 실패: {exc}')


def cmd_vstock_reserve(sku: str, qty: str) -> str:
    """/vstock_reserve <sku> <qty> — 재고 예약."""
    from .formatters import format_message

    sku = sku.strip()
    if not sku:
        return format_message('error', 'SKU를 입력해주세요.\n사용법: /vstock_reserve <sku> <qty>')
    try:
        quantity = int(qty)
    except (ValueError, TypeError):
        return format_message('error', '수량은 정수여야 합니다.')
    try:
        from src.virtual_inventory.virtual_stock import VirtualStockPool
        pool = VirtualStockPool()
        reservation = pool.reserve_stock(sku, quantity)
        lines = [
            f'✅ *예약 완료: `{sku}`*\n',
            f'• 예약 ID: `{reservation.reservation_id}`',
            f'• 수량: {reservation.quantity}개',
            f'• 상태: {reservation.status.value}',
        ]
        return format_message('info', '\n'.join(lines))
    except ValueError as exc:
        return format_message('error', str(exc))
    except Exception as exc:
        logger.error("cmd_vstock_reserve 오류: %s", exc)
        return format_message('error', f'예약 실패: {exc}')


def cmd_vstock_allocate(sku: str, qty: str) -> str:
    """/vstock_allocate <sku> <qty> — 소싱처 할당."""
    from .formatters import format_message

    sku = sku.strip()
    try:
        quantity = int(qty)
    except (ValueError, TypeError):
        return format_message('error', '수량은 정수여야 합니다.')
    try:
        from src.virtual_inventory.source_allocator import SourceAllocator
        allocator = SourceAllocator()
        result = allocator.allocate(sku, quantity)
        lines = [
            f'🔀 *할당 완료: `{sku}`*\n',
            f'• 할당 ID: `{result.allocation_id}`',
            f'• 수량: {result.quantity}개',
            f'• 총 비용: {result.total_cost:,.0f}',
            f'• 예상 배송: {result.estimated_delivery_days}일',
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vstock_allocate 오류: %s", exc)
        return format_message('error', f'할당 실패: {exc}')


def cmd_vstock_sync() -> str:
    """/vstock_sync — 채널 재고 동기화."""
    from .formatters import format_message

    try:
        from src.virtual_inventory.inventory_sync_bridge import InventorySyncBridge
        bridge = InventorySyncBridge()
        result = bridge.sync_to_channels()
        return format_message(
            'info',
            f'🔄 *채널 동기화 완료*\n• 동기화: {result.get("synced", 0)}개\n• 시간: {result.get("timestamp", "")}',
        )
    except Exception as exc:
        logger.error("cmd_vstock_sync 오류: %s", exc)
        return format_message('error', f'동기화 실패: {exc}')


def cmd_vstock_health() -> str:
    """/vstock_health — 재고 건강도."""
    from .formatters import format_message

    try:
        from src.virtual_inventory.stock_analytics import VirtualStockAnalytics
        analytics = VirtualStockAnalytics()
        health = analytics.get_stock_health()
        lines = [
            '💚 *재고 건강도*\n',
            f'• 정상: {health.get("healthy_pct", 0)}%',
            f'• 부족: {health.get("low_stock_pct", 0)}%',
            f'• 소진: {health.get("out_of_stock_pct", 0)}%',
            f'• 과잉: {health.get("overstock_pct", 0)}%',
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vstock_health 오류: %s", exc)
        return format_message('error', f'건강도 조회 실패: {exc}')


def cmd_vstock_risk() -> str:
    """/vstock_risk — 단일 소싱처 위험 상품."""
    from .formatters import format_message

    try:
        from src.virtual_inventory.stock_analytics import VirtualStockAnalytics
        analytics = VirtualStockAnalytics()
        risks = analytics.get_single_source_products()
        if not risks:
            return format_message('info', '단일 소싱처 위험 상품 없음')
        lines = [f'⚠️ *단일 소싱처 위험 ({len(risks)}종)*\n']
        for pid in risks[:20]:
            lines.append(f'• {pid}')
        return format_message('warning', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vstock_risk 오류: %s", exc)
        return format_message('error', f'위험 조회 실패: {exc}')


def cmd_vstock_dashboard() -> str:
    """/vstock_dashboard — 가상 재고 대시보드."""
    from .formatters import format_message

    try:
        from src.virtual_inventory.virtual_inventory_dashboard import VirtualInventoryDashboard
        from src.virtual_inventory.virtual_stock import VirtualStockPool
        from src.virtual_inventory.stock_alerts import VirtualStockAlertService
        from src.virtual_inventory.stock_analytics import VirtualStockAnalytics
        from src.virtual_inventory.inventory_sync_bridge import InventorySyncBridge
        from src.virtual_inventory.source_allocator import SourceAllocator

        pool = VirtualStockPool()
        svc = VirtualStockAlertService()
        svc.set_stock_pool(pool)
        analytics = VirtualStockAnalytics()
        analytics.set_stock_pool(pool)
        bridge = InventorySyncBridge()
        bridge.set_stock_pool(pool)
        allocator = SourceAllocator()
        allocator.set_stock_pool(pool)

        dashboard = VirtualInventoryDashboard()
        dashboard.set_components(pool, svc, analytics, bridge, allocator)
        data = dashboard.get_dashboard_data()

        health = data.get('stock_health', {})
        alerts = data.get('alerts', {})
        reservations = data.get('reservations', {})
        lines = [
            '📊 *가상 재고 대시보드*\n',
            f'• 정상: {health.get("healthy_pct", 0)}% / 소진: {health.get("out_of_stock_pct", 0)}%',
            f'• 알림: {alerts.get("total", 0)}개 (미확인: {alerts.get("unacknowledged", 0)})',
            f'• 예약: {reservations.get("pending_count", 0)}건 대기',
            f'• 단일 소싱처 위험: {len(data.get("single_source_risks", []))}종',
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vstock_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')
