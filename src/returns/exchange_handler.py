"""src/returns/exchange_handler.py — Phase 37: 교환 처리."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ExchangeHandler:
    """교환 요청 처리기.

    - 동일 상품 재배송
    - 옵션 변경 교환
    """

    def __init__(self):
        self._exchanges: Dict[str, dict] = {}

    def create_exchange(
        self,
        return_id: str,
        product_id: str,
        original_option: str = '',
        new_option: str = '',
        same_product: bool = True,
    ) -> dict:
        """교환 요청 생성.

        Args:
            return_id: 연결된 반품 ID
            product_id: 상품 ID
            original_option: 원래 옵션 (색상/사이즈 등)
            new_option: 교환 옵션 (same_product=True이고 new_option이 비어있으면 original_option으로 설정)
            same_product: 동일 상품 재배송 여부

        Returns:
            교환 요청 딕셔너리
        """
        exchange_id = str(uuid.uuid4())[:8]
        if same_product and not new_option:
            new_option = original_option
        record = {
            'id': exchange_id,
            'return_id': return_id,
            'product_id': product_id,
            'original_option': original_option,
            'new_option': new_option,
            'same_product': same_product,
            'option_changed': original_option != new_option,
            'status': 'pending',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'shipped_at': None,
            'tracking_number': None,
        }
        self._exchanges[exchange_id] = record
        logger.info("교환 요청 생성: %s (return_id=%s)", exchange_id, return_id)
        return record

    def get(self, exchange_id: str) -> Optional[dict]:
        return self._exchanges.get(exchange_id)

    def list_by_return(self, return_id: str) -> List[dict]:
        return [e for e in self._exchanges.values() if e['return_id'] == return_id]

    def ship(self, exchange_id: str, tracking_number: str) -> Optional[dict]:
        """교환 상품 출고 처리."""
        record = self._exchanges.get(exchange_id)
        if not record:
            return None
        record['status'] = 'shipped'
        record['shipped_at'] = datetime.now(timezone.utc).isoformat()
        record['tracking_number'] = tracking_number
        return record

    def complete(self, exchange_id: str) -> Optional[dict]:
        """교환 완료 처리."""
        record = self._exchanges.get(exchange_id)
        if not record:
            return None
        record['status'] = 'completed'
        return record
