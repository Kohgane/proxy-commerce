"""src/channel_sync/dashboard.py — 채널 동기화 대시보드 (Phase 109).

ChannelSyncDashboard: 채널별 동기화 현황 + 건강도 + 큐 현황
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ChannelSyncDashboard:
    """채널 동기화 대시보드."""

    def __init__(self, engine=None, listing_manager=None, conflict_resolver=None, scheduler=None):
        self._engine = engine
        self._listing_manager = listing_manager
        self._conflict_resolver = conflict_resolver
        self._scheduler = scheduler

    def get_dashboard(self) -> dict:
        """전체 대시보드 데이터."""
        result: Dict = {
            'sync_stats': {},
            'listing_stats': {},
            'channel_health': {},
            'queue_status': {},
            'conflict_stats': {},
            'scheduler_stats': {},
        }

        if self._engine:
            result['sync_stats'] = self._engine.get_sync_stats()
            result['channel_health'] = self._engine.get_channel_health()
            result['queue_status'] = self._engine.get_queue_status()

        if self._listing_manager:
            result['listing_stats'] = self._listing_manager.get_stats()

        if self._conflict_resolver:
            result['conflict_stats'] = self._conflict_resolver.get_stats()

        if self._scheduler:
            result['scheduler_stats'] = self._scheduler.get_stats()

        return result

    def get_channel_summary(self) -> dict:
        """채널별 동기화 현황 요약."""
        summary: Dict = {}

        if self._engine:
            health = self._engine.get_channel_health()
            stats = self._engine.get_sync_stats()
            by_channel = stats.get('by_channel', {})

            for channel, h in health.items():
                channel_stats = by_channel.get(channel, {})
                summary[channel] = {
                    'healthy': h.get('healthy', False),
                    'success': channel_stats.get('success', 0),
                    'failed': channel_stats.get('failed', 0),
                }

        if self._listing_manager:
            listing_stats = self._listing_manager.get_stats()
            by_channel_listings = listing_stats.get('by_channel', {})
            for channel, count in by_channel_listings.items():
                if channel not in summary:
                    summary[channel] = {}
                summary[channel]['listings'] = count

        return summary

    def get_recent_sync_feed(self, limit: int = 20) -> list:
        """최근 동기화 피드."""
        if self._engine:
            return self._engine.get_sync_history(limit=limit)
        return []

    def get_pending_conflicts(self) -> list:
        """미해결 충돌 목록."""
        if self._conflict_resolver:
            return [c.to_dict() for c in self._conflict_resolver.get_unresolved_conflicts()]
        return []
