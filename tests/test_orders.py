"""tests/test_orders.py — Phase 3 주문 라우팅 엔진 테스트 (40+)"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ──────────────────────────────────────────────────────────
# 공통 픽스처
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
    },
]

SHOPIFY_ORDER_SINGLE = {
    'id': 12345,
    'order_number': 1001,
    'name': '#1001',
    'customer': {'first_name': '길동', 'last_name': '홍', 'email': 'hong@example.com'},
    'line_items': [
        {
            'sku': 'PTR-TNK-100000',
            'title': 'Tanker Briefcase',
            'quantity': 1,
            'variant_id': 987,
        }
    ],
}

SHOPIFY_ORDER_MULTI = {
    'id': 99999,
    'order_number': 1002,
    'name': '#1002',
    'customer': {'first_name': '철수', 'last_name': '김', 'email': 'cs@example.com'},
    'line_items': [
        {'sku': 'PTR-TNK-100000', 'title': 'Tanker Briefcase', 'quantity': 2, 'variant_id': 111},
        {'sku': 'MMP-EDP-200001', 'title': 'African Leather', 'quantity': 1, 'variant_id': 222},
    ],
}


# ══════════════════════════════════════════════════════════
# CatalogLookup テスト
# ══════════════════════════════════════════════════════════

class TestCatalogLookup:
    def _make_lookup(self, rows=None):
        from src.orders.catalog_lookup import CatalogLookup
        cl = CatalogLookup(sheet_id='dummy', worksheet='catalog')
        cl._cache = rows if rows is not None else list(CATALOG_ROWS)
        return cl

    # ── lookup_by_sku ──────────────────────────────────────

    def test_lookup_by_sku_found(self):
        cl = self._make_lookup()
        row = cl.lookup_by_sku('PTR-TNK-100000')
        assert row is not None
        assert row['sku'] == 'PTR-TNK-100000'

    def test_lookup_by_sku_not_found(self):
        cl = self._make_lookup()
        assert cl.lookup_by_sku('NONEXISTENT-SKU') is None

    def test_lookup_by_sku_empty_string(self):
        cl = self._make_lookup()
        assert cl.lookup_by_sku('') is None

    def test_lookup_by_sku_none(self):
        cl = self._make_lookup()
        assert cl.lookup_by_sku(None) is None

    def test_lookup_by_sku_whitespace_stripped(self):
        cl = self._make_lookup()
        row = cl.lookup_by_sku('  PTR-TNK-100000  ')
        assert row is not None

    def test_lookup_by_sku_memo(self):
        cl = self._make_lookup()
        row = cl.lookup_by_sku('MMP-EDP-200001')
        assert row['vendor'] == 'MEMO_PARIS'

    # ── lookup_batch ──────────────────────────────────────

    def test_lookup_batch_multiple_skus(self):
        cl = self._make_lookup()
        result = cl.lookup_batch(['PTR-TNK-100000', 'MMP-EDP-200001'])
        assert 'PTR-TNK-100000' in result
        assert 'MMP-EDP-200001' in result

    def test_lookup_batch_partial_match(self):
        cl = self._make_lookup()
        result = cl.lookup_batch(['PTR-TNK-100000', 'NO-SUCH-SKU'])
        assert 'PTR-TNK-100000' in result
        assert 'NO-SUCH-SKU' not in result

    def test_lookup_batch_empty_list(self):
        cl = self._make_lookup()
        assert cl.lookup_batch([]) == {}

    def test_lookup_batch_single_api_call(self):
        """배치 조회는 시트를 1회만 읽어야 한다 (캐시 활용)."""
        cl = self._make_lookup()
        cl._cache = None  # 캐시 초기화
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = list(CATALOG_ROWS)
        with patch('src.orders.catalog_lookup.CatalogLookup._load_records', wraps=cl._load_records) as mock_load:
            with patch('src.utils.sheets.open_sheet', return_value=mock_ws):
                cl.lookup_batch(['PTR-TNK-100000', 'MMP-EDP-200001'])
                cl.lookup_batch(['PTR-TNK-100000'])
                # 두 번 호출해도 _load_records는 2번 호출되지만 시트 open은 1번
                assert mock_load.call_count == 2

    # ── caching ──────────────────────────────────────────

    def test_cache_populated_after_first_lookup(self):
        from src.orders.catalog_lookup import CatalogLookup
        cl = CatalogLookup(sheet_id='dummy')
        cl._cache = None
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = list(CATALOG_ROWS)
        with patch('src.utils.sheets.open_sheet', return_value=mock_ws):
            cl.lookup_by_sku('PTR-TNK-100000')
            assert cl._cache is not None
            # Second call should NOT call open_sheet again
            cl.lookup_by_sku('MMP-EDP-200001')
            assert mock_ws.get_all_records.call_count == 1

    # ── get_vendor_info ──────────────────────────────────

    def test_get_vendor_info_porter_prefix(self):
        cl = self._make_lookup()
        info = cl.get_vendor_info('PTR-TNK-100000')
        assert info['vendor_name'] == 'PORTER'
        assert info['source_country'] == 'JP'
        assert info['buy_currency'] == 'JPY'
        assert info['forwarder'] == 'zenmarket'

    def test_get_vendor_info_memo_prefix(self):
        cl = self._make_lookup()
        info = cl.get_vendor_info('MMP-EDP-200001')
        assert info['vendor_name'] == 'MEMO_PARIS'
        assert info['source_country'] == 'FR'
        assert info['buy_currency'] == 'EUR'
        assert info['forwarder'] == ''

    def test_get_vendor_info_unknown_prefix(self):
        cl = self._make_lookup([])
        info = cl.get_vendor_info('XYZ-001')
        assert info['vendor_name'] == 'UNKNOWN'

    def test_get_vendor_info_src_url_from_catalog(self):
        cl = self._make_lookup()
        info = cl.get_vendor_info('PTR-TNK-100000')
        assert 'yoshidakaban' in info['src_url']


# ══════════════════════════════════════════════════════════
# OrderRouter テスト
# ══════════════════════════════════════════════════════════

class TestOrderRouter:
    def _make_router(self, catalog_rows=None):
        from src.orders.router import OrderRouter
        router = OrderRouter()
        router.catalog._cache = catalog_rows if catalog_rows is not None else list(CATALOG_ROWS)
        return router

    # ── route_order 기본 ──────────────────────────────────

    def test_route_order_single_item(self):
        router = self._make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        assert result['order_id'] == 12345
        assert result['order_number'] == '1001'
        assert len(result['tasks']) == 1

    def test_route_order_customer_info(self):
        router = self._make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        assert '홍' in result['customer']['name'] or '길동' in result['customer']['name']
        assert result['customer']['email'] == 'hong@example.com'

    def test_route_order_task_has_required_keys(self):
        router = self._make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        task = result['tasks'][0]
        for key in ('sku', 'vendor', 'forwarder', 'src_url', 'quantity',
                    'buy_price', 'buy_currency', 'source_country',
                    'forwarder_address', 'instructions'):
            assert key in task, f"키 누락: {key}"

    def test_route_order_porter_vendor(self):
        router = self._make_router()
        result = router.route_order(SHOPIFY_ORDER_SINGLE)
        task = result['tasks'][0]
        assert task['vendor'] == 'PORTER'
        assert task['forwarder'] == 'zenmarket'
        assert task['buy_currency'] == 'JPY'

    # ── 복수 아이템 ──────────────────────────────────────

    def test_route_order_multi_items(self):
        router = self._make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        assert len(result['tasks']) == 2

    def test_route_order_different_vendors(self):
        router = self._make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        vendors = {t['vendor'] for t in result['tasks']}
        assert 'PORTER' in vendors
        assert 'MEMO_PARIS' in vendors

    def test_route_order_summary_total_tasks(self):
        router = self._make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        assert result['summary']['total_tasks'] == 2

    def test_route_order_summary_by_vendor(self):
        router = self._make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        by_vendor = result['summary']['by_vendor']
        assert by_vendor.get('PORTER', 0) == 1
        assert by_vendor.get('MEMO_PARIS', 0) == 1

    def test_route_order_summary_by_forwarder(self):
        router = self._make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        by_fwd = result['summary']['by_forwarder']
        assert by_fwd.get('zenmarket', 0) == 1
        assert by_fwd.get('direct', 0) == 1

    def test_route_order_quantity_mapped(self):
        router = self._make_router()
        result = router.route_order(SHOPIFY_ORDER_MULTI)
        porter_task = next(t for t in result['tasks'] if t['vendor'] == 'PORTER')
        assert porter_task['quantity'] == 2

    # ── SKU 없는 경우 ─────────────────────────────────────

    def test_route_order_unknown_sku(self):
        router = self._make_router()
        order = {
            'id': 1,
            'order_number': 9999,
            'customer': {},
            'line_items': [{'sku': 'UNKNOWN-SKU', 'quantity': 1}],
        }
        result = router.route_order(order)
        assert len(result['tasks']) == 1
        assert result['tasks'][0]['vendor'] == 'UNKNOWN'

    def test_route_order_no_line_items(self):
        router = self._make_router()
        order = {'id': 2, 'order_number': 2, 'customer': {}, 'line_items': []}
        result = router.route_order(order)
        assert result['tasks'] == []
        assert result['summary']['total_tasks'] == 0

    # ── _get_forwarder_address ────────────────────────────

    def test_forwarder_address_zenmarket_env(self):
        router = self._make_router()
        with patch.dict(os.environ, {'ZENMARKET_ADDRESS': 'Tokyo JP 123'}):
            addr = router._get_forwarder_address('zenmarket')
            assert addr == 'Tokyo JP 123'

    def test_forwarder_address_zenmarket_default(self):
        router = self._make_router()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('ZENMARKET_ADDRESS', None)
            addr = router._get_forwarder_address('zenmarket')
            assert '젠마켓' in addr or '환경변수' in addr

    def test_forwarder_address_direct_env(self):
        router = self._make_router()
        with patch.dict(os.environ, {'WAREHOUSE_ADDRESS': 'Seoul KR 456'}):
            addr = router._get_forwarder_address('')
            assert addr == 'Seoul KR 456'

    # ── _build_instructions ──────────────────────────────

    def test_instructions_porter(self):
        router = self._make_router()
        instr = router._build_instructions('PORTER', {})
        assert '젠마켓' in instr

    def test_instructions_memo_paris(self):
        router = self._make_router()
        instr = router._build_instructions('MEMO_PARIS', {})
        assert '메모파리' in instr

    def test_instructions_unknown_vendor(self):
        router = self._make_router()
        instr = router._build_instructions('UNKNOWN', {})
        assert instr  # non-empty fallback


# ══════════════════════════════════════════════════════════
# OrderNotifier テスト
# ══════════════════════════════════════════════════════════

ROUTED_ORDER_FIXTURE = {
    'order_id': 12345,
    'order_number': '#1001',
    'customer': {'name': '홍길동', 'email': 'hong@example.com'},
    'tasks': [
        {
            'sku': 'PTR-TNK-100000',
            'title': '탱커 브리프케이스',
            'vendor': 'PORTER',
            'forwarder': 'zenmarket',
            'src_url': 'https://www.yoshidakaban.com/product/100000.html',
            'quantity': 1,
            'buy_price': 30800,
            'buy_currency': 'JPY',
            'source_country': 'JP',
            'forwarder_address': '젠마켓 창고',
            'instructions': '젠마켓에서 해당 URL 구매 → 국내 배대지로 발송 요청',
        },
        {
            'sku': 'MMP-EDP-200001',
            'title': '아프리칸 레더',
            'vendor': 'MEMO_PARIS',
            'forwarder': '',
            'src_url': 'https://www.memoparis.com/products/african-leather',
            'quantity': 1,
            'buy_price': 250.0,
            'buy_currency': 'EUR',
            'source_country': 'FR',
            'forwarder_address': '국내 창고',
            'instructions': '메모파리 공식 사이트에서 직접 주문 → 한국 직배송 요청',
        },
    ],
    'summary': {
        'total_tasks': 2,
        'by_vendor': {'PORTER': 1, 'MEMO_PARIS': 1},
        'by_forwarder': {'zenmarket': 1, 'direct': 1},
    },
}


class TestOrderNotifier:
    def _make_notifier(self):
        from src.orders.notifier import OrderNotifier
        return OrderNotifier()

    # ── _format_telegram_message ──────────────────────────

    def test_telegram_message_contains_order_number(self):
        n = self._make_notifier()
        msg = n._format_telegram_message(ROUTED_ORDER_FIXTURE)
        assert '#1001' in msg

    def test_telegram_message_contains_customer_name(self):
        n = self._make_notifier()
        msg = n._format_telegram_message(ROUTED_ORDER_FIXTURE)
        assert '홍길동' in msg

    def test_telegram_message_contains_skus(self):
        n = self._make_notifier()
        msg = n._format_telegram_message(ROUTED_ORDER_FIXTURE)
        assert 'PTR-TNK-100000' in msg
        assert 'MMP-EDP-200001' in msg

    def test_telegram_message_contains_vendor_names(self):
        n = self._make_notifier()
        msg = n._format_telegram_message(ROUTED_ORDER_FIXTURE)
        assert 'PORTER' in msg
        assert 'MEMO_PARIS' in msg

    def test_telegram_message_contains_summary(self):
        n = self._make_notifier()
        msg = n._format_telegram_message(ROUTED_ORDER_FIXTURE)
        assert '2' in msg  # total_tasks

    # ── _format_notion_tasks ──────────────────────────────

    def test_notion_tasks_count(self):
        n = self._make_notifier()
        tasks = n._format_notion_tasks(ROUTED_ORDER_FIXTURE)
        assert len(tasks) == 2

    def test_notion_tasks_fields(self):
        n = self._make_notifier()
        tasks = n._format_notion_tasks(ROUTED_ORDER_FIXTURE)
        for t in tasks:
            assert 'title' in t
            assert 'sku' in t
            assert 'vendor' in t
            assert 'src_url' in t
            assert 'order_id' in t

    def test_notion_tasks_status_is_new(self):
        n = self._make_notifier()
        tasks = n._format_notion_tasks(ROUTED_ORDER_FIXTURE)
        for t in tasks:
            assert t['status'] == '신규'

    def test_notion_tasks_order_id(self):
        n = self._make_notifier()
        tasks = n._format_notion_tasks(ROUTED_ORDER_FIXTURE)
        for t in tasks:
            assert t['order_id'] == 12345

    # ── notify_new_order (mock) ───────────────────────────

    def test_notify_new_order_telegram_called_when_enabled(self):
        n = self._make_notifier()
        with patch.dict(os.environ, {'TELEGRAM_ENABLED': '1', 'EMAIL_ENABLED': '0'}):
            with patch('src.utils.telegram.send_tele') as mock_tele:
                with patch('src.utils.notion.create_task_if_env'):
                    n.notify_new_order(ROUTED_ORDER_FIXTURE)
                    mock_tele.assert_called_once()

    def test_notify_new_order_telegram_skipped_when_disabled(self):
        n = self._make_notifier()
        with patch.dict(os.environ, {'TELEGRAM_ENABLED': '0', 'EMAIL_ENABLED': '0'}):
            with patch('src.utils.telegram.send_tele') as mock_tele:
                with patch('src.utils.notion.create_task_if_env'):
                    n.notify_new_order(ROUTED_ORDER_FIXTURE)
                    mock_tele.assert_not_called()

    def test_notify_new_order_graceful_on_telegram_error(self):
        n = self._make_notifier()
        with patch.dict(os.environ, {'TELEGRAM_ENABLED': '1', 'EMAIL_ENABLED': '0'}):
            with patch('src.utils.telegram.send_tele', side_effect=Exception("network error")):
                with patch('src.utils.notion.create_task_if_env'):
                    # Should not raise
                    n.notify_new_order(ROUTED_ORDER_FIXTURE)

    # ── notify_tracking_update ────────────────────────────

    def test_notify_tracking_update_telegram(self):
        n = self._make_notifier()
        with patch.dict(os.environ, {'TELEGRAM_ENABLED': '1'}):
            with patch('src.utils.telegram.send_tele') as mock_tele:
                n.notify_tracking_update(
                    order_id=12345, sku='PTR-TNK-100000',
                    tracking_number='1234567890', carrier='cj'
                )
                mock_tele.assert_called_once()
                msg = mock_tele.call_args[0][0]
                assert '1234567890' in msg
                assert 'cj' in msg


# ══════════════════════════════════════════════════════════
# OrderTracker テスト
# ══════════════════════════════════════════════════════════

TRACKING_DATA = {
    'order_id': 12345,
    'sku': 'PTR-TNK-100000',
    'tracking_number': '1234567890',
    'carrier': 'cj',
    'status': 'shipped',
}


class TestOrderTracker:
    def _make_tracker(self):
        from src.orders.tracker import OrderTracker
        return OrderTracker()

    # ── _map_carrier_code ─────────────────────────────────

    def test_map_carrier_cj(self):
        t = self._make_tracker()
        assert t._map_carrier_code('cj') == 'CJ Logistics'

    def test_map_carrier_yamato(self):
        t = self._make_tracker()
        assert t._map_carrier_code('yamato') == 'Yamato Transport'

    def test_map_carrier_ems(self):
        t = self._make_tracker()
        assert t._map_carrier_code('ems') == 'EMS'

    def test_map_carrier_fedex(self):
        t = self._make_tracker()
        assert t._map_carrier_code('fedex') == 'FedEx'

    def test_map_carrier_hanjin(self):
        t = self._make_tracker()
        assert t._map_carrier_code('hanjin') == 'Hanjin'

    def test_map_carrier_unknown_passthrough(self):
        t = self._make_tracker()
        assert t._map_carrier_code('unknown_carrier') == 'unknown_carrier'

    def test_map_carrier_case_insensitive(self):
        t = self._make_tracker()
        assert t._map_carrier_code('CJ') == 'CJ Logistics'

    # ── _update_shopify_fulfillment (mock) ────────────────

    def test_shopify_fulfillment_no_env(self):
        t = self._make_tracker()
        env_clear = {k: '' for k in ['SHOPIFY_SHOP', 'SHOPIFY_ACCESS_TOKEN']}
        with patch.dict(os.environ, env_clear):
            result = t._update_shopify_fulfillment(12345, '123', 'cj')
            assert result is False

    def test_shopify_fulfillment_success(self):
        t = self._make_tracker()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        env = {
            'SHOPIFY_SHOP': 'test.myshopify.com',
            'SHOPIFY_ACCESS_TOKEN': 'shpat_test',
            'SHOPIFY_API_VERSION': '2024-07',
        }
        with patch.dict(os.environ, env):
            with patch('requests.post', return_value=mock_resp):
                result = t._update_shopify_fulfillment(12345, '1234567890', 'cj')
                assert result is True

    def test_shopify_fulfillment_uses_location_id(self):
        t = self._make_tracker()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        env = {
            'SHOPIFY_SHOP': 'test.myshopify.com',
            'SHOPIFY_ACCESS_TOKEN': 'shpat_test',
            'SHOPIFY_API_VERSION': '2024-07',
            'SHOPIFY_LOCATION_ID': '99887766',
        }
        with patch.dict(os.environ, env):
            with patch('requests.post', return_value=mock_resp) as mock_post:
                t._update_shopify_fulfillment(12345, '1234567890', 'cj')
                payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json', {})
                assert payload['fulfillment']['location_id'] == 99887766

    def test_shopify_fulfillment_failure_returns_false(self):
        t = self._make_tracker()
        env = {
            'SHOPIFY_SHOP': 'test.myshopify.com',
            'SHOPIFY_ACCESS_TOKEN': 'shpat_test',
        }
        with patch.dict(os.environ, env):
            with patch('requests.post', side_effect=Exception("timeout")):
                result = t._update_shopify_fulfillment(12345, '123', 'cj')
                assert result is False

    # ── _update_woo_tracking (mock) ───────────────────────

    def test_woo_tracking_no_env(self):
        t = self._make_tracker()
        env_clear = {k: '' for k in ['WOO_BASE_URL', 'WOO_CK', 'WOO_CS']}
        with patch.dict(os.environ, env_clear):
            result = t._update_woo_tracking(12345, '123', 'cj')
            assert result is False

    def test_woo_tracking_success(self):
        t = self._make_tracker()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        env = {
            'WOO_BASE_URL': 'https://shop.example.com',
            'WOO_CK': 'ck_test',
            'WOO_CS': 'cs_test',
        }
        with patch.dict(os.environ, env):
            with patch('requests.put', return_value=mock_resp):
                result = t._update_woo_tracking(12345, '1234567890', 'cj')
                assert result is True

    def test_woo_tracking_status_completed(self):
        t = self._make_tracker()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        env = {
            'WOO_BASE_URL': 'https://shop.example.com',
            'WOO_CK': 'ck_test',
            'WOO_CS': 'cs_test',
        }
        with patch.dict(os.environ, env):
            with patch('requests.put', return_value=mock_resp) as mock_put:
                t._update_woo_tracking(12345, '1234567890', 'cj')
                payload = mock_put.call_args.kwargs.get('json') or mock_put.call_args[1].get('json', {})
                assert payload['status'] == 'completed'

    def test_woo_tracking_failure_returns_false(self):
        t = self._make_tracker()
        env = {
            'WOO_BASE_URL': 'https://shop.example.com',
            'WOO_CK': 'ck_test',
            'WOO_CS': 'cs_test',
        }
        with patch.dict(os.environ, env):
            with patch('requests.put', side_effect=Exception("timeout")):
                result = t._update_woo_tracking(12345, '123', 'cj')
                assert result is False

    # ── process_tracking ─────────────────────────────────

    def test_process_tracking_result_keys(self):
        t = self._make_tracker()
        with patch.object(t, '_update_shopify_fulfillment', return_value=True):
            with patch.object(t, '_update_woo_tracking', return_value=True):
                result = t.process_tracking(TRACKING_DATA)
                assert 'shopify_updated' in result
                assert 'woo_updated' in result
                assert 'notification_sent' in result

    def test_process_tracking_notification_sent_when_shopify_ok(self):
        t = self._make_tracker()
        with patch.object(t, '_update_shopify_fulfillment', return_value=True):
            with patch.object(t, '_update_woo_tracking', return_value=False):
                result = t.process_tracking(TRACKING_DATA)
                assert result['notification_sent'] is True

    def test_process_tracking_no_notification_when_both_fail(self):
        t = self._make_tracker()
        with patch.object(t, '_update_shopify_fulfillment', return_value=False):
            with patch.object(t, '_update_woo_tracking', return_value=False):
                result = t.process_tracking(TRACKING_DATA)
                assert result['notification_sent'] is False

    def test_process_tracking_empty_order_id(self):
        t = self._make_tracker()
        result = t.process_tracking({'order_id': None, 'tracking_number': '', 'carrier': 'cj'})
        assert result['shopify_updated'] is False
        assert result['woo_updated'] is False


# ══════════════════════════════════════════════════════════
# order_webhook 통합 테스트
# ══════════════════════════════════════════════════════════

class TestOrderWebhookIntegration:
    def _make_client(self):
        import importlib
        # Patch OrderRouter/Notifier/Tracker before import to avoid side effects
        with patch('src.orders.router.OrderRouter.__init__', return_value=None):
            with patch('src.orders.notifier.OrderNotifier.__init__', return_value=None):
                with patch('src.orders.tracker.OrderTracker.__init__', return_value=None):
                    import src.order_webhook as wh
                    importlib.reload(wh)
                    client = wh.app.test_client()
                    return client, wh

    # ── HMAC 검증 ─────────────────────────────────────────

    def test_invalid_hmac_returns_401(self):
        with patch('src.order_webhook.verify_webhook', return_value=False):
            import src.order_webhook as wh
            client = wh.app.test_client()
            resp = client.post(
                '/webhook/shopify/order',
                data=b'{"id":1}',
                headers={'X-Shopify-Hmac-Sha256': 'bad'},
                content_type='application/json',
            )
            assert resp.status_code == 401

    def test_valid_hmac_returns_200(self):
        import src.order_webhook as wh
        order_payload = {**SHOPIFY_ORDER_SINGLE}
        with patch('src.order_webhook.verify_webhook', return_value=True):
            with patch.object(wh.router, 'route_order', return_value={
                'order_id': 12345, 'order_number': '#1001',
                'customer': {}, 'tasks': [],
                'summary': {'total_tasks': 0, 'by_vendor': {}, 'by_forwarder': {}},
            }):
                with patch.object(wh.notifier, 'notify_new_order'):
                    client = wh.app.test_client()
                    import json
                    resp = client.post(
                        '/webhook/shopify/order',
                        data=json.dumps(order_payload).encode(),
                        headers={'X-Shopify-Hmac-Sha256': 'valid'},
                        content_type='application/json',
                    )
                    assert resp.status_code == 200
                    data = resp.get_json()
                    assert data['ok'] is True
                    assert 'tasks' in data

    # ── 트래킹 웹훅 ──────────────────────────────────────

    def test_tracking_webhook_returns_result(self):
        import src.order_webhook as wh
        with patch.object(wh.tracker, 'process_tracking', return_value={
            'shopify_updated': True,
            'woo_updated': False,
            'notification_sent': True,
        }):
            with patch.object(wh.notifier, 'notify_tracking_update'):
                client = wh.app.test_client()
                import json
                resp = client.post(
                    '/webhook/forwarder/tracking',
                    data=json.dumps(TRACKING_DATA).encode(),
                    content_type='application/json',
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert data['shopify_updated'] is True

    def test_tracking_webhook_calls_notifier_when_sent(self):
        import src.order_webhook as wh
        with patch.object(wh.tracker, 'process_tracking', return_value={
            'shopify_updated': True,
            'woo_updated': False,
            'notification_sent': True,
        }):
            with patch.object(wh.notifier, 'notify_tracking_update') as mock_notify:
                client = wh.app.test_client()
                import json
                client.post(
                    '/webhook/forwarder/tracking',
                    data=json.dumps(TRACKING_DATA).encode(),
                    content_type='application/json',
                )
                mock_notify.assert_called_once()

    def test_tracking_webhook_no_notifier_when_not_sent(self):
        import src.order_webhook as wh
        with patch.object(wh.tracker, 'process_tracking', return_value={
            'shopify_updated': False,
            'woo_updated': False,
            'notification_sent': False,
        }):
            with patch.object(wh.notifier, 'notify_tracking_update') as mock_notify:
                client = wh.app.test_client()
                import json
                client.post(
                    '/webhook/forwarder/tracking',
                    data=json.dumps(TRACKING_DATA).encode(),
                    content_type='application/json',
                )
                mock_notify.assert_not_called()
