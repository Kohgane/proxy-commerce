"""src/cli/system_commands.py — 시스템 관리 CLI 커맨드.

커맨드:
  health check            — 전체 시스템 헬스 체크
  cache stats             — 캐시 히트율/사용량 출력
  cache clear             — 캐시 전체 초기화
  audit recent [--limit]  — 최근 감사 로그 출력
"""

import logging
import os

logger = logging.getLogger(__name__)


def cmd_health(args):
    """헬스 체크 커맨드를 처리한다."""
    _health_check()


def _health_check():
    """전체 시스템 헬스 체크를 실행한다."""
    print("🏥 시스템 헬스 체크 중...")
    checks = {}

    # Google Sheets 연결 확인
    try:
        from ..utils.sheets import open_sheet
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        if sheet_id:
            open_sheet(sheet_id, os.getenv("WORKSHEET", "catalog"))
            checks["google_sheets"] = True
        else:
            checks["google_sheets"] = False
    except Exception:
        checks["google_sheets"] = False

    # 환율 서비스 확인
    try:
        from ..fx.provider import FXProvider
        FXProvider().get_rates()
        checks["fx_service"] = True
    except Exception:
        checks["fx_service"] = False

    # 시크릿 확인
    try:
        from ..utils.secret_check import check_secrets
        result = check_secrets("core")
        checks["secrets"] = len(result["core"]["missing"]) == 0
    except Exception:
        checks["secrets"] = False

    print("\n📊 헬스 체크 결과")
    print("─" * 40)
    all_ok = True
    for service, ok in checks.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {service}: {'정상' if ok else '비정상'}")
        if not ok:
            all_ok = False

    print("─" * 40)
    print(f"종합 상태: {'✅ 정상' if all_ok else '❌ 일부 비정상'}")


def cmd_cache(args):
    """캐시 커맨드를 처리한다."""
    sub = getattr(args, "cache_cmd", "stats")
    if sub == "clear":
        _cache_clear()
    else:
        _cache_stats()


def _cache_stats():
    """캐시 히트율과 사용량을 출력한다."""
    try:
        from ..cache.api_cache import _global_cache
        stats = _global_cache.stats.to_dict()
        size = _global_cache.size()
        print("\n📊 캐시 통계")
        print("─" * 40)
        print(f"  현재 항목 수: {size}개")
        print(f"  캐시 히트: {stats['hits']}회")
        print(f"  캐시 미스: {stats['misses']}회")
        print(f"  히트율: {stats['hit_rate'] * 100:.1f}%")
        print(f"  eviction: {stats['evictions']}회")
    except Exception as exc:
        print(f"❌ 캐시 통계 조회 실패: {exc}")


def _cache_clear():
    """캐시를 전체 초기화한다."""
    try:
        from ..cache.api_cache import _global_cache
        _global_cache.clear()
        print("✅ 캐시 초기화 완료")
    except Exception as exc:
        print(f"❌ 캐시 초기화 실패: {exc}")


def cmd_audit(args):
    """감사 로그 커맨드를 처리한다."""
    limit = getattr(args, "limit", 20)
    _audit_recent(limit)


def _audit_recent(limit: int = 20):
    """최근 감사 로그를 출력한다."""
    try:
        from ..utils.sheets import open_sheet
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        ws = open_sheet(sheet_id, os.getenv("AUDIT_WORKSHEET", "audit_log"))
        rows = ws.get_all_records()
        recent = rows[-limit:] if len(rows) > limit else rows
        recent = list(reversed(recent))

        print(f"\n📋 최근 감사 로그 (최대 {limit}개)")
        print("─" * 80)
        print(f"{'시각':<25} {'이벤트':<30} {'액터':<15} {'리소스'}")
        print("─" * 80)
        for r in recent:
            print(
                f"{str(r.get('timestamp', ''))[:24]:<25} "
                f"{str(r.get('event_type', '')):<30} "
                f"{str(r.get('actor', '')):<15} "
                f"{str(r.get('resource', ''))}"
            )
    except Exception as exc:
        print(f"❌ 감사 로그 조회 실패: {exc}")
