"""텔레그램 메시지 포맷팅 — 마크다운 형식."""

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# 주문 상태 한국어 표시명
_STATUS_LABELS = {
    'new': '신규',
    'routed': '발주 대기',
    'ordered': '발주 완료',
    'shipped_vendor': '벤더 출고',
    'at_forwarder': '포워더 도착',
    'shipped_domestic': '국내 배송 중',
    'delivered': '배송 완료',
    'cancelled': '취소',
}


def _rate_change(current, prev) -> str:
    """환율 변동률 문자열 반환."""
    try:
        c = Decimal(str(current))
        p = Decimal(str(prev))
        if p == 0:
            return ''
        pct = (c - p) / p * 100
        sign = '+' if pct >= 0 else ''
        return f" ({sign}{float(pct):.2f}%)"
    except Exception:
        return ''


def _format_status(stats: dict, pending: list = None) -> str:
    """주문 현황 포맷."""
    total = stats.get('total', 0)
    by_status = stats.get('by_status', {})

    lines = ["*📦 주문 현황*\n"]
    lines.append(f"전체 주문: *{total}건*\n")

    if by_status:
        lines.append("상태별 현황:")
        for status, count in sorted(by_status.items()):
            if count > 0:
                label = _STATUS_LABELS.get(status, status)
                lines.append(f"  • {label}: {count}건")

    if pending:
        lines.append(f"\n미완료 주문: *{len(pending)}건*")

    return '\n'.join(lines)


def _format_revenue(data: dict, label: str = '') -> str:
    """매출 요약 포맷."""
    lines = [f"*💰 매출 요약 — {label}*\n"]

    total_orders = data.get('total_orders', 0)
    total_revenue_krw = data.get('total_revenue_krw', 0)
    total_margin_krw = data.get('total_margin_krw', 0)
    avg_margin_pct = data.get('avg_margin_pct', 0)

    lines.append(f"주문 수: *{total_orders}건*")
    lines.append(f"총 매출: *{int(total_revenue_krw):,}원*")
    lines.append(f"총 마진: *{int(total_margin_krw):,}원*")
    lines.append(f"평균 마진율: *{float(avg_margin_pct):.1f}%*")

    by_vendor = data.get('by_vendor', {})
    if by_vendor:
        lines.append("\n벤더별 매출:")
        for vendor, info in by_vendor.items():
            rev = int(info.get('revenue_krw', 0))
            cnt = info.get('orders', 0)
            lines.append(f"  • {vendor}: {rev:,}원 ({cnt}건)")

    return '\n'.join(lines)


def _format_stock(items: list, label: str = '') -> str:
    """재고 현황 포맷."""
    lines = [f"*📊 재고 현황 — {label}*\n"]
    if not items:
        lines.append("해당 조건의 상품이 없습니다.")
        return '\n'.join(lines)

    lines.append(f"총 {len(items)}개 상품:\n")
    for item in items[:20]:  # 최대 20개 표시
        sku = item.get('sku', '-')
        title = item.get('title', '-')[:20]
        stock = item.get('stock', '?')
        vendor = item.get('vendor', '-')
        lines.append(f"  • `{sku}` {title} — 재고: {stock} ({vendor})")

    if len(items) > 20:
        lines.append(f"\n_... 외 {len(items) - 20}개 생략_")

    return '\n'.join(lines)


def _format_fx(rates: dict, prev_rates: dict = None) -> str:
    """환율 포맷."""
    lines = ["*💱 현재 환율*\n"]

    pairs = [('USDKRW', 'USD/KRW'), ('JPYKRW', 'JPY/KRW'), ('EURKRW', 'EUR/KRW')]
    for key, label in pairs:
        val = rates.get(key, '-')
        change = ''
        if prev_rates and key in prev_rates:
            change = _rate_change(val, prev_rates[key])
        lines.append(f"  • {label}: *{val}*{change}")

    provider = rates.get('provider', '-')
    fetched_at = rates.get('fetched_at', '-')[:19]
    lines.append(f"\n_출처: {provider} | {fetched_at}_")

    return '\n'.join(lines)


def _format_error(message: str) -> str:
    """에러 메시지 포맷."""
    return f"*❌ 오류*\n\n{message}"


def _format_reviews(summary: dict, label: str = '') -> str:
    """리뷰 요약 포맷."""
    lines = [f"*⭐ 리뷰 요약 — {label}*\n"]
    total = summary.get('total_reviews', 0)
    avg = summary.get('average_rating', 0.0)
    negative = summary.get('negative_count', 0)
    lines.append(f"전체 리뷰: *{total}건*")
    lines.append(f"평균 평점: *{float(avg):.1f}점*")
    if negative:
        lines.append(f"부정 리뷰: *{negative}건* ⚠️")
    by_rating = summary.get('by_rating', {})
    if by_rating:
        lines.append("\n평점별 분포:")
        for rating in range(5, 0, -1):
            count = by_rating.get(rating, 0)
            stars = '⭐' * rating
            lines.append(f"  {stars}: {count}건")
    top_keywords = summary.get('top_keywords', [])
    if top_keywords:
        kws = ', '.join(f"{kw}({cnt})" for kw, cnt in top_keywords[:5])
        lines.append(f"\n주요 키워드: {kws}")
    return '\n'.join(lines)


def _format_promos(promos: list, label: str = '') -> str:
    """프로모션 목록 포맷."""
    lines = [f"*🎯 {label}*\n"]
    if not promos:
        lines.append("해당 프로모션이 없습니다.")
        return '\n'.join(lines)
    lines.append(f"총 {len(promos)}개:\n")
    for p in promos[:10]:
        name = p.get('name', '-')
        ptype = p.get('type', '-')
        value = p.get('value', '')
        end_date = str(p.get('end_date', ''))[:10]
        lines.append(f"  • *{name}* ({ptype}) {f'~ {end_date}' if end_date else ''}")
        if value:
            lines.append(f"    할인: {value}")
    if len(promos) > 10:
        lines.append(f"\n_... 외 {len(promos) - 10}개 생략_")
    return '\n'.join(lines)


def _format_customer_segments(summary: dict) -> str:
    """고객 세그먼트 요약 포맷."""
    lines = ["*👥 고객 세그먼트 요약*\n"]
    icons = {
        'VIP': '👑', 'LOYAL': '💚', 'AT_RISK': '⚠️',
        'NEW': '🆕', 'DORMANT': '😴',
    }
    for seg, info in summary.items():
        icon = icons.get(seg, '👤')
        count = info.get('count', 0)
        avg_spent = int(info.get('avg_spent_krw', 0))
        lines.append(f"{icon} *{seg}*: {count}명 (평균 {avg_spent:,}원)")
    return '\n'.join(lines)


def _format_customer_list(customers: list, label: str = '') -> str:
    """고객 목록 포맷."""
    lines = [f"*👥 고객 목록 — {label}*\n"]
    if not customers:
        lines.append("해당 고객이 없습니다.")
        return '\n'.join(lines)
    lines.append(f"총 {len(customers)}명:\n")
    for c in customers[:15]:
        email = c.get('email', '-')
        name = c.get('name', '-')
        orders = c.get('total_orders', 0)
        spent = int(float(c.get('total_spent_krw', 0) or 0))
        lines.append(f"  • {name} ({email}) — {orders}회 / {spent:,}원")
    if len(customers) > 15:
        lines.append(f"\n_... 외 {len(customers) - 15}명 생략_")
    return '\n'.join(lines)


def format_message(msg_type: str, data, **kwargs) -> str:
    """메시지 타입에 따라 포맷 함수 라우팅.

    Args:
        msg_type: 'status' | 'revenue' | 'stock' | 'fx' | 'error'
                  | 'reviews' | 'promos' | 'customer_segments' | 'customer_list'
        data: 각 타입에 맞는 데이터
        **kwargs: 추가 파라미터 (label, pending, prev_rates 등)
    """
    formatters = {
        'status': lambda d: _format_status(d, pending=kwargs.get('pending')),
        'revenue': lambda d: _format_revenue(d, label=kwargs.get('label', '')),
        'stock': lambda d: _format_stock(d, label=kwargs.get('label', '')),
        'fx': lambda d: _format_fx(d, prev_rates=kwargs.get('prev_rates')),
        'error': lambda d: _format_error(d),
        'reviews': lambda d: _format_reviews(d, label=kwargs.get('label', '')),
        'promos': lambda d: _format_promos(d, label=kwargs.get('label', '')),
        'customer_segments': lambda d: _format_customer_segments(d),
        'customer_list': lambda d: _format_customer_list(d, label=kwargs.get('label', '')),
    }
    formatter = formatters.get(msg_type, lambda d: str(d))
    try:
        return formatter(data)
    except Exception as exc:
        logger.error("format_message('%s') 오류: %s", msg_type, exc)
        return f"메시지 포맷 오류: {exc}"
