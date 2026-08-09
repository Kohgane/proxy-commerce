"""tests/conftest.py — pytest 공통 fixture 모음.

모든 테스트 파일에서 재사용 가능한 mock fixture를 제공한다.
- mock_google_sheets: gspread 워크시트 mock
- mock_shopify: Shopify REST/GraphQL mock
- mock_woocommerce: WooCommerce REST API mock
- mock_telegram: Telegram 알림 mock
- mock_env: 기본 환경변수 mock
- flask_client: order_webhook Flask 테스트 클라이언트
"""

import os
import re
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 셀러 콘솔 인증 강제는 운영 기본 ON(SELLER_CONSOLE_AUTH 미설정 시 "1"). 단 테스트는
# 세션 없이 페이지를 직접 호출하므로 OFF로 고정한다(모듈 로드 전에 설정해야 반영됨).
os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")


# ──────────────────────────────────────────────────────────
# v86-K: KGP_REQUIRE_BROWSER — 인프라 부재 시 '조용한 skip' 금지(실패로 전환).
#
# 배경(v86-H2 교훈): CI가 collect-only라 실브라우저/노드 하네스가 항상 skip → "값 계약 그린인데
#   화면엔 버튼 없음" 류의 회귀가 통과했다(오너 실기기 사고의 구조적 원인). 이 플래그가 켜지면
#   브라우저/노드/jsdom/Pillow/PG 인프라 부재로 인한 skip을 **실패**로 바꿔, 게이트가 실제로 물게 한다.
#   플래그가 꺼져 있으면(기본) 종전대로 skip — 로컬 개발 편의는 유지.
#
# ※ 인프라 skip만 전환한다(정직). 의도적 로직/데이터 skip(주문 품질 등)은 그대로 둔다.
# ──────────────────────────────────────────────────────────
_REQUIRE_BROWSER = os.getenv("KGP_REQUIRE_BROWSER") == "1"
# 인메모리 하네스 인프라(브라우저/노드/jsdom/Pillow)만 전환한다 — 이것들의 조용한 skip이 곧 '값 그린인데
#   화면엔 버튼 없음' 류 false-green의 원인(v86-H2). PG(DATABASE_URL)는 **별도 인프라 레인**이다: 전역
#   DATABASE_URL은 앱을 PG 모드로 바꿔 인메모리 가정 테스트 다수를 깨므로, PG 계약은 격리된 pg-suite 잡에서
#   따로 돈다 → 여기서는 PG skip을 실패로 바꾸지 않는다(그러면 인메모리 레인이 거짓 red가 된다).
_INFRA_SKIP_RE = re.compile(
    r"(Playwright|chromium|node\s*미설치|jsdom|Pillow|브라우저)",
    re.I,
)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if not _REQUIRE_BROWSER or not getattr(rep, "skipped", False):
        return
    lr = rep.longrepr
    reason = ""
    try:
        reason = str(lr[2]) if isinstance(lr, tuple) and len(lr) >= 3 else str(lr)
    except Exception:
        reason = str(lr)
    if _INFRA_SKIP_RE.search(reason):
        rep.outcome = "failed"
        rep.longrepr = (
            "KGP_REQUIRE_BROWSER=1: 인프라 부재로 조용한 skip 금지 → 실패 처리. "
            "사유: " + reason + " — CI/로컬에 해당 인프라(브라우저/노드/jsdom/Pillow/PG)를 설치하라."
        )


# ──────────────────────────────────────────────────────────
# 환경변수 fixture
# ──────────────────────────────────────────────────────────

BASE_ENV = {
    'GOOGLE_SERVICE_JSON_B64': 'dGVzdA==',  # base64('test')
    'GOOGLE_SHEET_ID': 'test_sheet_id_123',
    'SHOPIFY_SHOP': 'test-store.myshopify.com',
    'SHOPIFY_ACCESS_TOKEN': 'shpat_test_token',
    'SHOPIFY_CLIENT_SECRET': 'test_client_secret',
    'WOO_BASE_URL': 'https://test-shop.example.com',
    'WOO_CK': 'ck_test_consumer_key',
    'WOO_CS': 'cs_test_consumer_secret',
    'DEEPL_API_KEY': 'test-deepl-api-key:fx',
    'TELEGRAM_BOT_TOKEN': '123456:ABC-test-token',
    'TELEGRAM_CHAT_ID': '-100123456789',
    'APP_VERSION': '8.0.0',
    'TRANSLATE_PROVIDER': 'none',
    'FX_USE_LIVE': '0',
}


@pytest.fixture
def mock_env(monkeypatch):
    """기본 환경변수 mock. 테스트별로 오버라이드 가능."""
    for k, v in BASE_ENV.items():
        monkeypatch.setenv(k, v)
    yield BASE_ENV


# ──────────────────────────────────────────────────────────
# Google Sheets mock fixture
# ──────────────────────────────────────────────────────────

def _make_worksheet(rows: list = None):
    """gspread Worksheet mock을 생성한다."""
    ws = MagicMock()
    rows = rows or []
    ws.get_all_records.return_value = list(rows)
    ws.row_values.return_value = list((rows[0].keys() if rows else []))
    ws.update_cell.return_value = None
    ws.append_row.return_value = None
    ws.update.return_value = None
    return ws


@pytest.fixture
def mock_google_sheets():
    """gspread open_sheet를 mock으로 대체한다."""
    with patch('src.utils.sheets.open_sheet') as mock_open:
        ws = _make_worksheet()
        mock_open.return_value = ws
        yield mock_open, ws


@pytest.fixture
def mock_gspread_authorize():
    """gspread.authorize 전체를 mock으로 대체한다."""
    with patch('gspread.authorize') as mock_auth:
        client = MagicMock()
        mock_auth.return_value = client
        sh = MagicMock()
        client.open_by_key.return_value = sh
        ws = MagicMock()
        ws.get_all_records.return_value = []
        sh.worksheet.return_value = ws
        sh.add_worksheet.return_value = ws
        yield mock_auth, client, sh, ws


# ──────────────────────────────────────────────────────────
# Shopify mock fixture
# ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_shopify_request():
    """Shopify REST API 요청을 mock으로 대체한다."""
    with patch('src.vendors.shopify_client._request_with_retry') as mock_req:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'products': [], 'orders': []}
        mock_req.return_value = resp
        yield mock_req


@pytest.fixture
def mock_shopify_graphql():
    """Shopify GraphQL 쿼리를 mock으로 대체한다."""
    with patch('src.vendors.shopify_client.graphql_query') as mock_gql:
        mock_gql.return_value = {
            'products': {'edges': []},
            'productVariants': {'edges': []},
        }
        yield mock_gql


# ──────────────────────────────────────────────────────────
# WooCommerce mock fixture
# ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_woocommerce_request():
    """WooCommerce REST API 요청을 mock으로 대체한다."""
    with patch('src.vendors.woocommerce_client._request_with_retry') as mock_req:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'id': 1, 'sku': 'TEST-SKU', 'status': 'publish'}
        mock_req.return_value = resp
        yield mock_req


# ──────────────────────────────────────────────────────────
# Telegram mock fixture
# ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_telegram():
    """Telegram 알림 발송을 mock으로 대체한다."""
    with patch('src.utils.telegram.send_tele') as mock_tele:
        mock_tele.return_value = None
        yield mock_tele


@pytest.fixture
def mock_telegram_requests():
    """Telegram requests.post를 mock으로 대체한다."""
    with patch('requests.post') as mock_post:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'ok': True}
        mock_post.return_value = resp
        yield mock_post


# ──────────────────────────────────────────────────────────
# Flask test client fixture
# ──────────────────────────────────────────────────────────

@pytest.fixture
def flask_client():
    """order_webhook Flask 앱의 테스트 클라이언트."""
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    # rate limiter는 테스트에서 비활성화
    with wh.app.test_client() as c:
        yield c


# ──────────────────────────────────────────────────────────
# 샘플 데이터 fixture
# ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_catalog_rows():
    """테스트용 카탈로그 행 데이터."""
    return [
        {
            'sku': 'PTR-TNK-001',
            'title_ko': '포터 탱커 브리프케이스',
            'title_en': 'Porter Tanker Briefcase',
            'src_url': 'https://www.yoshidakaban.com/product/100000.html',
            'buy_currency': 'JPY',
            'buy_price': 30800,
            'sell_price_krw': 370000,
            'margin_pct': 18.0,
            'stock': 5,
            'stock_status': 'in_stock',
            'vendor': 'porter',
            'source_country': 'JP',
            'forwarder': 'zenmarket',
            'status': 'active',
        },
        {
            'sku': 'MMP-EDP-001',
            'title_ko': '메모파리 아프리카 레더',
            'title_en': 'Memo Paris African Leather',
            'src_url': 'https://www.memoparis.com/products/african-leather',
            'buy_currency': 'EUR',
            'buy_price': 250.0,
            'sell_price_krw': 420000,
            'margin_pct': 20.0,
            'stock': 3,
            'stock_status': 'in_stock',
            'vendor': 'memo_paris',
            'source_country': 'FR',
            'forwarder': '',
            'status': 'active',
        },
    ]


@pytest.fixture
def sample_order_rows():
    """테스트용 주문 행 데이터."""
    return [
        {
            'order_id': '10001',
            'order_number': '#1001',
            'customer_name': '홍길동',
            'customer_email': 'hong@example.com',
            'order_date': '2026-03-01T10:00:00Z',
            'sku': 'PTR-TNK-001',
            'vendor': 'PORTER',
            'buy_price': 30800,
            'buy_currency': 'JPY',
            'sell_price_krw': 370000,
            'sell_price_usd': 266.0,
            'margin_pct': 18.0,
            'status': 'paid',
            'status_updated_at': '2026-03-01T10:01:00Z',
            'shipping_country': 'KR',
        },
        {
            'order_id': '10002',
            'order_number': '#1002',
            'customer_name': 'Jane Doe',
            'customer_email': 'jane@example.com',
            'order_date': '2026-03-02T11:00:00Z',
            'sku': 'MMP-EDP-001',
            'vendor': 'MEMO_PARIS',
            'buy_price': 250.0,
            'buy_currency': 'EUR',
            'sell_price_krw': 420000,
            'sell_price_usd': 300.0,
            'margin_pct': 20.0,
            'status': 'shipped',
            'status_updated_at': '2026-03-03T08:00:00Z',
            'shipping_country': 'US',
        },
    ]


@pytest.fixture
def sample_fx_rates():
    """테스트용 환율 데이터."""
    return {
        'USDKRW': Decimal('1380'),
        'JPYKRW': Decimal('9.2'),
        'EURKRW': Decimal('1500'),
    }


@pytest.fixture
def sample_shopify_order():
    """테스트용 Shopify 주문 payload."""
    return {
        'id': 12345,
        'order_number': 1001,
        'name': '#1001',
        'email': 'customer@example.com',
        'customer': {'first_name': '길동', 'last_name': '홍', 'email': 'customer@example.com'},
        'line_items': [
            {
                'id': 1,
                'sku': 'PTR-TNK-001',
                'title': 'Porter Tanker Briefcase',
                'quantity': 1,
                'price': '370000.00',
            }
        ],
        'shipping_address': {'country_code': 'KR', 'country': 'South Korea'},
        'financial_status': 'paid',
        'total_price': '370000.00',
        'currency': 'KRW',
    }


# ──────────────────────────────────────────────────────────
# Phase 10: 검증기 상태 리셋 fixture
# ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_order_validator():
    """각 테스트 후 OrderValidator 중복 감지 캐시를 초기화한다.

    order_webhook.py의 모듈 레벨 order_validator 싱글톤이 테스트 간
    상태를 공유하지 않도록 한다.
    """
    yield
    try:
        import src.order_webhook as wh
        if hasattr(wh, 'order_validator'):
            wh.order_validator.reset_duplicate_cache()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_inmemory_stores():
    """PG-only 전환: PG 미설정(개발/테스트) 인메모리 스토어를 테스트 간 초기화(상태 누수 방지)."""
    def _clear():
        try:
            import src.seller_console.collect_history_store as ch
            ch._in_memory[:] = []
        except Exception:
            pass
        try:
            import src.auth.personal_tokens as pt
            pt._in_memory[:] = []
            pt._token_cache.clear()
        except Exception:
            pass
        try:
            import src.seller_console.orders.sheets_adapter as oa
            oa._MEM.rows[:] = []
        except Exception:
            pass
    _clear()
    yield
    _clear()


# ──────────────────────────────────────────────────────────
# Phase 31-35 fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_inventory_sync():
    """재고 동기화 mock fixture."""
    with patch('src.inventory_sync.sync_manager.InventorySyncManager') as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        mock_instance.sync_all_channels.return_value = {'synced_count': 0, 'results': {}, 'timestamp': '2024-01-01'}
        mock_instance.sync_sku.return_value = {'sku': 'test', 'resolved_stock': 10}
        mock_instance.get_sync_status.return_value = {'channels': ['coupang', 'naver', 'internal'], 'last_sync': {}}
        yield mock_instance


@pytest.fixture
def mock_translation():
    """번역 관리자 mock fixture."""
    with patch('src.translation.translator.TranslationManager') as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        mock_instance.get_all.return_value = []
        mock_instance.create_request.return_value = {
            'request_id': 'test-req-id',
            'status': 'review',
            'translated_text': '[ko] test',
        }
        yield mock_instance


@pytest.fixture
def mock_pricing_engine():
    """가격 엔진 mock fixture."""
    with patch('src.pricing_engine.auto_pricer.AutoPricer') as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        mock_instance.run.return_value = {'dry_run': True, 'processed': 0, 'results': []}
        mock_instance.simulate.return_value = {'sku': 'test', 'prices': {'margin_based': '14286'}}
        yield mock_instance


@pytest.fixture
def mock_suppliers():
    """공급자 관리자 mock fixture."""
    with patch('src.suppliers.supplier_manager.SupplierManager') as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        mock_instance.list_all.return_value = []
        yield mock_instance


@pytest.fixture
def mock_notification_hub():
    """알림 허브 mock fixture."""
    with patch('src.notifications.notification_hub.NotificationHub') as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        mock_instance.dispatch.return_value = {}
        yield mock_instance
