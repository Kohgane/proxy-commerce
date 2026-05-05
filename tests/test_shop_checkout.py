"""tests/test_shop_checkout.py — 자체몰 체크아웃 테스트 (Phase 131).

주문 생성 + 토스 sandbox confirm + 취소 검증.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_sheets_adapter():
    """OrderSheetsAdapter mock."""
    adapter = MagicMock()
    adapter.get_all_rows.return_value = []
    adapter.upsert_row.return_value = True
    return adapter


@pytest.fixture
def checkout_svc(mock_sheets_adapter):
    """CheckoutService with mocked sheets."""
    from src.shop.checkout import CheckoutService
    svc = CheckoutService()
    with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
        yield svc, mock_sheets_adapter


@pytest.fixture
def sample_cart_summary():
    return {
        "items": [
            {
                "slug": "alo-yoga-legging-xs",
                "title_ko": "Alo Yoga 레깅스 XS",
                "qty": 2,
                "price_krw": 75000,
                "line_total": 150000,
                "options": {"size": "XS"},
                "shipping_fee_krw": 0,
            }
        ],
        "subtotal_krw": 150000,
        "shipping_fee_krw": 0,
        "total_krw": 150000,
        "item_count": 2,
    }


@pytest.fixture
def sample_buyer_info():
    return {
        "name": "홍길동",
        "phone": "010-1234-5678",
        "address": "서울시 강남구 테헤란로 123",
        "memo": "문 앞에 놔주세요",
    }


# ---------------------------------------------------------------------------
# 1. 임포트
# ---------------------------------------------------------------------------

def test_import():
    from src.shop.checkout import CheckoutService
    assert CheckoutService is not None


def test_gen_order_id():
    from src.shop.checkout import _gen_order_id
    oid = _gen_order_id()
    assert oid.startswith("ORD-")
    assert len(oid) > 10


def test_order_token():
    from src.shop.checkout import _order_token
    t = _order_token("ORD-20260504-001", "010-1234-5678")
    assert len(t) == 16
    # 동일 입력 → 동일 토큰
    t2 = _order_token("ORD-20260504-001", "010-1234-5678")
    assert t == t2


# ---------------------------------------------------------------------------
# 2. create_order
# ---------------------------------------------------------------------------

class TestCreateOrder:
    def test_creates_order_id(self, sample_cart_summary, sample_buyer_info, mock_sheets_adapter):
        from src.shop.checkout import CheckoutService
        svc = CheckoutService()
        with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
            order_id = svc.create_order(sample_cart_summary, sample_buyer_info)
        assert order_id.startswith("ORD-")

    def test_upserts_row(self, sample_cart_summary, sample_buyer_info, mock_sheets_adapter):
        from src.shop.checkout import CheckoutService
        svc = CheckoutService()
        with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
            svc.create_order(sample_cart_summary, sample_buyer_info)
        mock_sheets_adapter.upsert_row.assert_called_once()
        row = mock_sheets_adapter.upsert_row.call_args[0][0]
        assert row["status"] == "new"
        assert row["marketplace"] == "kohganemultishop"

    def test_buyer_info_masked(self, sample_cart_summary, sample_buyer_info, mock_sheets_adapter):
        from src.shop.checkout import CheckoutService
        svc = CheckoutService()
        with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
            svc.create_order(sample_cart_summary, sample_buyer_info)
        row = mock_sheets_adapter.upsert_row.call_args[0][0]
        # 이름 마스킹 확인
        assert "홍" in row["buyer_name_masked"]
        assert "길동" not in row["buyer_name_masked"] or "*" in row["buyer_name_masked"]


# ---------------------------------------------------------------------------
# 3. request_payment
# ---------------------------------------------------------------------------

class TestRequestPayment:
    def test_order_not_found(self, mock_sheets_adapter):
        from src.shop.checkout import CheckoutService
        svc = CheckoutService()
        mock_sheets_adapter.get_all_rows.return_value = []
        with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
            result = svc.request_payment("NONEXISTENT-ORDER")
        assert "error" in result

    def test_returns_props(self, mock_sheets_adapter):
        from src.shop.checkout import CheckoutService
        order_row = {
            "order_id": "ORD-20260504-TESTXXXX",
            "total_krw": "150000",
            "items_json": '[{"title": "테스트 상품", "qty": 1}]',
            "buyer_name_masked": "홍*동",
            "status": "new",
        }
        mock_sheets_adapter.get_all_rows.return_value = [order_row]
        svc = CheckoutService()
        with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
            props = svc.request_payment("ORD-20260504-TESTXXXX")
        assert "client_key" in props
        assert props["order_id"] == "ORD-20260504-TESTXXXX"
        assert props["amount"] == 150000


# ---------------------------------------------------------------------------
# 4. confirm_payment — sandbox
# ---------------------------------------------------------------------------

class TestConfirmPayment:
    def test_sandbox_confirm(self, mock_sheets_adapter, monkeypatch):
        """TOSS_SECRET_KEY 미설정 → sandbox 응답."""
        monkeypatch.delenv("TOSS_CLIENT_KEY", raising=False)
        monkeypatch.delenv("TOSS_SECRET_KEY", raising=False)

        order_row = {
            "order_id": "ORD-20260504-TESTXXXX",
            "total_krw": "150000",
            "items_json": '[{"title": "테스트", "qty": 1}]',
            "buyer_name_masked": "홍*동",
            "buyer_phone_masked": "010-****-5678",
            "buyer_address_masked": "서울시 ***",
            "notes": "",
            "status": "new",
        }
        mock_sheets_adapter.get_all_rows.return_value = [order_row]

        from src.shop.checkout import CheckoutService
        svc = CheckoutService()
        with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
            with patch("src.notifications.telegram.send_telegram"):
                result = svc.confirm_payment(
                    payment_key="sandbox_key_abc123",
                    order_id="ORD-20260504-TESTXXXX",
                    amount=150000,
                )
        assert result.get("ok") is True
        assert result.get("sandbox") is True

    def test_amount_mismatch_rejected(self, mock_sheets_adapter):
        """금액 불일치 → 거부."""
        order_row = {
            "order_id": "ORD-20260504-TESTXXXX",
            "total_krw": "150000",
            "items_json": "[]",
            "notes": "",
            "status": "new",
        }
        mock_sheets_adapter.get_all_rows.return_value = [order_row]

        from src.shop.checkout import CheckoutService
        svc = CheckoutService()
        with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
            result = svc.confirm_payment(
                payment_key="any-key",
                order_id="ORD-20260504-TESTXXXX",
                amount=99999,  # 다른 금액
            )
        assert result.get("ok") is False
        assert "불일치" in result.get("error", "") or "mismatch" in result.get("error", "").lower()

    def test_order_not_found(self, mock_sheets_adapter):
        mock_sheets_adapter.get_all_rows.return_value = []
        from src.shop.checkout import CheckoutService
        svc = CheckoutService()
        with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
            result = svc.confirm_payment("pkey", "NONEXISTENT", 1000)
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# 5. cancel_payment
# ---------------------------------------------------------------------------

class TestCancelPayment:
    def test_cancel_ok(self, mock_sheets_adapter, monkeypatch):
        monkeypatch.delenv("TOSS_SECRET_KEY", raising=False)
        order_row = {
            "order_id": "ORD-TEST-CANCEL",
            "total_krw": "50000",
            "notes": "",
            "status": "paid",
        }
        mock_sheets_adapter.get_all_rows.return_value = [order_row]

        from src.shop.checkout import CheckoutService
        svc = CheckoutService()
        with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
            result = svc.cancel_payment("ORD-TEST-CANCEL", "고객 요청")
        assert result.get("ok") is True

    def test_cancel_not_found(self, mock_sheets_adapter):
        mock_sheets_adapter.get_all_rows.return_value = []
        from src.shop.checkout import CheckoutService
        svc = CheckoutService()
        with patch.object(svc, "_get_sheets_adapter", return_value=mock_sheets_adapter):
            result = svc.cancel_payment("NONEXISTENT")
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# 6. generate_order_token
# ---------------------------------------------------------------------------

def test_generate_order_token():
    from src.shop.checkout import CheckoutService
    svc = CheckoutService()
    token = svc.generate_order_token("ORD-20260504-001", "010-1234-5678")
    assert isinstance(token, str)
    assert len(token) == 16
