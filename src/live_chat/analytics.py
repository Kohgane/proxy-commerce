"""src/live_chat/analytics.py — 채팅 분석 (Phase 107)."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ChatAnalytics:
    """채팅 서비스 분석 대시보드."""

    def __init__(self):
        # 세션 데이터 (세션 딕셔너리 목록)
        self._sessions: List[dict] = []
        # 메시지 데이터 (메시지 딕셔너리 목록)
        self._messages: List[dict] = []

    # ── 데이터 수집 ────────────────────────────────────────────────────────────

    def record_session(self, session_dict: dict) -> None:
        self._sessions.append(dict(session_dict))

    def record_message(self, message_dict: dict) -> None:
        self._messages.append(dict(message_dict))

    # ── 실시간 지표 ────────────────────────────────────────────────────────────

    def get_realtime_metrics(
        self,
        active_sessions: int = 0,
        waiting_customers: int = 0,
        online_agents: int = 0,
    ) -> dict:
        return {
            'active_sessions': active_sessions,
            'waiting_customers': waiting_customers,
            'online_agents': online_agents,
            'timestamp': datetime.now(tz=timezone.utc).isoformat(),
        }

    # ── 성과 지표 ──────────────────────────────────────────────────────────────

    def get_performance_metrics(self) -> dict:
        sessions = self._sessions
        if not sessions:
            return {
                'avg_first_response_seconds': 0.0,
                'avg_resolution_seconds': 0.0,
                'avg_session_duration_seconds': 0.0,
                'average_rating': 0.0,
                'total_sessions': 0,
            }

        # 만족도
        rated = [s for s in sessions if s.get('rating') is not None]
        avg_rating = (
            sum(s['rating'] for s in rated) / len(rated) if rated else 0.0
        )

        # 응답 시간 (시뮬레이션: 60~300초)
        avg_first_response = 120.0
        avg_resolution = 600.0
        avg_duration = 480.0

        return {
            'avg_first_response_seconds': avg_first_response,
            'avg_resolution_seconds': avg_resolution,
            'avg_session_duration_seconds': avg_duration,
            'average_rating': round(avg_rating, 2),
            'total_sessions': len(sessions),
            'rated_sessions': len(rated),
        }

    # ── 상담원별 성과 ──────────────────────────────────────────────────────────

    def get_agent_performance(self) -> List[dict]:
        agent_data: Dict[str, dict] = defaultdict(lambda: {
            'total_sessions': 0,
            'total_rating': 0.0,
            'rated_count': 0,
        })
        for s in self._sessions:
            aid = s.get('agent_id')
            if not aid:
                continue
            agent_data[aid]['total_sessions'] += 1
            if s.get('rating') is not None:
                agent_data[aid]['total_rating'] += s['rating']
                agent_data[aid]['rated_count'] += 1

        results = []
        for aid, data in agent_data.items():
            rated = data['rated_count']
            avg_r = data['total_rating'] / rated if rated else 0.0
            results.append({
                'agent_id': aid,
                'total_sessions': data['total_sessions'],
                'average_rating': round(avg_r, 2),
                'rated_sessions': rated,
            })
        return sorted(results, key=lambda x: -x['total_sessions'])

    # ── 문의 유형별 분석 ────────────────────────────────────────────────────────

    def get_category_analysis(self) -> dict:
        category_counts: Dict[str, int] = defaultdict(int)
        for s in self._sessions:
            for tag in s.get('tags', []):
                category_counts[tag] += 1
        total = sum(category_counts.values())
        return {
            'by_category': dict(category_counts),
            'total_tagged': total,
        }

    # ── 피크 시간대 분석 ────────────────────────────────────────────────────────

    def get_peak_hours(self) -> dict:
        hourly: Dict[int, int] = defaultdict(int)
        for s in self._sessions:
            started = s.get('started_at', '')
            if started:
                try:
                    dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
                    hourly[dt.hour] += 1
                except Exception:
                    pass
        if not hourly:
            return {'peak_hour': None, 'hourly_distribution': {}}
        peak_hour = max(hourly, key=lambda h: hourly[h])
        return {
            'peak_hour': peak_hour,
            'hourly_distribution': {str(h): c for h, c in sorted(hourly.items())},
        }

    # ── 통합 대시보드 ──────────────────────────────────────────────────────────

    def get_dashboard(
        self,
        active_sessions: int = 0,
        waiting_customers: int = 0,
        online_agents: int = 0,
    ) -> dict:
        return {
            'realtime': self.get_realtime_metrics(
                active_sessions=active_sessions,
                waiting_customers=waiting_customers,
                online_agents=online_agents,
            ),
            'performance': self.get_performance_metrics(),
            'agent_performance': self.get_agent_performance(),
            'category_analysis': self.get_category_analysis(),
            'peak_hours': self.get_peak_hours(),
        }
