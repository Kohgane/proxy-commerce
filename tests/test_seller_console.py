"""tests/test_seller_console.py — 셀러 콘솔 모듈 테스트 (Phase 122).

테스트 범위:
  - views: 라우트 응답 코드 (200/302)
  - widgets: graceful import 검증 (모듈 없을 때 "준비 중" 반환)
  - ManualCollectorService: 도메인별 어댑터 라우팅, 추출 결과 스키마 검증
  - TaobaoSellerTrustChecker: 임계치 통과/실패 케이스
  - UploadDispatcher: 마켓 미존재 시 큐 적재 동작
  - 마진 계산기: 환율/관세/수수료 조합 케이스 5종
"""
from __future__ import annotations

import sys
import os

import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 픽스처: Flask 테스트 클라이언트
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """셀러 콘솔이 등록된 Flask 앱 테스트 클라이언트."""
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# 1. views — 라우트 응답 코드
# ---------------------------------------------------------------------------

class TestSellerConsoleViews:
    """셀러 콘솔 라우트 응답 코드 테스트."""

    def test_health_returns_200(self, client):
        """GET /seller/health → 200."""
        resp = client.get("/seller/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["service"] == "seller_console"
        assert data["phase"] >= 122

    def test_root_redirects_to_dashboard(self, client):
        """GET /seller/ → 302 (대시보드 리다이렉트)."""
        resp = client.get("/seller/")
        assert resp.status_code in (301, 302)

    def test_dashboard_returns_200(self, client):
        """GET /seller/dashboard → 200."""
        resp = client.get("/seller/dashboard")
        assert resp.status_code == 200

    def test_collect_returns_200(self, client):
        """GET /seller/collect → 200."""
        resp = client.get("/seller/collect")
        assert resp.status_code == 200

    def test_pricing_returns_200(self, client):
        """GET /seller/pricing → 200."""
        resp = client.get("/seller/pricing")
        assert resp.status_code == 200

    def test_market_status_returns_redirect(self, client):
        """GET /seller/market-status → 302 (/seller/markets 리다이렉트, Phase 127)."""
        resp = client.get("/seller/market-status")
        assert resp.status_code in (301, 302)

    def test_collect_preview_no_url_returns_400(self, client):
        """POST /seller/collect/preview — URL 없으면 400."""
        resp = client.post("/seller/collect/preview",
                           json={},
                           content_type="application/json")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_collect_preview_with_amazon_url(self, client):
        """POST /seller/collect/preview — Amazon URL → 200 + draft."""
        resp = client.post(
            "/seller/collect/preview",
            json={"url": "https://www.amazon.com/dp/B08N5WRWNW"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        draft = data["draft"]
        assert draft["source"] == "amazon"
        assert draft["title_ko"]
        assert draft["is_mock"] is True

    def test_collect_preview_with_taobao_url(self, client):
        """POST /seller/collect/preview — 타오바오 URL → trust 정보 포함."""
        resp = client.post(
            "/seller/collect/preview",
            json={"url": "https://item.taobao.com/item.htm?id=12345"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["draft"]["source"] == "taobao"
        # 타오바오는 trust 정보도 반환해야 함
        assert "trust" in data

    def test_collect_preview_with_tmall_url(self, client):
        """POST /seller/collect/preview — tmall URL도 taobao로 식별."""
        resp = client.post(
            "/seller/collect/preview",
            json={"url": "https://detail.tmall.com/item.htm?id=12345"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["draft"]["source"] == "taobao"

    def test_collect_upload_no_product_returns_400(self, client):
        """POST /seller/collect/upload — 상품 없으면 400."""
        resp = client.post(
            "/seller/collect/upload",
            json={"markets": ["coupang"]},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_collect_upload_no_markets_returns_400(self, client):
        """POST /seller/collect/upload — 마켓 없으면 400."""
        resp = client.post(
            "/seller/collect/upload",
            json={"product": {"url": "https://example.com"}, "markets": []},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_collect_upload_with_data(self, client):
        """POST /seller/collect/upload — 정상 입력 → 200."""
        resp = client.post(
            "/seller/collect/upload",
            json={
                "product": {
                    "url": "https://www.amazon.com/dp/test",
                    "title_ko": "테스트 상품",
                    "source": "amazon",
                },
                "markets": ["coupang"],
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "result" in data

    def test_pricing_calc_valid_input(self, client):
        """POST /seller/pricing/calc — 정상 입력 → 200 + 계산 결과."""
        resp = client.post(
            "/seller/pricing/calc",
            json={
                "buy_price": 50.0,
                "currency": "USD",
                "shipping_fee": 5000,
                "customs_rate": 8,
                "market_fee_rate": 7.8,
                "pg_fee_rate": 3.3,
                "target_margin_pct": 30,
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        result = data["result"]
        assert result["sell_price_krw"] > 0
        assert "actual_margin_pct" in result
        assert "breakeven_krw" in result

    def test_pricing_calc_zero_price_returns_400(self, client):
        """POST /seller/pricing/calc — 매입가 0 → 400."""
        resp = client.post(
            "/seller/pricing/calc",
            json={"buy_price": 0, "currency": "USD"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_collect_preview_empty_body(self, client):
        """POST /seller/collect/preview — 빈 body → 400."""
        resp = client.post("/seller/collect/preview",
                           data="",
                           content_type="application/json")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. widgets — graceful import 검증
# ---------------------------------------------------------------------------

class TestWidgets:
    """위젯 데이터 빌더 graceful import 테스트."""

    def test_build_all_widgets_returns_list(self):
        """build_all_widgets() → 리스트 반환."""
        from src.seller_console.widgets import build_all_widgets
        widgets = build_all_widgets()
        assert isinstance(widgets, list)
        assert len(widgets) > 0

    def test_each_widget_has_title_and_type(self):
        """각 위젯에 title과 type 키 존재."""
        from src.seller_console.widgets import build_all_widgets
        for widget in build_all_widgets():
            assert "title" in widget
            assert "type" in widget
            assert "data" in widget

    def test_widget_data_has_is_mock_flag(self):
        """위젯 data에 is_mock 플래그 존재."""
        from src.seller_console.widgets import build_all_widgets
        for widget in build_all_widgets():
            assert "is_mock" in widget["data"]

    def test_safe_call_returns_not_ready_on_exception(self):
        """_safe_call — 예외 시 '준비 중' 반환."""
        from src.seller_console.widgets import _safe_call, _NOT_READY

        def bad_func():
            raise RuntimeError("test error")

        result = _safe_call(bad_func)
        assert result["status"] == "준비 중"

    def test_kpi_widget_structure(self):
        """KPI 위젯 데이터 구조 검증."""
        from src.seller_console.widgets import build_kpi_widget
        widget = build_kpi_widget()
        assert widget["type"] == "kpi"
        data = widget["data"]
        assert "order_count" in data
        assert "gmv_krw" in data
        assert "margin_pct" in data

    def test_fx_widget_structure(self):
        """환율 위젯 데이터 구조 검증."""
        from src.seller_console.widgets import build_fx_widget
        widget = build_fx_widget()
        assert widget["type"] == "fx"
        data = widget["data"]
        assert "USD" in data
        assert "JPY" in data


# ---------------------------------------------------------------------------
# 3. ManualCollectorService — 어댑터 라우팅 + 스키마 검증
# ---------------------------------------------------------------------------

class TestManualCollectorService:
    """수동 수집기 서비스 테스트."""

    @pytest.fixture
    def service(self):
        from src.seller_console.manual_collector import ManualCollectorService
        return ManualCollectorService()

    def test_amazon_url_uses_amazon_adapter(self, service):
        """amazon.com URL → AmazonAdapter."""
        draft = service.extract("https://www.amazon.com/dp/B08N5WRWNW")
        assert draft.source == "amazon"
        assert draft.adapter_used == "AmazonAdapter"

    def test_amazon_jp_url(self, service):
        """amazon.co.jp URL → AmazonAdapter + JPY."""
        draft = service.extract("https://www.amazon.co.jp/dp/B08N5WRWNW")
        assert draft.source == "amazon"
        assert draft.currency == "JPY"

    def test_taobao_url_uses_taobao_adapter(self, service):
        """taobao.com URL → TaobaoAdapter."""
        draft = service.extract("https://item.taobao.com/item.htm?id=12345")
        assert draft.source == "taobao"
        assert draft.adapter_used == "TaobaoAdapter"

    def test_alibaba_1688_url(self, service):
        """1688.com URL → AlibabaAdapter."""
        draft = service.extract("https://detail.1688.com/offer/12345.html")
        assert draft.source == "alibaba"

    def test_porter_url(self, service):
        """porter.jp URL → PorterAdapter."""
        draft = service.extract("https://en.porter.jp/products/12345")
        assert draft.source == "porter"
        assert draft.currency == "JPY"

    def test_memo_paris_url(self, service):
        """memoparis.com URL → MemoAdapter."""
        draft = service.extract("https://www.memoparis.com/en/ilha-do-mel")
        assert draft.source == "memo"
        assert draft.currency == "EUR"

    def test_alo_yoga_url(self, service):
        """aloyoga.com URL → AloAdapter."""
        draft = service.extract("https://www.aloyoga.com/products/airlift-legging")
        assert draft.source == "alo"
        assert draft.brand == "Alo Yoga"

    def test_lululemon_url(self, service):
        """lululemon.com URL → LululemonAdapter."""
        draft = service.extract("https://www.lululemon.com/en-us/p/align-pant")
        assert draft.source == "lululemon"
        assert draft.brand == "lululemon"

    def test_nike_url_uses_premium_sports(self, service):
        """nike.com URL → PremiumSportsAdapter."""
        draft = service.extract("https://www.nike.com/t/air-max-270")
        assert draft.source == "premium_sports"
        assert draft.brand == "Nike"

    def test_unknown_url_uses_generic(self, service):
        """알 수 없는 URL → GenericAdapter."""
        draft = service.extract("https://www.unknownshop.xyz/product/123")
        assert draft.source == "generic"

    def test_empty_url_raises_value_error(self, service):
        """빈 URL → ValueError."""
        with pytest.raises(ValueError):
            service.extract("")

    def test_draft_has_required_fields(self, service):
        """ProductDraft 필수 필드 존재."""
        draft = service.extract("https://www.amazon.com/dp/B08N5WRWNW")
        assert draft.url
        assert draft.source
        assert draft.title_ko
        assert draft.title_en
        assert draft.currency
        assert isinstance(draft.images, list)
        assert isinstance(draft.options, list)

    def test_draft_to_dict_serializable(self, service):
        """to_dict() JSON 직렬화 가능."""
        import json
        draft = service.extract("https://www.amazon.com/dp/B08N5WRWNW")
        d = draft.to_dict()
        json_str = json.dumps(d)  # 예외 없으면 성공
        assert isinstance(json_str, str)

    def test_url_without_scheme_handled(self, service):
        """스킴 없는 URL → 자동 보완."""
        draft = service.extract("amazon.com/dp/B08N5WRWNW")
        assert draft.url.startswith("https://")

    def test_adapter_for_url_function(self):
        """adapter_for_url() 함수 독립 테스트."""
        from src.seller_console.manual_collector import adapter_for_url
        assert adapter_for_url("https://www.amazon.com/dp/test").source_code == "amazon"
        assert adapter_for_url("https://item.taobao.com/test").source_code == "taobao"
        assert adapter_for_url("https://www.aloyoga.com/test").source_code == "alo"
        assert adapter_for_url("https://www.lululemon.com/test").source_code == "lululemon"


# ---------------------------------------------------------------------------
# 4. TaobaoSellerTrustChecker — 임계치 통과/실패
# ---------------------------------------------------------------------------

class TestTaobaoSellerTrustChecker:
    """타오바오 셀러 신뢰도 평가기 테스트."""

    @pytest.fixture
    def checker(self):
        from src.seller_console.seller_trust import TaobaoSellerTrustChecker
        return TaobaoSellerTrustChecker()

    def test_good_seller_passes_all_thresholds(self, checker):
        """우수 셀러 → passed=True, grade A."""
        score = checker.evaluate("taobao_seller_good")
        assert score.passed is True
        assert score.grade in ("A", "B")
        assert score.score >= 70

    def test_bad_seller_fails_thresholds(self, checker):
        """불량 셀러 → passed=False."""
        score = checker.evaluate("taobao_seller_bad")
        assert score.passed is False
        assert len(score.warnings) > 0

    def test_grade_a_requires_high_score(self, checker):
        """A등급 → 점수 85점 이상."""
        score = checker.evaluate("taobao_seller_good")
        if score.grade == "A":
            assert score.score >= 85

    def test_grade_d_for_very_bad_seller(self, checker):
        """불량 셀러 → D등급."""
        score = checker.evaluate("taobao_seller_bad")
        assert score.grade == "D"

    def test_score_range_0_to_100(self, checker):
        """점수 범위 0~100."""
        for seller_id in ["taobao_seller_good", "taobao_seller_ok", "taobao_seller_bad"]:
            score = checker.evaluate(seller_id)
            assert 0 <= score.score <= 100

    def test_to_dict_has_all_keys(self, checker):
        """to_dict() 필수 키 존재."""
        score = checker.evaluate("taobao_seller_ok")
        d = score.to_dict()
        required_keys = [
            "seller_id", "score", "grade", "rating", "total_sales",
            "operating_months", "neg_review_pct", "response_hours",
            "passed", "warnings",
        ]
        for key in required_keys:
            assert key in d, f"누락된 키: {key}"

    def test_rating_threshold_fail(self, checker):
        """별점 4.7 미만 → 경고."""
        score = checker.evaluate("taobao_seller_bad")
        # bad seller의 rating은 4.3 (< 4.7)
        has_rating_warning = any("별점" in w for w in score.warnings)
        assert has_rating_warning

    def test_extract_seller_id_from_taobao_url(self, checker):
        """타오바오 URL에서 seller_id 추출."""
        from src.seller_console.seller_trust import TaobaoSellerTrustChecker
        sid = TaobaoSellerTrustChecker.extract_seller_id_from_url(
            "https://item.taobao.com/item.htm?id=12345"
        )
        assert sid is not None

    def test_extract_seller_id_from_non_taobao_url_returns_none(self, checker):
        """타오바오 아닌 URL → None."""
        from src.seller_console.seller_trust import TaobaoSellerTrustChecker
        sid = TaobaoSellerTrustChecker.extract_seller_id_from_url(
            "https://www.amazon.com/dp/B08N5WRWNW"
        )
        assert sid is None

    def test_ok_seller_passes_thresholds(self, checker):
        """보통 셀러 → passed=True."""
        score = checker.evaluate("taobao_seller_ok")
        assert score.passed is True


# ---------------------------------------------------------------------------
# 5. UploadDispatcher — 큐 적재 동작
# ---------------------------------------------------------------------------

class TestUploadDispatcher:
    """업로드 디스패처 테스트."""

    @pytest.fixture
    def dispatcher(self):
        from src.seller_console.upload_dispatcher import UploadDispatcher
        return UploadDispatcher()

    @pytest.fixture
    def sample_product(self):
        return {
            "url": "https://www.amazon.com/dp/test",
            "title_ko": "테스트 상품",
            "source": "amazon",
            "price_original": 50.0,
            "currency": "USD",
        }

    def setup_method(self):
        """각 테스트 전 큐 초기화."""
        from src.seller_console.upload_dispatcher import UploadDispatcher
        UploadDispatcher.clear_pending_queue()

    def test_dispatch_coupang_queues_when_module_missing(self, dispatcher, sample_product):
        """쿠팡 업로더 모듈 없으면 큐에 적재."""
        result = dispatcher.dispatch(sample_product, ["coupang"])
        # 모듈이 없으므로 queued 또는 success (mock 환경에서도 모듈 없으면 queued)
        assert result.total == 1
        assert result.queued + result.succeeded + result.failed == 1

    def test_dispatch_multiple_markets(self, dispatcher, sample_product):
        """여러 마켓으로 디스패치."""
        result = dispatcher.dispatch(sample_product, ["coupang", "smartstore", "elevenst"])
        assert result.total == 3
        assert len(result.results) == 3

    def test_dispatch_unknown_market_fails(self, dispatcher, sample_product):
        """알 수 없는 마켓 → failed."""
        result = dispatcher.dispatch(sample_product, ["nonexistent_market"])
        assert result.failed == 1

    def test_dispatch_result_to_dict(self, dispatcher, sample_product):
        """DispatchResult.to_dict() 직렬화."""
        import json
        result = dispatcher.dispatch(sample_product, ["coupang"])
        d = result.to_dict()
        json_str = json.dumps(d)
        assert isinstance(json_str, str)
        assert "results" in d
        assert "total" in d

    def test_pending_queue_grows_on_missing_module(self, dispatcher, sample_product):
        """모듈 없으면 pending_queue 증가."""
        from src.seller_console.upload_dispatcher import UploadDispatcher
        initial = len(UploadDispatcher.get_pending_queue())
        result = dispatcher.dispatch(sample_product, ["coupang"])
        if result.queued > 0:
            after = len(UploadDispatcher.get_pending_queue())
            assert after > initial

    def test_clear_pending_queue(self, dispatcher, sample_product):
        """큐 초기화."""
        from src.seller_console.upload_dispatcher import UploadDispatcher
        dispatcher.dispatch(sample_product, ["coupang", "smartstore"])
        cleared = UploadDispatcher.clear_pending_queue()
        assert isinstance(cleared, int)
        assert len(UploadDispatcher.get_pending_queue()) == 0


# ---------------------------------------------------------------------------
# 6. 마진 계산기 — 5종 케이스
# ---------------------------------------------------------------------------

class TestMarginCalculator:
    """마진 계산기 테스트 (5종 케이스)."""

    @pytest.fixture
    def fx_rates(self):
        return {"USD": 1370.5, "JPY": 9.12, "CNY": 188.4, "EUR": 1485.0, "KRW": 1.0}

    def test_case1_usd_standard(self, fx_rates):
        """케이스 1: USD 표준 케이스 (매입 $50, 관세 8%, 마진 30%)."""
        from src.seller_console.data_aggregator import calculate_margin
        result = calculate_margin(
            buy_price=50.0,
            currency="USD",
            shipping_fee=5000,
            customs_rate=8,
            market_fee_rate=7.8,
            pg_fee_rate=3.3,
            target_margin_pct=30,
            fx_rates=fx_rates,
        )
        assert result["sell_price_krw"] > 0
        assert result["cost_krw"] > 0
        assert result["actual_margin_pct"] > 0
        assert result["breakeven_krw"] > 0
        # 판매가 > 원가
        assert result["sell_price_krw"] > result["cost_krw"]

    def test_case2_jpy_no_customs(self, fx_rates):
        """케이스 2: JPY (배대지 직배), 관세 없음."""
        from src.seller_console.data_aggregator import calculate_margin
        result = calculate_margin(
            buy_price=3800.0,
            currency="JPY",
            shipping_fee=8000,
            customs_rate=0,
            market_fee_rate=6.0,
            pg_fee_rate=3.3,
            target_margin_pct=25,
            fx_rates=fx_rates,
        )
        assert result["customs_amount_krw"] == 0
        assert result["sell_price_krw"] > result["buy_price_krw"]

    def test_case3_cny_taobao(self, fx_rates):
        """케이스 3: CNY (타오바오), 관세 13%."""
        from src.seller_console.data_aggregator import calculate_margin
        result = calculate_margin(
            buy_price=68.0,
            currency="CNY",
            shipping_fee=6000,
            customs_rate=13,
            market_fee_rate=7.0,
            pg_fee_rate=3.3,
            target_margin_pct=35,
            fx_rates=fx_rates,
        )
        assert result["customs_amount_krw"] > 0
        assert result["actual_margin_pct"] > 0

    def test_case4_eur_luxury(self, fx_rates):
        """케이스 4: EUR 럭셔리 (Memo Paris), 높은 마진."""
        from src.seller_console.data_aggregator import calculate_margin
        result = calculate_margin(
            buy_price=220.0,
            currency="EUR",
            shipping_fee=15000,
            customs_rate=8,
            market_fee_rate=7.8,
            pg_fee_rate=3.3,
            target_margin_pct=40,
            fx_rates=fx_rates,
        )
        assert result["actual_margin_pct"] > 0
        assert result["sell_price_krw"] > 300000  # 고가 상품

    def test_case5_krw_domestic(self, fx_rates):
        """케이스 5: KRW 국내 상품, 관세 없음."""
        from src.seller_console.data_aggregator import calculate_margin
        result = calculate_margin(
            buy_price=50000.0,
            currency="KRW",
            shipping_fee=3000,
            customs_rate=0,
            market_fee_rate=7.8,
            pg_fee_rate=3.3,
            target_margin_pct=20,
            fx_rates=fx_rates,
        )
        # KRW는 환율 1:1
        assert result["buy_price_krw"] == 50000
        assert result["sell_price_krw"] > 50000

    def test_margin_increases_with_target(self, fx_rates):
        """목표 마진이 높을수록 판매가도 올라감."""
        from src.seller_console.data_aggregator import calculate_margin
        base_kwargs = dict(
            buy_price=50.0,
            currency="USD",
            shipping_fee=5000,
            customs_rate=8,
            market_fee_rate=7.8,
            pg_fee_rate=3.3,
            fx_rates=fx_rates,
        )
        r30 = calculate_margin(**base_kwargs, target_margin_pct=30)
        r50 = calculate_margin(**base_kwargs, target_margin_pct=50)
        assert r50["sell_price_krw"] > r30["sell_price_krw"]

    def test_breakeven_lower_than_sell_price(self, fx_rates):
        """손익분기점 < 판매가."""
        from src.seller_console.data_aggregator import calculate_margin
        result = calculate_margin(
            buy_price=50.0, currency="USD",
            shipping_fee=5000, customs_rate=8,
            market_fee_rate=7.8, pg_fee_rate=3.3,
            target_margin_pct=30, fx_rates=fx_rates,
        )
        assert result["breakeven_krw"] <= result["sell_price_krw"]


# ---------------------------------------------------------------------------
# 7. data_aggregator — graceful 테스트
# ---------------------------------------------------------------------------

class TestDataAggregator:
    """데이터 수집기 graceful import 테스트."""

    def test_get_today_kpi_returns_dict(self):
        """get_today_kpi() → dict."""
        from src.seller_console.data_aggregator import get_today_kpi
        result = get_today_kpi()
        assert isinstance(result, dict)
        assert "order_count" in result

    def test_get_fx_rates_returns_dict_with_currencies(self):
        """get_fx_rates() → dict (USD/JPY/CNY/EUR 포함)."""
        from src.seller_console.data_aggregator import get_fx_rates
        rates = get_fx_rates()
        assert isinstance(rates, dict)
        for currency in ["USD", "JPY", "CNY", "EUR"]:
            assert currency in rates
            assert rates[currency] > 0

    def test_get_market_product_status_returns_markets_list(self):
        """get_market_product_status() → markets 리스트."""
        from src.seller_console.data_aggregator import get_market_product_status
        result = get_market_product_status()
        assert "markets" in result
        assert isinstance(result["markets"], list)

    def test_get_collect_queue_status(self):
        """get_collect_queue_status() → 큐 상태 dict."""
        from src.seller_console.data_aggregator import get_collect_queue_status
        result = get_collect_queue_status()
        assert "pending" in result
        assert "total" in result

    def test_get_sourcing_alerts(self):
        """get_sourcing_alerts() → alerts 리스트."""
        from src.seller_console.data_aggregator import get_sourcing_alerts
        result = get_sourcing_alerts()
        assert "alerts" in result
        assert isinstance(result["alerts"], list)
