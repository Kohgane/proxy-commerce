"""tests/test_dashboard_web_ui.py — 대시보드 웹 UI Blueprint 테스트.

Phase 20: 수집/업로드/주문 통합 관리 화면 라우트 검증.
"""

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def web_client(mock_env, monkeypatch):
    """웹 UI Blueprint이 등록된 Flask 테스트 클라이언트."""
    monkeypatch.setenv("DASHBOARD_WEB_UI_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "test-sheet-id")

    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    try:
        from src.dashboard.web_ui import web_ui_bp
        # 이미 등록돼 있으면 스킵
        if "dashboard_web_ui" not in wh.app.blueprints:
            wh.app.register_blueprint(web_ui_bp)
    except Exception:
        pass
    with wh.app.test_client() as c:
        yield c


@pytest.fixture
def sample_products():
    return [
        {
            "sku": "AMZ-001", "title_original": "Backpack Pro", "title_ko": "백팩 프로",
            "marketplace": "amazon", "country": "US", "price_original": 99.99,
            "price_krw": 132000, "status": "active", "collected_at": "2026-03-01",
        },
        {
            "sku": "TAO-001", "title_original": "夹克外套", "title_ko": "",
            "marketplace": "taobao", "country": "CN", "price_original": 180.0,
            "price_krw": 33000, "status": "active", "collected_at": "2026-03-02",
        },
    ]


@pytest.fixture
def sample_upload_history():
    return [
        {
            "sku": "AMZ-001", "market": "coupang", "status": "success",
            "price_krw": 139000, "uploaded_at": "2026-03-05T10:00:00Z",
        },
        {
            "sku": "AMZ-001", "market": "naver", "status": "failed",
            "price_krw": 139000, "uploaded_at": "2026-03-05T10:01:00Z",
        },
    ]


@pytest.fixture
def sample_orders():
    return [
        {
            "order_id": "10001", "order_number": "#1001",
            "customer_name": "홍길동", "sku": "AMZ-001",
            "sell_price_krw": 139000, "margin_pct": 20.0,
            "status": "paid", "order_date": "2026-03-01T10:00:00Z",
        },
        {
            "order_id": "10002", "order_number": "#1002",
            "customer_name": "김영희", "sku": "TAO-001",
            "sell_price_krw": 45000, "margin_pct": 15.0,
            "status": "shipped", "order_date": "2026-03-02T11:00:00Z",
        },
    ]


# ---------------------------------------------------------------------------
# 메인 대시보드 (/)
# ---------------------------------------------------------------------------

class TestDashboardIndex:
    def test_index_returns_200(self, web_client, sample_orders, sample_products):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders), \
             patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products), \
             patch("src.dashboard.web_ui._get_fx_rates", return_value={"USDKRW": 1350.0}):
            resp = web_client.get("/dashboard/")
        assert resp.status_code == 200

    def test_index_contains_order_counts(self, web_client, sample_orders, sample_products):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders), \
             patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products), \
             patch("src.dashboard.web_ui._get_fx_rates", return_value={}):
            resp = web_client.get("/dashboard/")
        html = resp.data.decode("utf-8")
        assert "전체 주문" in html

    def test_index_contains_product_count(self, web_client, sample_orders, sample_products):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders), \
             patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products), \
             patch("src.dashboard.web_ui._get_fx_rates", return_value={}):
            resp = web_client.get("/dashboard/")
        html = resp.data.decode("utf-8")
        assert "수집 상품" in html

    def test_index_shows_fx_section(self, web_client, sample_orders, sample_products):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders), \
             patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products), \
             patch("src.dashboard.web_ui._get_fx_rates", return_value={"USDKRW": 1350.0}):
            resp = web_client.get("/dashboard/")
        html = resp.data.decode("utf-8")
        assert "환율" in html


# ---------------------------------------------------------------------------
# 요약 JSON (/summary)
# ---------------------------------------------------------------------------

class TestDashboardSummaryJson:
    def test_summary_json_returns_200(self, web_client, sample_orders, sample_products):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders), \
             patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products), \
             patch("src.dashboard.web_ui._get_fx_rates", return_value={"USDKRW": 1350.0}):
            resp = web_client.get("/dashboard/summary")
        assert resp.status_code == 200

    def test_summary_json_has_expected_keys(self, web_client, sample_orders, sample_products):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders), \
             patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products), \
             patch("src.dashboard.web_ui._get_fx_rates", return_value={"USDKRW": 1350.0}):
            resp = web_client.get("/dashboard/summary")
        data = resp.get_json()
        assert "orders" in data
        assert "revenue_krw" in data
        assert "products" in data
        assert "fx" in data

    def test_summary_order_counts(self, web_client, sample_orders, sample_products):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders), \
             patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products), \
             patch("src.dashboard.web_ui._get_fx_rates", return_value={}):
            resp = web_client.get("/dashboard/summary")
        data = resp.get_json()
        assert data["orders"]["total"] == 2
        assert data["orders"]["pending"] == 1
        assert data["orders"]["shipped"] == 1

    def test_summary_product_counts(self, web_client, sample_orders, sample_products):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders), \
             patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products), \
             patch("src.dashboard.web_ui._get_fx_rates", return_value={}):
            resp = web_client.get("/dashboard/summary")
        data = resp.get_json()
        assert data["products"]["total"] == 2
        assert data["products"]["amazon"] == 1
        assert data["products"]["taobao"] == 1

    def test_summary_revenue(self, web_client, sample_orders, sample_products):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders), \
             patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products), \
             patch("src.dashboard.web_ui._get_fx_rates", return_value={}):
            resp = web_client.get("/dashboard/summary")
        data = resp.get_json()
        assert data["revenue_krw"] == 139000 + 45000


# ---------------------------------------------------------------------------
# 상품 수집 (/products)
# ---------------------------------------------------------------------------

class TestProductsPage:
    def test_products_returns_200(self, web_client, sample_products):
        with patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products):
            resp = web_client.get("/dashboard/products")
        assert resp.status_code == 200

    def test_products_shows_sku(self, web_client, sample_products):
        with patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products):
            resp = web_client.get("/dashboard/products")
        html = resp.data.decode("utf-8")
        assert "AMZ-001" in html

    def test_products_marketplace_filter_amazon(self, web_client, sample_products):
        with patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products):
            resp = web_client.get("/dashboard/products?marketplace=amazon")
        html = resp.data.decode("utf-8")
        assert "AMZ-001" in html
        assert "TAO-001" not in html

    def test_products_marketplace_filter_taobao(self, web_client, sample_products):
        with patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products):
            resp = web_client.get("/dashboard/products?marketplace=taobao")
        html = resp.data.decode("utf-8")
        assert "TAO-001" in html
        assert "AMZ-001" not in html

    def test_products_json_format(self, web_client, sample_products):
        with patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products):
            resp = web_client.get("/dashboard/products?format=json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 2
        assert len(data["products"]) == 2

    def test_products_translation_filter_yes(self, web_client, sample_products):
        with patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products):
            resp = web_client.get("/dashboard/products?format=json&translated=yes")
        data = resp.get_json()
        # AMZ-001 has title_ko, TAO-001 does not
        assert data["count"] == 1
        assert data["products"][0]["sku"] == "AMZ-001"

    def test_products_translation_filter_no(self, web_client, sample_products):
        with patch("src.dashboard.web_ui._load_collected_products", return_value=sample_products):
            resp = web_client.get("/dashboard/products?format=json&translated=no")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["products"][0]["sku"] == "TAO-001"

    def test_products_empty_returns_200(self, web_client):
        with patch("src.dashboard.web_ui._load_collected_products", return_value=[]):
            resp = web_client.get("/dashboard/products")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 업로드 이력 (/uploads)
# ---------------------------------------------------------------------------

class TestUploadsPage:
    def test_uploads_returns_200(self, web_client, sample_upload_history):
        with patch("src.dashboard.web_ui._load_upload_history", return_value=sample_upload_history):
            resp = web_client.get("/dashboard/uploads")
        assert resp.status_code == 200

    def test_uploads_shows_sku(self, web_client, sample_upload_history):
        with patch("src.dashboard.web_ui._load_upload_history", return_value=sample_upload_history):
            resp = web_client.get("/dashboard/uploads")
        html = resp.data.decode("utf-8")
        assert "AMZ-001" in html

    def test_uploads_market_filter_coupang(self, web_client, sample_upload_history):
        with patch("src.dashboard.web_ui._load_upload_history", return_value=sample_upload_history):
            resp = web_client.get("/dashboard/uploads?format=json&market=coupang")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["history"][0]["market"] == "coupang"

    def test_uploads_market_filter_naver(self, web_client, sample_upload_history):
        with patch("src.dashboard.web_ui._load_upload_history", return_value=sample_upload_history):
            resp = web_client.get("/dashboard/uploads?format=json&market=naver")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["history"][0]["market"] == "naver"

    def test_uploads_json_format(self, web_client, sample_upload_history):
        with patch("src.dashboard.web_ui._load_upload_history", return_value=sample_upload_history):
            resp = web_client.get("/dashboard/uploads?format=json")
        data = resp.get_json()
        assert data["count"] == 2

    def test_uploads_empty_returns_200(self, web_client):
        with patch("src.dashboard.web_ui._load_upload_history", return_value=[]):
            resp = web_client.get("/dashboard/uploads")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 주문 현황 (/orders)
# ---------------------------------------------------------------------------

class TestOrdersPage:
    def test_orders_returns_200(self, web_client, sample_orders):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders):
            resp = web_client.get("/dashboard/orders")
        assert resp.status_code == 200

    def test_orders_shows_order_id(self, web_client, sample_orders):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders):
            resp = web_client.get("/dashboard/orders")
        html = resp.data.decode("utf-8")
        assert "10001" in html

    def test_orders_status_filter_paid(self, web_client, sample_orders):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders):
            resp = web_client.get("/dashboard/orders?format=json&status=paid")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["orders"][0]["status"] == "paid"

    def test_orders_status_filter_shipped(self, web_client, sample_orders):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders):
            resp = web_client.get("/dashboard/orders?format=json&status=shipped")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["orders"][0]["status"] == "shipped"

    def test_orders_json_format(self, web_client, sample_orders):
        with patch("src.dashboard.web_ui._load_orders", return_value=sample_orders):
            resp = web_client.get("/dashboard/orders?format=json")
        data = resp.get_json()
        assert data["count"] == 2

    def test_orders_empty_returns_200(self, web_client):
        with patch("src.dashboard.web_ui._load_orders", return_value=[]):
            resp = web_client.get("/dashboard/orders")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 환율·마진 (/fx)
# ---------------------------------------------------------------------------

class TestFxPage:
    def test_fx_returns_200(self, web_client):
        with patch("src.dashboard.web_ui._get_fx_rates", return_value={"USDKRW": 1350.0, "JPYKRW": 9.0}):
            resp = web_client.get("/dashboard/fx")
        assert resp.status_code == 200

    def test_fx_shows_rate(self, web_client):
        with patch("src.dashboard.web_ui._get_fx_rates", return_value={"USDKRW": 1350.0}):
            resp = web_client.get("/dashboard/fx")
        html = resp.data.decode("utf-8")
        assert "USDKRW" in html

    def test_fx_json_format(self, web_client):
        with patch("src.dashboard.web_ui._get_fx_rates", return_value={"USDKRW": 1350.0}):
            resp = web_client.get("/dashboard/fx?format=json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "rates" in data
        assert data["rates"]["USDKRW"] == 1350.0

    def test_fx_margin_calculator(self, web_client):
        with patch("src.dashboard.web_ui._get_fx_rates", return_value={"USDKRW": 1350.0}):
            resp = web_client.get("/dashboard/fx?buy_price=100&currency=USD&margin_pct=20")
        html = resp.data.decode("utf-8")
        assert "계산 결과" in html
        assert "₩" in html

    def test_fx_invalid_buy_price(self, web_client):
        with patch("src.dashboard.web_ui._get_fx_rates", return_value={"USDKRW": 1350.0}):
            resp = web_client.get("/dashboard/fx?buy_price=abc&currency=USD&margin_pct=20")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "입력값을 확인하세요" in html

    def test_fx_no_rates_returns_200(self, web_client):
        with patch("src.dashboard.web_ui._get_fx_rates", return_value={}):
            resp = web_client.get("/dashboard/fx")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 수집 작업 시작 (POST /collect/start)
# ---------------------------------------------------------------------------

class TestCollectStart:
    def test_collect_start_json_returns_202(self, web_client):
        resp = web_client.post(
            "/dashboard/collect/start?format=json",
            json={"source": "amazon"},
        )
        assert resp.status_code == 202

    def test_collect_start_json_has_status(self, web_client):
        resp = web_client.post(
            "/dashboard/collect/start?format=json",
            json={"source": "taobao"},
        )
        data = resp.get_json()
        assert data["status"] == "started"
        assert "source" in data
        assert "timestamp" in data

    def test_collect_start_default_source(self, web_client):
        resp = web_client.post(
            "/dashboard/collect/start?format=json",
            json={},
        )
        data = resp.get_json()
        assert data["source"] == "all"

    def test_collect_start_form_redirects(self, web_client):
        resp = web_client.post(
            "/dashboard/collect/start",
            data={"source": "amazon"},
        )
        # HTML 폼 제출은 302 리디렉션
        assert resp.status_code in (302, 200)


# ---------------------------------------------------------------------------
# 업로드 실행 (POST /upload/run)
# ---------------------------------------------------------------------------

class TestUploadRun:
    def test_upload_run_json_returns_202(self, web_client):
        resp = web_client.post(
            "/dashboard/upload/run?format=json",
            json={"market": "coupang", "skus": [], "dry_run": True},
        )
        assert resp.status_code == 202

    def test_upload_run_json_has_status(self, web_client):
        resp = web_client.post(
            "/dashboard/upload/run?format=json",
            json={"market": "naver", "skus": [], "dry_run": True},
        )
        data = resp.get_json()
        assert data["market"] == "naver"
        assert "status" in data
        assert "timestamp" in data

    def test_upload_run_with_skus(self, web_client):
        mock_result = {"total": 1, "success": 1, "failed": 0, "results": []}
        with patch("src.uploaders.upload_manager.UploadManager") as MockMgr:
            MockMgr.return_value.upload_to_market.return_value = mock_result
            resp = web_client.post(
                "/dashboard/upload/run?format=json",
                json={"market": "coupang", "skus": ["AMZ-001"], "dry_run": False},
            )
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "completed"

    def test_upload_run_form_redirects(self, web_client):
        resp = web_client.post(
            "/dashboard/upload/run",
            data={"market": "coupang"},
        )
        assert resp.status_code in (302, 200)

    def test_upload_run_upload_manager_error(self, web_client):
        with patch("src.uploaders.upload_manager.UploadManager") as MockMgr:
            MockMgr.return_value.upload_to_market.side_effect = RuntimeError("연결 실패")
            resp = web_client.post(
                "/dashboard/upload/run?format=json",
                json={"market": "coupang", "skus": ["SKU-ERR"]},
            )
        data = resp.get_json()
        assert data["status"] == "error"
        assert "연결 실패" in data["error"]


# ---------------------------------------------------------------------------
# 비활성화 상태 테스트
# ---------------------------------------------------------------------------

class TestWebUiDisabled:
    def test_disabled_index_returns_503(self, web_client, monkeypatch):
        monkeypatch.setenv("DASHBOARD_WEB_UI_ENABLED", "0")
        import src.dashboard.web_ui as wui
        original = wui._WEB_UI_ENABLED
        wui._WEB_UI_ENABLED = False
        try:
            resp = web_client.get("/dashboard/")
            assert resp.status_code == 503
        finally:
            wui._WEB_UI_ENABLED = original

    def test_disabled_summary_returns_503(self, web_client, monkeypatch):
        import src.dashboard.web_ui as wui
        original = wui._WEB_UI_ENABLED
        wui._WEB_UI_ENABLED = False
        try:
            resp = web_client.get("/dashboard/summary")
            assert resp.status_code == 503
        finally:
            wui._WEB_UI_ENABLED = original
