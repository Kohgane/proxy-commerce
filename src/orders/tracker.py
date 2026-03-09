"""배송 추적 + Shopify/WooCommerce Fulfillment 업데이트 모듈."""

import os
import logging

import requests

logger = logging.getLogger(__name__)

# 택배사 코드 → Shopify/WooCommerce 호환 코드 매핑
CARRIER_MAP: dict[str, dict] = {
    'yamato': {
        'shopify': 'Yamato Transport',
        'tracking_url': 'https://jizen.kuronekoyamato.co.jp/jizen/servlet/crjz.b.NQ0010?id={}',
    },
    'ems': {
        'shopify': 'EMS',
        'tracking_url': 'https://service.epost.go.kr/trace.RetrieveEmsRi498TraceDe.postal?ems_gubun=E&POST_CODE={}',
    },
    'fedex': {
        'shopify': 'FedEx',
        'tracking_url': 'https://www.fedex.com/fedextrack/?trknbr={}',
    },
    'cj': {
        'shopify': 'CJ Logistics',
        'tracking_url': 'https://www.cjlogistics.com/ko/tool/parcel/tracking?gnbInvcNo={}',
    },
    'hanjin': {
        'shopify': 'Hanjin',
        'tracking_url': 'https://www.hanjin.com/kor/CMS/DeliveryMgr/WaybillResult.do?mession-id=0&wblnum={}',
    },
}


class OrderTracker:
    """주문 배송 추적 + 스토어 Fulfillment 업데이트."""

    # ── 공개 API ────────────────────────────────────────────

    def process_tracking(self, tracking_data: dict) -> dict:
        """배대지/직배송 추적 정보를 처리.

        tracking_data:
        {
            'order_id': 12345,
            'sku': 'PTR-TNK-001',
            'tracking_number': '...',
            'carrier': 'yamato' | 'ems' | 'fedex' | 'cj' | ...,
            'status': 'shipped' | 'in_transit' | 'delivered',
        }

        Returns:
        {
            'shopify_updated': True/False,
            'woo_updated': True/False,
            'notification_sent': True/False,
        }
        """
        order_id = tracking_data.get('order_id')
        tracking_number = str(tracking_data.get('tracking_number', ''))
        carrier = str(tracking_data.get('carrier', ''))

        shopify_ok = False
        woo_ok = False

        if order_id and tracking_number:
            shopify_ok = self._update_shopify_fulfillment(order_id, tracking_number, carrier)
            woo_ok = self._update_woo_tracking(order_id, tracking_number, carrier)

        return {
            'shopify_updated': shopify_ok,
            'woo_updated': woo_ok,
            'notification_sent': shopify_ok or woo_ok,
        }

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _update_shopify_fulfillment(
        self,
        order_id,
        tracking_number: str,
        carrier: str,
    ) -> bool:
        """Shopify REST API로 fulfillment 생성/업데이트.

        POST /admin/api/{version}/orders/{order_id}/fulfillments.json
        SHOPIFY_LOCATION_ID 환경변수 사용.
        """
        shop = os.getenv('SHOPIFY_SHOP')
        token = os.getenv('SHOPIFY_ACCESS_TOKEN')
        api_version = os.getenv('SHOPIFY_API_VERSION', '2024-07')
        location_id = os.getenv('SHOPIFY_LOCATION_ID')

        if not shop or not token:
            logger.warning("Shopify env vars not set — fulfillment skipped")
            return False

        carrier_info = CARRIER_MAP.get(carrier.lower(), {})
        shopify_carrier = carrier_info.get('shopify', carrier)
        tracking_url = carrier_info.get('tracking_url', '').format(tracking_number) if tracking_number else ''

        payload: dict = {
            'fulfillment': {
                'tracking_number': tracking_number,
                'tracking_company': shopify_carrier,
                'tracking_url': tracking_url,
                'notify_customer': True,
            }
        }
        if location_id:
            payload['fulfillment']['location_id'] = int(location_id)

        url = f"https://{shop}/admin/api/{api_version}/orders/{order_id}/fulfillments.json"
        headers = {
            'X-Shopify-Access-Token': token,
            'Content-Type': 'application/json',
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            logger.info("Shopify fulfillment created for order %s, tracking %s", order_id, tracking_number)
            return True
        except Exception as exc:
            logger.error("Shopify fulfillment update failed: %s", exc)
            return False

    def _update_woo_tracking(
        self,
        order_id,
        tracking_number: str,
        carrier: str,
    ) -> bool:
        """WooCommerce REST API로 주문 노트 추가 + 상태 변경 (processing → completed).

        PUT /wp-json/wc/v3/orders/{order_id} with status + customer_note
        """
        base_url = os.getenv('WOO_BASE_URL')
        ck = os.getenv('WOO_CK')
        cs = os.getenv('WOO_CS')
        api_version = os.getenv('WOO_API_VERSION', 'wc/v3')

        if not base_url or not ck or not cs:
            logger.warning("WooCommerce env vars not set — tracking update skipped")
            return False

        carrier_display = self._map_carrier_code(carrier)
        note = f'[발송 완료] 택배사: {carrier_display} / 송장번호: {tracking_number}'

        payload = {
            'status': 'completed',
            'customer_note': note,
        }
        url = f"{base_url.rstrip('/')}/wp-json/{api_version}/orders/{order_id}"
        try:
            r = requests.put(url, auth=(ck, cs), json=payload, timeout=30)
            r.raise_for_status()
            logger.info("WooCommerce order %s updated to completed, tracking %s", order_id, tracking_number)
            return True
        except Exception as exc:
            logger.error("WooCommerce tracking update failed: %s", exc)
            return False

    def _map_carrier_code(self, carrier: str) -> str:
        """택배사 코드 → Shopify/WooCommerce 호환 코드 매핑."""
        info = CARRIER_MAP.get(carrier.lower(), {})
        return info.get('shopify', carrier)
