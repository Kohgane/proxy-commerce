"""src/payments/toss.py — 토스페이먼츠 결제 stub (Phase 130).

키 미설정 시 sandbox 시뮬레이션.
ADAPTER_DRY_RUN=1 시 외부 API 호출 차단.

Phase 132에서 PortOne과 통합 또는 별도 완전 구현 예정.

환경변수:
  TOSS_CLIENT_KEY   — 토스페이먼츠 클라이언트 키
  TOSS_SECRET_KEY   — 토스페이먼츠 시크릿 키 (서버용)
"""
from __future__ import annotations

import base64
import logging
import os
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.tosspayments.com"
_SANDBOX_BASE_URL = "https://api.tosspayments.com"  # sandbox와 동일 도메인, 테스트 키로 구분


def _api_active() -> bool:
    return bool(os.getenv("TOSS_CLIENT_KEY")) and bool(os.getenv("TOSS_SECRET_KEY"))


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


def _auth_header() -> str:
    """토스페이먼츠 Basic 인증 헤더 값 생성."""
    secret_key = os.getenv("TOSS_SECRET_KEY", "")
    encoded = base64.b64encode(f"{secret_key}:".encode()).decode()
    return f"Basic {encoded}"


def confirm_payment(payment_key: str, order_id: str, amount: int) -> dict:
    """결제 승인 요청.

    Args:
        payment_key: 토스페이먼츠 paymentKey
        order_id: 주문 ID
        amount: 결제 금액 (원)

    Returns:
        {
          "ok": bool,
          "payment_key": str,
          "order_id": str,
          "amount": int,
          "status": str,   # "DONE" | "CANCELED" | "FAILED"
          "method": str,
          "sandbox": bool,
        }
    """
    if _dry_run():
        logger.info("ADAPTER_DRY_RUN=1 — 토스 결제 승인 차단: %s", order_id)
        return _sandbox_response(payment_key, order_id, amount, reason="dry_run")

    if not _api_active():
        logger.info("TOSS_CLIENT_KEY/SECRET_KEY 미설정 — sandbox 시뮬레이션")
        return _sandbox_response(payment_key, order_id, amount, reason="key_missing")

    try:
        import requests
        resp = requests.post(
            f"{_BASE_URL}/v1/payments/{payment_key}/confirm",
            headers={
                "Authorization": _auth_header(),
                "Content-Type": "application/json",
            },
            json={"orderId": order_id, "amount": amount},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "payment_key": data.get("paymentKey", payment_key),
            "order_id": data.get("orderId", order_id),
            "amount": data.get("totalAmount", amount),
            "status": data.get("status", "DONE"),
            "method": data.get("method", ""),
            "sandbox": False,
        }
    except Exception as exc:
        logger.warning("토스 결제 승인 실패: %s", exc)
        return {"ok": False, "error": str(exc), "sandbox": False}


def cancel_payment(payment_key: str, cancel_reason: str = "고객 요청") -> dict:
    """결제 취소 요청.

    Args:
        payment_key: 취소할 결제의 paymentKey
        cancel_reason: 취소 사유

    Returns:
        {"ok": bool, "payment_key": str, "status": str, "sandbox": bool}
    """
    if _dry_run():
        logger.info("ADAPTER_DRY_RUN=1 — 토스 결제 취소 차단: %s", payment_key)
        return {"ok": True, "payment_key": payment_key, "status": "CANCELED", "sandbox": True}

    if not _api_active():
        logger.info("TOSS_CLIENT_KEY/SECRET_KEY 미설정 — sandbox 취소 시뮬레이션")
        return {"ok": True, "payment_key": payment_key, "status": "CANCELED", "sandbox": True}

    try:
        import requests
        resp = requests.post(
            f"{_BASE_URL}/v1/payments/{payment_key}/cancel",
            headers={
                "Authorization": _auth_header(),
                "Content-Type": "application/json",
            },
            json={"cancelReason": cancel_reason},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "payment_key": payment_key,
            "status": data.get("status", "CANCELED"),
            "sandbox": False,
        }
    except Exception as exc:
        logger.warning("토스 결제 취소 실패: %s", exc)
        return {"ok": False, "error": str(exc), "sandbox": False}


def _sandbox_response(payment_key: str, order_id: str, amount: int, reason: str = "") -> dict:
    """sandbox/stub 응답."""
    return {
        "ok": True,
        "payment_key": payment_key or f"toss_sandbox_{uuid.uuid4().hex[:12]}",
        "order_id": order_id,
        "amount": amount,
        "status": "DONE",
        "method": "카드",
        "sandbox": True,
        "reason": reason,
    }
