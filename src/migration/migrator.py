"""
마이그레이션 실행기 — 버전 스크립트 자동 발견 및 순차 실행.

src/migration/versions/ 디렉토리에서 마이그레이션 스크립트를 자동으로 발견하고
버전 순서에 따라 실행한다.
"""

import importlib
import logging
import os
import pkgutil
from typing import List, Optional

from .schema_manager import SchemaManager

logger = logging.getLogger(__name__)


class MigrationRecord:
    """마이그레이션 실행 이력 레코드."""

    def __init__(self, version: str, description: str, success: bool, error: Optional[str] = None):
        self.version = version
        self.description = description
        self.success = success
        self.error = error

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"<MigrationRecord {status} v{self.version}: {self.description}>"


class Migrator:
    """마이그레이션 실행기.

    versions/ 디렉토리의 마이그레이션 스크립트를 순차적으로 실행하고 롤백을 지원한다.
    각 마이그레이션 모듈은 다음 함수를 포함해야 한다:
        - up(client, sheet_id) → 마이그레이션 적용
        - down(client, sheet_id) → 마이그레이션 롤백
        - VERSION (str) → 버전 문자열
        - DESCRIPTION (str) → 설명
    """

    def __init__(self, sheets_client=None, sheet_id: Optional[str] = None, versions_dir: Optional[str] = None):
        """초기화.

        인자:
            sheets_client: gspread 클라이언트
            sheet_id: Google Sheets 스프레드시트 ID
            versions_dir: 마이그레이션 스크립트 디렉토리 경로
        """
        self._client = sheets_client
        self._sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID", "")
        self._versions_dir = versions_dir or os.path.join(os.path.dirname(__file__), "versions")
        self._history: List[MigrationRecord] = []

    # ── 스크립트 발견 ──────────────────────────────────────────

    def discover_migrations(self) -> List[dict]:
        """versions/ 디렉토리에서 마이그레이션 모듈을 발견한다.

        반환:
            version 기준 오름차순 정렬된 마이그레이션 메타데이터 목록
        """
        migrations = []
        for _, module_name, _ in pkgutil.iter_modules([self._versions_dir]):
            if not module_name.startswith("v"):
                continue
            full_name = f"src.migration.versions.{module_name}"
            try:
                mod = importlib.import_module(full_name)
                migrations.append({
                    "version": getattr(mod, "VERSION", module_name),
                    "description": getattr(mod, "DESCRIPTION", ""),
                    "module": mod,
                    "module_name": module_name,
                })
            except ImportError as exc:
                logger.error("마이그레이션 모듈 로드 실패: %s — %s", full_name, exc)

        migrations.sort(key=lambda x: x["version"])
        return migrations

    # ── 실행 ──────────────────────────────────────────────────

    def run(self, target_version: Optional[str] = None, dry_run: bool = False) -> List[MigrationRecord]:
        """마이그레이션을 순차적으로 실행한다.

        인자:
            target_version: 목표 버전 (None이면 최신 버전까지)
            dry_run: True이면 실제 실행 없이 시뮬레이션만

        반환:
            실행된 마이그레이션 이력 목록
        """
        schema_mgr = SchemaManager(self._client, self._sheet_id)
        current = schema_mgr.get_current_version() or "000"

        migrations = self.discover_migrations()
        to_run = [m for m in migrations if m["version"] > current]
        if target_version:
            to_run = [m for m in to_run if m["version"] <= target_version]

        if not to_run:
            logger.info("적용할 마이그레이션 없음 (현재 버전: %s)", current)
            return []

        logger.info("%s개 마이그레이션 실행 예정 (dry_run=%s)", len(to_run), dry_run)
        records: List[MigrationRecord] = []

        for mig in to_run:
            record = self._execute_up(mig, dry_run)
            records.append(record)
            self._history.append(record)

            if not record.success:
                logger.error("마이그레이션 v%s 실패 — 중단", mig["version"])
                break

            if not dry_run:
                schema_mgr.update_version(mig["version"], mig["description"])

        return records

    def rollback(self, steps: int = 1, dry_run: bool = False) -> List[MigrationRecord]:
        """마이그레이션을 롤백한다.

        인자:
            steps: 롤백할 단계 수
            dry_run: True이면 실제 실행 없이 시뮬레이션만

        반환:
            실행된 롤백 이력 목록
        """
        schema_mgr = SchemaManager(self._client, self._sheet_id)
        current = schema_mgr.get_current_version() or "000"

        migrations = self.discover_migrations()
        applied = [m for m in migrations if m["version"] <= current]
        to_rollback = list(reversed(applied))[:steps]

        records: List[MigrationRecord] = []
        for mig in to_rollback:
            record = self._execute_down(mig, dry_run)
            records.append(record)
            self._history.append(record)

            if not record.success:
                logger.error("롤백 v%s 실패 — 중단", mig["version"])
                break

        return records

    def get_history(self) -> List[MigrationRecord]:
        """실행 이력을 반환한다."""
        return list(self._history)

    # ── 내부 헬퍼 ─────────────────────────────────────────────

    def _execute_up(self, mig: dict, dry_run: bool) -> MigrationRecord:
        """단일 마이그레이션 up() 실행."""
        version = mig["version"]
        description = mig["description"]

        if dry_run:
            logger.info("[DRY-RUN] up: v%s — %s", version, description)
            return MigrationRecord(version, description, success=True)

        try:
            up_fn = getattr(mig["module"], "up", None)
            if up_fn is None:
                raise AttributeError(f"v{version} 모듈에 up() 함수가 없습니다.")
            up_fn(self._client, self._sheet_id)
            logger.info("마이그레이션 up 완료: v%s", version)
            return MigrationRecord(version, description, success=True)
        except Exception as exc:  # noqa: BLE001
            logger.error("마이그레이션 up 실패 v%s: %s", version, exc)
            return MigrationRecord(version, description, success=False, error=str(exc))

    def _execute_down(self, mig: dict, dry_run: bool) -> MigrationRecord:
        """단일 마이그레이션 down() 실행."""
        version = mig["version"]
        description = mig["description"]

        if dry_run:
            logger.info("[DRY-RUN] down: v%s — %s", version, description)
            return MigrationRecord(version, description, success=True)

        try:
            down_fn = getattr(mig["module"], "down", None)
            if down_fn is None:
                raise AttributeError(f"v{version} 모듈에 down() 함수가 없습니다.")
            down_fn(self._client, self._sheet_id)
            logger.info("마이그레이션 down 완료: v%s", version)
            return MigrationRecord(version, description, success=True)
        except Exception as exc:  # noqa: BLE001
            logger.error("마이그레이션 down 실패 v%s: %s", version, exc)
            return MigrationRecord(version, description, success=False, error=str(exc))
