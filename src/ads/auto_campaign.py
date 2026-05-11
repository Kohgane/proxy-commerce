"""src/ads/auto_campaign.py — 광고 자동 운영 (Phase 144).

매출 잠재력 높은 SKU 자동 추출 → 마켓별 캠페인 자동 생성 →
키워드 입찰가 자동 조정 (목표 ROAS 기준) + 일일 예산 가드.

환경변수:
  ADS_AUTO_CAMPAIGN_ENABLED=1          자동 운영 활성화 (기본: 0)
  ADS_AUTO_CAMPAIGN_AUTO_LAUNCH=0      캠페인 자동 launch (기본: 0, 수동 승인)
  ADS_DAILY_BUDGET_KRW=20000           일일 예산 (원)
  ADS_TARGET_ROAS=3.0                  목표 ROAS
  ADS_BID_ADJUST_MAX_PCT=20            최대 입찰가 조정 비율 (%)
  KEYWORD_OPT_PROVIDER=mock            mock | naver_searchad | coupang_ads
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 환경변수
# ---------------------------------------------------------------------------

_ENABLED = os.getenv("ADS_AUTO_CAMPAIGN_ENABLED", "0") == "1"
_AUTO_LAUNCH = os.getenv("ADS_AUTO_CAMPAIGN_AUTO_LAUNCH", "0") == "1"
_DAILY_BUDGET_KRW = int(os.getenv("ADS_DAILY_BUDGET_KRW", "20000"))
_TARGET_ROAS = float(os.getenv("ADS_TARGET_ROAS", "3.0"))
_BID_ADJUST_MAX_PCT = float(os.getenv("ADS_BID_ADJUST_MAX_PCT", "20"))
_PROVIDER = os.getenv("KEYWORD_OPT_PROVIDER", "mock")

# ROAS 추정 공식 상수
_SEARCH_SCALE = 10000.0          # 검색량 정규화 기준 (10,000회 = 1.0)
_SEARCH_FACTOR_CAP = 5.0         # 검색량 가중치 최대값
_MARGIN_TO_ROAS_DIVISOR = 10.0   # 마진율(%) → ROAS 스케일 변환 계수

# 예산 분배 상수
_CAMPAIGNS_PER_BUDGET = 4        # 일일 예산을 몇 개 캠페인으로 분할
_MAX_CAMPAIGN_BUDGET_KRW = 10000 # 캠페인당 최대 일일 예산 (원)

# ---------------------------------------------------------------------------
# 도메인 모델
# ---------------------------------------------------------------------------


@dataclass
class CampaignRec:
    """캠페인 추천 항목."""
    rec_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    sku: str = ""
    product_name: str = ""
    channel: str = "coupang"           # coupang | naver | internal
    keywords: List[str] = field(default_factory=list)
    estimated_roas: float = 0.0
    estimated_revenue_krw: float = 0.0
    daily_budget_krw: int = 0
    status: str = "pending"            # pending | approved | launched | paused
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rec_id": self.rec_id,
            "sku": self.sku,
            "product_name": self.product_name,
            "channel": self.channel,
            "keywords": self.keywords,
            "estimated_roas": self.estimated_roas,
            "estimated_revenue_krw": self.estimated_revenue_krw,
            "daily_budget_krw": self.daily_budget_krw,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class PerformanceData:
    """캠페인 성과 데이터."""
    campaign_id: str
    impressions: int = 0
    clicks: int = 0
    cost_krw: float = 0.0
    revenue_krw: float = 0.0
    conversions: int = 0

    @property
    def roas(self) -> float:
        return self.revenue_krw / self.cost_krw if self.cost_krw > 0 else 0.0

    @property
    def cpc_krw(self) -> float:
        return self.cost_krw / self.clicks if self.clicks > 0 else 0.0

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "impressions": self.impressions,
            "clicks": self.clicks,
            "cost_krw": self.cost_krw,
            "revenue_krw": self.revenue_krw,
            "conversions": self.conversions,
            "roas": round(self.roas, 2),
            "cpc_krw": round(self.cpc_krw, 0),
            "ctr": round(self.ctr * 100, 2),
        }


# ---------------------------------------------------------------------------
# 인메모리 저장소 (싱글톤)
# ---------------------------------------------------------------------------

_campaign_recs: Dict[str, CampaignRec] = {}
_active_campaigns: Dict[str, Dict[str, Any]] = {}


def _get_store() -> tuple[Dict[str, CampaignRec], Dict[str, Dict[str, Any]]]:
    return _campaign_recs, _active_campaigns


# ---------------------------------------------------------------------------
# 핵심 함수
# ---------------------------------------------------------------------------


def recommend_campaigns(roas_target: float = _TARGET_ROAS) -> List[CampaignRec]:
    """매출/마진 잠재력 + 검색량 기반 캠페인 추천.

    실제 운영에서는 sourcing/listing 데이터와 검색량 API를 연동.
    현재는 mock 데이터 기반 추천 반환.
    """
    recs_store, _ = _get_store()

    # mock SKU 목록 (실제 운영: src.listing.auto_publish에서 조회)
    mock_skus = [
        {"sku": "SKU-001", "name": "유니클로 플리스 자켓 L", "margin_pct": 28.0, "monthly_search": 12000},
        {"sku": "SKU-002", "name": "나이키 에어포스 240", "margin_pct": 22.0, "monthly_search": 35000},
        {"sku": "SKU-003", "name": "무인양품 에코백 M", "margin_pct": 35.0, "monthly_search": 8500},
        {"sku": "SKU-004", "name": "아디다스 트레이닝 팬츠", "margin_pct": 19.0, "monthly_search": 27000},
    ]

    results: List[CampaignRec] = []
    for item in mock_skus:
        # 마진 + 검색량으로 잠재 ROAS 추정
        # search_factor: 검색량을 _SEARCH_SCALE 기준으로 정규화, 최대 _SEARCH_FACTOR_CAP
        # estimated_roas: 마진율을 _MARGIN_TO_ROAS_DIVISOR로 스케일하여 검색량 가중치 적용
        search_factor = min(item["monthly_search"] / _SEARCH_SCALE, _SEARCH_FACTOR_CAP)
        estimated_roas = (item["margin_pct"] / _MARGIN_TO_ROAS_DIVISOR) * search_factor
        if estimated_roas < roas_target * 0.5:
            continue  # 기대 ROAS 너무 낮으면 제외

        for channel in ["coupang", "naver"]:
            rec = CampaignRec(
                sku=item["sku"],
                product_name=item["name"],
                channel=channel,
                keywords=[item["name"].split()[0], item["name"]],
                estimated_roas=round(estimated_roas, 2),
                estimated_revenue_krw=round(item["monthly_search"] * 1.2),
                daily_budget_krw=min(_DAILY_BUDGET_KRW // _CAMPAIGNS_PER_BUDGET, _MAX_CAMPAIGN_BUDGET_KRW),
                status="pending",
            )
            recs_store[rec.rec_id] = rec
            results.append(rec)

    return results


def create_campaign(rec: CampaignRec, channel: str) -> str:
    """채널별 광고 API 호출 (또는 mock).

    Returns:
        campaign_id: 생성된 캠페인 ID
    """
    _, active = _get_store()

    if not _ENABLED:
        logger.info("ADS_AUTO_CAMPAIGN_ENABLED=0 — mock 캠페인 생성: %s/%s", channel, rec.sku)

    if not _AUTO_LAUNCH:
        logger.info("ADS_AUTO_CAMPAIGN_AUTO_LAUNCH=0 — 수동 승인 대기: %s", rec.rec_id)
        rec.status = "pending"
        return f"PENDING-{rec.rec_id}"

    campaign_id = f"{channel.upper()}-{rec.sku}-{str(uuid.uuid4())[:6]}"

    # 채널별 API mock
    if _PROVIDER == "mock" or channel in ("coupang", "naver"):
        logger.info("mock 캠페인 생성: channel=%s sku=%s id=%s", channel, rec.sku, campaign_id)
        active[campaign_id] = {
            "campaign_id": campaign_id,
            "rec_id": rec.rec_id,
            "channel": channel,
            "sku": rec.sku,
            "product_name": rec.product_name,
            "keywords": rec.keywords,
            "daily_budget_krw": rec.daily_budget_krw,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        rec.status = "launched"

    return campaign_id


def adjust_bids(campaign_id: str, performance: PerformanceData) -> Dict[str, Any]:
    """ROAS 기반 입찰가 조정.

    ROAS 미달 → 입찰가 인하, 초과 → 인상 (ADS_BID_ADJUST_MAX_PCT 한도 내).

    Returns:
        {action, old_bid, new_bid, reason, roas, target_roas}
    """
    _, active = _get_store()
    campaign = active.get(campaign_id)
    if campaign is None:
        return {"action": "no_op", "reason": "캠페인을 찾을 수 없습니다"}

    current_bid = campaign.get("current_bid_krw", 500)
    roas = performance.roas
    max_adjust_pct = _BID_ADJUST_MAX_PCT / 100.0

    if roas == 0:
        # 노출/클릭 없음 — 일시정지 또는 입찰가 인하
        new_bid = max(int(current_bid * (1 - max_adjust_pct)), 50)
        action = "decrease"
        reason = "ROAS=0 (노출 없음) → 입찰가 최대 인하"
    elif roas < _TARGET_ROAS * 0.8:
        # ROAS 크게 미달 → 최대 인하
        decrease_pct = min((1 - roas / _TARGET_ROAS) * 0.5, max_adjust_pct)
        new_bid = max(int(current_bid * (1 - decrease_pct)), 50)
        action = "decrease"
        reason = f"ROAS {roas:.2f} < 목표 {_TARGET_ROAS} → 입찰가 인하 {decrease_pct*100:.0f}%"
    elif roas < _TARGET_ROAS:
        # ROAS 소폭 미달 → 소폭 인하
        decrease_pct = (1 - roas / _TARGET_ROAS) * 0.3
        new_bid = max(int(current_bid * (1 - decrease_pct)), 50)
        action = "decrease"
        reason = f"ROAS {roas:.2f} 소폭 미달 → 소폭 인하"
    elif roas > _TARGET_ROAS * 1.5:
        # ROAS 크게 초과 → 입찰가 인상 (한도 내)
        increase_pct = min((roas / _TARGET_ROAS - 1) * 0.3, max_adjust_pct)
        new_bid = int(current_bid * (1 + increase_pct))
        action = "increase"
        reason = f"ROAS {roas:.2f} 초과 → 입찰가 인상 {increase_pct*100:.0f}%"
    else:
        # ROAS 적절 — 유지
        new_bid = current_bid
        action = "no_op"
        reason = f"ROAS {roas:.2f} 목표 근접 → 유지"

    campaign["current_bid_krw"] = new_bid
    logger.info("입찰가 조정: %s action=%s %d→%d", campaign_id, action, current_bid, new_bid)

    return {
        "campaign_id": campaign_id,
        "action": action,
        "old_bid": current_bid,
        "new_bid": new_bid,
        "reason": reason,
        "roas": round(roas, 2),
        "target_roas": _TARGET_ROAS,
    }


def pause_low_performers(min_roas: float = 0.5) -> List[str]:
    """ROAS가 min_roas 미만인 캠페인 일시정지."""
    _, active = _get_store()
    paused = []
    for cid, c in active.items():
        roas = c.get("roas", 0.0)
        if roas < min_roas and c.get("status") == "active":
            c["status"] = "paused"
            paused.append(cid)
            logger.info("성과 부진 캠페인 일시정지: %s (ROAS=%s)", cid, roas)
    return paused


def ads_stats() -> Dict[str, Any]:
    """광고 자동 운영 현황 통계 (admin diagnostics용)."""
    recs_store, active = _get_store()

    by_channel: Dict[str, int] = {}
    total_cost = 0.0
    total_revenue = 0.0
    for c in active.values():
        ch = c.get("channel", "unknown")
        by_channel[ch] = by_channel.get(ch, 0) + 1
        total_cost += c.get("cost_krw", 0.0)
        total_revenue += c.get("revenue_krw", 0.0)

    roas = total_revenue / total_cost if total_cost > 0 else 0.0
    pending_recs = sum(1 for r in recs_store.values() if r.status == "pending")

    return {
        "enabled": _ENABLED,
        "auto_launch": _AUTO_LAUNCH,
        "daily_budget_krw": _DAILY_BUDGET_KRW,
        "target_roas": _TARGET_ROAS,
        "active_campaigns": len(active),
        "by_channel": by_channel,
        "cost_krw_24h": round(total_cost),
        "revenue_krw_24h": round(total_revenue),
        "roas_24h": round(roas, 2),
        "pending_recs": pending_recs,
    }
