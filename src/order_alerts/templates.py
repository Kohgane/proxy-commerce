"""주문 알림 메시지 템플릿 모듈.

각 주문 상태에 맞는 텔레그램 메시지를 렌더링합니다.
"""

_PLATFORM_LABEL = {
    'coupang': '쿠팡',
    'naver': '네이버 스마트스토어',
}

_PLATFORM_EMOJI = {
    'coupang': '🛒',
    'naver': '🟢',
}


def _base_info(order: dict) -> tuple:
    """공통 주문 정보 추출."""
    platform = order.get('platform', 'unknown')
    emoji = _PLATFORM_EMOJI.get(platform, '📦')
    label = _PLATFORM_LABEL.get(platform, platform)
    order_number = order.get('order_number', order.get('order_id', 'N/A'))
    buyer_name = order.get('buyer_name', '')
    total_price = order.get('total_price', 0)
    price_str = f"{int(total_price):,}원" if total_price else 'N/A'

    product_names = order.get('product_names', [])
    quantities = order.get('quantities', [])
    items_lines = '\n'.join(
        f'  • {name} × {qty}' for name, qty in zip(product_names, quantities)
    ) or '  • (상품 정보 없음)'

    return emoji, label, order_number, buyer_name, price_str, items_lines


def render_order_received(order: dict) -> str:
    """주문 접수 메시지 렌더링."""
    emoji, label, order_number, buyer_name, price_str, items_lines = _base_info(order)
    created_at = order.get('created_at', '')
    time_line = f"\n🕐 주문시각: {created_at[:19].replace('T', ' ')}" if len(created_at) >= 19 else ''
    return (
        f"{emoji} *[{label}] 신규 주문 접수*\n\n"
        f"📋 주문번호: `{order_number}`\n"
        f"🛍 상품:\n{items_lines}\n"
        f"💰 결제금액: {price_str}\n"
        f"👤 구매자: {buyer_name}"
        f"{time_line}"
    )


def render_payment_confirmed(order: dict) -> str:
    """결제 확인 메시지 렌더링."""
    emoji, label, order_number, buyer_name, price_str, items_lines = _base_info(order)
    return (
        f"{emoji} *[{label}] 결제 확인 완료*\n\n"
        f"📋 주문번호: `{order_number}`\n"
        f"💳 결제금액: {price_str} 확인됨\n"
        f"👤 구매자: {buyer_name}\n"
        f"🛍 상품:\n{items_lines}"
    )


def render_shipping(order: dict) -> str:
    """배송 시작 메시지 렌더링."""
    emoji, label, order_number, buyer_name, price_str, items_lines = _base_info(order)
    tracking = order.get('tracking_number', '')
    tracking_line = f"\n🔍 운송장번호: `{tracking}`" if tracking else ''
    return (
        f"{emoji} *[{label}] 배송 시작*\n\n"
        f"📋 주문번호: `{order_number}`\n"
        f"🚚 상품이 발송되었습니다\n"
        f"👤 구매자: {buyer_name}\n"
        f"🛍 상품:\n{items_lines}"
        f"{tracking_line}"
    )


def render_delivered(order: dict) -> str:
    """배송 완료 메시지 렌더링."""
    emoji, label, order_number, buyer_name, price_str, items_lines = _base_info(order)
    return (
        f"{emoji} *[{label}] 배송 완료*\n\n"
        f"📋 주문번호: `{order_number}`\n"
        f"✅ 배송이 완료되었습니다\n"
        f"👤 구매자: {buyer_name}\n"
        f"🛍 상품:\n{items_lines}"
    )


def render_cancelled(order: dict) -> str:
    """주문 취소 메시지 렌더링."""
    emoji, label, order_number, buyer_name, price_str, items_lines = _base_info(order)
    reason = order.get('cancel_reason', '')
    reason_line = f"\n📝 취소사유: {reason}" if reason else ''
    return (
        f"{emoji} *[{label}] 주문 취소*\n\n"
        f"📋 주문번호: `{order_number}`\n"
        f"❌ 주문이 취소되었습니다\n"
        f"👤 구매자: {buyer_name}\n"
        f"💰 결제금액: {price_str}"
        f"{reason_line}"
    )


def render_refunded(order: dict) -> str:
    """환불 처리 메시지 렌더링."""
    emoji, label, order_number, buyer_name, price_str, items_lines = _base_info(order)
    return (
        f"{emoji} *[{label}] 환불 처리*\n\n"
        f"📋 주문번호: `{order_number}`\n"
        f"🔄 환불이 처리되었습니다\n"
        f"👤 구매자: {buyer_name}\n"
        f"💰 환불금액: {price_str}"
    )


_RENDERERS = {
    'order_received': render_order_received,
    'payment_confirmed': render_payment_confirmed,
    'shipping': render_shipping,
    'delivered': render_delivered,
    'cancelled': render_cancelled,
    'refunded': render_refunded,
}


def render_for_status(order: dict, status: str) -> str:
    """상태 코드에 따라 적절한 렌더러를 호출.

    Args:
        order: 정규화된 주문 딕셔너리
        status: 주문 상태 ('order_received', 'payment_confirmed', 'shipping',
                          'delivered', 'cancelled', 'refunded')

    Returns:
        포맷팅된 텔레그램 메시지 문자열
    """
    renderer = _RENDERERS.get(status)
    if renderer is None:
        return render_order_received(order)
    return renderer(order)
