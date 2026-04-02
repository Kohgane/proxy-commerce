"""공급자 관리."""

import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class SupplierManager:
    """공급자 CRUD 관리."""

    def __init__(self):
        self._suppliers: dict = {}

    def add(self, supplier_data: dict) -> dict:
        """공급자 추가.

        Args:
            supplier_data: 공급자 정보 딕셔너리

        Returns:
            생성된 공급자 딕셔너리
        """
        supplier_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        supplier = {
            'supplier_id': supplier_id,
            'active': True,
            'created_at': now,
            'updated_at': now,
            **supplier_data,
        }
        self._suppliers[supplier_id] = supplier
        logger.info("공급자 추가: %s", supplier_id)
        return supplier

    def get(self, supplier_id: str) -> dict | None:
        """공급자 조회."""
        return self._suppliers.get(supplier_id)

    def update(self, supplier_id: str, data: dict) -> dict | None:
        """공급자 정보 업데이트."""
        supplier = self._suppliers.get(supplier_id)
        if not supplier:
            return None
        supplier.update(data)
        supplier['updated_at'] = datetime.now().isoformat()
        logger.info("공급자 업데이트: %s", supplier_id)
        return supplier

    def deactivate(self, supplier_id: str) -> bool:
        """공급자 비활성화."""
        supplier = self._suppliers.get(supplier_id)
        if not supplier:
            return False
        supplier['active'] = False
        supplier['updated_at'] = datetime.now().isoformat()
        logger.info("공급자 비활성화: %s", supplier_id)
        return True

    def list_all(self, active_only: bool = False) -> list:
        """공급자 목록 조회."""
        suppliers = list(self._suppliers.values())
        if active_only:
            suppliers = [s for s in suppliers if s.get('active', True)]
        return suppliers
