"""src/returns/return_manager.py — Phase 37: 반품 요청 관리."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 유효한 상태 전환 맵
_TRANSITIONS = {
    'requested': ['approved', 'rejected'],
    'approved': ['received', 'cancelled'],
    'received': ['inspected'],
    'inspected': ['refunded', 'exchanged'],
    'refunded': [],
    'exchanged': [],
    'rejected': [],
    'cancelled': [],
}


class ReturnManager:
    """반품/교환 요청 CRUD + 상태 전환 관리."""

    def __init__(self):
        self._returns: Dict[str, dict] = {}

    def create(self, data: dict) -> dict:
        """반품 요청 생성."""
        return_id = data.get('id') or str(uuid.uuid4())[:8]
        record = {
            'id': return_id,
            'order_id': data.get('order_id', ''),
            'product_id': data.get('product_id', ''),
            'reason': data.get('reason', ''),
            'type': data.get('type', 'return'),  # return | exchange
            'status': 'requested',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'notes': data.get('notes', ''),
            'inspection_grade': None,
            'refund_amount': None,
        }
        self._returns[return_id] = record
        logger.info("반품 요청 생성: %s", return_id)
        return record

    def get(self, return_id: str) -> Optional[dict]:
        """반품 요청 조회."""
        return self._returns.get(return_id)

    def list_all(self, status: Optional[str] = None, order_id: Optional[str] = None) -> List[dict]:
        """반품 요청 목록 조회."""
        items = list(self._returns.values())
        if status:
            items = [r for r in items if r.get('status') == status]
        if order_id:
            items = [r for r in items if r.get('order_id') == order_id]
        return sorted(items, key=lambda x: x['created_at'], reverse=True)

    def update_status(self, return_id: str, new_status: str, notes: str = '') -> Optional[dict]:
        """상태 전환 처리."""
        record = self._returns.get(return_id)
        if not record:
            return None
        current = record['status']
        allowed = _TRANSITIONS.get(current, [])
        if new_status not in allowed:
            raise ValueError(f"상태 전환 불가: {current} → {new_status}")
        record['status'] = new_status
        record['updated_at'] = datetime.now(timezone.utc).isoformat()
        if notes:
            record['notes'] = notes
        logger.info("반품 상태 변경: %s %s → %s", return_id, current, new_status)
        return record

    def set_inspection(self, return_id: str, grade: str, refund_amount) -> Optional[dict]:
        """검수 등급 및 환불 금액 설정."""
        record = self._returns.get(return_id)
        if not record:
            return None
        record['inspection_grade'] = grade
        record['refund_amount'] = str(refund_amount)
        record['updated_at'] = datetime.now(timezone.utc).isoformat()
        return record

    def delete(self, return_id: str) -> bool:
        """반품 요청 삭제."""
        if return_id in self._returns:
            del self._returns[return_id]
            return True
        return False
