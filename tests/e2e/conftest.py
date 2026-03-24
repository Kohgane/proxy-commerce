"""tests/e2e/conftest.py — E2E 테스트 공통 fixture."""

import base64
import hashlib
import hmac
import os
import sys
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
