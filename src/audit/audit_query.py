"""src/audit/audit_query.py — Phase 41: 감사 로그 조회/검색."""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class AuditQuery:
    """감사 로그 조회 서비스.

    - 기간/사용자/이벤트 타입/리소스 필터
    - 페이지네이션
    - 전문 검색
    """

    def __init__(self, store=None):
        self._store = store

    def _get_records(self) -> List[dict]:
        if self._store is not None:
            return self._store.get_all()
        return []

    def filter(
        self,
        records: Optional[List[dict]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        resource: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[dict]:
        """필터 적용.

        Args:
            records: 대상 레코드 목록 (None이면 store에서 가져옴)
            start_time: ISO 8601 시작 시각
            end_time: ISO 8601 종료 시각
            user_id: 사용자/actor 필터
            event_type: 이벤트 타입 필터
            resource: 리소스 필터 (부분 일치)
            keyword: 전문 검색 키워드

        Returns:
            필터된 레코드 목록
        """
        items = records if records is not None else self._get_records()

        if start_time:
            items = [r for r in items if r.get('timestamp', '') >= start_time]
        if end_time:
            items = [r for r in items if r.get('timestamp', '') <= end_time]
        if user_id:
            items = [r for r in items if r.get('actor', '') == user_id]
        if event_type:
            items = [r for r in items if r.get('event_type', '') == event_type]
        if resource:
            items = [r for r in items if resource in r.get('resource', '')]
        if keyword:
            kw = keyword.lower()
            items = [r for r in items if self._contains_keyword(r, kw)]
        return items

    def _contains_keyword(self, record: dict, keyword: str) -> bool:
        """레코드의 모든 문자열 필드에서 키워드 검색."""
        for value in record.values():
            if isinstance(value, str) and keyword in value.lower():
                return True
            if isinstance(value, dict):
                for v in value.values():
                    if isinstance(v, str) and keyword in v.lower():
                        return True
        return False

    def paginate(self, records: List[dict], page: int = 1, per_page: int = 20) -> dict:
        """페이지네이션 적용.

        Returns:
            {'items': [...], 'total': int, 'page': int, 'per_page': int, 'pages': int}
        """
        total = len(records)
        pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        return {
            'items': records[start:end],
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': pages,
        }

    def search(self, keyword: str, records: Optional[List[dict]] = None) -> List[dict]:
        """전문 검색."""
        return self.filter(records=records, keyword=keyword)

    def query(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        resource: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """필터 + 페이지네이션 통합 조회."""
        filtered = self.filter(
            start_time=start_time,
            end_time=end_time,
            user_id=user_id,
            event_type=event_type,
            resource=resource,
            keyword=keyword,
        )
        # 최신순 정렬
        filtered = sorted(filtered, key=lambda x: x.get('timestamp', ''), reverse=True)
        return self.paginate(filtered, page=page, per_page=per_page)
