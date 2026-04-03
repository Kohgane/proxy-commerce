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


def _format_tracking(data, **kwargs) -> str:
    """배송 추적 메시지를 포맷한다."""
    status_emoji = {
        'picked_up': '📦',
        'in_transit': '🚚',
        'out_for_delivery': '🏃',
        'delivered': '✅',
        'exception': '⚠️',
    }
    # data may be a ShipmentRecord dataclass or a plain dict
    if hasattr(data, 'tracking_number'):
        tn = data.tracking_number
        carrier = data.carrier
        status = data.status.value if hasattr(data.status, 'value') else str(data.status)
        events = data.events or []
    else:
        tn = data.get('tracking_number', '-')
        carrier = data.get('carrier', '-')
        status = data.get('status', '-')
        events = data.get('events', [])

    emoji = status_emoji.get(status, '📦')
    lines = [f"*{emoji} 배송 추적*\n"]
    lines.append(f"운송장: *{tn}*")
    lines.append(f"택배사: *{carrier}*")
    lines.append(f"상태: *{status}*")
    if events:
        lines.append("\n*최근 이벤트:*")
        for ev in events[-3:]:
            if hasattr(ev, 'description'):
                lines.append(f"• {ev.location} — {ev.description}")
            else:
                lines.append(f"• {ev.get('location', '')} — {ev.get('description', '')}")
    return '\n'.join(lines)


def _format_cs_tickets(data, **kwargs) -> str:
    label = kwargs.get('label', '전체')
    if not data:
        return f'📋 CS 티켓 목록 ({label}): 없음'
    lines = [f'📋 CS 티켓 목록 ({label}) — {len(data)}건']
    for t in data:
        ticket_id = getattr(t, 'id', t.get('id', '')) if not hasattr(t, 'id') else t.id
        subject = getattr(t, 'subject', '') if hasattr(t, 'subject') else t.get('subject', '')
        status = getattr(t, 'status', '') if hasattr(t, 'status') else t.get('status', '')
        priority = getattr(t, 'priority', '') if hasattr(t, 'priority') else t.get('priority', '')
        # Handle enum values
        if hasattr(status, 'value'):
            status = status.value
        if hasattr(priority, 'value'):
            priority = priority.value
        lines.append(f'• [{priority}] {subject} ({status}) — {ticket_id[:8]}…')
    return '\n'.join(lines)


def _format_cs_reply(data, **kwargs) -> str:
    if data is None:
        return '❌ CS 답변 전송 실패'
    msg_id = getattr(data, 'id', '') if hasattr(data, 'id') else data.get('id', '')
    content = getattr(data, 'content', '') if hasattr(data, 'content') else data.get('content', '')
    return f'✅ CS 답변 전송 완료\n메시지 ID: {msg_id}\n내용: {content}'


def _format_analytics(data: dict, label: str = '', **kwargs) -> str:
    """분석 데이터 포맷."""
    if not data:
        return '📊 분석 데이터 없음'
    if 'error' in data:
        return f'❌ {data["error"]}'
    if 'message' in data:
        return f'📊 [{label}] {data["message"]}'
    lines = [f'📊 분석 결과 [{label}]']
    for key, value in data.items():
        if not isinstance(value, (list, dict)):
            lines.append(f'  {key}: {value}')
    return '\n'.join(lines)


def _format_sync_inventory(data: dict, **kwargs) -> str:
    synced = data.get('synced_count', 0)
    ts = data.get('timestamp', '')
    return f'🔄 재고 동기화 완료\n동기화 SKU: {synced}건\n시각: {ts}'


def _format_stock_status(data: dict, label: str = '', **kwargs) -> str:
    if 'sku' in data:
        resolved = data.get('resolved_stock', 0)
        return f'📦 재고 상태 [{label}]\n결정 재고: {resolved}개'
    channels = data.get('channels', [])
    return f'📦 재고 동기화 상태\n등록 채널: {", ".join(channels)}'


def _format_translate(data: dict, **kwargs) -> str:
    req_id = data.get('request_id', '')[:8]
    status = data.get('status', '')
    translated = data.get('translated_text', '')
    return f'🌐 번역 요청 완료\nID: {req_id}…\n상태: {status}\n번역: {translated}'


def _format_translation_status(data: list, **kwargs) -> str:
    if not data:
        return '🌐 번역 요청: 없음'
    lines = [f'🌐 번역 요청 목록 — {len(data)}건']
    for req in data[:5]:
        req_id = req.get('request_id', '')[:8]
        status = req.get('status', '')
        lines.append(f'  • {req_id}… [{status}]')
    return '\n'.join(lines)


def _format_reprice(data: dict, label: str = '', **kwargs) -> str:
    processed = data.get('processed', 0)
    dry_run = data.get('dry_run', False)
    mode = '시뮬레이션' if dry_run else '적용'
    return f'💰 가격 산정 ({mode}) [{label}]\n처리 SKU: {processed}건'


def _format_price_history(data: list, label: str = '', **kwargs) -> str:
    change_rate = kwargs.get('change_rate', 0.0)
    if not data:
        return f'💰 가격 이력 [{label}]: 없음'
    lines = [f'💰 가격 이력 [{label}] — {len(data)}건 (변동률: {change_rate:.1f}%)']
    for entry in data[-5:]:
        lines.append(f'  • {entry.get("price")} ({entry.get("channel")})')
    return '\n'.join(lines)


def _format_suppliers(data: list, **kwargs) -> str:
    if not data:
        return '🏭 공급자 목록: 없음'
    lines = [f'🏭 공급자 목록 — {len(data)}개']
    for s in data[:5]:
        name = s.get('name', s.get('supplier_id', ''))
        active = '✅' if s.get('active') else '❌'
        lines.append(f'  • {active} {name}')
    return '\n'.join(lines)


def _format_supplier_score(data: dict, **kwargs) -> str:
    sid = data.get('supplier_id', '')
    score = data.get('score', 0)
    grade = data.get('grade', 'D')
    return f'🏭 공급자 점수\nID: {sid}\n점수: {score:.1f}\n등급: {grade}'


def _format_po_create(data: dict, **kwargs) -> str:
    po_id = data.get('po_id', '')[:8]
    sku = data.get('sku', '')
    qty = data.get('qty', 0)
    status = data.get('status', '')
    return f'📋 발주서 생성 완료\nPO ID: {po_id}…\nSKU: {sku}\n수량: {qty}\n상태: {status}'


def _format_returns(data, label: str = '', **kwargs) -> str:
    """반품/교환 목록 포맷."""
    if not data:
        return f'📦 반품 목록{f" — {label}" if label else ""}: 없음'
    lines = [f'📦 반품 목록{f" — {label}" if label else ""} ({len(data)}건)']
    for r in data[:5]:
        rid = str(r.get('id', ''))[:8]
        status = r.get('status', '')
        reason = r.get('reason', '')[:20]
        lines.append(f'  • [{rid}] {status} — {reason}')
    return '\n'.join(lines)


def _format_coupons(data, label: str = '', **kwargs) -> str:
    """쿠폰 목록 포맷."""
    if not data:
        return f'🎟 쿠폰 목록{f" — {label}" if label else ""}: 없음'
    lines = [f'🎟 쿠폰 목록{f" — {label}" if label else ""} ({len(data)}개)']
    for c in data[:5]:
        if c is None:
            continue
        code = c.get('code', '')
        ctype = c.get('type', '')
        value = c.get('value', '')
        active = '✅' if c.get('active') else '❌'
        lines.append(f'  • {active} {code} ({ctype}: {value})')
    return '\n'.join(lines)


def _format_categories(data, label: str = '', **kwargs) -> str:
    """카테고리 목록 포맷."""
    if not data:
        return f'📂 카테고리{f" — {label}" if label else ""}: 없음'
    lines = [f'📂 카테고리{f" — {label}" if label else ""} ({len(data)}개)']
    for c in data[:10]:
        name = c.get('name', '')
        active = '✅' if c.get('active', True) else '❌'
        lines.append(f'  • {active} {name}')
    return '\n'.join(lines)


def _format_jobs(data, label: str = '', **kwargs) -> str:
    """스케줄러 작업 목록 포맷."""
    if not data:
        return f'⏰ 작업 목록{f" — {label}" if label else ""}: 없음'
    lines = [f'⏰ 작업{f" — {label}" if label else ""} ({len(data)}개)']
    for j in data[:10]:
        name = j.get('name', j.get('job_name', ''))
        status = j.get('status', '')
        stype = j.get('schedule_type', '')
        sval = j.get('schedule_value', '')
        lines.append(f'  • [{status}] {name} ({stype}: {sval})')
    return '\n'.join(lines)


def _format_audit_log(data, label: str = '', **kwargs) -> str:
    """감사 로그 포맷."""
    if not data:
        return f'📋 감사 로그{f" — {label}" if label else ""}: 없음'
    lines = [f'📋 감사 로그{f" — {label}" if label else ""} ({len(data)}건)']
    for entry in data[:5]:
        ts = str(entry.get('timestamp', ''))[:19]
        etype = entry.get('event_type', '')
        actor = entry.get('actor', '')
        resource = entry.get('resource', '')[:20]
        lines.append(f'  • [{ts}] {etype} | {actor} | {resource}')
    return '\n'.join(lines)


def format_message(msg_type: str, data, **kwargs) -> str:
    """메시지 타입에 따라 포맷 함수 라우팅.

    Args:
        msg_type: 'status' | 'revenue' | 'stock' | 'fx' | 'error'
                  | 'reviews' | 'promos' | 'customer_segments' | 'customer_list'
                  | 'campaigns' | 'report' | 'abtest'
                  | 'competitor' | 'forecast' | 'trends' | 'rules'
                  | 'order_alerts' | 'settlement' | 'cs_tickets' | 'cs_reply'
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
        'tracking': lambda d: _format_tracking(d),
        'cs_tickets': lambda d: _format_cs_tickets(d, label=kwargs.get('label', '전체')),
        'cs_reply': lambda d: _format_cs_reply(d),
        'analytics': lambda d: _format_analytics(d, label=kwargs.get('label', '')),
        'sync_inventory': lambda d: _format_sync_inventory(d),
        'stock_status': lambda d: _format_stock_status(d, label=kwargs.get('label', '')),
        'translate': lambda d: _format_translate(d),
        'translation_status': lambda d: _format_translation_status(d),
        'reprice': lambda d: _format_reprice(d, label=kwargs.get('label', '')),
        'price_history': lambda d: _format_price_history(
            d, label=kwargs.get('label', ''), change_rate=kwargs.get('change_rate', 0.0)
        ),
        'suppliers': lambda d: _format_suppliers(d),
        'supplier_score': lambda d: _format_supplier_score(d),
        'po_create': lambda d: _format_po_create(d),
        'returns': lambda d: _format_returns(d, label=kwargs.get('label', '')),
        'coupons': lambda d: _format_coupons(d, label=kwargs.get('label', '')),
        'categories': lambda d: _format_categories(d, label=kwargs.get('label', '')),
        'jobs': lambda d: _format_jobs(d, label=kwargs.get('label', '')),
        'audit_log': lambda d: _format_audit_log(d, label=kwargs.get('label', '')),
        'wishlist': lambda d: _format_wishlist(d, label=kwargs.get('label', '')),
        'bundles': lambda d: _format_bundles(d, label=kwargs.get('label', '')),
        'currency': lambda d: _format_currency(d),
        'payment_status': lambda d: _format_payment_status(d),
        'images': lambda d: _format_images(d, label=kwargs.get('label', '')),
        'user_profile': lambda d: _format_user_profile(d),
        'user_addresses': lambda d: _format_user_addresses(d, label=kwargs.get('label', '')),
        'user_activity': lambda d: _format_user_activity(d, label=kwargs.get('label', '')),
        'search_results': lambda d: _format_search_results(d, label=kwargs.get('label', '')),
        'popular_searches': lambda d: _format_popular_searches(d),
        # Phase 49: 멀티테넌시
        'tenant_info': lambda d: _format_tenant_info(d),
        'tenant_usage': lambda d: _format_tenant_usage(d, label=kwargs.get('label', '')),
        # Phase 50: A/B 테스트
        'experiment_list': lambda d: _format_experiment_list(d),
        'experiment_result': lambda d: _format_experiment_result(d),
        # Phase 51: 웹훅 관리
        'webhook_list': lambda d: _format_webhook_list(d),
        'webhook_test': lambda d: _format_webhook_test(d, label=kwargs.get('label', '')),
        # Phase 54: 벤치마크
        'benchmark_result': lambda d: _format_benchmark_result(d, label=kwargs.get('label', '')),
        'benchmark_results': lambda d: _format_benchmark_results(d),
    }
    formatter = formatters.get(msg_type, lambda d: str(d))
    try:
        return formatter(data)
    except Exception as exc:
        logger.error("format_message('%s') 오류: %s", msg_type, exc)
        return f"메시지 포맷 오류: {exc}"


def _format_wishlist(data, label: str = '') -> str:
    """위시리스트 포맷."""
    header = f"*🛍️ 위시리스트{f' — {label}' if label else ''}*\n"
    if not data:
        return header + "항목 없음"
    lines = [header]
    for item in data:
        if 'product_id' in item:
            lines.append(f"• {item.get('product_id')} (우선순위: {item.get('priority', '-')})")
        elif 'name' in item:
            lines.append(f"• {item.get('name')} (id: {item.get('id', '-')})")
        else:
            lines.append(f"• {item}")
    return "\n".join(lines)


def _format_bundles(data, label: str = '') -> str:
    """번들 포맷."""
    header = f"*📦 번들{f' — {label}' if label else ''}*\n"
    if not data:
        return header + "번들 없음"
    lines = [header]
    for bundle in data:
        name = bundle.get('name', bundle.get('strategy', str(bundle)))
        status = bundle.get('status', '')
        btype = bundle.get('type', '')
        lines.append(f"• {name} ({btype}) [{status}]")
    return "\n".join(lines)


def _format_currency(data) -> str:
    """통화 변환 포맷."""
    if isinstance(data, dict) and 'formatted' in data:
        return (
            f"*💱 통화 변환*\n"
            f"{data.get('amount')} {data.get('from')} = "
            f"*{data.get('formatted')}* ({data.get('to')})"
        )
    return str(data)


def _format_payment_status(data) -> str:
    """결제 상태 포맷."""
    if isinstance(data, dict):
        pid = data.get('payment_id', '-')
        status = data.get('status', '-')
        return f"*💳 결제 상태*\nID: `{pid}`\n상태: *{status}*"
    return str(data)


def _format_images(data, label: str = '') -> str:
    """이미지 갤러리 포맷."""
    header = f"*🖼️ 이미지{f' — {label}' if label else ''}*\n"
    if not data:
        return header + "이미지 없음"
    lines = [header]
    for img in data:
        lines.append(f"• [{img.get('format', '?')}] {img.get('url', '-')}")
    return "\n".join(lines)


def _format_user_profile(data) -> str:
    """사용자 프로필 포맷."""
    if not isinstance(data, dict):
        return str(data)
    grade_emoji = {'bronze': '🥉', 'silver': '🥈', 'gold': '🥇', 'vip': '💎'}.get(
        data.get('grade', 'bronze'), '🥉'
    )
    return (
        f"*👤 내 프로필*\n"
        f"이름: {data.get('name', '-')}\n"
        f"이메일: {data.get('email', '-')}\n"
        f"등급: {grade_emoji} {data.get('grade', 'bronze').upper()}\n"
        f"누적 구매: {data.get('total_purchase_amount', '0')}원"
    )


def _format_user_addresses(data, label: str = '') -> str:
    """배송지 포맷."""
    header = f"*📍 배송지{f' — {label}' if label else ''}*\n"
    if not data:
        return header + "배송지 없음"
    lines = [header]
    for addr in data:
        lines.append(
            f"• {addr.get('recipient_name', '-')} / "
            f"{addr.get('address1', '-')}, {addr.get('city', '-')}"
        )
    return "\n".join(lines)


def _format_user_activity(data, label: str = '') -> str:
    """활동 로그 포맷."""
    header = f"*📋 활동 로그{f' — {label}' if label else ''}*\n"
    if not data:
        return header + "활동 없음"
    lines = [header]
    for record in data:
        lines.append(
            f"• [{record.get('activity_type', '-')}] "
            f"{record.get('recorded_at', '-')[:10]}"
        )
    return "\n".join(lines)


def _format_search_results(data, label: str = '') -> str:
    """검색 결과 포맷."""
    header = f"*🔍 검색 결과{f': {label}' if label else ''}*\n"
    if not data:
        return header + "결과 없음"
    lines = [header, f"총 {len(data)}건"]
    for product in data[:10]:
        lines.append(f"• {product.get('title', '-')} — {product.get('price', '-')}원")
    return "\n".join(lines)


def _format_popular_searches(data) -> str:
    """인기 검색어 포맷."""
    header = "*🔥 인기 검색어*\n"
    if not data:
        return header + "데이터 없음"
    lines = [header]
    for i, item in enumerate(data[:10], 1):
        if isinstance(item, dict):
            lines.append(f"{i}. {item.get('query', '-')} ({item.get('count', 0)}회)")
        else:
            lines.append(f"{i}. {item}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Phase 49: 멀티테넌시 포맷터
# ─────────────────────────────────────────────────────────────

def _format_tenant_info(data) -> str:
    """테넌트 정보 포맷."""
    if isinstance(data, dict) and 'tenant' in data:
        t = data['tenant']
        cfg = data.get('config', {})
        return (
            f"*🏢 테넌트 정보*\n"
            f"ID: `{t.get('tenant_id', '-')}`\n"
            f"이름: {t.get('name', '-')}\n"
            f"플랜: {t.get('plan', '-')}\n"
            f"상태: {'✅ 활성' if t.get('active') else '❌ 비활성'}\n"
            f"마진율: {cfg.get('margin_rate', '-')}"
        )
    tenants = data.get('tenants', data) if isinstance(data, dict) else data
    if not tenants:
        return "*🏢 테넌트 목록*\n테넌트 없음"
    lines = ["*🏢 테넌트 목록*"]
    for t in (tenants if isinstance(tenants, list) else [tenants]):
        lines.append(f"• {t.get('name', '-')} ({t.get('plan', '-')}) — "
                     f"{'활성' if t.get('active') else '비활성'}")
    return "\n".join(lines)


def _format_tenant_usage(data, label: str = '') -> str:
    """테넌트 사용량 포맷."""
    header = f"*📊 테넌트 사용량{f' — {label}' if label else ''}*\n"
    if isinstance(data, list):
        if not data:
            return header + "데이터 없음"
        lines = [header]
        for item in data:
            lines.append(
                f"• {item.get('tenant_id', '-')}: "
                f"API {item.get('api_calls', 0)}, "
                f"주문 {item.get('orders', 0)}, "
                f"상품 {item.get('products', 0)}"
            )
        return "\n".join(lines)
    return (
        header
        + f"API 호출: {data.get('api_calls', 0)}\n"
        + f"주문수: {data.get('orders', 0)}\n"
        + f"상품수: {data.get('products', 0)}"
    )


# ─────────────────────────────────────────────────────────────
# Phase 50: A/B 테스트 포맷터
# ─────────────────────────────────────────────────────────────

def _format_experiment_list(data) -> str:
    """실험 목록 포맷."""
    header = "*🧪 실험 목록*\n"
    if not data:
        return header + "실험 없음"
    lines = [header]
    for exp in data[:10]:
        lines.append(
            f"• [{exp.get('status', '-')}] {exp.get('name', '-')} "
            f"(ID: `{exp.get('experiment_id', '-')[:8]}...`)"
        )
    return "\n".join(lines)


def _format_experiment_result(data) -> str:
    """실험 결과 포맷."""
    name = data.get('name', '-')
    winner = data.get('winner', '-')
    lines = [f"*🧪 실험 결과: {name}*"]
    for v in data.get('variants', []):
        lines.append(
            f"• {v.get('variant', '-')}: "
            f"CVR {v.get('cvr', 0):.2%}, "
            f"노출 {v.get('impressions', 0)}"
        )
    if winner:
        lines.append(f"\n🏆 승자: {winner}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Phase 51: 웹훅 관리 포맷터
# ─────────────────────────────────────────────────────────────

def _format_webhook_list(data) -> str:
    """웹훅 목록 포맷."""
    header = "*🔔 웹훅 목록*\n"
    if not data:
        return header + "웹훅 없음"
    lines = [header]
    for w in data[:10]:
        lines.append(
            f"• {w.get('name', '-') or w.get('webhook_id', '-')[:8]} — "
            f"{w.get('url', '-')} "
            f"({'활성' if w.get('active') else '비활성'})"
        )
    return "\n".join(lines)


def _format_webhook_test(data, label: str = '') -> str:
    """웹훅 테스트 결과 포맷."""
    status = data.get('status', '-')
    icon = "✅" if status == "success" else "❌"
    return (
        f"*🔔 웹훅 테스트{f' — {label}' if label else ''}*\n"
        f"{icon} 상태: {status}\n"
        f"응답 코드: {data.get('response_code', '-')}"
    )


# ─────────────────────────────────────────────────────────────
# Phase 54: 벤치마크 포맷터
# ─────────────────────────────────────────────────────────────

def _format_benchmark_result(data, label: str = '') -> str:
    """벤치마크 결과 포맷."""
    stats = data.get('stats', {})
    profile = data.get('profile', {})
    return (
        f"*⚡ 벤치마크 결과{f': {label}' if label else ''}*\n"
        f"총 요청: {stats.get('count', 0)}\n"
        f"평균: {stats.get('mean', 0):.1f}ms\n"
        f"p95: {stats.get('p95', 0):.1f}ms\n"
        f"p99: {stats.get('p99', 0):.1f}ms\n"
        f"처리량: {data.get('throughput_rps', 0):.1f} RPS\n"
        f"에러율: {data.get('error_rate', 0):.1f}%"
    )


def _format_benchmark_results(data) -> str:
    """벤치마크 결과 목록 포맷."""
    header = "*⚡ 벤치마크 이력*\n"
    if not data:
        return header + "이력 없음"
    lines = [header]
    for report in data[-5:]:
        profile = report.get('profile', {})
        stats = report.get('stats', {})
        lines.append(
            f"• {profile.get('name', '-')}: "
            f"p95={stats.get('p95', 0):.1f}ms, "
            f"RPS={report.get('throughput_rps', 0):.1f}"
        )
    return "\n".join(lines)
