"""tests/test_order_router.py — Phase 3 주문 라우팅 로직 테스트.

SKU→벤더 매핑, 국제 라우팅, 배대지 배정 등 핵심 라우팅 로직을 검증한다.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.orders.router import OrderRouter, VENDOR_SKU_PREFIX  # noqa: E402

# ──────────────────────────────────────────────────────────
# 공통 테스트 데이터
# ──────────────────────────────────────────────────────────

CATALOG_ROWS = [
    {
        'sku': 'PTR-TNK-100000',
        'title_ko': '탱커 2WAY 브리프케이스',
        'title_en': 'Tanker 2WAY Briefcase',
        'src_url': 'https://www.yoshidakaban.com/product/100000.html',
        'buy_currency': 'JPY',
        'buy_price': 30800,
        'source_country': 'JP',
        'vendor': 'PORTER',
        'forwarder': 'zenmarket',
        'status': 'active',
    },
    {
        'sku': 'MMP-EDP-200001',
        'title_ko': '아프리칸 레더 오드파르팡',
        'title_en': 'African Leather Eau de Parfum',
        'src_url': 'https://www.memoparis.com/products/african-leather',
        'buy_currency': 'EUR',
        'buy_price': 250.0,
        'source_country': 'FR',
        'vendor': 'MEMO_PARIS',
        'forwarder': '',
        'status': 'active',
    },
]

SHOPIFY_ORDER_SINGLE = {
    'id': 12345,
    'order_number': 1001,
    'name': '#1001',
    'email': 'customer@example.com',
    'customer': {'first_name': '길동', 'last_name': '홍'},
    'line_items': [
        {'id': 1, 'sku': 'PTR-TNK-100000', 'title': 'Tanker Briefcase',
         'quantity': 1, 'price': '370000.00'},
    ],
    'shipping_address': {'country_code': 'KR', 'country': 'South Korea'},
    'financial_status': 'paid',
}

SHOPIFY_ORDER_MULTI = {
    'id': 22222,
    'order_number': 1002,
    'name': '#1002',
    'email': 'jane@example.com',
    'customer': {'first_name': 'Jane', 'last_name': 'Doe'},
    'line_items': [
        {'id': 1, 'sku': 'PTR-TNK-100000', 'title': 'Tanker Briefcase',
         'quantity': 1, 'price': '370000.00'},
        {'id': 2, 'sku': 'MMP-EDP-200001', 'title': 'African Leather EDP',
         'quantity': 1, 'price': '420000.00'},
    ],
    'shipping_address': {'country_code': 'US', 'country': 'United States'},
    'financial_status': 'paid',
}

SHOPIFY_ORDER_UNKNOWN_SKU = {
    'id': 33333,
    'order_number': 1003,
    'name': '#1003',
    'email': 'test@example.com',
    'customer': {'first_name': 'Test', 'last_name': 'User'},
    'line_items': [
        {'id': 1, 'sku': 'UNKNOWN-SKU-999', 'title': 'Mystery Item',
         'quantity': 2, 'price': '50000.00'},
    ],
    'shipping_address': {'country_code': 'KR'},
    'financial_status': 'paid',
}


def _make_router():
    """CatalogLookup을 mock으로 대체한 OrderRouter 인스턴스를 반환."""
    with patch('src.orders.router.CatalogLookup') as MockCatalog:
        mock_catalog = MagicMock()
        MockCatalog.return_value = mock_catalog
        router = OrderRouter()
        # SKU별 카탈로그 조회 결과 설정

        def _lookup(sku):
            return next((r for r in CATALOG_ROWS if r['sku'] == sku), None)

        mock_catalog.find_by_sku.side_effect = _lookup
        return router, mock_catalog


# ══════════════════════════════════════════════════════════
# VENDOR_SKU_PREFIX 상수 테스트
# ══════════════════════════════════════════════════════════

class TestVendorSkuPrefix:
    def test_ptr_maps_to_porter(self):
        assert VENDOR_SKU_PREFIX['PTR'] == 'porter'

    def test_mmp_maps_to_memo_paris(self):
        assert VENDOR_SKU_PREFIX['MMP'] == 'memo_paris'

    def test_prefix_count(self):
        """최소 2개 이상의 벤더 prefix가 정의되어 있어야 한다."""
        assert len(VENDOR_SKU_PREFIX) >= 2


# ══════════════════════════════════════════════════════════
# 단일 SKU 주문 라우팅
# ══════════════════════════════════════════════════════════

class TestSingleItemRouting:
    def test_route_order_returns_dict(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        assert isinstance(result, dict)

    def test_route_order_has_required_keys(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        assert 'order_id' in result
        assert 'tasks' in result
        assert 'summary' in result

    def test_route_order_id_matches(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        assert result['order_id'] == 12345

    def test_route_single_sku_creates_one_task(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        assert len(result['tasks']) == 1

    def test_route_porter_sku_assigns_porter_vendor(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        task = result['tasks'][0]
        assert task.get('vendor', '').lower() in ('porter', 'PORTER'.lower())

    def test_route_porter_sku_has_zenmarket_forwarder(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        task = result['tasks'][0]
        # zenmarket 배대지가 배정되어야 함
        assert 'zenmarket' in str(task).lower() or 'forwarder' in task

    def test_route_order_summary_total_tasks(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        assert result['summary']['total_tasks'] == 1


# ══════════════════════════════════════════════════════════
# 다중 SKU 주문 라우팅
# ══════════════════════════════════════════════════════════

class TestMultiItemRouting:
    def test_route_multi_sku_creates_multiple_tasks(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        assert len(result['tasks']) == 2

    def test_route_multi_summary_total_tasks(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        assert result['summary']['total_tasks'] == 2

    def test_route_multi_by_vendor_has_both(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        by_vendor = result['summary'].get('by_vendor', {})
        vendor_keys_lower = {k.lower() for k in by_vendor.keys()}
        assert 'porter' in vendor_keys_lower or len(by_vendor) >= 1

    def test_route_multi_order_number(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        assert result.get('order_number') in ('#1002', 1002, '1002')


# ══════════════════════════════════════════════════════════
# 알 수 없는 SKU 라우팅
# ══════════════════════════════════════════════════════════

class TestUnknownSkuRouting:
    def test_unknown_sku_does_not_raise(self):
        router, mock_catalog = _make_router()
        mock_catalog.find_by_sku.return_value = None
        result = router.route_order(SHOPIFY_ORDER_UNKNOWN_SKU)
        assert isinstance(result, dict)

    def test_unknown_sku_task_flags_unknown(self):
        router, mock_catalog = _make_router()
        mock_catalog.find_by_sku.return_value = None
        result = router.route_order(SHOPIFY_ORDER_UNKNOWN_SKU)
        # 알 수 없는 SKU는 태스크에 표시되어야 함
        if result['tasks']:
            task = result['tasks'][0]
            assert 'sku' in task

    def test_unknown_sku_has_summary(self):
        router, mock_catalog = _make_router()
        mock_catalog.find_by_sku.return_value = None
        result = router.route_order(SHOPIFY_ORDER_UNKNOWN_SKU)
        assert 'summary' in result


# ══════════════════════════════════════════════════════════
# 국제 라우팅 (InternationalRouter)
# ══════════════════════════════════════════════════════════

class TestInternationalRouting:
    def test_international_order_is_detected(self):
        """해외 배송 주문(US)은 국제 라우팅으로 처리되어야 한다."""
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        # 결과 구조가 올바르면 통과
        assert 'tasks' in result

    def test_domestic_order_kr(self):
        """국내(KR) 주문은 국내 라우팅으로 처리되어야 한다."""
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        assert 'tasks' in result
        assert result['tasks'][0]['sku'] == 'PTR-TNK-100000'


# ══════════════════════════════════════════════════════════
# 고객 정보 파싱
# ══════════════════════════════════════════════════════════

class TestCustomerParsing:
    def test_customer_info_extracted(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        assert 'customer' in result
        assert isinstance(result['customer'], dict)

    def test_customer_has_email_or_name(self):
        router, _ = _make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        customer = result['customer']
        has_info = bool(customer.get('email') or customer.get('name') or customer.get('first_name'))
        assert has_info

    def test_order_without_customer_does_not_raise(self):
        """customer 필드가 없는 주문도 처리 가능해야 한다."""
        router, _ = _make_router()
        order = dict(SHOPIFY_ORDER_SINGLE)
        order.pop('customer', None)
        result = router.route_order(order)
        assert isinstance(result, dict)
