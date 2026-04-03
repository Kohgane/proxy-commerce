"""src/bundles/bundle_manager.py — Phase 44: 번들 CRUD."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BUNDLE_TYPES = {'fixed', 'pick_n', 'mix_match'}
BUNDLE_STATUSES = {'draft', 'active', 'inactive'}


class BundleManager:
    """번들 생성/수정/삭제, 구성 상품 관리.

    번들 타입:
      - fixed:      고정 구성 (모든 상품 포함)
      - pick_n:     N개 선택 (pick_count 지정)
      - mix_match:  조합 자유 (최소/최대 수량)
    """

    def __init__(self):
        self._bundles: Dict[str, dict] = {}

    def create(self, data: dict) -> dict:
        """번들 생성."""
        bundle_type = data.get('type', 'fixed')
        if bundle_type not in BUNDLE_TYPES:
            raise ValueError(f"지원하지 않는 번들 타입: {bundle_type}")
        status = data.get('status', 'draft')
        if status not in BUNDLE_STATUSES:
            raise ValueError(f"지원하지 않는 상태: {status}")
        bundle_id = data.get('id') or str(uuid.uuid4())[:8]
        bundle = {
            'id': bundle_id,
            'name': data.get('name', ''),
            'description': data.get('description', ''),
            'type': bundle_type,
            'status': status,
            'items': [],                          # [{product_id, quantity}]
            'pick_count': int(data.get('pick_count', 0)),
            'min_items': int(data.get('min_items', 1)),
            'max_items': int(data.get('max_items', 10)),
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._bundles[bundle_id] = bundle
        logger.info("번들 생성: %s (type=%s)", bundle_id, bundle_type)
        return bundle

    def get(self, bundle_id: str) -> Optional[dict]:
        return self._bundles.get(bundle_id)

    def list_all(self, status: Optional[str] = None) -> List[dict]:
        bundles = list(self._bundles.values())
        if status:
            bundles = [b for b in bundles if b['status'] == status]
        return bundles

    def update(self, bundle_id: str, data: dict) -> dict:
        bundle = self._bundles.get(bundle_id)
        if bundle is None:
            raise KeyError(f"번들 없음: {bundle_id}")
        for key in ('name', 'description', 'pick_count', 'min_items', 'max_items'):
            if key in data:
                bundle[key] = data[key]
        if 'status' in data:
            if data['status'] not in BUNDLE_STATUSES:
                raise ValueError(f"지원하지 않는 상태: {data['status']}")
            bundle['status'] = data['status']
        return bundle

    def delete(self, bundle_id: str) -> bool:
        if bundle_id not in self._bundles:
            return False
        del self._bundles[bundle_id]
        return True

    def add_item(self, bundle_id: str, product_id: str, quantity: int = 1) -> dict:
        """구성 상품 추가."""
        bundle = self._bundles.get(bundle_id)
        if bundle is None:
            raise KeyError(f"번들 없음: {bundle_id}")
        # 중복 체크
        for item in bundle['items']:
            if item['product_id'] == product_id:
                item['quantity'] += quantity
                return bundle
        bundle['items'].append({'product_id': product_id, 'quantity': quantity})
        return bundle

    def remove_item(self, bundle_id: str, product_id: str) -> dict:
        """구성 상품 제거."""
        bundle = self._bundles.get(bundle_id)
        if bundle is None:
            raise KeyError(f"번들 없음: {bundle_id}")
        bundle['items'] = [i for i in bundle['items'] if i['product_id'] != product_id]
        return bundle

    def activate(self, bundle_id: str) -> dict:
        return self.update(bundle_id, {'status': 'active'})

    def deactivate(self, bundle_id: str) -> dict:
        return self.update(bundle_id, {'status': 'inactive'})
