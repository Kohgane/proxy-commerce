"""src/bot/channel_sync_commands.py — 채널 동기화 봇 커맨드 (Phase 109)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def cmd_sync_status() -> str:
    """/sync_status — 전체 동기화 현황 요약."""
    try:
        from src.channel_sync.sync_engine import ChannelSyncEngine
        engine = ChannelSyncEngine()
        stats = engine.get_sync_stats()
        status = engine.get_sync_status()

        listing_stats = status.get('listing_stats', {})
        queue_stats = status.get('queue_stats', {})
        by_channel = stats.get('by_channel', {})

        lines = ['📊 *채널 동기화 현황*\n']
        lines.append(f"• 총 동기화: {stats.get('total', 0)}건")
        lines.append(f"• 성공: {stats.get('success', 0)}건")
        lines.append(f"• 실패: {stats.get('failed', 0)}건")
        lines.append(f"• 동기화된 상품: {stats.get('products_synced', 0)}개\n")

        if by_channel:
            lines.append('*채널별 현황:*')
            for ch, counts in by_channel.items():
                lines.append(f"  {ch}: 성공 {counts.get('success', 0)} / 실패 {counts.get('failed', 0)}")

        if listing_stats:
            lines.append(f"\n*리스팅:* 총 {listing_stats.get('total', 0)}개")
            by_state = listing_stats.get('by_state', {})
            for state, cnt in by_state.items():
                lines.append(f"  {state}: {cnt}개")

        if queue_stats:
            lines.append(f"\n*대기 큐:* {queue_stats.get('total', 0)}건")

        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_sync_status 오류: %s", exc)
        return f'❌ 동기화 현황 조회 실패: {exc}'


def cmd_sync_channel(channel: str) -> str:
    """/sync_channel <channel> — 특정 채널 동기화 트리거."""
    channel = channel.strip().lower()
    valid_channels = ('coupang', 'naver', 'internal')
    if channel not in valid_channels:
        return f'❌ 유효하지 않은 채널: {channel}\n사용 가능: {", ".join(valid_channels)}'
    try:
        from src.channel_sync.sync_engine import ChannelSyncEngine
        from src.channel_sync.sync_scheduler import ChannelSyncScheduler
        engine = ChannelSyncEngine()
        scheduler = ChannelSyncScheduler()
        result = engine.sync_all(channel=channel)
        job = scheduler.schedule_full_sync(channel=channel)
        return (
            f'🔄 *{channel} 채널 동기화 완료*\n'
            f'• 성공: {result.get("synced", 0)}건\n'
            f'• 실패: {result.get("failed", 0)}건\n'
            f'• 작업 ID: `{job.job_id}`'
        )
    except Exception as exc:
        logger.error("cmd_sync_channel 오류: %s", exc)
        return f'❌ 채널 동기화 실패: {exc}'


def cmd_sync_product(product_id: str) -> str:
    """/sync_product <product_id> — 특정 상품 전체 채널 동기화."""
    product_id = product_id.strip()
    if not product_id:
        return '❌ 상품 ID를 입력해주세요.\n사용법: /sync_product <product_id>'
    try:
        from src.channel_sync.sync_engine import ChannelSyncEngine
        engine = ChannelSyncEngine()
        result = engine.sync_product(product_id, product_data={'product_id': product_id})
        lines = [f'🔄 *상품 동기화 완료: `{product_id}`*\n']
        for ch, r in result.get('results', {}).items():
            status_icon = '✅' if r.get('success') else '❌'
            lines.append(f'{status_icon} {ch}: {r.get("message", r.get("error", ""))}')
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_sync_product 오류: %s", exc)
        return f'❌ 상품 동기화 실패: {exc}'


def cmd_sync_force() -> str:
    """/sync_force — 강제 전체 동기화."""
    try:
        from src.channel_sync.sync_engine import ChannelSyncEngine
        from src.channel_sync.sync_scheduler import ChannelSyncScheduler
        engine = ChannelSyncEngine()
        scheduler = ChannelSyncScheduler()
        result = engine.sync_all()
        job = scheduler.schedule_full_sync()
        return (
            f'⚡ *강제 전체 동기화 완료*\n'
            f'• 성공: {result.get("synced", 0)}건\n'
            f'• 실패: {result.get("failed", 0)}건\n'
            f'• 채널: {", ".join(result.get("channels", []))}\n'
            f'• 작업 ID: `{job.job_id}`'
        )
    except Exception as exc:
        logger.error("cmd_sync_force 오류: %s", exc)
        return f'❌ 강제 동기화 실패: {exc}'


def cmd_listing_status(product_id: str = '') -> str:
    """/listing_status [product_id] — 리스팅 현황."""
    try:
        from src.channel_sync.listing_manager import ListingStatusManager
        manager = ListingStatusManager()
        listings = manager.get_listings(product_id=product_id.strip() or None)
        stats = manager.get_stats()

        if not listings:
            return '📋 *리스팅 없음*\n등록된 리스팅이 없습니다.'

        lines = [f'📋 *리스팅 현황* (총 {stats.get("total", 0)}개)\n']
        for l in listings[:10]:
            state = l.state.value if hasattr(l.state, 'value') else str(l.state)
            lines.append(f'• [{l.channel}] {l.title or l.product_id} — {state}')
        if len(listings) > 10:
            lines.append(f'  ... 외 {len(listings) - 10}개')
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_listing_status 오류: %s", exc)
        return f'❌ 리스팅 현황 조회 실패: {exc}'


def cmd_listing_pause(listing_id: str, reason: str = '') -> str:
    """/listing_pause <listing_id> <reason> — 리스팅 일시중지."""
    listing_id = listing_id.strip()
    if not listing_id:
        return '❌ 리스팅 ID를 입력해주세요.\n사용법: /listing_pause <listing_id> <reason>'
    try:
        from src.channel_sync.listing_manager import ListingStatusManager
        manager = ListingStatusManager()
        listing = manager.pause_listing(listing_id, reason or '수동 일시중지')
        if not listing:
            return f'❌ 리스팅을 찾을 수 없습니다: {listing_id}'
        return f'⏸ *리스팅 일시중지 완료*\n• ID: `{listing_id}`\n• 사유: {reason or "수동 일시중지"}'
    except Exception as exc:
        logger.error("cmd_listing_pause 오류: %s", exc)
        return f'❌ 리스팅 일시중지 실패: {exc}'


def cmd_listing_resume(listing_id: str) -> str:
    """/listing_resume <listing_id> — 리스팅 재활성화."""
    listing_id = listing_id.strip()
    if not listing_id:
        return '❌ 리스팅 ID를 입력해주세요.\n사용법: /listing_resume <listing_id>'
    try:
        from src.channel_sync.listing_manager import ListingStatusManager
        manager = ListingStatusManager()
        listing = manager.resume_listing(listing_id)
        if not listing:
            return f'❌ 리스팅을 찾을 수 없습니다: {listing_id}'
        return f'▶️ *리스팅 재활성화 완료*\n• ID: `{listing_id}`'
    except Exception as exc:
        logger.error("cmd_listing_resume 오류: %s", exc)
        return f'❌ 리스팅 재활성화 실패: {exc}'


def cmd_channel_health() -> str:
    """/channel_health — 판매채널 건강도."""
    try:
        from src.channel_sync.sync_engine import ChannelSyncEngine
        engine = ChannelSyncEngine()
        health = engine.get_channel_health()
        lines = ['💚 *채널 건강도*\n']
        for ch, info in health.items():
            icon = '✅' if info.get('healthy') else '❌'
            lines.append(f'{icon} {ch}: {"정상" if info.get("healthy") else "점검 필요"}')
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_channel_health 오류: %s", exc)
        return f'❌ 채널 건강도 조회 실패: {exc}'


def cmd_sync_dashboard() -> str:
    """/sync_dashboard — 동기화 대시보드 요약."""
    try:
        from src.channel_sync.sync_engine import ChannelSyncEngine
        from src.channel_sync.dashboard import ChannelSyncDashboard
        from src.channel_sync.listing_manager import ListingStatusManager
        from src.channel_sync.conflict_resolver import SyncConflictResolver
        from src.channel_sync.sync_scheduler import ChannelSyncScheduler

        engine = ChannelSyncEngine()
        dashboard = ChannelSyncDashboard(
            engine=engine,
            listing_manager=ListingStatusManager(),
            conflict_resolver=SyncConflictResolver(),
            scheduler=ChannelSyncScheduler(),
        )
        data = dashboard.get_dashboard()
        sync_stats = data.get('sync_stats', {})
        listing_stats = data.get('listing_stats', {})
        conflict_stats = data.get('conflict_stats', {})

        lines = [
            '🗂 *채널 동기화 대시보드*\n',
            f'*동기화:* 총 {sync_stats.get("total", 0)}건 | 성공 {sync_stats.get("success", 0)} | 실패 {sync_stats.get("failed", 0)}',
            f'*리스팅:* 총 {listing_stats.get("total", 0)}개',
            f'*충돌:* 미해결 {conflict_stats.get("unresolved", 0)}건',
        ]
        channel_health = data.get('channel_health', {})
        if channel_health:
            lines.append('\n*채널 상태:*')
            for ch, info in channel_health.items():
                icon = '✅' if info.get('healthy') else '❌'
                lines.append(f'  {icon} {ch}')
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_sync_dashboard 오류: %s", exc)
        return f'❌ 대시보드 조회 실패: {exc}'


def cmd_sync_conflicts() -> str:
    """/sync_conflicts — 미해결 충돌 목록."""
    try:
        from src.channel_sync.conflict_resolver import SyncConflictResolver
        resolver = SyncConflictResolver()
        conflicts = resolver.get_unresolved_conflicts()
        if not conflicts:
            return '✅ 미해결 충돌 없음'
        lines = [f'⚠️ *미해결 충돌 ({len(conflicts)}건)*\n']
        for c in conflicts[:10]:
            lines.append(
                f'• [{c.channel}] {c.product_id} — {c.field_name}: '
                f'{c.source_value} vs {c.channel_value} (ID: `{c.conflict_id[:8]}`)'
            )
        if len(conflicts) > 10:
            lines.append(f'  ... 외 {len(conflicts) - 10}건')
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_sync_conflicts 오류: %s", exc)
        return f'❌ 충돌 목록 조회 실패: {exc}'
