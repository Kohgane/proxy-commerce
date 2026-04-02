"""공급자 커뮤니케이션 — 이메일 템플릿 및 발송."""

import logging

logger = logging.getLogger(__name__)

_TEMPLATES = {
    'order': """안녕하세요,

새로운 발주서가 생성되었습니다.

발주 번호: {po_id}
SKU: {sku}
수량: {qty}

확인 부탁드립니다.

감사합니다.""",

    'confirm': """안녕하세요,

발주서 {po_id}가 확인되었습니다.

납기 예정일: {delivery_date}

감사합니다.""",

    'claim': """안녕하세요,

주문 {po_id}와 관련하여 클레임이 접수되었습니다.

내용: {claim_content}

빠른 처리 부탁드립니다.

감사합니다.""",
}


class SupplierCommunication:
    """공급자 이메일 커뮤니케이션."""

    def __init__(self):
        self._sent: list = []

    def get_template(self, template_type: str) -> str:
        """템플릿 조회.

        Args:
            template_type: 'order' | 'confirm' | 'claim'

        Returns:
            템플릿 문자열
        """
        template = _TEMPLATES.get(template_type)
        if not template:
            raise ValueError(f'유효하지 않은 템플릿 유형: {template_type}')
        return template

    def send_email(self, supplier_id: str, template_type: str, context: dict = None) -> bool:
        """이메일 발송 (mock).

        Args:
            supplier_id: 공급자 ID
            template_type: 템플릿 유형
            context: 템플릿 변수 딕셔너리

        Returns:
            발송 성공 여부
        """
        try:
            template = self.get_template(template_type)
            ctx = context or {}
            body = template.format(**ctx)
            record = {
                'supplier_id': supplier_id,
                'template_type': template_type,
                'body': body,
            }
            self._sent.append(record)
            logger.info("공급자 이메일 발송 (mock): %s (%s)", supplier_id, template_type)
            return True
        except Exception as exc:
            logger.error("이메일 발송 오류: %s", exc)
            return False

    def get_sent_history(self) -> list:
        """발송 이력 반환."""
        return list(self._sent)
