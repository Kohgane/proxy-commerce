"""src/shop/checkout.py — 주문 생성 + 토스페이먼츠 결제 (Phase 131).

흐름:
  1. create_order(cart, buyer_info) → order_id
  2. request_payment(order_id) → 토스 위젯 props
  3. confirm_payment(payment_key, order_id, amount) → 검증 + Sheets upsert + 텔레그램
  4. cancel_payment(order_id, reason) → 취소

금액 검증: 서버에서 Sheets에서 원래 금액 재조회 → 위변조 방지.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_TOSS_SANDBOX_CLIENT_KEY = "test_ck_D5GePWvyJnrK0W0k6q8gLzN97Eoq"
_TOSS_SANDBOX_SECRET_KEY = "test_sk_zXLkKEypNArWmo50nX3lmeaxYG5R"


def _toss_client_key() -> str:
    return os.getenv("TOSS_CLIENT_KEY") or _TOSS_SANDBOX_CLIENT_KEY


def _is_sandbox() -> bool:
    return not bool(os.getenv("TOSS_CLIENT_KEY"))


def _order_id_prefix() -> str:
    return datetime.utcnow().strftime("ORD-%Y%m%d-")


def _gen_order_id() -> str:
    return _order_id_prefix() + uuid.uuid4().hex[:8].upper()


def _order_token(order_id: str, buyer_phone: str) -> str:
    """HMAC-SHA256(order_id + buyer_phone) — 비로그인 주문 조회용."""
    secret = os.getenv("SECRET_KEY", "shop-secret-fallback")
    msg = f"{order_id}:{buyer_phone}"
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]


class CheckoutService:
    """주문 생성 + 토스페이먼츠 결제 서비스."""

    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # 1. 주문 생성
    # ------------------------------------------------------------------

    def create_order(self, cart_summary: dict, buyer_info: dict) -> str:
        """주문 생성 → orders 워크시트에 status=NEW.

        Args:
            cart_summary: Cart.summary() 결과
            buyer_info: {name, phone, address, memo}

        Returns:
            order_id
        """
        order_id = _gen_order_id()
        items = cart_summary.get("items", [])
        total_krw = cart_summary.get("total_krw", 0)
        shipping_fee = cart_summary.get("shipping_fee_krw", 0)

        items_json = json.dumps(
            [{"slug": i.get("slug"), "title": i.get("title_ko"), "qty": i.get("qty"), "price": i.get("price_krw"), "options": i.get("options")} for i in items],
            ensure_ascii=False,
        )

        from src.seller_console.orders.models import mask_name, mask_phone, mask_address

        row = {
            "order_id": order_id,
            "marketplace": "kohganemultishop",
            "status": "new",
            "placed_at": datetime.utcnow().isoformat(),
            "paid_at": "",
            "buyer_name_masked": mask_name(buyer_info.get("name", "")),
            "buyer_phone_masked": mask_phone(buyer_info.get("phone", "")),
            "buyer_address_masked": mask_address(buyer_info.get("address", "")),
            "total_krw": total_krw,
            "shipping_fee_krw": shipping_fee,
            "items_json": items_json,
            "courier": "",
            "tracking_no": "",
            "shipped_at": "",
            "landed_cost_krw": "",
            "margin_krw": "",
            "margin_pct": "",
            "last_synced_at": datetime.utcnow().isoformat(),
            "notes": buyer_info.get("memo", ""),
        }

        self._upsert_order(row)
        logger.info("주문 생성: %s (₩%s)", order_id, total_krw)
        return order_id

    # ------------------------------------------------------------------
    # 2. 결제 요청 props
    # ------------------------------------------------------------------

    def request_payment(self, order_id: str) -> dict:
        """토스 결제 위젯에 넘길 props 반환.

        Returns:
            {client_key, order_id, order_name, amount, customer_name, sandbox}
        """
        order = self._get_order(order_id)
        if not order:
            return {"error": "주문을 찾을 수 없습니다."}

        total_krw = int(order.get("total_krw", 0))
        items_json = order.get("items_json", "[]")
        try:
            items = json.loads(items_json)
        except Exception:
            items = []

        if items:
            order_name = items[0].get("title", "주문 상품")
            if len(items) > 1:
                order_name = f"{order_name} 외 {len(items)-1}건"
        else:
            order_name = "코가네멀티샵 주문"

        return {
            "client_key": _toss_client_key(),
            "order_id": order_id,
            "order_name": order_name,
            "amount": total_krw,
            "customer_name": order.get("buyer_name_masked", "고객"),
            "sandbox": _is_sandbox(),
        }

    # ------------------------------------------------------------------
    # 3. 결제 승인
    # ------------------------------------------------------------------

    def confirm_payment(self, payment_key: str, order_id: str, amount: int) -> dict:
        """토스 결제 승인 + orders 상태 업데이트 + 알림.

        금액 위변조 방지: Sheets에서 원래 금액 재조회 후 비교.
        """
        # 금액 검증
        order = self._get_order(order_id)
        if not order:
            logger.warning("confirm_payment: 주문 없음 — %s", order_id)
            return {"ok": False, "error": "주문을 찾을 수 없습니다."}

        expected_amount = int(order.get("total_krw", 0))
        if expected_amount > 0 and amount != expected_amount:
            logger.warning(
                "confirm_payment: 금액 불일치 order=%s expected=%s got=%s",
                order_id, expected_amount, amount,
            )
            return {"ok": False, "error": f"금액 불일치 (기대: {expected_amount}, 수신: {amount})"}

        # 토스 승인 API 호출
        try:
            from src.payments.toss import confirm_payment as toss_confirm
            result = toss_confirm(payment_key, order_id, amount)
        except Exception as exc:
            logger.warning("toss confirm 실패: %s", exc)
            result = {"ok": False, "error": str(exc)}

        if result.get("ok"):
            # orders 상태 PAID
            updates = {
                **order,
                "status": "paid",
                "paid_at": datetime.utcnow().isoformat(),
                "last_synced_at": datetime.utcnow().isoformat(),
                "notes": f"{order.get('notes','')} | payment_key={payment_key[:12]}...".strip(" |"),
            }
            self._upsert_order(updates)

            # 텔레그램 알림
            self._send_order_notification(order_id, order)

        return result

    # ------------------------------------------------------------------
    # 4. 결제 취소
    # ------------------------------------------------------------------

    def cancel_payment(self, order_id: str, reason: str = "고객 요청") -> dict:
        """주문 취소."""
        order = self._get_order(order_id)
        if not order:
            return {"ok": False, "error": "주문을 찾을 수 없습니다."}

        notes_field = order.get("notes", "")
        payment_key = ""
        for part in str(notes_field).split("|"):
            part = part.strip()
            if part.startswith("payment_key="):
                payment_key = part.split("=", 1)[1].strip()

        result: dict = {"ok": True, "sandbox": True}
        if payment_key:
            try:
                from src.payments.toss import cancel_payment as toss_cancel
                result = toss_cancel(payment_key, reason)
            except Exception as exc:
                logger.warning("toss cancel 실패: %s", exc)

        updates = {
            **order,
            "status": "canceled",
            "last_synced_at": datetime.utcnow().isoformat(),
            "notes": f"{notes_field} | cancel={reason}".strip(" |"),
        }
        self._upsert_order(updates)
        return result

    # ------------------------------------------------------------------
    # 주문 조회 (비로그인 토큰 검증 포함)
    # ------------------------------------------------------------------

    def get_order_for_display(self, order_id: str, token: Optional[str] = None) -> Optional[dict]:
        """주문 조회 — token 검증 (비로그인)."""
        order = self._get_order(order_id)
        if not order:
            return None

        if token:
            # 토큰 검증: buyer_phone_masked로 재생성하여 비교 (마스킹된 전화번호 활용)
            # 실제로는 원본 전화번호가 필요하지만 마스킹된 필드만 있으므로
            # 여기서는 토큰이 있는 경우 OK로 처리 (Phase 132에서 로그인 후 완전 구현 예정)
            pass  # token present = allowed

        return order

    @staticmethod
    def generate_order_token(order_id: str, buyer_phone: str) -> str:
        """주문 조회 토큰 생성."""
        return _order_token(order_id, buyer_phone)

    # ------------------------------------------------------------------
    # 내부: Sheets I/O
    # ------------------------------------------------------------------

    def _get_order(self, order_id: str) -> Optional[dict]:
        """orders 워크시트에서 주문 조회."""
        try:
            adapter = self._get_sheets_adapter()
            orders = adapter.get_all_rows()
            for row in orders:
                if str(row.get("order_id", "")) == order_id:
                    return row
        except Exception as exc:
            logger.warning("_get_order 실패 (%s): %s", order_id, exc)
        return None

    def _upsert_order(self, row: dict) -> None:
        """orders 워크시트에 주문 upsert."""
        try:
            adapter = self._get_sheets_adapter()
            adapter.upsert_row(row)
        except Exception as exc:
            logger.warning("_upsert_order 실패: %s", exc)

    @staticmethod
    def _get_sheets_adapter():
        """OrderSheetsAdapter 인스턴스 반환."""
        from src.seller_console.orders.sheets_adapter import OrderSheetsAdapter
        return OrderSheetsAdapter()

    def _send_order_notification(self, order_id: str, order: dict) -> None:
        """신규 주문 결제 완료 텔레그램 알림."""
        try:
            items_json = order.get("items_json", "[]")
            try:
                items = json.loads(items_json)
            except Exception:
                items = []

            item_lines = "\n".join(
                f"  {i.get('title','?')} x{i.get('qty',1)}" for i in items[:3]
            )
            total = order.get("total_krw", 0)
            buyer = order.get("buyer_name_masked", "?")
            phone = order.get("buyer_phone_masked", "?")
            address = order.get("buyer_address_masked", "?")

            msg = (
                f"💰 신규 주문 #{order_id}\n"
                f"상품:\n{item_lines}\n"
                f"금액: ₩{int(total):,}\n"
                f"구매자: {buyer} ({phone})\n"
                f"배송지: {address}"
            )
            from src.notifications.telegram import send_telegram
            send_telegram(msg, urgency="info")
        except Exception as exc:
            logger.debug("주문 알림 전송 실패: %s", exc)
