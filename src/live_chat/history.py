"""src/live_chat/history.py — 채팅 이력 관리 (Phase 107)."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ChatHistoryManager:
    """채팅 이력 저장/조회/검색."""

    def __init__(self):
        # session_id → {session_data, messages}
        self._history: Dict[str, dict] = {}
        # customer_id → [session_id]
        self._customer_sessions: Dict[str, List[str]] = defaultdict(list)

    # ── 세션 저장 ────────────────────────────────────────────────────────────

    def save_session(self, session_dict: dict, messages: List[dict]) -> None:
        session_id = session_dict['session_id']
        customer_id = session_dict['customer_id']
        self._history[session_id] = {
            'session': session_dict,
            'messages': list(messages),
            'saved_at': datetime.now(tz=timezone.utc).isoformat(),
        }
        if session_id not in self._customer_sessions[customer_id]:
            self._customer_sessions[customer_id].append(session_id)
        logger.info("채팅 이력 저장: 세션 %s", session_id)

    def get_session_history(self, session_id: str) -> Optional[dict]:
        return self._history.get(session_id)

    def get_customer_history(
        self, customer_id: str, limit: int = 20
    ) -> List[dict]:
        session_ids = self._customer_sessions.get(customer_id, [])
        results = []
        for sid in reversed(session_ids[-limit:]):
            record = self._history.get(sid)
            if record:
                results.append(record['session'])
        return results

    # ── 검색 ──────────────────────────────────────────────────────────────────

    def search(self, keyword: str, limit: int = 50) -> List[dict]:
        """키워드 기반 메시지 이력 검색."""
        keyword_lower = keyword.lower()
        results = []
        for record in self._history.values():
            for msg in record.get('messages', []):
                if keyword_lower in msg.get('content', '').lower():
                    results.append({
                        'session': record['session'],
                        'message': msg,
                    })
                    if len(results) >= limit:
                        return results
        return results

    # ── 통계 ──────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        sessions = [r['session'] for r in self._history.values()]
        total = len(sessions)
        rated = [s for s in sessions if s.get('rating') is not None]
        avg_rating = (sum(s['rating'] for s in rated) / len(rated)) if rated else 0.0

        # 메시지 수 통계
        all_messages = [
            msg
            for r in self._history.values()
            for msg in r.get('messages', [])
            if msg.get('sender_type') not in ('system',)
        ]
        avg_messages = len(all_messages) / total if total else 0.0

        # 일별 상담 건수 (closed/resolved 기준)
        daily: Dict[str, int] = defaultdict(int)
        for s in sessions:
            ended = s.get('ended_at') or s.get('started_at', '')
            if ended:
                day = ended[:10]
                daily[day] += 1

        return {
            'total_sessions': total,
            'rated_sessions': len(rated),
            'average_rating': round(avg_rating, 2),
            'average_messages_per_session': round(avg_messages, 1),
            'daily_counts': dict(daily),
        }

    def get_daily_count(self, date_str: str) -> int:
        count = 0
        for record in self._history.values():
            session = record['session']
            started = session.get('started_at', '')
            if started.startswith(date_str):
                count += 1
        return count
