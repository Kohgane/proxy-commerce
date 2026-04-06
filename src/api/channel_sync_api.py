"""src/api/channel_sync_api.py — 판매채널 자동 연동 API Blueprint (Phase 109).

Blueprint: /api/v1/channel-sync

엔드포인트:
  POST   /sync                             — 전체 동기화 트리거
  POST   /sync/<product_id>               — 특정 상품 동기화
  POST   /handle-change                   — 소싱처 변동 이벤트 처리
  GET    /status                          — 전체 동기화 현황
  GET    /status/<product_id>             — 상품별 동기화 상태
  GET    /history                         — 동기화 이력
  GET    /stats                           — 동기화 통계
  GET    /listings                        — 전체 리스팅 목록
  GET    /listings/<product_id>           — 상품별 리스팅
  POST   /listings/<listing_id>/pause     — 리스팅 일시중지
  POST   /listings/<listing_id>/resume    — 리스팅 재활성화
  DELETE /listings/<listing_id>           — 리스팅 삭제
  GET    /channels                        — 채널 목록 + 건강도
  GET    /channels/<channel>/health       — 특정 채널 건강도
  GET    /dashboard                       — 대시보드 데이터
  GET    /conflicts                       — 미해결 충돌 목록
  POST   /conflicts/<conflict_id>/resolve — 충돌 수동 해결
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

channel_sync_bp = Blueprint(
    'channel_sync',
    __name__,
    url_prefix='/api/v1/channel-sync',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_engine = None
_listing_manager = None
_conflict_resolver = None
_scheduler = None
_dashboard = None


def _get_engine():
    global _engine
    if _engine is None:
        from src.channel_sync.sync_engine import ChannelSyncEngine
        _engine = ChannelSyncEngine()
    return _engine


def _get_listing_manager():
    global _listing_manager
    if _listing_manager is None:
        from src.channel_sync.listing_manager import ListingStatusManager
        _listing_manager = ListingStatusManager()
    return _listing_manager


def _get_conflict_resolver():
    global _conflict_resolver
    if _conflict_resolver is None:
        from src.channel_sync.conflict_resolver import SyncConflictResolver
        _conflict_resolver = SyncConflictResolver()
    return _conflict_resolver


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        from src.channel_sync.sync_scheduler import ChannelSyncScheduler
        _scheduler = ChannelSyncScheduler()
    return _scheduler


def _get_dashboard():
    global _dashboard
    if _dashboard is None:
        from src.channel_sync.dashboard import ChannelSyncDashboard
        _dashboard = ChannelSyncDashboard(
            engine=_get_engine(),
            listing_manager=_get_listing_manager(),
            conflict_resolver=_get_conflict_resolver(),
            scheduler=_get_scheduler(),
        )
    return _dashboard


# ── 동기화 ───────────────────────────────────────────────────────────────────

@channel_sync_bp.post('/sync')
def trigger_sync_all():
    """전체 동기화 트리거."""
    data = request.get_json(force=True) or {}
    channel = data.get('channel')
    try:
        result = _get_engine().sync_all(channel=channel)
        job = _get_scheduler().schedule_full_sync(channel=channel)
        return jsonify({'success': True, 'result': result, 'job_id': job.job_id})
    except Exception as exc:
        logger.error("trigger_sync_all 오류: %s", exc)
        return jsonify({'error': '전체 동기화에 실패했습니다.'}), 500


@channel_sync_bp.post('/sync/<product_id>')
def trigger_sync_product(product_id: str):
    """특정 상품 동기화."""
    data = request.get_json(force=True) or {}
    channels = data.get('channels')
    product_data = data.get('product_data') or {'product_id': product_id}
    try:
        result = _get_engine().sync_product(product_id, channels=channels, product_data=product_data)
        return jsonify({'success': True, 'result': result})
    except Exception as exc:
        logger.error("trigger_sync_product 오류: %s", exc)
        return jsonify({'error': '상품 동기화에 실패했습니다.'}), 500


@channel_sync_bp.post('/handle-change')
def handle_change():
    """소싱처 변동 이벤트 처리."""
    data = request.get_json(force=True) or {}
    if not data.get('change_type'):
        return jsonify({'error': 'change_type이 필요합니다.'}), 400
    try:
        result = _get_engine().handle_source_change(data)
        return jsonify({'success': True, 'result': result})
    except Exception as exc:
        logger.error("handle_change 오류: %s", exc)
        return jsonify({'error': '변동 이벤트 처리에 실패했습니다.'}), 500


# ── 동기화 상태 ───────────────────────────────────────────────────────────────

@channel_sync_bp.get('/status')
def get_sync_status():
    """전체 동기화 현황."""
    try:
        status = _get_engine().get_sync_status()
        return jsonify({'success': True, **status})
    except Exception as exc:
        logger.error("get_sync_status 오류: %s", exc)
        return jsonify({'error': '동기화 현황 조회에 실패했습니다.'}), 500


@channel_sync_bp.get('/status/<product_id>')
def get_product_sync_status(product_id: str):
    """상품별 동기화 상태."""
    try:
        status = _get_engine().get_sync_status(product_id=product_id)
        return jsonify({'success': True, **status})
    except Exception as exc:
        logger.error("get_product_sync_status 오류: %s", exc)
        return jsonify({'error': '상품별 동기화 상태 조회에 실패했습니다.'}), 500


@channel_sync_bp.get('/history')
def get_sync_history():
    """동기화 이력."""
    product_id = request.args.get('product_id')
    channel = request.args.get('channel')
    limit = int(request.args.get('limit', 50))
    try:
        history = _get_engine().get_sync_history(product_id=product_id, channel=channel, limit=limit)
        return jsonify({'success': True, 'history': history, 'total': len(history)})
    except Exception as exc:
        logger.error("get_sync_history 오류: %s", exc)
        return jsonify({'error': '동기화 이력 조회에 실패했습니다.'}), 500


@channel_sync_bp.get('/stats')
def get_sync_stats():
    """동기화 통계."""
    try:
        stats = _get_engine().get_sync_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as exc:
        logger.error("get_sync_stats 오류: %s", exc)
        return jsonify({'error': '동기화 통계 조회에 실패했습니다.'}), 500


# ── 리스팅 ───────────────────────────────────────────────────────────────────

@channel_sync_bp.get('/listings')
def get_all_listings():
    """전체 리스팅 목록."""
    try:
        listings = _get_engine()._listing_manager.get_listings()
        return jsonify({
            'success': True,
            'listings': [l.to_dict() for l in listings],
            'total': len(listings),
        })
    except Exception as exc:
        logger.error("get_all_listings 오류: %s", exc)
        return jsonify({'error': '리스팅 목록 조회에 실패했습니다.'}), 500


@channel_sync_bp.get('/listings/<product_id>')
def get_product_listings(product_id: str):
    """상품별 리스팅."""
    try:
        listings = _get_engine()._listing_manager.get_listings(product_id=product_id)
        return jsonify({
            'success': True,
            'product_id': product_id,
            'listings': [l.to_dict() for l in listings],
            'total': len(listings),
        })
    except Exception as exc:
        logger.error("get_product_listings 오류: %s", exc)
        return jsonify({'error': '상품별 리스팅 조회에 실패했습니다.'}), 500


@channel_sync_bp.post('/listings/<listing_id>/pause')
def pause_listing(listing_id: str):
    """리스팅 일시중지."""
    data = request.get_json(force=True) or {}
    reason = data.get('reason', '수동 일시중지')
    try:
        listing = _get_engine()._listing_manager.pause_listing(listing_id, reason)
        if not listing:
            return jsonify({'error': 'listing not found'}), 404
        return jsonify({'success': True, 'listing': listing.to_dict()})
    except Exception as exc:
        logger.error("pause_listing 오류: %s", exc)
        return jsonify({'error': '리스팅 일시중지에 실패했습니다.'}), 500


@channel_sync_bp.post('/listings/<listing_id>/resume')
def resume_listing(listing_id: str):
    """리스팅 재활성화."""
    try:
        listing = _get_engine()._listing_manager.resume_listing(listing_id)
        if not listing:
            return jsonify({'error': 'listing not found'}), 404
        return jsonify({'success': True, 'listing': listing.to_dict()})
    except Exception as exc:
        logger.error("resume_listing 오류: %s", exc)
        return jsonify({'error': '리스팅 재활성화에 실패했습니다.'}), 500


@channel_sync_bp.delete('/listings/<listing_id>')
def delete_listing(listing_id: str):
    """리스팅 삭제."""
    try:
        listing = _get_engine()._listing_manager.delete_listing(listing_id)
        if not listing:
            return jsonify({'error': 'listing not found'}), 404
        return jsonify({'success': True, 'listing': listing.to_dict()})
    except Exception as exc:
        logger.error("delete_listing 오류: %s", exc)
        return jsonify({'error': '리스팅 삭제에 실패했습니다.'}), 500


# ── 채널 ─────────────────────────────────────────────────────────────────────

@channel_sync_bp.get('/channels')
def get_channels():
    """채널 목록 + 건강도."""
    try:
        health = _get_engine().get_channel_health()
        return jsonify({'success': True, 'channels': health})
    except Exception as exc:
        logger.error("get_channels 오류: %s", exc)
        return jsonify({'error': '채널 목록 조회에 실패했습니다.'}), 500


@channel_sync_bp.get('/channels/<channel>/health')
def get_channel_health(channel: str):
    """특정 채널 건강도."""
    try:
        health = _get_engine().get_channel_health(channel=channel)
        if channel not in health:
            return jsonify({'error': f'unknown channel: {channel}'}), 404
        return jsonify({'success': True, 'health': health[channel]})
    except Exception as exc:
        logger.error("get_channel_health 오류: %s", exc)
        return jsonify({'error': '채널 건강도 조회에 실패했습니다.'}), 500


# ── 대시보드 ─────────────────────────────────────────────────────────────────

@channel_sync_bp.get('/dashboard')
def get_dashboard():
    """대시보드 데이터."""
    try:
        data = _get_dashboard().get_dashboard()
        return jsonify({'success': True, **data})
    except Exception as exc:
        logger.error("get_dashboard 오류: %s", exc)
        return jsonify({'error': '대시보드 데이터 조회에 실패했습니다.'}), 500


# ── 충돌 ─────────────────────────────────────────────────────────────────────

@channel_sync_bp.get('/conflicts')
def get_conflicts():
    """미해결 충돌 목록."""
    try:
        conflicts = _get_conflict_resolver().get_unresolved_conflicts()
        return jsonify({
            'success': True,
            'conflicts': [c.to_dict() for c in conflicts],
            'total': len(conflicts),
        })
    except Exception as exc:
        logger.error("get_conflicts 오류: %s", exc)
        return jsonify({'error': '충돌 목록 조회에 실패했습니다.'}), 500


@channel_sync_bp.post('/conflicts/<conflict_id>/resolve')
def resolve_conflict(conflict_id: str):
    """충돌 수동 해결."""
    data = request.get_json(force=True) or {}
    resolved_value = data.get('resolved_value')
    resolution_note = data.get('resolution_note', '')
    try:
        conflict = _get_conflict_resolver().resolve_conflict(conflict_id, resolved_value, resolution_note)
        if not conflict:
            return jsonify({'error': 'conflict not found'}), 404
        return jsonify({'success': True, 'conflict': conflict.to_dict()})
    except Exception as exc:
        logger.error("resolve_conflict 오류: %s", exc)
        return jsonify({'error': '충돌 수동 해결에 실패했습니다.'}), 500
