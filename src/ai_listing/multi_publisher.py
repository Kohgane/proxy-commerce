"""src/ai_listing/multi_publisher.py — 멀티마켓 동시 등록 (Phase 149).

Phase 143 listing/registration 연동.
각 마켓 어댑터 호출 (mock 우선).
실패 시 부분 성공 허용 + 큐에 재시도.
"""
from __future__ import annotations

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MARKETS = [
    m.strip()
    for m in os.getenv("AI_LISTING_MARKETS_DEFAULT", "coupang,smartstore").split(",")
    if m.strip()
]


@dataclass
class PublishJob:
    """개별 마켓 등록 작업."""

    ai_listing_id: str
    market: str
    product_data: Dict[str, Any]
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "queued"  # queued | publishing | success | failed
    external_product_id: Optional[str] = None
    error_message: Optional[str] = None
    published_at: Optional[str] = None


@dataclass
class PublishResult:
    """멀티마켓 등록 결과."""

    ai_listing_id: str
    jobs: List[PublishJob]

    @property
    def success_count(self) -> int:
        return sum(1 for j in self.jobs if j.status == "success")

    @property
    def failed_count(self) -> int:
        return sum(1 for j in self.jobs if j.status == "failed")

    @property
    def partial_success(self) -> bool:
        return self.success_count > 0 and self.failed_count > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ai_listing_id": self.ai_listing_id,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "partial_success": self.partial_success,
            "markets": [
                {
                    "market": j.market,
                    "status": j.status,
                    "external_product_id": j.external_product_id,
                    "error_message": j.error_message,
                    "published_at": j.published_at,
                }
                for j in self.jobs
            ],
        }


# ── 마켓 어댑터 (mock) ────────────────────────────────────────────────────────

def _mock_publish(job: PublishJob) -> PublishJob:
    """Mock 마켓 등록 (실제 API 미연결 시)."""
    import time
    time.sleep(0.05)  # 네트워크 지연 시뮬레이션
    job.status = "success"
    job.external_product_id = f"MOCK-{job.market.upper()}-{job.job_id[:8]}"
    job.published_at = datetime.now(timezone.utc).isoformat()
    logger.info("[mock] %s 등록 성공: %s", job.market, job.external_product_id)
    return job


def _publish_to_market(job: PublishJob) -> PublishJob:
    """단일 마켓 등록 (어댑터 연동 또는 mock)."""
    job.status = "publishing"
    try:
        # Phase 143 auto_publish 어댑터 연동 시도
        from src.listing.auto_publish import publish_to_channel

        result = publish_to_channel(
            channel=job.market,
            product=job.product_data,
        )
        if result and result.get("ok"):
            job.status = "success"
            job.external_product_id = result.get("product_id", f"EXT-{job.job_id[:8]}")
            job.published_at = datetime.now(timezone.utc).isoformat()
        else:
            job.status = "failed"
            job.error_message = result.get("error", "등록 실패") if result else "응답 없음"
    except (ImportError, AttributeError):
        # Phase 143 어댑터 미연결 → mock
        job = _mock_publish(job)
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)[:200]
        logger.warning("%s 등록 실패: %s", job.market, exc)

    return job


# ── 멀티마켓 동시 등록 ────────────────────────────────────────────────────────

def publish_to_markets(
    ai_listing_id: str,
    product_data: Dict[str, Any],
    markets: Optional[List[str]] = None,
    max_workers: int = 4,
) -> PublishResult:
    """여러 마켓에 동시 등록.

    Args:
        ai_listing_id:  AI 리스팅 ID
        product_data:   등록할 상품 데이터 dict
        markets:        등록 대상 마켓 리스트 (None이면 기본값)
        max_workers:    동시 실행 워커 수

    Returns:
        PublishResult (부분 성공 허용)
    """
    target_markets = markets or _DEFAULT_MARKETS
    jobs = [
        PublishJob(
            ai_listing_id=ai_listing_id,
            market=market,
            product_data=product_data,
        )
        for market in target_markets
    ]

    completed: List[PublishJob] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_publish_to_market, job): job for job in jobs}
        for future in as_completed(futures):
            try:
                result_job = future.result()
                completed.append(result_job)
            except Exception as exc:
                original_job = futures[future]
                original_job.status = "failed"
                original_job.error_message = f"Executor 오류: {exc}"
                completed.append(original_job)

    # 실패한 잡을 큐에 재시도 요청
    failed_markets = [j.market for j in completed if j.status == "failed"]
    if failed_markets:
        _enqueue_retry(ai_listing_id, product_data, failed_markets)

    return PublishResult(ai_listing_id=ai_listing_id, jobs=completed)


def _enqueue_retry(
    ai_listing_id: str,
    product_data: Dict[str, Any],
    markets: List[str],
) -> None:
    """실패한 마켓 등록을 잡 큐에 재시도 요청."""
    try:
        from src.jobs.queue_manager import FileJobQueue

        q = FileJobQueue()
        q.enqueue(
            job_type="ai_listing_retry",
            payload={
                "ai_listing_id": ai_listing_id,
                "markets": markets,
                "product_data": product_data,
            },
            idempotency_key=f"ai_listing_retry_{ai_listing_id}_{'_'.join(sorted(markets))}",
        )
        logger.info("AI listing 재시도 큐 등록: %s → %s", ai_listing_id, markets)
    except Exception as exc:
        logger.debug("재시도 큐 등록 실패 (무시): %s", exc)


def publisher_stats() -> Dict[str, Any]:
    """24h 등록 통계 (mock)."""
    return {
        "attempts_24h": 0,
        "success_24h": 0,
        "failed_24h": 0,
        "by_market": {m: {"success": 0, "failed": 0} for m in _DEFAULT_MARKETS},
    }
