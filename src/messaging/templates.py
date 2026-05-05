"""src/messaging/templates.py — 다국어 메시지 템플릿 관리 (Phase 134).

템플릿 로드 우선순위:
1. src/messaging/templates/{event}/{locale}.{channel}.txt
2. src/messaging/templates/{event}/{locale}.txt
3. src/messaging/templates/{event}/ko.txt (폴백)

변수 치환: {order_id}, {tracking_no}, {courier_name}, {eta_date}, {shop_url}, ...
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class MessageTemplate:
    """메시지 템플릿."""

    event: str
    locale: str
    channel: str
    body: str

    def render(self, context: dict) -> str:
        """변수 치환."""
        try:
            return self.body.format_map(_SafeDict(context))
        except Exception as exc:
            logger.warning("템플릿 렌더링 오류: %s", exc)
            return self.body


class _SafeDict(dict):
    """누락 키를 빈 문자열로 대체하는 dict."""

    def __missing__(self, key):
        return f"{{{key}}}"


class TemplateStore:
    """템플릿 로드/캐시."""

    _cache: dict = {}

    def get(self, event: str, channel: str, locale: str) -> MessageTemplate:
        """템플릿 조회. 없으면 폴백 적용."""
        # 캐시 키
        cache_key = f"{event}:{locale}:{channel}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        body = self._load(event, locale, channel)
        tpl = MessageTemplate(event=event, locale=locale, channel=channel, body=body)
        self._cache[cache_key] = tpl
        return tpl

    def _load(self, event: str, locale: str, channel: str) -> str:
        """템플릿 파일 로드 (폴백 포함)."""
        candidates = [
            _TEMPLATES_DIR / event / f"{locale}.{channel}.txt",
            _TEMPLATES_DIR / event / f"{locale}.txt",
            _TEMPLATES_DIR / event / "ko.txt",
            _TEMPLATES_DIR / event / "default.txt",
        ]
        for path in candidates:
            if path.exists():
                try:
                    return path.read_text(encoding="utf-8")
                except Exception as exc:
                    logger.warning("템플릿 읽기 오류 %s: %s", path, exc)

        # 인라인 기본 템플릿
        return _INLINE_TEMPLATES.get(event, f"[{event}] {{order_id}}")


# ---------------------------------------------------------------------------
# 인라인 기본 템플릿 (파일 없을 때 폴백)
# ---------------------------------------------------------------------------

_INLINE_TEMPLATES = {
    "order_received": "주문이 접수되었습니다. 주문번호: {order_id}",
    "payment_confirmed": "결제가 완료되었습니다. 주문번호: {order_id}",
    "order_shipped": "배송이 시작되었습니다. 운송장: {courier_name} {tracking_no}",
    "order_delivered": "배송이 완료되었습니다. 주문번호: {order_id}",
    "refund_requested": "환불 요청이 접수되었습니다. 주문번호: {order_id}",
    "refund_completed": "환불이 완료되었습니다. 주문번호: {order_id}",
    "out_of_stock": "해당 상품이 품절되었습니다. 상품명: {product_name}",
    "cs_auto_reply": "문의를 접수했습니다. 영업일 1일 내 답변드리겠습니다.",
}
