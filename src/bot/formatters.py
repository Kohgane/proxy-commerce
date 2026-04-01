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


def _format_campaigns(campaigns: list, label: str = '') -> str:
    """캠페인 목록 포맷."""
    lines = [f"*📣 {label}*\n"]
    if not campaigns:
        lines.append("캠페인이 없습니다.")
        return '\n'.join(lines)
    lines.append(f"총 {len(campaigns)}개:\n")
    for c in campaigns[:10]:
        name = c.get('name', '-')
        status = c.get('status', '-')
        ctype = c.get('type', '-')
        budget = int(float(c.get('budget_krw', 0) or 0))
        lines.append(f"  • *{name}* [{status}] ({ctype}) — {budget:,}원")
    if len(campaigns) > 10:
        lines.append(f"\n_... 외 {len(campaigns) - 10}개 생략_")
    return '\n'.join(lines)


def _format_report(data: dict, label: str = '') -> str:
    """리포트 요약 포맷."""
    rtype = data.get('report_type', label)
    lines = [f"*📊 {rtype.upper()} 리포트*\n"]
    if 'error' in data:
        lines.append(f"오류: {data['error']}")
        return '\n'.join(lines)
    if rtype == 'sales':
        lines.append(f"총 주문: *{data.get('total_orders', 0)}건*")
        lines.append(f"총 매출: *{int(data.get('total_revenue_krw', 0)):,}원*")
        lines.append(f"평균 주문: *{int(data.get('avg_order_krw', 0)):,}원*")
    elif rtype == 'inventory':
        lines.append(f"전체 SKU: *{data.get('total_skus', 0)}*")
        lines.append(f"재고 없음: *{data.get('out_of_stock', 0)}*")
        lines.append(f"저재고: *{data.get('low_stock', 0)}*")
    elif rtype == 'customers':
        lines.append(f"전체 고객: *{data.get('total_customers', 0)}명*")
        lines.append(f"신규 고객: *{data.get('new_customers', 0)}명*")
    elif rtype == 'marketing':
        lines.append(f"전체 캠페인: *{data.get('total_campaigns', 0)}*")
        lines.append(f"활성 캠페인: *{data.get('active_campaigns', 0)}*")
        lines.append(f"총 예산: *{int(data.get('total_budget_krw', 0)):,}원*")
    return '\n'.join(lines)


def _format_abtest(data: dict, label: str = '') -> str:
    """A/B 테스트 결과 포맷."""
    lines = [f"*🧪 A/B 테스트 — {label}*\n"]
    if not data:
        lines.append("데이터가 없습니다.")
        return '\n'.join(lines)
    for variant in ('A', 'B'):
        info = data.get(variant, {})
        impressions = info.get('impressions', 0)
        conversions = info.get('conversions', 0)
        rate = info.get('conversion_rate', 0.0)
        lines.append(f"  *변형 {variant}*: 노출 {impressions} / 전환 {conversions} ({rate:.1%})")
    significant = data.get('is_significant', False)
    lines.append(f"\n통계적 유의성: {'✅ 유의미' if significant else '❌ 유의미하지 않음'}")
    return '\n'.join(lines)


def _format_competitor(data, label: str = '') -> str:
    """경쟁사 가격 비교 포맷."""
    lines = [f"*🏪 경쟁사 가격 비교 — {label}*\n"]

    # 단일 SKU 비교 케이스
    if isinstance(data, dict) and 'our_sku' in data and 'competitors' in data:
        our_price = data.get('our_price_krw', 0)
        lines.append(f"우리 가격: *{int(our_price):,}원*")
        lines.append(f"경쟁사 최저가: *{int(data.get('best_competitor_price_krw', 0)):,}원*\n")
        competitors = data.get('competitors', [])
        if competitors:
            lines.append("경쟁사 목록:")
            for c in competitors[:10]:
                name = c.get('competitor_name', '-')
                price_krw = c.get('competitor_price_krw', 0)
                diff = c.get('price_diff_pct', 0)
                sign = '+' if diff >= 0 else ''
                lines.append(f"  • {name}: {int(price_krw):,}원 ({sign}{diff:.1f}%)")
        else:
            lines.append("경쟁사 데이터 없음")
        return '\n'.join(lines)

    # 전체 요약 케이스
    overpriced = data.get('overpriced', [])
    underpriced = data.get('underpriced', [])
    lines.append(f"가격 경쟁력 부족: *{len(overpriced)}개*")
    lines.append(f"마진 개선 가능: *{len(underpriced)}개*")

    if overpriced:
        lines.append("\n🚨 더 비싼 상품 (상위 5개):")
        for item in overpriced[:5]:
            lines.append(
                f"  • `{item['our_sku']}` +{item['price_diff_pct']:.1f}% "
                f"[{item['competitor_name']}]"
            )

    if underpriced:
        lines.append("\n💡 더 저렴한 상품 (상위 5개):")
        for item in underpriced[:5]:
            lines.append(
                f"  • `{item['our_sku']}` {item['price_diff_pct']:.1f}% "
                f"[{item['competitor_name']}]"
            )

    return '\n'.join(lines)


def _format_forecast(data: dict, label: str = '') -> str:
    """수요 예측 포맷."""
    lines = [f"*🔮 수요 예측 — {label}*\n"]

    forecast = data.get('forecast')
    if forecast:
        sku = forecast.get('sku', label)
        predicted = forecast.get('predicted_qty', 0)
        confidence = forecast.get('confidence', '-')
        trend = forecast.get('trend', '-')
        avg_daily = forecast.get('avg_daily_demand', 0)
        lines.append(f"SKU: `{sku}`")
        lines.append(f"30일 예측 수요: *{predicted}개*")
        lines.append(f"일평균 수요: {avg_daily:.2f}개")
        lines.append(f"추세: {trend} | 신뢰도: {confidence}")

        stockout = data.get('stockout_risk')
        if stockout:
            days = stockout.get('days_of_stock')
            lines.append(f"\n⚠️ 재고 소진 예상: *{days:.0f}일 후*" if days else "")
        return '\n'.join(lines)

    # 전체 소진 위험 목록
    at_risk = data.get('stockout_risk', [])
    if not at_risk:
        lines.append("14일 내 소진 위험 상품 없음 ✅")
        return '\n'.join(lines)

    lines.append(f"⚠️ 14일 내 재고 소진 위험: *{len(at_risk)}개*\n")
    for item in at_risk[:10]:
        sku = item.get('sku', '-')
        days = item.get('days_of_stock')
        stock = item.get('current_stock', 0)
        days_str = f"{days:.0f}일" if days is not None else "즉시"
        lines.append(f"  • `{sku}` 재고 {stock}개 → {days_str} 후 소진")

    if len(at_risk) > 10:
        lines.append(f"\n_... 외 {len(at_risk) - 10}개_")

    return '\n'.join(lines)


def _format_trends(items: list, label: str = '') -> str:
    """상품 트렌드 포맷."""
    lines = [f"*📈 상품 트렌드 — {label}*\n"]

    if not items:
        lines.append("트렌드 데이터가 없습니다.")
        return '\n'.join(lines)

    lines.append(f"총 {len(items)}개 상품:\n")
    grade_icons = {
        'Star': '⭐', 'Cash Cow': '🐄', 'Rising': '🚀', 'Declining': '📉',
    }
    for item in items[:15]:
        sku = item.get('sku', '-')
        grade = item.get('grade', '-')
        growth = item.get('growth_rate_pct', 0)
        sales = item.get('total_sales', 0)
        icon = grade_icons.get(grade, '•')
        sign = '+' if growth >= 0 else ''
        lines.append(
            f"  {icon} `{sku}` [{grade}] 성장 {sign}{growth:.1f}% / {sales}개 판매"
        )

    if len(items) > 15:
        lines.append(f"\n_... 외 {len(items) - 15}개 생략_")

    return '\n'.join(lines)


def _format_rules(data, label: str = '') -> str:
    """자동화 규칙 포맷."""
    lines = [f"*⚙️ 자동화 규칙 — {label}*\n"]

    if isinstance(data, dict) and 'total' in data:
        # stats 케이스
        lines.append(f"전체 규칙: *{data.get('total', 0)}개*")
        lines.append(f"활성: *{data.get('enabled', 0)}개*")
        lines.append(f"비활성: *{data.get('disabled', 0)}개*")
        by_trigger = data.get('by_trigger', {})
        if by_trigger:
            lines.append("\n트리거별:")
            for trigger, count in by_trigger.items():
                lines.append(f"  • {trigger}: {count}개")
        return '\n'.join(lines)

    # list 케이스
    rules = data if isinstance(data, list) else []
    if not rules:
        lines.append("등록된 규칙이 없습니다.")
        return '\n'.join(lines)

    lines.append(f"총 {len(rules)}개:\n")
    for r in rules[:10]:
        name = r.get('name', '-')
        trigger = r.get('trigger', '-')
        enabled = str(r.get('enabled', '1')) in ('1', 'true', 'True')
        status = '✅' if enabled else '❌'
        lines.append(f"  {status} *{name}* ({trigger})")

    if len(rules) > 10:
        lines.append(f"\n_... 외 {len(rules) - 10}개 생략_")

    return '\n'.join(lines)


def _format_order_alerts(data: dict, label: str = '') -> str:
    """주문 알림 현황 포맷."""
    orders = data.get('orders', [])
    total = data.get('total', len(orders))
    lines = [f"*🔔 주문 알림 현황*\n"]
    lines.append(f"최근 주문: *{total}건*\n")

    if not orders:
        lines.append("최근 주문 알림이 없습니다.")
        return '\n'.join(lines)

    _platform_emoji = {'coupang': '🛒', 'naver': '🟢'}
    for order in orders[:10]:
        platform = order.get('platform', 'unknown')
        emoji = _platform_emoji.get(platform, '📦')
        order_number = order.get('order_number', order.get('order_id', 'N/A'))
        status = order.get('status', '-')
        buyer = order.get('buyer_name', '')
        lines.append(f"  {emoji} `{order_number}` [{status}] {buyer}")

    if total > 10:
        lines.append(f"\n_... 외 {total - 10}건 생략_")

    return '\n'.join(lines)


def _format_settlement(data: dict, label: str = '') -> str:
    """정산 요약 메시지를 포맷한다."""
    period_label = {'today': '오늘', 'week': '이번 주', 'month': '이번 달'}.get(label, label or '전체')
    lines = [f"*💰 정산 요약 — {period_label}*\n"]
    lines.append(f"주문 수: *{data.get('count', 0)}건*")
    lines.append(f"총 매출: *{data.get('total_revenue', 0):,.0f}원*")
    lines.append(f"총 원가: *{data.get('total_cost', 0):,.0f}원*")
    lines.append(f"총 수수료: *{data.get('total_fees', 0):,.0f}원*")
    lines.append(f"총 배송비: *{data.get('total_shipping', 0):,.0f}원*")
    net = data.get('total_net_profit', 0)
    emoji = '📈' if net >= 0 else '📉'
    lines.append(f"순이익: {emoji} *{net:,.0f}원*")
    return '\n'.join(lines)


def format_message(msg_type: str, data, **kwargs) -> str:
    """메시지 타입에 따라 포맷 함수 라우팅.

    Args:
        msg_type: 'status' | 'revenue' | 'stock' | 'fx' | 'error'
                  | 'reviews' | 'promos' | 'customer_segments' | 'customer_list'
                  | 'campaigns' | 'report' | 'abtest'
                  | 'competitor' | 'forecast' | 'trends' | 'rules'
                  | 'order_alerts' | 'settlement'
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
        'campaigns': lambda d: _format_campaigns(d, label=kwargs.get('label', '')),
        'report': lambda d: _format_report(d, label=kwargs.get('label', '')),
        'abtest': lambda d: _format_abtest(d, label=kwargs.get('label', '')),
        'competitor': lambda d: _format_competitor(d, label=kwargs.get('label', '')),
        'forecast': lambda d: _format_forecast(d, label=kwargs.get('label', '')),
        'trends': lambda d: _format_trends(d, label=kwargs.get('label', '')),
        'rules': lambda d: _format_rules(d, label=kwargs.get('label', '')),
        'order_alerts': lambda d: _format_order_alerts(d, label=kwargs.get('label', '')),
        'settlement': lambda d: _format_settlement(d, label=kwargs.get('label', '')),
    }
    formatter = formatters.get(msg_type, lambda d: str(d))
    try:
        return formatter(data)
    except Exception as exc:
        logger.error("format_message('%s') 오류: %s", msg_type, exc)
        return f"메시지 포맷 오류: {exc}"
