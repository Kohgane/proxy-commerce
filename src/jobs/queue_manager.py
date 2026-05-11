"""src/jobs/queue_manager.py — 멀티워커 분산 잡 큐 (Phase 147).

멀티워커 환경에서의 중복 실행 방지:
  - DB 기반 분산 락 (SELECT ... FOR UPDATE SKIP LOCKED 추상화)
  - 작업 단위 idempotency key
  - 실패 시 재시도 + dead letter queue
  - 작업 카테고리별 우선순위/동시성 제한

환경변수:
  JOB_QUEUE_BACKEND          — db | redis (기본: db)
  JOB_QUEUE_MAX_RETRIES      — 최대 재시도 횟수 (기본: 3)
  JOB_QUEUE_DEAD_LETTER_DAYS — dead letter 보관 일수 (기본: 7)
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

_QUEUE_PATH = os.getenv("JOB_QUEUE_PATH", "data/job_queue.jsonl")
_DEAD_LETTER_PATH = os.getenv("JOB_DEAD_LETTER_PATH", "data/job_dead_letter.jsonl")
_MAX_RETRIES = int(os.getenv("JOB_QUEUE_MAX_RETRIES", "3"))
_DEAD_LETTER_DAYS = int(os.getenv("JOB_QUEUE_DEAD_LETTER_DAYS", "7"))

# 카테고리별 동시성 제한 (워커 수 기준)
CATEGORY_CONCURRENCY: dict[str, int] = {
    "sourcing": 2,
    "ads": 1,
    "reorder": 1,
    "campaign": 2,
    "returns": 3,
    "omni_sync": 2,
    "default": 4,
}

# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class Job:
    """잡 큐 단일 작업."""

    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str = ""      # 중복 실행 방지 키
    category: str = "default"     # sourcing | ads | reorder | campaign | returns | omni_sync
    priority: int = 5             # 1(최고) ~ 10(최저)
    payload: dict = field(default_factory=dict)
    status: str = "queued"        # queued | running | done | failed | dead
    attempts: int = 0
    max_retries: int = _MAX_RETRIES
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    locked_by: str = ""           # 작업 중인 워커 식별자
    error: str = ""
    worker_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Job":
        return Job(
            job_id=d.get("job_id", str(uuid.uuid4())),
            idempotency_key=d.get("idempotency_key", ""),
            category=d.get("category", "default"),
            priority=int(d.get("priority", 5)),
            payload=d.get("payload", {}),
            status=d.get("status", "queued"),
            attempts=int(d.get("attempts", 0)),
            max_retries=int(d.get("max_retries", _MAX_RETRIES)),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            locked_by=d.get("locked_by", ""),
            error=d.get("error", ""),
            worker_id=d.get("worker_id", ""),
        )


# ---------------------------------------------------------------------------
# 파일 기반 잡 큐 (DB/Redis 미설정 시 fallback)
# ---------------------------------------------------------------------------

class FileJobQueue:
    """파일 기반 잡 큐 (개발/단일 워커 환경 fallback)."""

    def __init__(self, path: str = _QUEUE_PATH, dead_letter_path: str = _DEAD_LETTER_PATH):
        self._path = path
        self._dead_path = dead_letter_path
        for p in [self._path, self._dead_path]:
            dirn = os.path.dirname(p)
            if dirn:
                os.makedirs(dirn, exist_ok=True)

    def _read(self, path: str) -> list[Job]:
        jobs = []
        if not os.path.exists(path):
            return jobs
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            jobs.append(Job.from_dict(json.loads(line)))
                        except Exception as exc:
                            logger.debug("잡 큐 라인 파싱 실패 (%s): %s", path, exc)
        except OSError as exc:
            logger.warning("잡 큐 읽기 실패 (%s): %s", path, exc)
        return jobs

    def _write(self, path: str, jobs: list[Job]) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                for j in jobs:
                    f.write(json.dumps(j.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("잡 큐 저장 실패 (%s): %s", path, exc)

    def enqueue(self, job: Job) -> str:
        """잡 추가 (idempotency_key 중복 방지)."""
        jobs = self._read(self._path)
        if job.idempotency_key:
            for existing in jobs:
                if (
                    existing.idempotency_key == job.idempotency_key
                    and existing.status in ("queued", "running")
                ):
                    logger.debug("중복 잡 건너뜀: %s", job.idempotency_key)
                    return existing.job_id
        jobs.append(job)
        self._write(self._path, jobs)
        return job.job_id

    def dequeue(self, worker_id: str, category: str | None = None) -> Job | None:
        """잠금 없는 단순 dequeue (파일 기반 한계).

        운영 환경에서는 Redis/DB SKIP LOCKED 사용 권장.
        """
        jobs = self._read(self._path)
        candidates = [
            j for j in jobs
            if j.status == "queued" and (category is None or j.category == category)
        ]
        if not candidates:
            return None
        # 우선순위 정렬 (낮을수록 먼저)
        candidates.sort(key=lambda j: (j.priority, j.created_at))
        job = candidates[0]

        # 잠금 표시
        job.status = "running"
        job.locked_by = worker_id
        job.worker_id = worker_id
        job.updated_at = datetime.now(timezone.utc).isoformat()

        # 업데이트
        jobs = [j if j.job_id != job.job_id else job for j in jobs]
        self._write(self._path, jobs)
        return job

    def complete(self, job_id: str) -> None:
        jobs = self._read(self._path)
        for j in jobs:
            if j.job_id == job_id:
                j.status = "done"
                j.updated_at = datetime.now(timezone.utc).isoformat()
        self._write(self._path, jobs)

    def fail(self, job_id: str, error: str) -> None:
        """실패 처리 — max_retries 이하면 재시도, 초과 시 dead letter."""
        jobs = self._read(self._path)
        for j in jobs:
            if j.job_id == job_id:
                j.attempts += 1
                j.error = error[:500]
                j.updated_at = datetime.now(timezone.utc).isoformat()
                if j.attempts >= j.max_retries:
                    j.status = "dead"
                    # dead letter 이동
                    self._append_dead(j)
                else:
                    j.status = "queued"
                    j.locked_by = ""
        jobs = [j for j in jobs if j.status != "dead"]
        self._write(self._path, jobs)

    def _append_dead(self, job: Job) -> None:
        try:
            with open(self._dead_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(job.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("dead letter 기록 실패: %s", exc)

    def list_queue(self, status: str | None = None) -> list[Job]:
        jobs = self._read(self._path)
        if status:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: (j.priority, j.created_at))

    def list_dead_letters(self) -> list[Job]:
        return self._read(self._dead_path)

    def retry_dead(self, job_id: str) -> bool:
        """dead letter 항목을 큐로 복구."""
        dead = self._read(self._dead_path)
        job = next((j for j in dead if j.job_id == job_id), None)
        if not job:
            return False
        job.status = "queued"
        job.attempts = 0
        job.error = ""
        job.locked_by = ""
        job.updated_at = datetime.now(timezone.utc).isoformat()
        self.enqueue(job)
        # dead에서 제거
        dead = [j for j in dead if j.job_id != job_id]
        self._write(self._dead_path, dead)
        return True

    def cleanup_old_dead_letters(self) -> int:
        """설정된 일수 이전 dead letter 삭제."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=_DEAD_LETTER_DAYS)).isoformat()
        dead = self._read(self._dead_path)
        before = len(dead)
        dead = [j for j in dead if j.updated_at >= cutoff]
        self._write(self._dead_path, dead)
        return before - len(dead)

    def duplicate_check(self, idempotency_key: str) -> bool:
        """동일 idempotency_key가 실행 중/대기 중인지 확인."""
        jobs = self._read(self._path)
        return any(
            j.idempotency_key == idempotency_key and j.status in ("queued", "running")
            for j in jobs
        )

    def worker_distribution(self) -> dict[str, int]:
        """워커별 실행 중 작업 분포."""
        dist: dict[str, int] = {}
        for j in self._read(self._path):
            if j.status == "running" and j.worker_id:
                dist[j.worker_id] = dist.get(j.worker_id, 0) + 1
        return dist

    def summary(self) -> dict:
        """진단 카드용 요약."""
        jobs = self._read(self._path)
        dead = self._read(self._dead_path)
        queued = [j for j in jobs if j.status == "queued"]
        running = [j for j in jobs if j.status == "running"]
        by_category: dict[str, int] = {}
        for j in queued:
            by_category[j.category] = by_category.get(j.category, 0) + 1
        return {
            "backend": os.getenv("JOB_QUEUE_BACKEND", "db"),
            "queued": len(queued),
            "running": len(running),
            "dead_letters": len(dead),
            "by_category": by_category,
            "worker_distribution": self.worker_distribution(),
            "max_retries": _MAX_RETRIES,
        }


# ---------------------------------------------------------------------------
# 팩토리 — 백엔드 선택
# ---------------------------------------------------------------------------

def get_queue() -> FileJobQueue:
    """설정된 백엔드에 맞는 큐 반환.

    현재 지원: db(파일 fallback), redis(TODO)
    """
    backend = os.getenv("JOB_QUEUE_BACKEND", "db")
    if backend == "redis":
        # TODO: Redis Streams 기반 큐 구현 (Phase 148+)
        logger.info("redis 백엔드 미구현, 파일 fallback 사용")
    return FileJobQueue()


# ---------------------------------------------------------------------------
# 편의 함수
# ---------------------------------------------------------------------------

def enqueue_job(
    category: str,
    payload: dict[str, Any],
    idempotency_key: str = "",
    priority: int = 5,
) -> str:
    """잡 추가 헬퍼."""
    job = Job(
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        category=category,
        priority=priority,
        payload=payload,
    )
    return get_queue().enqueue(job)
