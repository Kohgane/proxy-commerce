"""src/ads/keyword_optimizer.py — 키워드 입찰 최적화 (Phase 144).

키워드별 검색량/경쟁도/CPC 추정 → 상품-키워드 매칭 점수 →
입찰가 추천 (목표 CPA 기반) + 네거티브 키워드 자동 제안 (ROAS 0인 검색어).

환경변수:
  KEYWORD_OPT_PROVIDER=mock   mock | naver_searchad | coupang_ads
  ADS_TARGET_ROAS=3.0
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TARGET_ROAS = float(os.getenv("ADS_TARGET_ROAS", "3.0"))
_PROVIDER = os.getenv("KEYWORD_OPT_PROVIDER", "mock")

# ---------------------------------------------------------------------------
# 도메인 모델
# ---------------------------------------------------------------------------


@dataclass
class KeywordMetrics:
    """키워드 성과 지표."""
    keyword: str
    monthly_search: int = 0
    competition: float = 0.0     # 0.0(낮음) ~ 1.0(높음)
    avg_cpc_krw: float = 0.0
    impressions: int = 0
    clicks: int = 0
    cost_krw: float = 0.0
    revenue_krw: float = 0.0
    conversions: int = 0
    match_score: float = 0.0     # 상품-키워드 매칭 점수 (0~1)

    @property
    def roas(self) -> float:
        return self.revenue_krw / self.cost_krw if self.cost_krw > 0 else 0.0

    @property
    def cpa_krw(self) -> float:
        return self.cost_krw / self.conversions if self.conversions > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "monthly_search": self.monthly_search,
            "competition": round(self.competition, 2),
            "avg_cpc_krw": round(self.avg_cpc_krw),
            "impressions": self.impressions,
            "clicks": self.clicks,
            "cost_krw": round(self.cost_krw),
            "revenue_krw": round(self.revenue_krw),
            "conversions": self.conversions,
            "roas": round(self.roas, 2),
            "cpa_krw": round(self.cpa_krw),
            "match_score": round(self.match_score, 2),
        }


# ---------------------------------------------------------------------------
# 검색량/경쟁도 추정 (mock)
# ---------------------------------------------------------------------------

# mock 키워드 데이터베이스
_MOCK_KEYWORD_DB: Dict[str, Dict[str, Any]] = {
    "유니클로": {"monthly_search": 85000, "competition": 0.7, "avg_cpc_krw": 320},
    "나이키": {"monthly_search": 120000, "competition": 0.85, "avg_cpc_krw": 450},
    "무인양품": {"monthly_search": 42000, "competition": 0.55, "avg_cpc_krw": 280},
    "아디다스": {"monthly_search": 95000, "competition": 0.80, "avg_cpc_krw": 390},
    "에어포스": {"monthly_search": 35000, "competition": 0.75, "avg_cpc_krw": 520},
    "플리스 자켓": {"monthly_search": 18000, "competition": 0.45, "avg_cpc_krw": 210},
    "에코백": {"monthly_search": 27000, "competition": 0.40, "avg_cpc_krw": 180},
    "트레이닝 팬츠": {"monthly_search": 32000, "competition": 0.60, "avg_cpc_krw": 250},
    "일본직구": {"monthly_search": 65000, "competition": 0.65, "avg_cpc_krw": 300},
    "해외직구": {"monthly_search": 180000, "competition": 0.90, "avg_cpc_krw": 550},
}


def get_keyword_metrics(keywords: List[str]) -> List[KeywordMetrics]:
    """키워드별 검색량/경쟁도/CPC 추정.

    KEYWORD_OPT_PROVIDER=mock 시 내부 DB 기반 mock 반환.
    실제 운영: 네이버 검색광고 API / 쿠팡 ADS API 호출.
    """
    results = []
    for kw in keywords:
        # mock 데이터 조회 (부분 매칭)
        db_entry = None
        for db_kw, data in _MOCK_KEYWORD_DB.items():
            if db_kw in kw or kw in db_kw:
                db_entry = data
                break

        if db_entry is None:
            # 알 수 없는 키워드 — 기본값
            db_entry = {"monthly_search": 5000, "competition": 0.5, "avg_cpc_krw": 200}

        metrics = KeywordMetrics(
            keyword=kw,
            monthly_search=db_entry["monthly_search"],
            competition=db_entry["competition"],
            avg_cpc_krw=db_entry["avg_cpc_krw"],
        )
        results.append(metrics)
    return results


def match_keywords_to_product(product_name: str, candidate_keywords: List[str]) -> List[KeywordMetrics]:
    """상품-키워드 매칭 점수 계산 (임베딩 + 카테고리 기반).

    현재 mock: 단순 문자열 오버랩 점수 사용.
    실제 운영: OpenAI embedding 유사도 + 카테고리 태그 매칭.
    """
    metrics_list = get_keyword_metrics(candidate_keywords)
    product_tokens = set(product_name.lower().split())

    for m in metrics_list:
        kw_tokens = set(m.keyword.lower().split())
        overlap = len(product_tokens & kw_tokens)
        union = len(product_tokens | kw_tokens)
        jaccard = overlap / union if union > 0 else 0.0
        # 검색량 보정: 높은 검색량 키워드에 가산점
        search_bonus = min(m.monthly_search / 100000, 0.3)
        m.match_score = min(jaccard + search_bonus, 1.0)

    # 매칭 점수 내림차순 정렬
    metrics_list.sort(key=lambda x: x.match_score, reverse=True)
    return metrics_list


def recommend_bids(metrics: List[KeywordMetrics], target_cpa_krw: float = 5000.0) -> List[Dict[str, Any]]:
    """목표 CPA 기반 입찰가 추천.

    recommended_bid = target_cpa × conversion_rate (추정)
    단, avg_cpc 기준 ±30% 범위로 클리핑.
    """
    results = []
    for m in metrics:
        # 전환율 추정 (검색량/경쟁도 기반 mock)
        est_cvr = max(0.005, 0.03 * (1 - m.competition))
        recommended_bid = int(target_cpa_krw * est_cvr)
        # avg_cpc 기준으로 ±30% 클리핑
        lower = int(m.avg_cpc_krw * 0.7)
        upper = int(m.avg_cpc_krw * 1.3)
        recommended_bid = max(lower, min(recommended_bid, upper))
        recommended_bid = max(recommended_bid, 50)  # 최소 50원

        results.append({
            "keyword": m.keyword,
            "monthly_search": m.monthly_search,
            "competition": m.competition,
            "avg_cpc_krw": m.avg_cpc_krw,
            "recommended_bid_krw": recommended_bid,
            "match_score": m.match_score,
        })
    return results


def suggest_negative_keywords(performance_data: List[Dict[str, Any]]) -> List[str]:
    """네거티브 키워드 자동 제안.

    ROAS=0 (비용 발생, 매출 없음) 이거나 전환율 극히 낮은 검색어를 제안.

    Args:
        performance_data: [{"keyword": str, "cost_krw": float, "revenue_krw": float, ...}]
    Returns:
        네거티브 키워드 목록
    """
    negatives = []
    for item in performance_data:
        cost = item.get("cost_krw", 0.0)
        revenue = item.get("revenue_krw", 0.0)
        keyword = item.get("keyword", "")

        if not keyword:
            continue

        # 비용 발생했는데 매출 0 → 네거티브 후보
        if cost > 0 and revenue == 0:
            negatives.append(keyword)
        # ROAS < 0.3 (목표의 10% 이하) → 네거티브 후보
        elif cost > 0 and (revenue / cost) < (_TARGET_ROAS * 0.1):
            negatives.append(keyword)

    return list(set(negatives))


def keyword_optimizer_stats() -> Dict[str, Any]:
    """키워드 최적화 현황 (admin diagnostics용)."""
    return {
        "provider": _PROVIDER,
        "target_roas": _TARGET_ROAS,
        "db_keywords": len(_MOCK_KEYWORD_DB),
    }
