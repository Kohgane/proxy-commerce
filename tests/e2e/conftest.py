"""tests/e2e/conftest.py — E2E 테스트 공통 fixture."""

import base64
import hashlib
import hmac
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# ── E2E Flask 클라이언트 ─────────────────────────────────────────

@pytest.fixture
def e2e_client():
    """order_webhook Flask 앱의 E2E 테스트 클라이언트."""
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    with wh.app.test_client() as c:
        yield c


# ── E2E 외부 서비스 mock ─────────────────────────────────────────

@pytest.fixture
def mock_sheets_e2e():
    """Google Sheets open_sheet를 E2E 테스트용으로 mock 처리한다."""
    with patch('src.utils.sheets.open_sheet') as mock_open:
        ws = MagicMock()
        ws.get_all_records.return_value = []
        ws.append_row.return_value = None
        ws.update_cell.return_value = None
        mock_open.return_value = ws
        yield mock_open, ws


@pytest.fixture
def mock_telegram_e2e():
    """Telegram 알림 발송을 E2E 테스트용으로 mock 처리한다."""
    with patch('src.utils.telegram.send_tele') as mock_tele:
        mock_tele.return_value = None
        yield mock_tele


@pytest.fixture
def mock_requests_e2e():
    """requests.post / requests.get을 E2E 테스트용으로 mock 처리한다."""
    with patch('requests.post') as mock_post, patch('requests.get') as mock_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'ok': True}
        mock_post.return_value = resp
        mock_get.return_value = resp
        yield mock_post, mock_get


# ── 수집기 mock ─────────────────────────────────────────────────

@pytest.fixture
def mock_amazon_collector():
    """AmazonCollector HTTP 요청을 mock 처리한다."""
    sample_product = {
        'collector_id': 'B08N5WRWNW',
        'source_url': 'https://www.amazon.com/dp/B08N5WRWNW',
        'title_original': 'Echo Dot (4th Gen)',
        'title_ko': '에코 닷 4세대',
        'title_en': 'Echo Dot (4th Gen)',
        'description_original': 'Smart speaker with Alexa',
        'description_ko': '알렉사 스마트 스피커',
        'description_html': '<p>Smart speaker with Alexa</p>',
        'price_original': 49.99,
        'currency': 'USD',
        'price_krw': 67500,
        'sell_price_krw': 82000,
        'images': ['https://images.amazon.com/img1.jpg'],
        'category': 'Electronics',
        'category_code': 'ELC',
        'brand': 'Amazon',
        'rating': 4.7,
        'review_count': 12000,
        'stock_status': 'in_stock',
        'weight_kg': 0.3,
        'dimensions': {},
        'options': {},
        'tags': ['Echo', 'Alexa', 'Smart Speaker'],
        'vendor': 'amazon_us',
        'marketplace': 'amazon',
        'country': 'US',
    }
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '<html><head></head><body>'
    resp.raise_for_status = MagicMock()
    with patch('requests.Session.get', return_value=resp), \
         patch('requests.get', return_value=resp):
        with patch(
            'src.collectors.amazon_collector.AmazonCollector.collect_product',
            return_value=sample_product,
        ) as mock_collect, patch(
            'src.collectors.amazon_collector.AmazonCollector.search_products',
            return_value=[sample_product],
        ) as mock_search:
            yield mock_collect, mock_search, sample_product


@pytest.fixture
def mock_taobao_collector():
    """TaobaoCollector HTTP 요청을 mock 처리한다."""
    sample_product = {
        'collector_id': '123456789012',
        'source_url': 'https://item.taobao.com/item.htm?id=123456789012',
        'title_original': '无线蓝牙耳机',
        'title_ko': '무선 블루투스 이어폰',
        'title_en': 'Wireless Bluetooth Earphone',
        'description_original': '蓝牙5.0 支持30小时续航',
        'description_ko': '블루투스 5.0, 30시간 배터리',
        'description_html': '<p>블루투스 5.0, 30시간 배터리</p>',
        'price_original': 29.9,
        'currency': 'CNY',
        'price_krw': 5560,
        'sell_price_krw': 8000,
        'images': ['https://img.taobao.com/main.jpg'],
        'category': '数码',
        'category_code': 'DIG',
        'brand': '',
        'rating': 4.8,
        'review_count': 500,
        'stock_status': 'in_stock',
        'weight_kg': 0.15,
        'dimensions': {},
        'options': {'color': '블랙'},
        'tags': ['数码', '耳机'],
        'vendor': 'taobao',
        'marketplace': 'taobao',
        'country': 'CN',
    }
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '<html><head></head><body></body></html>'
    resp.raise_for_status = MagicMock()
    with patch('requests.Session.get', return_value=resp), \
         patch('requests.get', return_value=resp):
        with patch(
            'src.collectors.taobao_collector.TaobaoCollector.collect_product',
            return_value=sample_product,
        ) as mock_collect, patch(
            'src.collectors.taobao_collector.TaobaoCollector.search_products',
            return_value=[sample_product],
        ) as mock_search:
            yield mock_collect, mock_search, sample_product


@pytest.fixture
def mock_coupang_uploader():
    """CoupangUploader API 호출을 mock 처리한다."""
    upload_result = {
        'success': True,
        'product_id': 'C-111222333',
        'url': 'https://www.coupang.com/vp/products/111222333',
        'market': 'coupang',
    }
    with patch(
        'src.uploaders.coupang_uploader.CoupangUploader.upload_product',
        return_value=upload_result,
    ) as mock_upload, patch(
        'src.uploaders.coupang_uploader.CoupangUploader._authenticate',
        return_value=True,
    ):
        yield mock_upload, upload_result


@pytest.fixture
def mock_naver_uploader():
    """NaverSmartStoreUploader API 호출을 mock 처리한다."""
    upload_result = {
        'success': True,
        'product_id': 'N-999888777',
        'url': 'https://smartstore.naver.com/mystore/products/999888777',
        'market': 'naver',
    }
    with patch(
        'src.uploaders.naver_uploader.NaverSmartStoreUploader.upload_product',
        return_value=upload_result,
    ) as mock_upload, patch(
        'src.uploaders.naver_uploader.NaverSmartStoreUploader._get_access_token',
        return_value='mock-naver-token',
    ):
        yield mock_upload, upload_result


@pytest.fixture
def mock_fx_rates():
    """실시간 환율 API를 mock 처리한다."""
    rates = {
        'USD': Decimal('1350'),
        'JPY': Decimal('9.0'),
        'CNY': Decimal('186'),
        'EUR': Decimal('1470'),
        'GBP': Decimal('1710'),
    }
    with patch(
        'src.fx.realtime_rates.RealtimeRates.get_rate',
        side_effect=lambda frm, to: rates.get(frm, Decimal('1350')),
    ) as mock_rate:
        yield mock_rate, rates


# ── 싱글톤 리셋 ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_singletons():
    """각 테스트 후 싱글톤 + 캐시를 초기화한다."""
    yield
    # OrderValidator 중복 감지 캐시 리셋
    try:
        import src.order_webhook as wh
        if hasattr(wh, 'order_validator'):
            wh.order_validator.reset_duplicate_cache()
    except Exception:
        pass
    # ConfigManager 싱글톤 리셋
    try:
        from src.config.manager import ConfigManager
        ConfigManager._reset_instance()
    except Exception:
        pass


# ── 헬퍼 함수 ───────────────────────────────────────────────────

def shopify_hmac_header(payload_bytes: bytes, secret: str) -> str:
    """Shopify HMAC-SHA256 서명 헤더 값을 생성한다."""
    digest = hmac.new(secret.encode('utf-8'), payload_bytes, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()
