"""src/wishlist/price_watch.py — Phase 43: 가격 변동 감시."""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PRICE_HISTORY_DAYS = 30


class PriceWatch:
    """목표 가격 설정, 현재 가격과 비교, 도달 시 알림 생성.

    - 가격 이력 추적 (최근 30일)
    - 목표 가격 도달 시 알림 레코드 생성
    """

    def __init__(self):
        self._watches: Dict[str, dict] = {}          # watch_id → watch
        self._price_history: Dict[str, List[dict]] = {}  # product_id → [{price, recorded_at}]
        self._alerts: List[dict] = []

    def watch(self, user_id: str, product_id: str, target_price: float) -> dict:
        """감시 등록."""
        watch_id = f"{user_id}:{product_id}"
        watch = {
            'id': watch_id,
            'user_id': user_id,
            'product_id': product_id,
            'target_price': float(target_price),
            'active': True,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._watches[watch_id] = watch
        return watch

    def unwatch(self, user_id: str, product_id: str) -> bool:
        watch_id = f"{user_id}:{product_id}"
        if watch_id not in self._watches:
            return False
        del self._watches[watch_id]
        return True

    def get_watch(self, user_id: str, product_id: str) -> Optional[dict]:
        return self._watches.get(f"{user_id}:{product_id}")

    def list_watches(self, user_id: str) -> List[dict]:
        return [w for w in self._watches.values() if w['user_id'] == user_id]

    def record_price(self, product_id: str, price: float) -> dict:
        """현재 가격 기록 + 감시 알림 체크."""
        record = {
            'product_id': product_id,
            'price': float(price),
            'recorded_at': datetime.now(timezone.utc).isoformat(),
        }
        history = self._price_history.setdefault(product_id, [])
        history.append(record)
        # 30일 초과 기록 제거
        cutoff = datetime.now(timezone.utc) - timedelta(days=PRICE_HISTORY_DAYS)
        self._price_history[product_id] = [
            h for h in history
            if datetime.fromisoformat(h['recorded_at']) >= cutoff
        ]
        # 알림 체크
        self._check_alerts(product_id, price)
        return record

    def _check_alerts(self, product_id: str, current_price: float):
        for watch in self._watches.values():
            if watch['product_id'] == product_id and watch['active']:
                if current_price <= watch['target_price']:
                    alert = {
                        'user_id': watch['user_id'],
                        'product_id': product_id,
                        'target_price': watch['target_price'],
                        'current_price': current_price,
                        'triggered_at': datetime.now(timezone.utc).isoformat(),
                    }
                    self._alerts.append(alert)
                    logger.info("가격 알림 발생: %s → %.2f (목표: %.2f)",
                                product_id, current_price, watch['target_price'])

    def get_alerts(self, user_id: Optional[str] = None) -> List[dict]:
        if user_id is None:
            return list(self._alerts)
        return [a for a in self._alerts if a['user_id'] == user_id]

    def get_price_history(self, product_id: str) -> List[dict]:
        return list(self._price_history.get(product_id, []))
