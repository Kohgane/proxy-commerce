"""src/sourcing_discovery/discovery_pipeline.py — 자동 발굴 파이프라인 (Phase 115)."""
from __future__ import annotations

import dataclasses
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    auto_discover_interval_hours: int = 24
    max_opportunities_per_run: int = 50
    min_opportunity_score: float = 60.0
    auto_approve_threshold: float = 85.0
    categories_to_monitor: List[str] = field(
        default_factory=lambda: [
            '전자기기', '뷰티', '건강식품', '반려동물', '스포츠',
        ]
    )
    platforms_to_scan: List[str] = field(
        default_factory=lambda: ['taobao', '1688', 'alibaba', 'amazon']
    )


@dataclass
class PipelineRun:
    run_id: str
    started_at: datetime
    completed_at: datetime
    opportunities_found: int
    opportunities_approved: int
    opportunities_rejected: int
    duration_seconds: float
    status: str


class DiscoveryPipeline:
    """소싱 발굴 자동 파이프라인."""

    def __init__(self) -> None:
        self._runs: List[PipelineRun] = []
        self._config: PipelineConfig = PipelineConfig()

    def run_pipeline(self) -> PipelineRun:
        """전체 파이프라인 실행."""
        from src.sourcing_discovery.trend_analyzer import TrendAnalyzer
        from src.sourcing_discovery.market_gap_analyzer import MarketGapAnalyzer
        from src.sourcing_discovery.opportunity_finder import SourcingOpportunityFinder
        from src.sourcing_discovery.profitability_predictor import ProfitabilityPredictor

        run_id = str(uuid.uuid4())[:12]
        started_at = datetime.now()
        start_time = time.monotonic()

        try:
            trend_analyzer = TrendAnalyzer()
            gap_analyzer = MarketGapAnalyzer()
            opportunity_finder = SourcingOpportunityFinder()
            predictor = ProfitabilityPredictor()

            # 트렌드 기반 기회 발굴
            rising = trend_analyzer.get_rising_trends(limit=10)
            opportunities = []
            for trend in rising[:5]:
                opps = opportunity_finder.discover_opportunities(
                    method='trend_based',
                    category=trend.category,
                    limit=5,
                )
                opportunities.extend(opps)

            # 마켓 갭 기반 기회 발굴
            top_gaps = gap_analyzer.get_top_gaps(limit=5)
            for gap in top_gaps[:3]:
                opps = opportunity_finder.discover_opportunities(
                    method='competitor_gap',
                    category=gap.category,
                    limit=3,
                )
                opportunities.extend(opps)

            # 수익성 필터링 및 자동 승인
            opportunities = opportunities[:self._config.max_opportunities_per_run]
            approved_count = 0
            rejected_count = 0

            for opp in opportunities:
                if opp.opportunity_score < self._config.min_opportunity_score:
                    opportunity_finder.reject_opportunity(opp.opportunity_id, '점수 미달')
                    rejected_count += 1
                elif opp.opportunity_score >= self._config.auto_approve_threshold:
                    opportunity_finder.approve_opportunity(opp.opportunity_id)
                    approved_count += 1

            completed_at = datetime.now()
            duration = time.monotonic() - start_time

            run = PipelineRun(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                opportunities_found=len(opportunities),
                opportunities_approved=approved_count,
                opportunities_rejected=rejected_count,
                duration_seconds=round(duration, 3),
                status='completed',
            )
        except Exception as exc:
            logger.error("파이프라인 실행 오류: %s", exc)
            completed_at = datetime.now()
            duration = time.monotonic() - start_time
            run = PipelineRun(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                opportunities_found=0,
                opportunities_approved=0,
                opportunities_rejected=0,
                duration_seconds=round(duration, 3),
                status='failed',
            )

        self._runs.append(run)
        return run

    def get_pipeline_history(self, limit: int = 10) -> List[PipelineRun]:
        """파이프라인 실행 이력 조회."""
        return self._runs[-limit:]

    def get_pipeline_config(self) -> PipelineConfig:
        """파이프라인 설정 조회."""
        return self._config

    def update_pipeline_config(self, updates: Dict[str, Any]) -> PipelineConfig:
        """파이프라인 설정 업데이트."""
        current = dataclasses.asdict(self._config)
        current.update({k: v for k, v in updates.items() if k in current})
        self._config = PipelineConfig(**current)
        return self._config
