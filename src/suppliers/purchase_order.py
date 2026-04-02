"""발주서 관리."""

import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

STATUS_DRAFT = 'draft'
STATUS_SENT = 'sent'
STATUS_CONFIRMED = 'confirmed'
STATUS_SHIPPED = 'shipped'
STATUS_RECEIVED = 'received'

VALID_STATUSES = {STATUS_DRAFT, STATUS_SENT, STATUS_CONFIRMED, STATUS_SHIPPED, STATUS_RECEIVED}


class PurchaseOrderManager:
    """발주서 CRUD 관리."""

    def __init__(self):
        self._orders: dict = {}

    def create(self, supplier_id: str, sku: str, qty: int) -> dict:
        """발주서 생성.

        Args:
            supplier_id: 공급자 ID
            sku: 상품 SKU
            qty: 수량

        Returns:
            생성된 발주서 딕셔너리
        """
        po_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        order = {
            'po_id': po_id,
            'supplier_id': supplier_id,
            'sku': sku,
            'qty': qty,
            'status': STATUS_DRAFT,
            'created_at': now,
            'updated_at': now,
        }
        self._orders[po_id] = order
        logger.info("발주서 생성: %s (공급자:%s, SKU:%s, 수량:%d)", po_id, supplier_id, sku, qty)
        return order

    def get(self, po_id: str) -> dict | None:
        """발주서 조회."""
        return self._orders.get(po_id)

    def update_status(self, po_id: str, status: str) -> dict | None:
        """발주서 상태 업데이트."""
        if status not in VALID_STATUSES:
            raise ValueError(f'유효하지 않은 상태: {status}. 유효값: {VALID_STATUSES}')
        order = self._orders.get(po_id)
        if not order:
            return None
        order['status'] = status
        order['updated_at'] = datetime.now().isoformat()
        logger.info("발주서 상태 변경: %s -> %s", po_id, status)
        return order

    def list_all(self) -> list:
        """발주서 목록 조회."""
        return list(self._orders.values())
