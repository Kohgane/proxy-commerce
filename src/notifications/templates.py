"""메시지 템플릿 관리 — 이메일 HTML/텍스트 + 텔레그램 텍스트."""

import logging

logger = logging.getLogger(__name__)

# ─── 한국어 템플릿 ────────────────────────────────────────

_KO_SUBJECTS = {
    'confirmed': '[주문 확인] 주문이 접수되었습니다 — #{order_id}',
    'shipped': '[배송 시작] 상품이 출발했습니다 — #{order_id}',
    'delivered': '[배송 완료] 상품이 도착했습니다 — #{order_id}',
}

_KO_HTML = {
    'confirmed': """<html><body>
<h2>주문이 확인되었습니다 ✅</h2>
<p>안녕하세요, {customer_name}님!</p>
<p>주문번호 <strong>{order_id}</strong>가 정상적으로 접수되었습니다.</p>
<table border="1" cellpadding="6" style="border-collapse:collapse;">
  <tr><th>SKU</th><td>{sku}</td></tr>
  <tr><th>상품명</th><td>{title}</td></tr>
  <tr><th>금액</th><td>{sell_price_krw:,}원</td></tr>
  <tr><th>상태</th><td>주문 접수</td></tr>
</table>
<p>배송이 시작되면 다시 안내드리겠습니다.</p>
<p>감사합니다.</p>
</body></html>""",

    'shipped': """<html><body>
<h2>상품이 출발했습니다 🚚</h2>
<p>안녕하세요, {customer_name}님!</p>
<p>주문번호 <strong>{order_id}</strong> 상품이 배송을 시작했습니다.</p>
<table border="1" cellpadding="6" style="border-collapse:collapse;">
  <tr><th>SKU</th><td>{sku}</td></tr>
  <tr><th>운송장 번호</th><td>{tracking_number}</td></tr>
  <tr><th>택배사</th><td>{carrier}</td></tr>
</table>
<p>감사합니다.</p>
</body></html>""",

    'delivered': """<html><body>
<h2>배송이 완료되었습니다 📦</h2>
<p>안녕하세요, {customer_name}님!</p>
<p>주문번호 <strong>{order_id}</strong> 상품 배송이 완료되었습니다.</p>
<p>이용해 주셔서 감사합니다!</p>
</body></html>""",
}

_KO_TEXT = {
    'confirmed': (
        "주문이 확인되었습니다 ✅\n"
        "주문번호: {order_id}\n"
        "SKU: {sku} / {title}\n"
        "금액: {sell_price_krw}원\n"
        "배송이 시작되면 다시 안내드리겠습니다."
    ),
    'shipped': (
        "상품이 출발했습니다 🚚\n"
        "주문번호: {order_id}\n"
        "운송장 번호: {tracking_number}\n"
        "택배사: {carrier}"
    ),
    'delivered': (
        "배송이 완료되었습니다 📦\n"
        "주문번호: {order_id}\n"
        "이용해 주셔서 감사합니다!"
    ),
}

# ─── 영어 템플릿 ────────────────────────────────────────

_EN_SUBJECTS = {
    'confirmed': '[Order Confirmed] Your order has been received — #{order_id}',
    'shipped': '[Shipped] Your order is on the way — #{order_id}',
    'delivered': '[Delivered] Your order has arrived — #{order_id}',
}

_EN_HTML = {
    'confirmed': """<html><body>
<h2>Order Confirmed ✅</h2>
<p>Hello, {customer_name}!</p>
<p>Your order <strong>{order_id}</strong> has been successfully placed.</p>
<table border="1" cellpadding="6" style="border-collapse:collapse;">
  <tr><th>SKU</th><td>{sku}</td></tr>
  <tr><th>Product</th><td>{title}</td></tr>
  <tr><th>Amount</th><td>{sell_price_krw:,} KRW</td></tr>
  <tr><th>Status</th><td>Confirmed</td></tr>
</table>
<p>We will notify you when your order ships.</p>
<p>Thank you!</p>
</body></html>""",

    'shipped': """<html><body>
<h2>Your Order is on the Way 🚚</h2>
<p>Hello, {customer_name}!</p>
<p>Order <strong>{order_id}</strong> has been shipped.</p>
<table border="1" cellpadding="6" style="border-collapse:collapse;">
  <tr><th>SKU</th><td>{sku}</td></tr>
  <tr><th>Tracking Number</th><td>{tracking_number}</td></tr>
  <tr><th>Carrier</th><td>{carrier}</td></tr>
</table>
<p>Thank you!</p>
</body></html>""",

    'delivered': """<html><body>
<h2>Order Delivered 📦</h2>
<p>Hello, {customer_name}!</p>
<p>Order <strong>{order_id}</strong> has been delivered.</p>
<p>Thank you for your purchase!</p>
</body></html>""",
}

_EN_TEXT = {
    'confirmed': (
        "Order Confirmed ✅\n"
        "Order ID: {order_id}\n"
        "SKU: {sku} / {title}\n"
        "Amount: {sell_price_krw} KRW"
    ),
    'shipped': (
        "Your order is on the way 🚚\n"
        "Order ID: {order_id}\n"
        "Tracking: {tracking_number} ({carrier})"
    ),
    'delivered': (
        "Order Delivered 📦\n"
        "Order ID: {order_id}\n"
        "Thank you for your purchase!"
    ),
}

# ─── 텔레그램 템플릿 ──────────────────────────────────────

TELEGRAM_TEMPLATES = {
    'confirmed': "✅ *주문 확인*\n주문번호: `{order_id}`\nSKU: `{sku}`\n금액: {sell_price_krw}원",
    'shipped': "🚚 *배송 시작*\n주문번호: `{order_id}`\n운송장: `{tracking_number}` ({carrier})",
    'delivered': "📦 *배송 완료*\n주문번호: `{order_id}`\n완료!",
}

_LOCALE_MAP = {
    'ko': (_KO_SUBJECTS, _KO_HTML, _KO_TEXT),
    'en': (_EN_SUBJECTS, _EN_HTML, _EN_TEXT),
}


def get_email_template(stage: str, order: dict, locale: str = 'ko') -> tuple:
    """이메일 템플릿 반환.

    Returns:
        (subject, html_body, text_body) 튜플
    """
    subjects, html_tmpl, text_tmpl = _LOCALE_MAP.get(locale, _LOCALE_MAP['ko'])

    if stage not in subjects:
        raise ValueError(f'알 수 없는 알림 단계: {stage}')

    # 안전한 포맷 — 누락된 키는 빈 문자열로 대체
    ctx = {
        'order_id': order.get('order_id', '-'),
        'customer_name': order.get('customer_name', '고객'),
        'sku': order.get('sku', '-'),
        'title': order.get('title', '-'),
        'sell_price_krw': order.get('sell_price_krw', 0),
        'tracking_number': order.get('tracking_number', '-'),
        'carrier': order.get('carrier', '-'),
    }

    try:
        subject = subjects[stage].format(**ctx)
    except (KeyError, ValueError):
        subject = subjects[stage]

    try:
        html_body = html_tmpl[stage].format(**ctx)
    except (KeyError, ValueError):
        html_body = text_tmpl[stage]

    try:
        text_body = text_tmpl[stage].format(**ctx)
    except (KeyError, ValueError):
        text_body = str(ctx)

    return subject, html_body, text_body


def get_telegram_template(stage: str, order: dict) -> str:
    """텔레그램 메시지 템플릿 반환."""
    tmpl = TELEGRAM_TEMPLATES.get(stage, '알림: {order_id}')
    ctx = {
        'order_id': order.get('order_id', '-'),
        'sku': order.get('sku', '-'),
        'sell_price_krw': order.get('sell_price_krw', 0),
        'tracking_number': order.get('tracking_number', '-'),
        'carrier': order.get('carrier', '-'),
    }
    try:
        return tmpl.format(**ctx)
    except (KeyError, ValueError):
        return str(ctx)


class NotificationTemplate:
    """이벤트 기반 알림 템플릿 렌더링."""

    _TEMPLATES = {
        'order_placed': '주문이 접수되었습니다. 주문번호: {order_id}',
        'order_shipped': '주문이 발송되었습니다. 운송장: {tracking_number}',
        'stock_low': '재고 부족 경고: {sku} (현재: {current_stock})',
        'price_changed': '가격 변동: {sku} {old_price} -> {new_price}',
        'cs_ticket': 'CS 티켓 접수: [{priority}] {subject}',
        'system_alert': '시스템 알림: {message}',
    }

    def render(self, event_type: str, data: dict) -> str:
        """이벤트 타입과 데이터로 메시지 렌더링."""
        template = self._TEMPLATES.get(event_type, '{message}')
        try:
            return template.format(**data)
        except (KeyError, ValueError):
            return template
