"""다국어 배송 상태 알림 템플릿."""
from __future__ import annotations

TEMPLATES = {
    'ko': {
        'picked_up': "📦 [{order_id}] 상품이 발송되었습니다.\n운송장: {tracking_no} ({carrier})",
        'in_transit': "🚚 [{order_id}] 배송 중입니다.\n위치: {location}\n운송장: {tracking_no}",
        'out_for_delivery': "🏃 [{order_id}] 오늘 배송 예정입니다!\n운송장: {tracking_no}",
        'delivered': "✅ [{order_id}] 배송이 완료되었습니다.\n감사합니다! 운송장: {tracking_no}",
        'exception': "⚠️ [{order_id}] 배송 중 문제가 발생했습니다.\n운송장: {tracking_no}\n고객센터: 1:1 문의",
        'delayed': "⏰ [{order_id}] 배송이 지연되고 있습니다.\n운송장: {tracking_no} ({carrier})\n지연 사유를 확인 중입니다.",
    },
    'en': {
        'picked_up': "📦 [{order_id}] Your order has been shipped.\nTracking: {tracking_no} ({carrier})",
        'in_transit': "🚚 [{order_id}] Your order is in transit.\nLocation: {location}\nTracking: {tracking_no}",
        'out_for_delivery': "🏃 [{order_id}] Your order is out for delivery today!\nTracking: {tracking_no}",
        'delivered': "✅ [{order_id}] Your order has been delivered.\nThank you! Tracking: {tracking_no}",
        'exception': "⚠️ [{order_id}] There is an issue with your delivery.\nTracking: {tracking_no}\nPlease contact support.",
        'delayed': "⏰ [{order_id}] Your delivery is delayed.\nTracking: {tracking_no} ({carrier})\nWe are investigating.",
    },
    'ja': {
        'picked_up': "📦 [{order_id}] 商品が発送されました。\n追跡番号: {tracking_no} ({carrier})",
        'in_transit': "🚚 [{order_id}] 配送中です。\n現在地: {location}\n追跡番号: {tracking_no}",
        'out_for_delivery': "🏃 [{order_id}] 本日配達予定です！\n追跡番号: {tracking_no}",
        'delivered': "✅ [{order_id}] お荷物が届きました。\nありがとうございます！追跡番号: {tracking_no}",
        'exception': "⚠️ [{order_id}] 配送に問題が発生しました。\n追跡番号: {tracking_no}\nサポートにお問い合わせください。",
        'delayed': "⏰ [{order_id}] 配送が遅延しています。\n追跡番号: {tracking_no} ({carrier})\n調査中です。",
    },
    'zh': {
        'picked_up': "📦 [{order_id}] 您的商品已发货。\n追踪号: {tracking_no} ({carrier})",
        'in_transit': "🚚 [{order_id}] 您的包裹正在运输中。\n位置: {location}\n追踪号: {tracking_no}",
        'out_for_delivery': "🏃 [{order_id}] 您的包裹今天将送达！\n追踪号: {tracking_no}",
        'delivered': "✅ [{order_id}] 您的包裹已成功送达。\n感谢您的购买！追踪号: {tracking_no}",
        'exception': "⚠️ [{order_id}] 您的包裹配送出现问题。\n追踪号: {tracking_no}\n请联系客服。",
        'delayed': "⏰ [{order_id}] 您的包裹配送延迟。\n追踪号: {tracking_no} ({carrier})\n我们正在调查。",
    },
}

SUPPORTED_LANGUAGES = list(TEMPLATES.keys())
SUPPORTED_STATUSES = list(TEMPLATES['ko'].keys())


def render_template(status: str, language: str, **kwargs) -> str:
    """상태와 언어에 맞는 템플릿을 렌더링한다."""
    lang = language if language in TEMPLATES else 'ko'
    status_templates = TEMPLATES[lang]
    template = status_templates.get(status, status_templates.get('exception', ''))
    try:
        return template.format(**{k: (v or '') for k, v in kwargs.items()})
    except KeyError:
        return template
