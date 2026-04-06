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


# ─────────────────────────────────────────────────────────────
# Phase 67: 실시간 대시보드 포맷터
# ─────────────────────────────────────────────────────────────

def _format_realtime_status(data) -> str:
    return (
        f"*🔴 실시간 연결 상태*\n"
        f"연결된 클라이언트: {data.get('total_connections', 0)}개\n"
        f"활성 채널: {data.get('active_channels', 0)}개\n"
        f"하트비트 성공률: {data.get('heartbeat_rate', 0):.1%}"
    )


def _format_realtime_metrics(data) -> str:
    orders = data.get('orders', {})
    revenue = data.get('revenue', {})
    return (
        f"*📊 실시간 메트릭*\n"
        f"주문: 전체 {orders.get('count', 0)}건 / 대기 {orders.get('pending', 0)}건\n"
        f"오늘 매출: {revenue.get('today', 0):,}원\n"
        f"에러율: {data.get('error_rate', 0):.2%}"
    )


# ─────────────────────────────────────────────────────────────
# Phase 68: 데이터 교환 포맷터
# ─────────────────────────────────────────────────────────────

def _format_export(data) -> str:
    return (
        f"*📤 데이터 내보내기*\n"
        f"형식: {data.get('format', '-')}\n"
        f"레코드: {data.get('records', 0)}건\n"
        f"완료 시각: {str(data.get('exported_at', '-'))[:19]}"
    )


def _format_import_status(data) -> str:
    if isinstance(data, list):
        return f"*📥 가져오기 현황*\n작업 수: {len(data)}개"
    return (
        f"*📥 가져오기 현황*\n"
        f"처리: {data.get('records_processed', 0)}건\n"
        f"성공: {data.get('records_valid', 0)}건\n"
        f"실패: {data.get('records_invalid', 0)}건"
    )


# ─────────────────────────────────────────────────────────────
# Phase 69: 규칙 엔진 포맷터
# ─────────────────────────────────────────────────────────────

def _format_rules_list(data) -> str:
    header = f"*⚖️ 규칙 목록 ({len(data)}개)*\n"
    if not data:
        return header + "규칙 없음"
    lines = [header]
    for r in data[:5]:
        status = '✅' if r.get('enabled', True) else '❌'
        lines.append(f"• {status} {r.get('name', '-')} (우선순위: {r.get('priority', 0)})")
    return "\n".join(lines)


def _format_rules_test(data) -> str:
    results = data.get('results', [])
    return (
        f"*⚖️ 규칙 테스트 결과*\n"
        f"규칙 ID: {str(data.get('rule_id', '-'))[:8]}...\n"
        f"실행된 액션: {len(results)}개"
    )


# ─────────────────────────────────────────────────────────────
# Phase 70: KPI 포맷터
# ─────────────────────────────────────────────────────────────

def _format_kpi_summary(data) -> str:
    header = f"*📈 KPI 요약 ({len(data)}개)*\n"
    if not data:
        return header + "KPI 없음"
    lines = [header]
    for name, value in list(data.items())[:5]:
        lines.append(f"• {name}: {value}")
    return "\n".join(lines)


def _format_kpi_detail(data) -> str:
    return (
        f"*📈 KPI 상세*\n"
        f"이름: {data.get('name', '-')}\n"
        f"목표: {data.get('target', 0)} {data.get('unit', '')}\n"
        f"주기: {data.get('period', '-')}\n"
        f"공식: {data.get('formula', '-')}"
    )


def _format_kpi_alerts(data) -> str:
    header = f"*🔔 KPI 알림 ({len(data)}개)*\n"
    if not data:
        return header + "알림 없음"
    lines = [header]
    for a in data[:5]:
        lines.append(f"• [{a.get('alert_type', '-')}] {a.get('kpi_name', '-')}: {a.get('current_value', 0)}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Phase 71: 마켓플레이스 동기화 포맷터
# ─────────────────────────────────────────────────────────────

def _format_sync_marketplace(data) -> str:
    return (
        f"*🔄 마켓플레이스 동기화*\n"
        f"마켓플레이스: {data.get('marketplace', '-')}\n"
        f"작업 유형: {data.get('job_type', '-')}\n"
        f"상태: {data.get('status', '-')}\n"
        f"동기화: {data.get('records_synced', 0)}건"
    )


def _format_sync_status(data) -> str:
    marketplaces = data.get('marketplaces', {})
    header = f"*🔄 동기화 현황*\n"
    lines = [header]
    for name, status in marketplaces.items():
        lines.append(f"• {name}: {status.get('status', '-')} ({status.get('last_sync', '-')})")
    return "\n".join(lines) if len(lines) > 1 else header + "동기화 없음"


def _format_sync_logs(data) -> str:
    return (
        f"*🔄 동기화 로그 요약*\n"
        f"전체: {data.get('total_jobs', 0)}건\n"
        f"성공: {data.get('success_count', 0)}건\n"
        f"실패: {data.get('failure_count', 0)}건\n"
        f"건너뜀: {data.get('skip_count', 0)}건"
    )


# ─────────────────────────────────────────────────────────────
# Phase 72: 보안 강화 포맷터
# ─────────────────────────────────────────────────────────────

def _format_security_audit(data) -> str:
    header = f"*🔒 보안 감사 로그 ({len(data)}개)*\n"
    if not data:
        return header + "로그 없음"
    lines = [header]
    for e in data[:5]:
        lines.append(f"• [{e.get('event_type', '-')}] {e.get('user_id', '-')} @ {e.get('ip', '-')}")
    return "\n".join(lines)


def _format_security_sessions(data) -> str:
    header = f"*🔒 활성 세션 ({len(data)}개)*\n"
    if not data:
        return header + "세션 없음"
    lines = [header]
    for s in data[:5]:
        lines.append(f"• {s.get('user_id', '-')} ({str(s.get('session_id', '-'))[:8]}...)")
    return "\n".join(lines)


def _format_ip_block(data) -> str:
    action = data.get('action', '-')
    return (
        f"*🔒 IP 차단*\n"
        f"IP: {data.get('ip', '-')}\n"
        f"조치: {action}\n"
        f"접근 허용: {'예' if data.get('allowed', False) else '아니오'}"
    )


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
        # Phase 55: 파일 스토리지
        'storage_usage': lambda d: _format_storage_usage(d),
        'storage_quota': lambda d: _format_storage_quota(d),
        # Phase 56: 이메일 서비스
        'email_stats': lambda d: _format_email_stats(d),
        'email_send': lambda d: _format_email_send(d),
        # Phase 57: 검색 엔진
        'search_popular': lambda d: _format_search_popular(d),
        # Phase 58: 작업 파이프라인
        'pipeline_run': lambda d: _format_pipeline_run(d),
        'pipeline_status': lambda d: _format_pipeline_status(d),
        # Phase 59: 피쳐 플래그
        'flag_list': lambda d: _format_flag_list(d),
        'flag_toggle': lambda d: _format_flag_toggle(d),
        # Phase 60: 외부 연동
        'integration_list': lambda d: _format_integration_list(d),
        'integration_sync': lambda d: _format_integration_sync(d),
        # Phase 61: 백업/복원
        'backup_create': lambda d: _format_backup_create(d),
        'backup_list': lambda d: _format_backup_list(d),
        'backup_restore': lambda d: _format_backup_restore(d),
        # Phase 62: 레이트 리미팅
        'ratelimit_status': lambda d: _format_ratelimit_status(d),
        'ratelimit_policy': lambda d: _format_ratelimit_policy(d),
        # Phase 63: CMS
        'cms_list': lambda d: _format_cms_list(d),
        'cms_publish': lambda d: _format_cms_publish(d),
        'cms_draft': lambda d: _format_cms_draft(d),
        # Phase 64: 이벤트 소싱
        'events_recent': lambda d: _format_events_recent(d),
        'events_replay': lambda d: _format_events_replay(d),
        # Phase 65: 캐시 계층
        'cache_stats': lambda d: _format_cache_stats(d),
        'cache_clear': lambda d: _format_cache_clear(d),
        # Phase 66: 워크플로 엔진
        'workflow_list': lambda d: _format_workflow_list(d),
        'workflow_start': lambda d: _format_workflow_start(d),
        'workflow_status': lambda d: _format_workflow_status(d),
        # Phase 67: 실시간 대시보드
        'realtime_status': lambda d: _format_realtime_status(d),
        'realtime_metrics': lambda d: _format_realtime_metrics(d),
        # Phase 68: 데이터 교환
        'export': lambda d: _format_export(d),
        'import_status': lambda d: _format_import_status(d),
        # Phase 69: 규칙 엔진
        'rules_list': lambda d: _format_rules_list(d),
        'rules_test': lambda d: _format_rules_test(d),
        # Phase 70: KPI
        'kpi_summary': lambda d: _format_kpi_summary(d),
        'kpi_detail': lambda d: _format_kpi_detail(d),
        'kpi_alerts': lambda d: _format_kpi_alerts(d),
        # Phase 71: 마켓플레이스 동기화
        'sync_marketplace': lambda d: _format_sync_marketplace(d),
        'sync_status': lambda d: _format_sync_status(d),
        'sync_logs': lambda d: _format_sync_logs(d),
        # Phase 72: 보안 강화
        'security_audit': lambda d: _format_security_audit(d),
        'security_sessions': lambda d: _format_security_sessions(d),
        'ip_block': lambda d: _format_ip_block(d),
        # Phase 73: 고객 세그먼트
        'segments_list': lambda d: _format_segments_list(d),
        'segment_detail': lambda d: _format_segment_detail(d),
        'segment_export': lambda d: _format_segment_export(d),
        # Phase 74: 동적 폼 빌더
        'forms_list': lambda d: _format_forms_list(d),
        'form_submissions': lambda d: _format_form_submissions(d),
        # Phase 75: 워크플로 엔진 고도화
        'workflow_engine_list': lambda d: _format_workflow_engine_list(d),
        'workflow_engine_start': lambda d: _format_workflow_engine_start(d),
        'workflow_engine_status': lambda d: _format_workflow_engine_status(d),
        # Phase 76: 파일 스토리지
        'files_list': lambda d: _format_files_list(d),
        'file_quota': lambda d: _format_file_quota(d),
        'file_delete': lambda d: _format_file_delete(d),
        # Phase 77: 이벤트 소싱 고도화
        'events_list': lambda d: _format_events_list(d),
        'event_replay': lambda d: _format_event_replay(d),
        # Phase 78: 피처 플래그 고도화
        'flag_evaluate': lambda d: _format_flag_evaluate(d),
        # Phase 79: 리뷰 분석
        'review_stats': lambda d: _format_review_stats(d),
        'review_sentiment': lambda d: _format_review_sentiment(d),
        # Phase 80: 배송비 계산기
        'shipping_calc': lambda d: _format_shipping_calc(d),
        'shipping_zones': lambda d: _format_shipping_zones(d),
        # Phase 81: 알림 템플릿
        'templates_list': lambda d: _format_templates_list(d),
        'template_preview': lambda d: _format_template_preview(d),
        # Phase 82: 결제 복구
        'payment_failures': lambda d: _format_payment_failures(d),
        'payment_retry': lambda d: _format_payment_retry(d),
        # Phase 83: 상품 추천
        'recommendations': lambda d: _format_recommendations(d),
        'trending_products': lambda d: _format_trending_products(d),
        # Phase 84: 주문 분할/병합
        'order_split': lambda d: _format_order_split(d),
        'order_merge': lambda d: _format_order_merge(d),
        'sub_orders': lambda d: _format_sub_orders(d),
        # Phase 85: 재고 입출고 이력
        'stock_in': lambda d: _format_stock_in(d),
        'stock_out': lambda d: _format_stock_out(d),
        'stock_ledger': lambda d: _format_stock_ledger(d),
        # Phase 86: 고객 세그멘테이션
        'segments_list': lambda d: _format_segments_list(d),
        'segment_stats': lambda d: _format_segment_stats(d),
        # Phase 87: 상품 비교
        'compare': lambda d: _format_compare(d),
        'comparison_history': lambda d: _format_comparison_history(d),
        # Phase 88: 이메일 마케팅
        'campaigns_list': lambda d: _format_campaigns_list(d),
        'campaign_stats': lambda d: _format_campaign_stats(d),
        'campaign_send': lambda d: _format_campaign_send(d),
        # Phase 89: 창고 관리
        'warehouses': lambda d: _format_warehouses(d),
        'warehouse_status': lambda d: _format_warehouse_status(d),
        'picking_order': lambda d: _format_picking_order(d),
        # Phase 90: 세금 계산
        'tax_calc': lambda d: _format_tax_calc(d),
        'customs': lambda d: _format_customs(d),
        # Phase 102: 배송대행지
        'forwarding_status': lambda d: _format_forwarding_status(d),
        'incoming_record': lambda d: _format_incoming_record(d),
        'consolidation_group': lambda d: _format_consolidation_group(d),
        'shipment_record': lambda d: _format_shipment_record(d),
        'cost_estimate': lambda d: _format_cost_estimate(d),
        'forwarding_dashboard': lambda d: _format_forwarding_dashboard(d),
        # Phase 103: 풀필먼트
        'fulfillment_status': lambda d: _format_fulfillment_status(d),
        'inspection_result': lambda d: _format_inspection_result(d),
        'packing_result': lambda d: _format_packing_result(d),
        'fulfillment_dashboard': lambda d: _format_fulfillment_dashboard(d),
        # Phase 104: 중국 마켓플레이스
        'china_order': lambda d: _format_china_order(d),
        'china_search': lambda d: _format_china_search(d),
        'china_seller_score': lambda d: _format_china_seller_score(d),
        'china_dashboard': lambda d: _format_china_dashboard(d),
        'rpa_task': lambda d: _format_rpa_task(d),
        # Phase 105: 예외 처리
        'exception_case': lambda d: _format_exception_case(d),
        'exception_stats': lambda d: _format_exception_stats(d),
        'damage_report': lambda d: _format_damage_report(d),
        'price_alert': lambda d: _format_price_alert(d),
        'retry_record': lambda d: _format_retry_record(d),
        'exception_dashboard': lambda d: _format_exception_dashboard(d),
        # Phase 107: 실시간 채팅
        'chat_session': lambda d: _format_chat_session(d),
        'chat_stats': lambda d: _format_chat_stats(d),
        'chat_queue': lambda d: _format_chat_queue(d),
        'agent_profile': lambda d: _format_agent_profile(d),
        'chat_dashboard': lambda d: _format_chat_dashboard(d),
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
        exp_id = exp.get('experiment_id', '-')
        exp_id_short = exp_id[:8] + "..." if len(exp_id) > 8 else exp_id
        lines.append(
            f"• [{exp.get('status', '-')}] {exp.get('name', '-')} "
            f"(ID: `{exp_id_short}`)"
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


# ─────────────────────────────────────────────────────────────
# Phase 55: 파일 스토리지 포맷터
# ─────────────────────────────────────────────────────────────

def _format_storage_usage(data) -> str:
    """스토리지 사용량 포맷."""
    usage_mb = round(data.get('usage_bytes', 0) / 1024 / 1024, 2)
    quota_mb = round(data.get('quota_bytes', 0) / 1024 / 1024, 2)
    return (
        f"*💾 스토리지 사용량*\n"
        f"사용자: {data.get('owner_id', '-')}\n"
        f"사용: {usage_mb} MB / {quota_mb} MB\n"
        f"사용률: {data.get('usage_percent', 0):.1f}%"
    )


def _format_storage_quota(data) -> str:
    """스토리지 할당량 포맷."""
    quota_mb = round(data.get('quota_bytes', 0) / 1024 / 1024, 2)
    available_mb = round(data.get('available_bytes', 0) / 1024 / 1024, 2)
    return (
        f"*💾 스토리지 할당량*\n"
        f"사용자: {data.get('owner_id', '-')}\n"
        f"할당량: {quota_mb} MB\n"
        f"가용: {available_mb} MB"
    )


# ─────────────────────────────────────────────────────────────
# Phase 56: 이메일 서비스 포맷터
# ─────────────────────────────────────────────────────────────

def _format_email_stats(data) -> str:
    """이메일 통계 포맷."""
    return (
        f"*📧 이메일 통계*\n"
        f"발송: {data.get('total_sent', 0)}\n"
        f"열람: {data.get('total_opened', 0)} ({data.get('open_rate', 0):.1f}%)\n"
        f"클릭: {data.get('total_clicks', 0)}"
    )


def _format_email_send(data) -> str:
    """이메일 발송 결과 포맷."""
    results = data.get('results', [])
    status = results[0].get('status', '-') if results else '-'
    icon = "✅" if status == "sent" else "❌"
    return (
        f"*📧 이메일 발송*\n"
        f"{icon} 상태: {status}\n"
        f"ID: {data.get('email_id', '-')[:8]}..."
    )


# ─────────────────────────────────────────────────────────────
# Phase 57: 검색 엔진 포맷터
# ─────────────────────────────────────────────────────────────

def _format_search_popular(data) -> str:
    """인기 검색어 포맷."""
    header = "*🔍 인기 검색어*\n"
    if not data:
        return header + "데이터 없음"
    lines = [header]
    for i, item in enumerate(data[:10], 1):
        if isinstance(item, dict):
            lines.append(f"{i}. {item.get('query', item)}")
        else:
            lines.append(f"{i}. {item}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Phase 58: 작업 파이프라인 포맷터
# ─────────────────────────────────────────────────────────────

def _format_pipeline_run(data) -> str:
    """파이프라인 실행 결과 포맷."""
    name = data.get('name', '-')
    results = data.get('results', {})
    lines = [f"*⚙️ 파이프라인 실행: {name}*"]
    for stage, result in results.items():
        status = result.get('status', '-')
        icon = "✅" if status == "success" else ("⏭️" if status == "skipped" else "❌")
        lines.append(f"{icon} {stage}: {status} ({result.get('duration_ms', 0):.0f}ms)")
    return "\n".join(lines)


def _format_pipeline_status(data) -> str:
    """파이프라인 상태 포맷."""
    header = "*⚙️ 파이프라인 상태*\n"
    if not data:
        return header + "실행 이력 없음"
    lines = [header]
    for stat in data[:5]:
        lines.append(
            f"• {stat.get('pipeline_name', '-')}: "
            f"실행 {stat.get('runs', 0)}회, "
            f"성공률 {stat.get('success_rate', 0):.1f}%"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Phase 59: 피쳐 플래그 포맷터
# ─────────────────────────────────────────────────────────────

def _format_flag_list(data) -> str:
    """피쳐 플래그 목록 포맷."""
    header = "*🚩 피쳐 플래그 목록*\n"
    if not data:
        return header + "플래그 없음"
    lines = [header]
    for flag in data[:10]:
        icon = "✅" if flag.get('enabled') else "❌"
        lines.append(f"{icon} {flag.get('name', '-')}: {flag.get('description', '')}")
    return "\n".join(lines)


def _format_flag_toggle(data) -> str:
    """피쳐 플래그 토글 결과 포맷."""
    icon = "✅" if data.get('enabled') else "❌"
    return (
        f"*🚩 피쳐 플래그 토글*\n"
        f"이름: {data.get('name', '-')}\n"
        f"{icon} 상태: {'활성' if data.get('enabled') else '비활성'}"
    )


# ─────────────────────────────────────────────────────────────
# Phase 60: 외부 연동 포맷터
# ─────────────────────────────────────────────────────────────

def _format_integration_list(data) -> str:
    """연동 목록 포맷."""
    integrations = data.get('integrations', [])
    header = f"*🔗 연동 목록 ({len(integrations)}개)*\n"
    if not integrations:
        return header + "연동 없음"
    lines = [header]
    for name in integrations:
        lines.append(f"• {name}")
    return "\n".join(lines)


def _format_integration_sync(data) -> str:
    """연동 동기화 결과 포맷."""
    name = data.get('name', '-')
    result = data.get('result', {})
    synced = result.get('synced', False)
    icon = "✅" if synced else "❌"
    return (
        f"*🔗 연동 동기화: {name}*\n"
        f"{icon} 동기화: {'완료' if synced else '실패'}"
    )


# ─────────────────────────────────────────────────────────────
# Phase 61: 백업/복원 포맷터
# ─────────────────────────────────────────────────────────────

def _format_backup_create(data) -> str:
    """백업 생성 결과 포맷."""
    return (
        f"*💾 백업 생성 완료*\n"
        f"ID: {str(data.get('backup_id', '-'))[:8]}...\n"
        f"전략: {data.get('strategy', '-')}\n"
        f"크기: {data.get('size_bytes', 0)} bytes\n"
        f"생성: {data.get('created_at', '-')[:19]}"
    )


def _format_backup_list(data) -> str:
    """백업 목록 포맷."""
    header = f"*💾 백업 목록 ({len(data)}개)*\n"
    if not data:
        return header + "백업 없음"
    lines = [header]
    for b in data[:5]:
        lines.append(f"• {str(b.get('backup_id', '-'))[:8]}... ({b.get('strategy', '-')})")
    return "\n".join(lines)


def _format_backup_restore(data) -> str:
    """백업 복원 결과 포맷."""
    return (
        f"*💾 백업 복원*\n"
        f"ID: {str(data.get('backup_id', '-'))[:8]}...\n"
        f"✅ 복원 완료"
    )


# ─────────────────────────────────────────────────────────────
# Phase 62: 레이트 리미팅 포맷터
# ─────────────────────────────────────────────────────────────

def _format_ratelimit_status(data) -> str:
    """레이트 리밋 상태 포맷."""
    return (
        f"*🚦 레이트 리밋 상태*\n"
        f"정책 수: {data.get('total_policies', 0)}\n"
        f"사용량 항목: {len(data.get('usage', []))}"
    )


def _format_ratelimit_policy(data) -> str:
    """레이트 리밋 정책 포맷."""
    if "policies" in data:
        policies = data["policies"]
        header = f"*🚦 레이트 리밋 정책 ({len(policies)}개)*\n"
        if not policies:
            return header + "정책 없음"
        lines = [header]
        for p in policies[:5]:
            lines.append(f"• {p.get('endpoint', '-')}: {p.get('limit', 0)}req/{p.get('window', 0)}s")
        return "\n".join(lines)
    return (
        f"*🚦 레이트 리밋 정책*\n"
        f"엔드포인트: {data.get('endpoint', '-')}\n"
        f"제한: {data.get('limit', '-')} req/{data.get('window', '-')}s"
    )


# ─────────────────────────────────────────────────────────────
# Phase 63: CMS 포맷터
# ─────────────────────────────────────────────────────────────

def _format_cms_list(data) -> str:
    """CMS 콘텐츠 목록 포맷."""
    header = f"*📄 CMS 콘텐츠 목록 ({len(data)}개)*\n"
    if not data:
        return header + "콘텐츠 없음"
    lines = [header]
    for item in data[:5]:
        icon = "✅" if item.get("status") == "published" else "📝"
        lines.append(f"{icon} {item.get('title', '-')} [{item.get('content_type', '-')}]")
    return "\n".join(lines)


def _format_cms_publish(data) -> str:
    """콘텐츠 발행 결과 포맷."""
    return (
        f"*📄 콘텐츠 발행*\n"
        f"ID: {str(data.get('content_id', '-'))[:8]}...\n"
        f"✅ 상태: {data.get('status', 'published')}"
    )


def _format_cms_draft(data) -> str:
    """콘텐츠 초안 전환 결과 포맷."""
    return (
        f"*📄 콘텐츠 초안 전환*\n"
        f"ID: {str(data.get('content_id', '-'))[:8]}...\n"
        f"📝 상태: {data.get('status', 'draft')}"
    )


# ─────────────────────────────────────────────────────────────
# Phase 64: 이벤트 소싱 포맷터
# ─────────────────────────────────────────────────────────────

def _format_events_recent(data) -> str:
    """최근 이벤트 포맷."""
    header = f"*📨 최근 이벤트 ({len(data)}개)*\n"
    if not data:
        return header + "이벤트 없음"
    lines = [header]
    for e in data[:5]:
        lines.append(f"• [{e.get('event_type', '-')}] {e.get('aggregate_id', '-')[:8]}...")
    return "\n".join(lines)


def _format_events_replay(data) -> str:
    """이벤트 리플레이 결과 포맷."""
    events = data.get("events", [])
    return (
        f"*📨 이벤트 리플레이*\n"
        f"Aggregate: {data.get('aggregate_id', '-')[:8]}...\n"
        f"리플레이된 이벤트: {len(events)}개"
    )


# ─────────────────────────────────────────────────────────────
# Phase 65: 캐시 계층 포맷터
# ─────────────────────────────────────────────────────────────

def _format_cache_stats(data) -> str:
    """캐시 통계 포맷."""
    return (
        f"*⚡ 캐시 통계*\n"
        f"히트: {data.get('hits', 0)} / 미스: {data.get('misses', 0)}\n"
        f"히트율: {data.get('hit_rate', 0):.1%}\n"
        f"평균 히트: {data.get('avg_hit_ms', 0):.1f}ms"
    )


def _format_cache_clear(data) -> str:
    """캐시 초기화 결과 포맷."""
    count = data.get('invalidated', 0)
    if count == -1:
        return f"*⚡ 캐시 전체 초기화 완료*"
    return (
        f"*⚡ 캐시 무효화*\n"
        f"패턴: {data.get('pattern', '-')}\n"
        f"무효화된 항목: {count}개"
    )


# ─────────────────────────────────────────────────────────────
# Phase 66: 워크플로 엔진 포맷터
# ─────────────────────────────────────────────────────────────

def _format_workflow_list(data) -> str:
    """워크플로 목록 포맷."""
    header = f"*⚙️ 워크플로 목록 ({len(data)}개)*\n"
    if not data:
        return header + "워크플로 없음"
    lines = [header]
    for wf in data:
        lines.append(f"• {wf.get('name', '-')} (초기: {wf.get('initial_state', '-')})")
    return "\n".join(lines)


def _format_workflow_start(data) -> str:
    """워크플로 시작 결과 포맷."""
    return (
        f"*⚙️ 워크플로 시작*\n"
        f"인스턴스: {str(data.get('instance_id', '-'))[:8]}...\n"
        f"워크플로: {data.get('definition_name', '-')}\n"
        f"현재 상태: {data.get('current_state', '-')}"
    )


def _format_workflow_status(data) -> str:
    """워크플로 상태 포맷."""
    history = data.get("history", [])
    return (
        f"*⚙️ 워크플로 상태*\n"
        f"인스턴스: {str(data.get('instance_id', '-'))[:8]}...\n"
        f"현재 상태: {data.get('current_state', '-')}\n"
        f"전환 횟수: {len(history)}"
    )


# ─────────────────────────────────────────────────────────────
# Phase 73: 고객 세그먼트 포맷터
# ─────────────────────────────────────────────────────────────

def _format_segments_list(data) -> str:
    """세그먼트 목록 포맷."""
    header = f"*👥 세그먼트 목록 ({len(data)}개)*\n"
    if not data:
        return header + "세그먼트 없음"
    lines = [header]
    for seg in data:
        builtin_tag = " (내장)" if seg.get("builtin") else ""
        lines.append(f"• {seg.get('name', '-')}{builtin_tag} — {seg.get('customer_count', 0)}명")
    return "\n".join(lines)


def _format_segment_detail(data) -> str:
    """세그먼트 상세 포맷."""
    rules = data.get("rules", [])
    return (
        f"*👥 세그먼트: {data.get('name', '-')}*\n"
        f"설명: {data.get('description', '-')}\n"
        f"로직: {data.get('logic', 'AND')}\n"
        f"규칙 수: {len(rules)}개\n"
        f"고객 수: {data.get('customer_count', 0)}명"
    )


def _format_segment_export(data) -> str:
    """세그먼트 내보내기 결과 포맷."""
    return (
        f"*📊 세그먼트 내보내기*\n"
        f"세그먼트: {data.get('segment_name', '-')}\n"
        f"레코드: {data.get('record_count', 0)}개\n"
        f"✅ CSV 생성 완료"
    )


# ─────────────────────────────────────────────────────────────
# Phase 74: 동적 폼 빌더 포맷터
# ─────────────────────────────────────────────────────────────

def _format_forms_list(data) -> str:
    """폼 목록 포맷."""
    header = f"*📋 폼 목록 ({len(data)}개)*\n"
    if not data:
        return header + "폼 없음"
    lines = [header]
    for form in data:
        fields_count = len(form.get("fields", []))
        lines.append(f"• {form.get('name', '-')} (v{form.get('version', 1)}, {fields_count}개 필드)")
    return "\n".join(lines)


def _format_form_submissions(data) -> str:
    """폼 제출 목록 포맷."""
    submissions = data.get("submissions", [])
    return (
        f"*📋 폼 제출 목록*\n"
        f"폼 ID: {data.get('form_id', '-')}\n"
        f"제출 수: {len(submissions)}개"
    )


# ─────────────────────────────────────────────────────────────
# Phase 75: 워크플로 엔진 고도화 포맷터
# ─────────────────────────────────────────────────────────────

def _format_workflow_engine_list(data) -> str:
    """워크플로 엔진 목록 포맷."""
    header = f"*⚙️ 워크플로 목록 ({len(data)}개)*\n"
    if not data:
        return header + "워크플로 없음"
    lines = [header]
    for wf in data:
        states_count = len(wf.get("states", []))
        lines.append(f"• {wf.get('name', '-')} ({states_count}개 상태)")
    return "\n".join(lines)


def _format_workflow_engine_start(data) -> str:
    """워크플로 시작 결과 포맷."""
    return (
        f"*⚙️ 워크플로 시작*\n"
        f"인스턴스: {str(data.get('instance_id', '-'))[:8]}...\n"
        f"워크플로: {data.get('definition_name', '-')}\n"
        f"현재 상태: {data.get('current_state', '-')}"
    )


def _format_workflow_engine_status(data) -> str:
    """워크플로 인스턴스 상태 포맷."""
    history = data.get("history", [])
    return (
        f"*⚙️ 워크플로 상태*\n"
        f"인스턴스: {str(data.get('instance_id', '-'))[:8]}...\n"
        f"상태: {data.get('status', '-')}\n"
        f"현재: {data.get('current_state', '-')}\n"
        f"전환 횟수: {len(history)}"
    )


# ─────────────────────────────────────────────────────────────
# Phase 76: 파일 스토리지 포맷터
# ─────────────────────────────────────────────────────────────

def _format_files_list(data) -> str:
    """파일 목록 포맷."""
    header = f"*📁 파일 목록 ({len(data)}개)*\n"
    if not data:
        return header + "파일 없음"
    lines = [header]
    for f in data[:10]:
        lines.append(f"• {f.get('filename', '-')} ({f.get('size', 0):,}B)")
    if len(data) > 10:
        lines.append(f"_... 외 {len(data) - 10}개 생략_")
    return "\n".join(lines)


def _format_file_quota(data) -> str:
    """스토리지 사용량 포맷."""
    used_mb = data.get("used_bytes", 0) / (1024 * 1024)
    quota_mb = data.get("quota_bytes", 0) / (1024 * 1024)
    return (
        f"*📁 스토리지 사용량*\n"
        f"소유자: {data.get('owner_id', '-')}\n"
        f"사용: {used_mb:.1f}MB / {quota_mb:.1f}MB\n"
        f"사용률: {data.get('usage_pct', 0):.1f}%"
    )


def _format_file_delete(data) -> str:
    """파일 삭제 결과 포맷."""
    return (
        f"*📁 파일 삭제*\n"
        f"키: {data.get('key', '-')}\n"
        f"✅ 삭제 완료"
    )


# ─────────────────────────────────────────────────────────────
# Phase 77: 이벤트 소싱 포맷터
# ─────────────────────────────────────────────────────────────

def _format_events_list(data) -> str:
    """이벤트 목록 포맷."""
    header = f"*📨 이벤트 목록 ({len(data)}개)*\n"
    if not data:
        return header + "이벤트 없음"
    lines = [header]
    for e in data[:5]:
        lines.append(f"• [{e.get('event_type', '-')}] {e.get('aggregate_id', '-')[:8]}...")
    if len(data) > 5:
        lines.append(f"_... 외 {len(data) - 5}개 생략_")
    return "\n".join(lines)


def _format_event_replay(data) -> str:
    """이벤트 리플레이 결과 포맷."""
    return (
        f"*📨 이벤트 리플레이*\n"
        f"Aggregate: {data.get('aggregate_id', '-')[:8]}...\n"
        f"리플레이: {data.get('replayed_count', 0)}개"
    )


# ─────────────────────────────────────────────────────────────
# Phase 78: 피처 플래그 고도화 포맷터
# ─────────────────────────────────────────────────────────────

def _format_flag_evaluate(data) -> str:
    """플래그 평가 결과 포맷."""
    status = "✅ 활성" if data.get("enabled") else "❌ 비활성"
    return (
        f"*🚩 플래그 평가*\n"
        f"플래그: {data.get('flag_name', '-')}\n"
        f"사용자: {data.get('user_id', '-') or '(없음)'}\n"
        f"결과: {status}\n"
        f"이유: {data.get('reason', '-')}\n"
        f"변형: {data.get('variant') or '없음'}"
    )


# ---------------------------------------------------------------------------
# Phase 79: 리뷰 분석 포매터
# ---------------------------------------------------------------------------
def _format_review_stats(d: dict) -> str:
    """리뷰 통계를 포맷."""
    return (
        f"📊 리뷰 통계\n"
        f"상품 ID: {d.get('product_id', '-')}\n"
        f"리뷰 수: {d.get('review_count', 0)}\n"
        f"평균 평점: {d.get('avg_rating', 0):.1f}⭐\n"
        f"긍정 비율: {d.get('positive_ratio', 0):.1%}"
    )


def _format_review_sentiment(d: dict) -> str:
    """리뷰 감성 분석 결과를 포맷."""
    sentiment_map = {'positive': '😊 긍정', 'negative': '😞 부정', 'neutral': '😐 중립'}
    sentiment = sentiment_map.get(d.get('sentiment', 'neutral'), d.get('sentiment', '-'))
    return (
        f"💬 감성 분석\n"
        f"감성: {sentiment}\n"
        f"점수: {d.get('score', 0):.2f}"
    )


# ---------------------------------------------------------------------------
# Phase 80: 배송비 계산기 포매터
# ---------------------------------------------------------------------------
def _format_shipping_calc(d: dict) -> str:
    """배송비 계산 결과를 포맷."""
    return (
        f"🚚 배송비 계산\n"
        f"구역: {d.get('zone', '-')}\n"
        f"무게: {d.get('weight_g', 0)}g\n"
        f"배송비: {d.get('price', 0):,}원\n"
        f"택배사: {d.get('carrier', '-')}"
    )


def _format_shipping_zones(d: dict) -> str:
    """배송 구역 목록을 포맷."""
    zones = d if isinstance(d, list) else d.get('zones', [])
    lines = ["🌍 배송 구역 목록"]
    for z in zones:
        lines.append(f"• {z.get('zone_id', '-')}: {z.get('name', '-')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 81: 알림 템플릿 포매터
# ---------------------------------------------------------------------------
def _format_templates_list(d: dict) -> str:
    """템플릿 목록을 포맷."""
    templates = d if isinstance(d, list) else d.get('templates', [])
    lines = ["📝 알림 템플릿 목록"]
    for t in templates:
        lines.append(f"• [{t.get('channel', '-')}] {t.get('name', '-')} (v{t.get('version', 1)})")
    return "\n".join(lines)


def _format_template_preview(d: dict) -> str:
    """템플릿 미리보기를 포맷."""
    return (
        f"👁️ 템플릿 미리보기\n"
        f"이름: {d.get('name', '-')}\n"
        f"채널: {d.get('channel', '-')}\n"
        f"내용:\n{d.get('body_preview', '-')}"
    )


# ---------------------------------------------------------------------------
# Phase 82: 결제 복구 포매터
# ---------------------------------------------------------------------------
def _format_payment_failures(d: dict) -> str:
    """결제 실패 목록을 포맷."""
    failures = d if isinstance(d, list) else d.get('failures', [])
    lines = ["💳 결제 실패 목록"]
    for f in failures:
        lines.append(f"• {f.get('payment_id', '-')}: {f.get('error_code', '-')} ({f.get('status', '-')})")
    return "\n".join(lines)


def _format_payment_retry(d: dict) -> str:
    """결제 재시도 결과를 포맷."""
    success = d.get('success', False)
    icon = "✅" if success else "❌"
    return (
        f"{icon} 결제 재시도\n"
        f"결제 ID: {d.get('payment_id', '-')}\n"
        f"시도 횟수: {d.get('attempts', 0)}\n"
        f"결과: {'성공' if success else '실패'}"
    )


# ---------------------------------------------------------------------------
# Phase 83: 상품 추천 포매터
# ---------------------------------------------------------------------------
def _format_recommendations(d: dict) -> str:
    """추천 상품 목록을 포맷."""
    items = d if isinstance(d, list) else d.get('recommendations', [])
    lines = ["🎯 추천 상품"]
    for item in items[:10]:
        pid = item.get('product_id', item.get('id', '-'))
        lines.append(f"• {pid}")
    return "\n".join(lines)


def _format_trending_products(d: dict) -> str:
    """트렌딩 상품 목록을 포맷."""
    items = d if isinstance(d, list) else d.get('trending', [])
    lines = ["🔥 트렌딩 상품"]
    for item in items[:10]:
        pid = item.get('product_id', '-')
        score = item.get('score', 0)
        lines.append(f"• {pid} (점수: {score:.1f})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 84: 주문 분할/병합 포매터
# ---------------------------------------------------------------------------
def _format_order_split(d: dict) -> str:
    """주문 분할 결과를 포맷."""
    sub_orders = d.get('sub_orders', [])
    lines = [
        f"✂️ 주문 분할",
        f"원주문: {d.get('parent_order_id', '-')}",
        f"분할 수: {len(sub_orders)}",
    ]
    for so in sub_orders:
        so_id = so.get('sub_order_id', '-') if isinstance(so, dict) else getattr(so, 'sub_order_id', '-')
        lines.append(f"  • {so_id}")
    return "\n".join(lines)


def _format_order_merge(d: dict) -> str:
    """주문 병합 결과를 포맷."""
    return (
        f"🔀 주문 병합\n"
        f"병합 주문 ID: {d.get('merged_order_id', '-')}\n"
        f"원주문 수: {len(d.get('merged_order_ids', []))}\n"
        f"상태: {d.get('status', '-')}"
    )


def _format_sub_orders(d: dict) -> str:
    """하위 주문 목록을 포맷."""
    sub_orders = d.get('sub_orders', [])
    lines = [f"📦 하위 주문 목록 (원주문: {d.get('parent_order_id', '-')})"]
    for so in sub_orders:
        so_id = so if isinstance(so, str) else so.get('sub_order_id', '-')
        lines.append(f"• {so_id}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 85: 재고 입출고 이력 포매터
# ---------------------------------------------------------------------------
def _format_stock_in(d: dict) -> str:
    """재고 입고 결과를 포맷."""
    return (
        f"📥 재고 입고 완료\n"
        f"SKU: {d.get('sku', '-')}\n"
        f"수량: {d.get('quantity', 0)}\n"
        f"트랜잭션 ID: {d.get('transaction_id', '-')}"
    )


def _format_stock_out(d: dict) -> str:
    """재고 출고 결과를 포맷."""
    return (
        f"📤 재고 출고 완료\n"
        f"SKU: {d.get('sku', '-')}\n"
        f"수량: {d.get('quantity', 0)}\n"
        f"트랜잭션 ID: {d.get('transaction_id', '-')}"
    )


def _format_stock_ledger(d: dict) -> str:
    """재고 원장을 포맷."""
    return (
        f"📒 재고 원장\n"
        f"SKU: {d.get('sku', '-')}\n"
        f"현재 수량: {d.get('quantity', 0)}"
    )


# ---------------------------------------------------------------------------
# Phase 86: 고객 세그멘테이션 포매터
# ---------------------------------------------------------------------------
def _format_segments_list(d) -> str:
    """세그먼트 목록을 포맷."""
    segments = d if isinstance(d, list) else d.get('segments', [])
    lines = ["🎯 세그먼트 목록"]
    for seg in segments:
        if hasattr(seg, 'segment_id'):
            lines.append(f"• [{seg.segment_id[:8]}] {seg.name} (고객: {seg.customer_count})")
        else:
            lines.append(f"• [{seg.get('segment_id', '-')[:8]}] {seg.get('name', '-')}")
    if not segments:
        lines.append("(세그먼트 없음)")
    return "\n".join(lines)


def _format_segment_stats(d: dict) -> str:
    """세그먼트 통계를 포맷."""
    return (
        f"📊 세그먼트 통계\n"
        f"세그먼트 ID: {d.get('segment_id', '-')}\n"
        f"고객 수: {d.get('count', 0)}\n"
        f"평균 주문가: {d.get('avg_order_value', 0):,.0f}원\n"
        f"LTV: {d.get('ltv', 0):,.0f}원\n"
        f"재구매율: {d.get('repurchase_rate', 0):.1%}"
    )


# ---------------------------------------------------------------------------
# Phase 87: 상품 비교 포매터
# ---------------------------------------------------------------------------
def _format_compare(d: dict) -> str:
    """상품 비교 결과를 포맷."""
    scores = d.get('scores', [])
    lines = [f"🔍 상품 비교 (ID: {d.get('comparison_id', '-')[:8]})"]
    for s in scores:
        lines.append(f"• {s.get('product_id', '-')}: {s.get('score', 0):.4f}점")
    return "\n".join(lines)


def _format_comparison_history(d) -> str:
    """비교 이력을 포맷."""
    items = d if isinstance(d, list) else d.get('history', [])
    lines = ["📋 비교 이력"]
    for item in items[:10]:
        if hasattr(item, 'comparison_id'):
            lines.append(f"• {item.comparison_id[:8]}: {item.product_ids}")
        else:
            lines.append(f"• {item.get('comparison_id', '-')[:8]}: {item.get('product_ids', [])}")
    if not items:
        lines.append("(이력 없음)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 88: 이메일 마케팅 포매터
# ---------------------------------------------------------------------------
def _format_campaigns_list(d) -> str:
    """캠페인 목록을 포맷."""
    camps = d if isinstance(d, list) else d.get('campaigns', [])
    lines = ["📧 이메일 캠페인 목록"]
    for c in camps:
        if hasattr(c, 'campaign_id'):
            lines.append(f"• [{c.status}] {c.name}")
        else:
            lines.append(f"• [{c.get('status', '-')}] {c.get('name', '-')}")
    if not camps:
        lines.append("(캠페인 없음)")
    return "\n".join(lines)


def _format_campaign_stats(d: dict) -> str:
    """캠페인 통계를 포맷."""
    return (
        f"📊 캠페인 통계\n"
        f"캠페인 ID: {d.get('campaign_id', '-')}\n"
        f"발송 수: {d.get('sent_count', 0)}\n"
        f"오픈 수: {d.get('open_count', 0)} ({d.get('open_rate', 0):.1%})\n"
        f"클릭 수: {d.get('click_count', 0)} ({d.get('click_rate', 0):.1%})"
    )


def _format_campaign_send(d: dict) -> str:
    """캠페인 발송 결과를 포맷."""
    success = d.get('success', False)
    icon = "✅" if success else "❌"
    return (
        f"{icon} 캠페인 발송\n"
        f"캠페인 ID: {d.get('campaign_id', '-')}\n"
        f"발송 수: {d.get('sent_count', 0)}"
    )


# ---------------------------------------------------------------------------
# Phase 89: 창고 관리 포매터
# ---------------------------------------------------------------------------
def _format_warehouses(d) -> str:
    """창고 목록을 포맷."""
    whs = d if isinstance(d, list) else d.get('warehouses', [])
    lines = ["🏭 창고 목록"]
    for wh in whs:
        if hasattr(wh, 'warehouse_id'):
            status = "✅" if wh.is_active else "❌"
            lines.append(f"• {status} {wh.name} (용량: {wh.capacity})")
        else:
            lines.append(f"• {wh.get('name', '-')} (용량: {wh.get('capacity', 0)})")
    if not whs:
        lines.append("(창고 없음)")
    return "\n".join(lines)


def _format_warehouse_status(d: dict) -> str:
    """창고 현황을 포맷."""
    return (
        f"🏭 창고 현황\n"
        f"이름: {d.get('name', '-')}\n"
        f"용량: {d.get('capacity', 0)}\n"
        f"현재 사용: {d.get('current_usage', 0)}\n"
        f"구역 수: {d.get('zone_count', 0)}\n"
        f"로케이션 수: {d.get('location_count', 0)}\n"
        f"상태: {'활성' if d.get('is_active') else '비활성'}"
    )


def _format_picking_order(d: dict) -> str:
    """피킹 주문을 포맷."""
    items = d.get('items', [])
    return (
        f"🛒 피킹 주문 생성\n"
        f"주문 ID: {d.get('order_id', '-')}\n"
        f"피킹 ID: {d.get('pick_id', '-')}\n"
        f"아이템 수: {len(items)}\n"
        f"상태: {d.get('status', '-')}"
    )


# ---------------------------------------------------------------------------
# Phase 90: 세금 계산 포매터
# ---------------------------------------------------------------------------
def _format_tax_calc(d: dict) -> str:
    """세금 계산 결과를 포맷."""
    return (
        f"🧾 세금 계산\n"
        f"과세 금액: {d.get('amount', 0):,.0f}원\n"
        f"세금 합계: {d.get('total_tax', 0):,.0f}원\n"
        f"세금 포함 금액: {d.get('tax_inclusive_amount', 0):,.0f}원"
    )


def _format_customs(d: dict) -> str:
    """관세 계산 결과를 포맷."""
    if d.get('exempt'):
        return f"✅ 소액 면세 적용 (금액: {d.get('amount', 0):,.0f}원)"
    breakdown = d.get('breakdown', [])
    lines = [
        f"🛃 관세 계산",
        f"과세 금액: {d.get('amount', 0):,.0f}원",
        f"총 세금: {d.get('total_tax', 0):,.0f}원",
    ]
    for b in breakdown:
        lines.append(f"  • {b.get('rule', '-')}: {b.get('tax', 0):,.0f}원 ({b.get('rate', 0):.1%})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 102: 배송대행지 포매터
# ---------------------------------------------------------------------------
def _format_forwarding_status(d: dict) -> str:
    """배송대행 현황 포맷."""
    inc = d.get('incoming_stats', {})
    ship = d.get('shipment_stats', {})
    return (
        f"📦 배송대행 현황\n"
        f"입고 대기: {inc.get('waiting', 0)}\n"
        f"입고 완료: {inc.get('received', 0)}\n"
        f"배송 중: {ship.get('in_transit', 0)}\n"
        f"배송 완료: {ship.get('delivered', 0)}"
    )


def _format_incoming_record(d: dict) -> str:
    """입고 기록 포맷."""
    return (
        f"📬 입고 기록\n"
        f"주문 ID: {d.get('order_id', '-')}\n"
        f"트래킹: {d.get('tracking_number', '-')}\n"
        f"상태: {d.get('status', '-')}\n"
        f"무게: {d.get('weight_kg', 0):.2f}kg"
    )


def _format_consolidation_group(d: dict) -> str:
    """합배송 그룹 포맷."""
    return (
        f"📋 합배송 그룹\n"
        f"그룹 ID: {d.get('group_id', '-')}\n"
        f"주문 수: {len(d.get('order_ids', []))}건\n"
        f"상태: {d.get('status', '-')}\n"
        f"예상 무게: {d.get('estimated_weight_kg', 0):.2f}kg\n"
        f"비용 절감: ${d.get('savings_usd', 0):.2f}"
    )


def _format_shipment_record(d: dict) -> str:
    """배송 기록 포맷."""
    return (
        f"🚚 배송 기록\n"
        f"배송 ID: {d.get('shipment_id', '-')}\n"
        f"트래킹: {d.get('tracking_number', '-')}\n"
        f"상태: {d.get('status', '-')}\n"
        f"출발지: {d.get('origin_country', '-')}\n"
        f"도착지: {d.get('destination_country', '-')}"
    )


def _format_cost_estimate(d: dict) -> str:
    """비용 견적 포맷."""
    return (
        f"💰 배송비 견적\n"
        f"기본 배송비: ${d.get('base_shipping_usd', 0):.2f}\n"
        f"유류 할증: ${d.get('fuel_surcharge_usd', 0):.2f}\n"
        f"보험료: ${d.get('insurance_usd', 0):.2f}\n"
        f"대행 수수료: ${d.get('agent_fee_usd', 0):.2f}\n"
        f"관세: ${d.get('customs_duty_usd', 0):.2f}\n"
        f"부가세: ${d.get('vat_usd', 0):.2f}\n"
        f"합계: ${d.get('total_usd', 0):.2f}"
    )


def _format_forwarding_dashboard(d: dict) -> str:
    """배송대행 대시보드 포맷."""
    inc = d.get('incoming_stats', {})
    ship = d.get('shipment_stats', {})
    cons = d.get('consolidation_stats', {})
    return (
        f"📊 배송대행 대시보드\n"
        f"총 배송: {d.get('total_shipments', 0)}건\n"
        f"입고 대기: {inc.get('waiting', 0)}\n"
        f"배송 중: {ship.get('in_transit', 0)}\n"
        f"합배송 그룹: {cons.get('total_groups', 0)}\n"
        f"비용 절감 합계: ${cons.get('total_savings_usd', 0):.2f}"
    )


# ---------------------------------------------------------------------------
# Phase 103: 풀필먼트 포매터
# ---------------------------------------------------------------------------
def _format_fulfillment_status(d: dict) -> str:
    """풀필먼트 현황 포맷."""
    by_status = d.get('by_status', {})
    return (
        f"🏭 풀필먼트 현황\n"
        f"총 주문: {d.get('total', 0)}건\n"
        f"입고: {by_status.get('received', 0)}\n"
        f"검수 중: {by_status.get('inspecting', 0)}\n"
        f"포장 중: {by_status.get('packing', 0)}\n"
        f"발송 대기: {by_status.get('ready_to_ship', 0)}\n"
        f"발송됨: {by_status.get('shipped', 0)}\n"
        f"배송 중: {by_status.get('in_transit', 0)}\n"
        f"배송 완료: {by_status.get('delivered', 0)}"
    )


def _format_inspection_result(d: dict) -> str:
    """검수 결과 포맷."""
    return (
        f"🔍 검수 결과\n"
        f"주문: {d.get('order_id', '-')}\n"
        f"등급: {d.get('grade', '-')}\n"
        f"코멘트: {d.get('comment', '-')}\n"
        f"반품 필요: {'예' if d.get('requires_return') else '아니오'}"
    )


def _format_packing_result(d: dict) -> str:
    """포장 결과 포맷."""
    dims = d.get('dimensions_cm', {})
    return (
        f"📦 포장 결과\n"
        f"주문: {d.get('order_id', '-')}\n"
        f"포장 유형: {d.get('packing_type', '-')}\n"
        f"무게: {d.get('weight_kg', 0):.2f}kg\n"
        f"크기: {dims.get('length', 0)}×{dims.get('width', 0)}×{dims.get('height', 0)}cm"
    )


def _format_fulfillment_dashboard(d: dict) -> str:
    """풀필먼트 대시보드 포맷."""
    fulf = d.get('fulfillment_orders', {})
    ship = d.get('shipping', {})
    return (
        f"🏭 풀필먼트 대시보드\n"
        f"총 주문: {fulf.get('total', 0)}건\n"
        f"총 발송: {ship.get('total', 0)}건"
    )


# ---------------------------------------------------------------------------
# Phase 104: 중국 마켓플레이스 포매터
# ---------------------------------------------------------------------------

def _format_china_order(d: dict) -> str:
    """중국 구매 주문 포맷."""
    return (
        f"🇨🇳 중국 구매 주문\n"
        f"주문 ID: {d.get('order_id', '-')}\n"
        f"마켓: {d.get('marketplace', '-')}\n"
        f"수량: {d.get('quantity', 0)}\n"
        f"상태: {d.get('status', '-')}\n"
        f"에이전트: {d.get('agent') or '미배정'}"
    )


def _format_china_search(d: dict) -> str:
    """중국 상품 검색 결과 포맷."""
    results = d.get('results', [])
    header = f"🔍 {d.get('marketplace', '중국')} 검색: {d.get('keyword', '')} ({len(results)}건)\n"
    if not results:
        return header + "결과 없음"
    lines = [header]
    for p in results[:5]:
        price = p.get('price_cny') or (p.get('price_tiers') or [{}])[0].get('price_cny', 0)
        lines.append(f"• {p.get('title', '-')} — ¥{price:.2f}")
    return '\n'.join(lines)


def _format_china_seller_score(d: dict) -> str:
    """셀러 검증 점수 포맷."""
    emoji = '✅' if d.get('recommendation') == 'approved' else ('⚠️' if d.get('recommendation') == 'caution' else '❌')
    return (
        f"{emoji} 셀러 검증\n"
        f"셀러 ID: {d.get('seller_id', '-')}\n"
        f"신뢰도: {d.get('reliability', 0):.1f}\n"
        f"품질: {d.get('quality', 0):.1f}\n"
        f"종합: {d.get('overall', 0):.1f}\n"
        f"판정: {d.get('recommendation', '-')}"
    )


def _format_china_dashboard(d: dict) -> str:
    """중국 구매 대시보드 포맷."""
    orders = d.get('orders', {})
    payments = d.get('payments', {})
    rpa = d.get('rpa', {})
    return (
        f"🇨🇳 중국 구매 대시보드\n"
        f"총 주문: {orders.get('total', 0)}건\n"
        f"결제 총액: ¥{payments.get('total_amount_cny', 0):.2f}\n"
        f"RPA 작업: {rpa.get('total_tasks', 0)}건 "
        f"(성공률: {rpa.get('success_rate', 0) * 100:.1f}%)"
    )


def _format_rpa_task(d: dict) -> str:
    """RPA 작업 포맷."""
    status_emoji = {
        'completed': '✅',
        'running': '⏳',
        'failed': '❌',
        'manual_required': '⚠️',
        'pending': '🕐',
    }
    status = d.get('status', '-')
    emoji = status_emoji.get(status, '•')
    return (
        f"🤖 RPA 작업\n"
        f"작업 ID: {d.get('task_id', '-')}\n"
        f"유형: {d.get('task_type', '-')}\n"
        f"상태: {emoji} {status}\n"
        f"단계 수: {len(d.get('steps', []))}"
    )


# ─────────────────────────────────────────────────────────────
# Phase 105: 예외 처리 포맷터
# ─────────────────────────────────────────────────────────────

def _format_exception_case(d: dict) -> str:
    """예외 케이스 포맷."""
    severity_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴', 'critical': '🚨'}.get(d.get('severity', ''), '⚠️')
    return (
        f"🚨 예외 케이스\n"
        f"ID: {d.get('case_id', '-')}\n"
        f"유형: {d.get('type', '-')}\n"
        f"심각도: {severity_emoji} {d.get('severity', '-')}\n"
        f"상태: {d.get('status', '-')}\n"
        f"주문: {d.get('order_id') or '-'}\n"
        f"재시도: {d.get('retry_count', 0)}회"
    )


def _format_exception_stats(d: dict) -> str:
    """예외 통계 포맷."""
    lines = [
        f"📊 예외 통계",
        f"전체: {d.get('total', 0)}건",
        f"해결: {d.get('resolved', 0)}건",
        f"해결률: {d.get('resolution_rate', 0) * 100:.1f}%",
    ]
    by_sev = d.get('by_severity', {})
    if by_sev:
        lines.append('심각도별: ' + ', '.join(f'{k}:{v}' for k, v in by_sev.items()))
    return "\n".join(lines)


def _format_damage_report(d: dict) -> str:
    """훼손 보고 포맷."""
    grade_emoji = {'A': '🟡', 'B': '🟠', 'C': '🔴', 'D': '💀'}.get(d.get('grade', ''), '⚠️')
    return (
        f"📦 훼손 보고\n"
        f"ID: {d.get('report_id', '-')}\n"
        f"주문: {d.get('order_id', '-')}\n"
        f"유형: {d.get('damage_type', '-')}\n"
        f"등급: {grade_emoji} Grade {d.get('grade', '-')}\n"
        f"보상액: {d.get('compensation_amount', 0):,.0f}원\n"
        f"클레임: {'✅' if d.get('claim_sent') else '❌'}"
    )


def _format_price_alert(d: dict) -> str:
    """가격 알림 포맷."""
    type_emoji = {
        'price_drop': '📉', 'price_surge': '📈',
        'out_of_budget': '💸', 'better_deal_found': '🎯',
    }.get(d.get('alert_type', ''), '💰')
    change = d.get('change_percent', 0)
    return (
        f"{type_emoji} 가격 알림\n"
        f"상품: {d.get('product_id', '-')}\n"
        f"유형: {d.get('alert_type', '-')}\n"
        f"변동: {d.get('old_price', 0):,.0f} → {d.get('new_price', 0):,.0f} ({change:+.1f}%)"
    )


def _format_retry_record(d: dict) -> str:
    """재시도 레코드 포맷."""
    status_emoji = {
        'pending': '⏳', 'running': '🔄', 'succeeded': '✅',
        'failed': '❌', 'exhausted': '💀', 'manual_required': '🙋',
    }.get(d.get('status', ''), '❓')
    return (
        f"🔁 재시도 레코드\n"
        f"ID: {d.get('record_id', '-')}\n"
        f"작업: {d.get('task_type', '-')}\n"
        f"상태: {status_emoji} {d.get('status', '-')}\n"
        f"시도: {d.get('attempt_count', 0)}회"
    )


def _format_exception_dashboard(d: dict) -> str:
    """예외 대시보드 포맷."""
    exc = d.get('exceptions', {})
    recovery = d.get('recovery', {})
    lines = [
        "🛡️ 예외 대시보드",
        f"전체 예외: {exc.get('total', 0)}건",
        f"해결률: {exc.get('resolution_rate', 0) * 100:.1f}%",
        f"복구 성공률: {recovery.get('success_rate', 0) * 100:.1f}%",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Phase 106: 자율 운영 대시보드 포맷터
# ─────────────────────────────────────────────────────────────

def _format_ops_status(d: dict) -> str:
    """운영 상태 포맷."""
    mode_emoji = {
        'fully_auto': '🤖', 'semi_auto': '🔄', 'manual': '👤', 'emergency': '🚨',
    }.get(d.get('mode', ''), '❓')
    score = d.get('health_score', 0)
    return (
        f"{mode_emoji} 운영 상태\n"
        f"모드: {d.get('mode', '-')}\n"
        f"건강 점수: {score:.1f}/100\n"
        f"활성 알림: {d.get('active_alerts', 0)}건\n"
        f"자동 액션: {d.get('auto_actions_count', 0)}건"
    )


_REVENUE_STREAM_KEYS = {'proxy_buy', 'import_', 'export', 'commission', 'service_fee'}


def _format_revenue_summary(d: dict) -> str:
    """수익 요약 포맷."""
    total = sum(v for k, v in d.items() if k in _REVENUE_STREAM_KEYS and isinstance(v, (int, float)))
    lines = ['💰 수익 현황', f'총계: {total:,.0f}원']
    for key in _REVENUE_STREAM_KEYS:
        val = d.get(key, 0)
        if isinstance(val, (int, float)) and val > 0:
            lines.append(f'• {key}: {val:,.0f}원')
    return "\n".join(lines)


def _format_anomaly_alert(d: dict) -> str:
    """이상 알림 포맷."""
    sev_emoji = {
        'low': '🟡', 'medium': '🟠', 'high': '🔴', 'critical': '💀',
    }.get(d.get('severity', ''), '⚠️')
    return (
        f"{sev_emoji} 이상 알림\n"
        f"ID: {d.get('alert_id', '-')}\n"
        f"유형: {d.get('type', '-')}\n"
        f"지표: {d.get('metric_name', '-')}\n"
        f"편차: {d.get('deviation_percent', 0):.1f}%\n"
        f"확인: {'✅' if d.get('acknowledged') else '❌'}"
    )


def _format_automation_report(d: dict) -> str:
    """자동화 보고 포맷."""
    coverage = d.get('automation_coverage', 0)
    return (
        f"🤖 자동화 보고\n"
        f"커버리지: {coverage * 100:.1f}%\n"
        f"자동 처리: {d.get('auto_handled', 0)}건\n"
        f"수동 개입: {d.get('manual_interventions', 0)}건\n"
        f"목표 달성: {'✅' if coverage >= 0.95 else '❌'}"
    )


def _format_ops_dashboard(d: dict) -> str:
    """통합 대시보드 포맷."""
    realtime = d.get('realtime', {})
    return (
        f"📊 통합 대시보드\n"
        f"수익: {realtime.get('revenue_today', 0):,.0f}원\n"
        f"이익: {realtime.get('profit_today', 0):,.0f}원\n"
        f"마진: {realtime.get('margin_rate', 0) * 100:.1f}%\n"
        f"자동화율: {realtime.get('automation_rate', 0) * 100:.1f}%\n"
        f"건강 점수: {realtime.get('health_score', 0):.1f}/100"
    )


def _format_simulation_result(d: dict) -> str:
    """시뮬레이션 결과 포맷."""
    status_emoji = {
        'completed': '✅', 'failed': '❌', 'running': '🔄', 'pending': '⏳',
    }.get(d.get('status', ''), '❓')
    recs = d.get('recommendations', [])
    lines = [
        f"{status_emoji} 시뮬레이션 결과",
        f"수익 영향: {d.get('revenue_impact', 0):+,.0f}원",
        f"비용 영향: {d.get('cost_impact', 0):+,.0f}원",
        f"주문 영향: {d.get('order_impact', 0):+d}건",
        f"위험 점수: {d.get('risk_score', 0):.1f}/100",
    ]
    for rec in recs[:2]:
        lines.append(f'💡 {rec}')
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Phase 107: 실시간 채팅 고객 지원 포맷터
# ─────────────────────────────────────────────────────────────

def _format_chat_session(data: dict) -> str:
    """채팅 세션 포맷."""
    session_id = data.get('session_id', '-')
    status = data.get('status', '-')
    customer_id = data.get('customer_id', '-')
    agent_id = data.get('agent_id') or '미배정'
    rating = data.get('rating')
    rating_str = f'{rating}/5' if rating is not None else '-'
    return (
        f"*💬 채팅 세션*\n"
        f"ID: `{session_id[:8]}...`\n"
        f"상태: *{status}*\n"
        f"고객: {customer_id}\n"
        f"상담원: {agent_id}\n"
        f"메시지: {data.get('message_count', 0)}개\n"
        f"만족도: {rating_str}"
    )


def _format_chat_stats(data: dict) -> str:
    """채팅 통계 포맷."""
    lines = ['*📊 채팅 통계*\n']
    lines.append(f"전체 세션: *{data.get('total_sessions', 0)}건*")
    lines.append(f"평균 만족도: *{data.get('average_rating', 0):.1f}/5.0*")
    lines.append(f"평가 세션: {data.get('rated_sessions', 0)}건")
    by_status = data.get('by_status', {})
    if by_status:
        lines.append('\n상태별:')
        for status, count in by_status.items():
            lines.append(f"  • {status}: {count}건")
    return '\n'.join(lines)


def _format_chat_queue(data: dict) -> str:
    """대기열 포맷."""
    queue = data.get('queue', [])
    lines = [f"*🔢 채팅 대기열* ({len(queue)}명)\n"]
    if not queue:
        lines.append('대기 중인 고객이 없습니다.')
    else:
        for i, entry in enumerate(queue[:10], 1):
            vip = ' [VIP]' if entry.get('is_vip') else ''
            lines.append(f"  {i}. 고객 {entry.get('customer_id', '-')}{vip}")
        if len(queue) > 10:
            lines.append(f'_... 외 {len(queue) - 10}명_')
    agent_stats = data.get('agent_stats', {})
    if agent_stats:
        lines.append(f"\n가용 상담원: {agent_stats.get('available', 0)}명")
    return '\n'.join(lines)


def _format_agent_profile(data: dict) -> str:
    """상담원 프로필 포맷."""
    available = '✅ 가용' if data.get('is_available') else '❌ 불가'
    return (
        f"*🎧 상담원 프로필*\n"
        f"이름: *{data.get('name', '-')}*\n"
        f"상태: {data.get('status', '-')} ({available})\n"
        f"세션: {data.get('current_sessions', 0)}/{data.get('max_sessions', 0)}\n"
        f"스킬: {', '.join(data.get('skills', [])) or '-'}\n"
        f"평점: {data.get('rating', 0):.1f}/5.0\n"
        f"근무: {data.get('shift', '-')}"
    )


def _format_chat_dashboard(data: dict) -> str:
    """채팅 대시보드 포맷."""
    rt = data.get('realtime', {})
    perf = data.get('performance', {})
    lines = [
        '*📱 채팅 대시보드*\n',
        f"활성 세션: *{rt.get('active_sessions', 0)}건*",
        f"대기 고객: *{rt.get('waiting_customers', 0)}명*",
        f"온라인 상담원: *{rt.get('online_agents', 0)}명*",
        '',
        f"평균 첫 응답: {perf.get('avg_first_response_seconds', 0):.0f}초",
        f"평균 해결 시간: {perf.get('avg_resolution_seconds', 0):.0f}초",
        f"평균 만족도: {perf.get('average_rating', 0):.1f}/5.0",
        f"전체 세션: {perf.get('total_sessions', 0)}건",
    ]
    return '\n'.join(lines)
