"""src/email_service/email_template.py — 이메일 템플릿."""
from __future__ import annotations

from typing import Dict, Tuple


class EmailTemplate:
    """이메일 템플릿 (subject + body 렌더링)."""

    _BUILTIN: Dict[str, dict] = {
        "order_confirm": {
            "subject_template": "주문 확인: {order_id}",
            "body_template": "안녕하세요, {name}님!\n\n주문 {order_id}이 확인되었습니다.\n총액: {total}원",
        },
        "shipping_notify": {
            "subject_template": "배송 알림: {order_id}",
            "body_template": "안녕하세요, {name}님!\n\n주문 {order_id}이 발송되었습니다.\n운송장: {tracking_number}",
        },
        "password_reset": {
            "subject_template": "비밀번호 재설정",
            "body_template": "안녕하세요, {name}님!\n\n비밀번호 재설정 링크: {reset_link}\n\n유효시간: 24시간",
        },
    }

    def __init__(self, name: str, subject_template: str, body_template: str) -> None:
        self.name = name
        self.subject_template = subject_template
        self.body_template = body_template

    @classmethod
    def get_builtin(cls, name: str) -> "EmailTemplate":
        if name not in cls._BUILTIN:
            raise KeyError(f"내장 템플릿 없음: {name}")
        tmpl = cls._BUILTIN[name]
        return cls(name=name, **tmpl)

    @classmethod
    def list_builtins(cls) -> list:
        return list(cls._BUILTIN.keys())

    def render(self, context: dict) -> Tuple[str, str]:
        """(subject, body) 반환."""
        subject = self.subject_template.format_map(context)
        body = self.body_template.format_map(context)
        return subject, body
