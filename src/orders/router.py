"""주문 라우팅 엔진 — Shopify 주문 데이터 → 벤더별 구매 태스크 생성."""

import os
import logging

from .catalog_lookup import CatalogLookup, SKU_PREFIX_VENDOR

logger = logging.getLogger(__name__)

# SKU 접두어 → 벤더 키 매핑
VENDOR_SKU_PREFIX = {
    'PTR': 'porter',
    'MMP': 'memo_paris',
}

# 배대지 정보
FORWARDER_INFO: dict[str, dict] = {
    'zenmarket': {
        'name': 'Zenmarket',
        'country': 'JP',
        'instructions': '젠마켓 구매대행 신청 → 국내 배송지로 발송 요청',
        'address_env': 'ZENMARKET_ADDRESS',
        'default_address': '(젠마켓 기본 창고 — 환경변수 설정 필요)',
    },
    '': {
        'name': 'Direct',
        'country': '',
        'instructions': '공식 사이트에서 직접 주문 → 한국 직배송',
        'address_env': 'WAREHOUSE_ADDRESS',
        'default_address': '(국내 수령 주소 — 환경변수 설정 필요)',
    },
}


class OrderRouter:
    """주문을 분석하여 벤더별 구매 태스크로 라우팅하는 엔진."""

    def __init__(self):
        self.catalog = CatalogLookup()

    # ── 공개 API ────────────────────────────────────────────

    def route_order(self, order_data: dict) -> dict:
        """Shopify 주문 데이터 → 벤더별 구매 태스크 생성.

        Args:
            order_data: Shopify webhook order payload

        Returns:
            {
                'order_id': 12345,
                'order_number': '#1001',
                'customer': {'name': '...', 'email': '...'},
                'tasks': [...],
                'summary': {
                    'total_tasks': int,
                    'by_vendor': {...},
                    'by_forwarder': {...},
                },
            }
        """
        order_id = order_data.get('id')
        order_number = order_data.get('order_number') or order_data.get('name', '')
        customer_info = order_data.get('customer') or {}
        billing = order_data.get('billing_address') or {}
        customer_name = (
            customer_info.get('first_name', '') + ' ' + customer_info.get('last_name', '')
        ).strip() or billing.get('name', '')
        customer_email = customer_info.get('email', '') or order_data.get('email', '')

        line_items = order_data.get('line_items', [])

        # 배치 조회로 API 호출 최소화
        skus = []
        for it in line_items:
            sku = it.get('sku') or (it.get('variant_id') and str(it['variant_id'])) or ''
            skus.append(sku)
        catalog_map = self.catalog.lookup_batch(skus)

        tasks = []
        for it in line_items:
            sku = it.get('sku') or (it.get('variant_id') and str(it['variant_id'])) or ''
            catalog_row = catalog_map.get(sku) or self.catalog.lookup_by_sku(sku) or {}
            task = self._build_task(it, catalog_row)
            tasks.append(task)

        # 통계 집계
        by_vendor: dict[str, int] = {}
        by_forwarder: dict[str, int] = {}
        for t in tasks:
            vendor = t['vendor']
            fwd = t['forwarder'] or 'direct'
            by_vendor[vendor] = by_vendor.get(vendor, 0) + 1
            by_forwarder[fwd] = by_forwarder.get(fwd, 0) + 1

        return {
            'order_id': order_id,
            'order_number': str(order_number),
            'customer': {'name': customer_name, 'email': customer_email},
            'tasks': tasks,
            'summary': {
                'total_tasks': len(tasks),
                'by_vendor': by_vendor,
                'by_forwarder': by_forwarder,
            },
        }

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _build_task(self, line_item: dict, catalog_row: dict) -> dict:
        """단일 주문 라인 아이템 → 구매 태스크 dict 생성."""
        sku = line_item.get('sku') or (
            line_item.get('variant_id') and str(line_item['variant_id'])
        ) or ''

        # 벤더 정보 결정
        prefix = (sku or '').split('-')[0].upper()
        vendor_key = VENDOR_SKU_PREFIX.get(prefix, '')

        if vendor_key == 'porter':
            vendor_name = 'PORTER'
            source_country = 'JP'
            buy_currency = 'JPY'
            forwarder = 'zenmarket'
        elif vendor_key == 'memo_paris':
            vendor_name = 'MEMO_PARIS'
            source_country = 'FR'
            buy_currency = 'EUR'
            forwarder = ''
        else:
            vendor_name = str(catalog_row.get('vendor', 'UNKNOWN')).upper()
            source_country = str(catalog_row.get('source_country', ''))
            buy_currency = str(catalog_row.get('buy_currency', ''))
            forwarder = str(catalog_row.get('forwarder', ''))

        src_url = str(catalog_row.get('src_url', ''))
        try:
            buy_price = float(catalog_row.get('buy_price', 0) or 0)
        except (ValueError, TypeError):
            buy_price = 0.0

        quantity = int(line_item.get('quantity', 1) or 1)

        return {
            'sku': sku,
            'title': str(
                catalog_row.get('title_ko')
                or catalog_row.get('title_en')
                or line_item.get('title', '')
            ),
            'vendor': vendor_name,
            'forwarder': forwarder,
            'src_url': src_url,
            'quantity': quantity,
            'buy_price': buy_price,
            'buy_currency': buy_currency,
            'source_country': source_country,
            'forwarder_address': self._get_forwarder_address(forwarder),
            'instructions': self._build_instructions(vendor_name, catalog_row),
        }

    def _get_forwarder_address(self, forwarder: str) -> str:
        """배대지 이름 → 배대지 주소.

        환경변수:
          ZENMARKET_ADDRESS  (기본: 젠마켓 기본 창고 안내 문구)
          WAREHOUSE_ADDRESS  (기본: 국내 수령 주소 안내 문구)
        """
        info = FORWARDER_INFO.get(forwarder, FORWARDER_INFO[''])
        env_key = info['address_env']
        return os.getenv(env_key, info['default_address'])

    def _build_instructions(self, vendor_name: str, catalog_row: dict) -> str:
        """벤더별 구매 지시사항 생성."""
        if vendor_name == 'PORTER':
            return '젠마켓에서 해당 URL 구매 → 국내 배대지로 발송 요청'
        if vendor_name == 'MEMO_PARIS':
            return '메모파리 공식 사이트에서 직접 주문 → 한국 직배송 요청'
        return '구매처에서 직접 주문 후 지정 주소로 발송 요청'
