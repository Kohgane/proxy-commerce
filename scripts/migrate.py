#!/usr/bin/env python3
"""scripts/migrate.py — Phase 42: 마이그레이션 CLI.

사용법:
    python scripts/migrate.py up       # 모든 마이그레이션 실행
    python scripts/migrate.py down     # 마지막 마이그레이션 롤백
    python scripts/migrate.py status   # 마이그레이션 상태 출력
"""
import logging
import sys
import os

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def cmd_up():
    """마이그레이션 실행."""
    from src.migration.migrator import Migrator
    migrator = Migrator()
    logger.info("마이그레이션 실행 시작...")
    try:
        results = migrator.run_all()
        for record in results:
            status = '✓' if record.success else '✗'
            print(f"  {status} v{record.version}: {record.description}")
            if record.error:
                print(f"    오류: {record.error}")
        print(f"\n완료: {sum(1 for r in results if r.success)}개 성공, "
              f"{sum(1 for r in results if not r.success)}개 실패")
    except Exception as exc:
        logger.error("마이그레이션 실패: %s", exc)
        sys.exit(1)


def cmd_down():
    """마지막 마이그레이션 롤백."""
    from src.migration.migrator import Migrator
    migrator = Migrator()
    logger.info("마지막 마이그레이션 롤백...")
    try:
        result = migrator.rollback_last()
        if result:
            print(f"  롤백 완료: v{result.version}: {result.description}")
        else:
            print("  롤백할 마이그레이션 없음")
    except Exception as exc:
        logger.error("롤백 실패: %s", exc)
        sys.exit(1)


def cmd_status():
    """마이그레이션 상태 출력."""
    from src.migration.migrator import Migrator
    migrator = Migrator()
    try:
        scripts = migrator._discover_scripts()
        applied = migrator._applied_versions()
        print(f"마이그레이션 스크립트 {len(scripts)}개:")
        for script in scripts:
            version = getattr(script, 'VERSION', '?')
            desc = getattr(script, 'DESCRIPTION', '')
            status = '✓ 적용됨' if version in applied else '  미적용'
            print(f"  {status} v{version}: {desc}")
    except Exception as exc:
        logger.error("상태 조회 실패: %s", exc)
        # 실패해도 에러 없이 종료
        print("마이그레이션 상태를 가져올 수 없습니다 (DB 연결 필요).")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    command = sys.argv[1].lower()
    if command == 'up':
        cmd_up()
    elif command == 'down':
        cmd_down()
    elif command == 'status':
        cmd_status()
    else:
        print(f"알 수 없는 명령: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
