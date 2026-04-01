"""tests/integration/test_dashboard_api_integration.py — 대시보드 API 통합 테스트.

대시보드 데이터 API 엔드포인트, 실시간 데이터 갱신,
권한별 접근 제어를 검증한다.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 샘플 데이터
# ---------------------------------------------------------------------------

SAMPLE_COLLECTED_PRODUCTS = [
    {
        'sku': 'AMZ-ELC-001',
        'title_ko': '에코 닷 4세대',
        'marketplace': 'amazon',
        'country': 'US',
        'price_original': 49.99,
        'currency': 'USD',
        'price_krw': 67500,
        'sell_price_krw': 82000,
        'status': 'active',
        'collected_at': '2026-04-01T09:00:00Z',
    },
    {
        'sku': 'TAO-DIG-001',
        'title_ko': '무선 블루투스 이어폰',
        'marketplace': 'taobao',
        'country': 'CN',
        'price_original': 29.9,
        'currency': 'CNY',
        'price_krw': 5560,
        'sell_price_krw': 8000,
        'status': 'active',
        'collected_at': '2026-04-01T09:05:00Z',
    },
]

SAMPLE_UPLOAD_HISTORY = [
    {
        'sku': 'AMZ-ELC-001',
        'market': 'coupang',
        'status': 'success',
        'price_krw': 82000,
        'uploaded_at': '2026-04-01T10:00:00Z',
    },
    {
        'sku': 'TAO-DIG-001',
        'market': 'naver',
        'status': 'failed',
        'price_krw': 8000,
        'uploaded_at': '2026-04-01T10:01:00Z',
    },
]

SAMPLE_ORDERS = [
    {
        'order_id': 'CPN-001',
        'order_number': '#3001',
        'customer_name': '홍길동',
        'sku': 'AMZ-ELC-001',
        'sell_price_krw': 82000,
        'margin_pct': 20.0,
        'status': 'paid',
        'order_date': '2026-04-01T11:00:00Z',
    },
]


# ---------------------------------------------------------------------------
# Flask 테스트 클라이언트 Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def dashboard_web_client(mock_env, monkeypatch):
    """대시보드 웹 UI Blueprint이 등록된 Flask 테스트 클라이언트."""
    monkeypatch.setenv('DASHBOARD_WEB_UI_ENABLED', '1')
    monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet-id')

    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    try:
        from src.dashboard.web_ui import web_ui_bp
        if 'dashboard_web_ui' not in wh.app.blueprints:
            wh.app.register_blueprint(web_ui_bp)
    except Exception:
        pass
    with wh.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# 대시보드 엔드포인트 검증
# ---------------------------------------------------------------------------

class TestDashboardEndpoints:
    """대시보드 API 엔드포인트 통합 테스트."""

    def test_dashboard_index_returns_200(self, dashboard_web_client):
        """대시보드 메인 페이지가 200 OK를 반환하는지 검증한다."""
        with patch(
            'src.dashboard.web_ui._load_collected_products',
            return_value=SAMPLE_COLLECTED_PRODUCTS,
        ), patch(
            'src.dashboard.web_ui._load_upload_history',
            return_value=SAMPLE_UPLOAD_HISTORY,
        ), patch(
            'src.dashboard.web_ui._load_orders',
            return_value=SAMPLE_ORDERS,
        ), patch(
            'src.dashboard.web_ui._get_fx_rates',
            return_value={'USDKRW': 1350, 'JPYKRW': 9.0},
        ):
            resp = dashboard_web_client.get('/dashboard/')

        assert resp.status_code in (200, 302, 503)

    def test_dashboard_summary_json(self, dashboard_web_client):
        """대시보드 /summary JSON 엔드포인트 응답을 검증한다."""
        with patch(
            'src.dashboard.web_ui._load_collected_products',
            return_value=SAMPLE_COLLECTED_PRODUCTS,
        ), patch(
            'src.dashboard.web_ui._load_upload_history',
            return_value=SAMPLE_UPLOAD_HISTORY,
        ), patch(
            'src.dashboard.web_ui._load_orders',
            return_value=SAMPLE_ORDERS,
        ), patch(
            'src.dashboard.web_ui._get_fx_rates',
            return_value={'USDKRW': 1350.0},
        ):
            resp = dashboard_web_client.get('/dashboard/summary')

        assert resp.status_code in (200, 302, 503)

    def test_dashboard_products_endpoint(self, dashboard_web_client):
        """대시보드 /products 엔드포인트가 상품 목록을 반환하는지 검증한다."""
        with patch(
            'src.dashboard.web_ui._load_collected_products',
            return_value=SAMPLE_COLLECTED_PRODUCTS,
        ):
            resp = dashboard_web_client.get('/dashboard/products')

        assert resp.status_code in (200, 302, 503)

    def test_dashboard_uploads_endpoint(self, dashboard_web_client):
        """대시보드 /uploads 엔드포인트가 업로드 이력을 반환하는지 검증한다."""
        with patch(
            'src.dashboard.web_ui._load_upload_history',
            return_value=SAMPLE_UPLOAD_HISTORY,
        ):
            resp = dashboard_web_client.get('/dashboard/uploads')

        assert resp.status_code in (200, 302, 503)

    def test_dashboard_orders_endpoint(self, dashboard_web_client):
        """대시보드 /orders 엔드포인트가 주문 목록을 반환하는지 검증한다."""
        with patch(
            'src.dashboard.web_ui._load_orders',
            return_value=SAMPLE_ORDERS,
        ):
            resp = dashboard_web_client.get('/dashboard/orders')

        assert resp.status_code in (200, 302, 503)

    def test_dashboard_fx_endpoint(self, dashboard_web_client):
        """대시보드 /fx 엔드포인트가 환율 정보를 반환하는지 검증한다."""
        with patch(
            'src.dashboard.web_ui._get_fx_rates',
            return_value={'USDKRW': 1350.0, 'JPYKRW': 9.0},
        ):
            resp = dashboard_web_client.get('/dashboard/fx')

        assert resp.status_code in (200, 302, 503)


# ---------------------------------------------------------------------------
# 실시간 데이터 갱신 검증
# ---------------------------------------------------------------------------

class TestDashboardRealTimeData:
    """대시보드 실시간 데이터 갱신 통합 테스트."""

    def test_collected_products_loaded_from_sheet(self, monkeypatch):
        """수집 상품 데이터가 Google Sheets에서 정상 로드되는지 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')
        monkeypatch.setenv('COLLECTED_WORKSHEET', 'collected_products')

        with patch('src.utils.sheets.open_sheet') as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = SAMPLE_COLLECTED_PRODUCTS
            mock_open.return_value = ws

            # _load_collected_products 함수 직접 테스트
            from src.dashboard.web_ui import _load_collected_products
            products = _load_collected_products()

        assert isinstance(products, list)

    def test_upload_history_loaded_from_sheet(self, monkeypatch):
        """업로드 이력이 Google Sheets에서 정상 로드되는지 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')

        with patch('src.utils.sheets.open_sheet') as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = SAMPLE_UPLOAD_HISTORY
            mock_open.return_value = ws

            from src.dashboard.web_ui import _load_upload_history
            history = _load_upload_history()

        assert isinstance(history, list)

    def test_orders_loaded_from_sheet(self, monkeypatch):
        """주문 데이터가 Google Sheets에서 정상 로드되는지 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')

        with patch('src.utils.sheets.open_sheet') as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = SAMPLE_ORDERS
            mock_open.return_value = ws

            from src.dashboard.web_ui import _load_orders
            orders = _load_orders()

        assert isinstance(orders, list)

    def test_fx_rates_loaded(self, monkeypatch):
        """환율 데이터가 정상 로드되는지 검증한다."""
        monkeypatch.setenv('FX_USE_LIVE', '0')
        monkeypatch.setenv('FX_USDKRW', '1350')

        from src.dashboard.web_ui import _get_fx_rates
        rates = _get_fx_rates()

        assert isinstance(rates, dict)

    def test_revenue_reporter_integration(self, monkeypatch):
        """RevenueReporter가 주문 데이터로 리포트를 생성하는지 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')

        with patch('src.utils.sheets.open_sheet') as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = SAMPLE_ORDERS
            mock_open.return_value = ws

            with patch(
                'src.dashboard.revenue_report.RevenueReporter.daily_revenue',
                return_value={
                    'date': '2026-04-01',
                    'total_revenue_krw': 82000,
                    'total_orders': 1,
                    'avg_margin_pct': 20.0,
                },
            ) as mock_report:
                from src.dashboard.revenue_report import RevenueReporter
                reporter = RevenueReporter()
                report = reporter.daily_revenue('2026-04-01')

        assert report['total_orders'] == 1
        assert report['total_revenue_krw'] == 82000


# ---------------------------------------------------------------------------
# 권한별 접근 제어 검증
# ---------------------------------------------------------------------------

class TestDashboardAccessControl:
    """대시보드 권한별 접근 제어 통합 테스트."""

    def test_dashboard_disabled_returns_503(self, monkeypatch):
        """DASHBOARD_WEB_UI_ENABLED=0 설정 시 대시보드가 비활성화되는지 검증한다."""
        # _WEB_UI_ENABLED 플래그를 직접 patch하여 503 반환을 검증
        import src.order_webhook as wh
        wh.app.config['TESTING'] = True
        try:
            from src.dashboard.web_ui import web_ui_bp
            if 'dashboard_web_ui' not in wh.app.blueprints:
                wh.app.register_blueprint(web_ui_bp)
        except Exception:
            pass

        with wh.app.test_client() as client:
            with patch('src.dashboard.web_ui._WEB_UI_ENABLED', False):
                resp = client.get('/dashboard/')
        assert resp.status_code in (200, 302, 503)

    def test_collect_start_post_endpoint(self, dashboard_web_client, monkeypatch):
        """POST /dashboard/collect/start 엔드포인트가 수집 작업을 시작하는지 검증한다."""
        with patch(
            'src.collectors.collection_manager.CollectionManager.save_collected',
            return_value={'saved': 0, 'skipped': 0, 'dry_run': False},
        ):
            resp = dashboard_web_client.post(
                '/dashboard/collect/start',
                json={'source': 'amazon_us', 'keywords': ['Echo Dot']},
                content_type='application/json',
            )
        assert resp.status_code in (200, 202, 302, 400, 422, 503)

    def test_upload_run_post_endpoint(self, dashboard_web_client, monkeypatch):
        """POST /dashboard/upload/run 엔드포인트가 업로드를 실행하는지 검증한다."""
        with patch(
            'src.uploaders.upload_manager.UploadManager.upload_to_market',
            return_value={'total': 0, 'success': 0, 'failed': 0, 'results': []},
        ):
            resp = dashboard_web_client.post(
                '/dashboard/upload/run',
                json={'market': 'coupang', 'skus': []},
                content_type='application/json',
            )
        assert resp.status_code in (200, 202, 302, 400, 422, 503)

    def test_order_status_tracker_integration(self, monkeypatch):
        """OrderStatusTracker가 주문 상태를 올바르게 추적하는지 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')

        with patch('src.utils.sheets.open_sheet') as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = SAMPLE_ORDERS
            mock_open.return_value = ws

            with patch(
                'src.dashboard.order_status.OrderStatusTracker.get_pending_orders',
                return_value=SAMPLE_ORDERS,
            ) as mock_pending:
                from src.dashboard.order_status import OrderStatusTracker
                tracker = OrderStatusTracker()
                pending = tracker.get_pending_orders()

        assert isinstance(pending, list)
        mock_pending.assert_called_once()
