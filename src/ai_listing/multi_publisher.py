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
    product_url: Optional[str] = None        # 마켓 실제 상품 페이지 URL
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
                    "product_url": j.product_url,
                    "error_message": j.error_message,
                    "published_at": j.published_at,
                }
                for j in self.jobs
            ],
        }


# ── 실 업로더 연동 (수동 업로드와 동일한 UploadDispatcher 경로) ────────────────

# AI 페이지 마켓 코드 → UploadDispatcher 마켓 코드
_MARKET_CODE_MAP = {
    "coupang": "coupang",
    "smartstore": "smartstore",
    "11st": "elevenst",
    "elevenst": "elevenst",
    "woocommerce": "woocommerce",
    "kohganemultishop": "woocommerce",
    "shopify": "shopify",
}


def _build_dispatch_product(job: PublishJob) -> Dict[str, Any]:
    """AI 분석/마켓별 데이터 → UploadDispatcher product_data 형식.

    market_data[market] = {title, description, tags, category_code, suggested_price_krw}
    analysis = 공통 분석(이미지/원문/브랜드 등).
    """
    pd = job.product_data or {}
    analysis = pd.get("analysis") or {}
    md = (pd.get("market_data") or {}).get(job.market) or {}

    images = (
        analysis.get("images")
        or analysis.get("image_urls")
        or analysis.get("processed_image_urls")
        or []
    )
    price_krw = md.get("suggested_price_krw") or analysis.get("suggested_price_krw") or 0
    title = md.get("title") or analysis.get("title_translated") or analysis.get("title") or ""
    return {
        "sku": pd.get("listing_id") or job.ai_listing_id or "",
        "title": title,
        "title_ko": title,
        "sell_price_krw": price_krw,
        "price_krw": price_krw,
        "currency": "KRW",
        "category_code": md.get("category_code") or analysis.get("category_code") or "",
        "description": md.get("description") or analysis.get("description") or "",
        "description_html": md.get("description") or analysis.get("description") or "",
        "images": images if isinstance(images, list) else [],
        "options": analysis.get("options") or {},
        "keywords": md.get("tags") or analysis.get("keywords") or [],
        "brand": analysis.get("brand") or "",
        "url": analysis.get("source_url") or analysis.get("url") or "",
    }


def _publish_to_market(job: PublishJob) -> PublishJob:
    """단일 마켓 실 등록 — 수동 업로드와 동일한 UploadDispatcher(실 업로더) 사용.

    자격증명 미설정·API 실패 시 가짜 성공이 아니라 정직하게 실패/큐로 기록한다.
    지원하지 않는 마켓(쇼피/아마존 등 미연동)은 실패 + 사유.
    """
    job.status = "publishing"
    mapped = _MARKET_CODE_MAP.get(job.market)
    if not mapped:
        job.status = "failed"
        job.error_message = f"{job.market}는 자동발행 미연동입니다(마켓 승인·연동 필요)."
        return job
    try:
        from src.seller_console.upload_dispatcher import UploadDispatcher

        product_data = _build_dispatch_product(job)
        result = UploadDispatcher().dispatch(product_data, [mapped])
        r = result.results[0] if result.results else None
        if r is None:
            job.status = "failed"
            job.error_message = "업로드 결과가 비어 있습니다."
        elif r.success:
            job.status = "success"
            job.external_product_id = r.external_product_id or f"EXT-{job.job_id[:8]}"
            job.product_url = r.external_url
            job.published_at = datetime.now(timezone.utc).isoformat()
        elif r.queued:
            job.status = "failed"  # 실제 등록은 아직 안 됨 → 재시도 큐로
            job.error_message = (r.message or "큐 적재됨") + (f" ({r.hint})" if r.hint else "")
        else:
            job.status = "failed"
            job.error_message = (r.message or "등록 실패") + (f" ({r.hint})" if r.hint else "")
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
