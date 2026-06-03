"""src/ads/keyword_optimizer.py — 키워드 입찰 최적화 (Phase 144+160).

키워드별 검색량/경쟁도/CPC 추정 → 상품-키워드 매칭 점수 →
입찰가 추천 (목표 CPA 기반) + 네거티브 키워드 자동 제안 (ROAS 0인 검색어).

Phase 160 추가:
  get_keyword_trends() — 기간별(실시간/일/주/월/년) 검색량 시계열
  get_rising_keywords() — 급상승 키워드 추출
  get_related_keywords() — 연관/확장/롱테일 키워드 추천

환경변수:
  KEYWORD_OPT_PROVIDER=mock   mock | naver_searchad | coupang_ads
  ADS_TARGET_ROAS=3.0
  NAVER_SEARCHAD_API_KEY      네이버 검색광고 API 키 (PROVIDER=naver_searchad 시)
  NAVER_SEARCHAD_API_SECRET   네이버 검색광고 API 시크릿
"""
from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_TARGET_ROAS = float(os.getenv("ADS_TARGET_ROAS", "3.0"))
_PROVIDER = os.getenv("KEYWORD_OPT_PROVIDER", "mock")

# 네거티브 키워드 기준: ROAS가 목표의 _NEGATIVE_KW_ROAS_RATIO 이하이면 네거티브 후보
_NEGATIVE_KW_ROAS_RATIO = 0.1  # 목표 ROAS의 10% 이하 → 네거티브 제안

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

# 기간별 포인트 수 (Phase 160)
_PERIOD_POINTS: Dict[str, int] = {
    "realtime": 24,   # 최근 24시간 (시간별)
    "day": 30,        # 최근 30일 (일별)
    "week": 12,       # 최근 12주 (주별)
    "month": 12,      # 최근 12개월 (월별)
    "year": 5,        # 최근 5년 (연별)
}

# 급상승 키워드 mock (Phase 160)
_RISING_KEYWORDS: List[Dict[str, Any]] = [
    {"keyword": "플리스 집업", "change_pct": 142, "monthly_search": 22000, "competition": 0.42},
    {"keyword": "고프코어 패션", "change_pct": 98, "monthly_search": 15000, "competition": 0.38},
    {"keyword": "일본 브랜드 직구", "change_pct": 87, "monthly_search": 31000, "competition": 0.55},
    {"keyword": "오버핏 코트", "change_pct": 76, "monthly_search": 28000, "competition": 0.60},
    {"keyword": "캐주얼 슬랙스", "change_pct": 65, "monthly_search": 19000, "competition": 0.48},
    {"keyword": "무인양품 가방", "change_pct": 54, "monthly_search": 12000, "competition": 0.35},
    {"keyword": "아웃도어 러닝화", "change_pct": 48, "monthly_search": 24000, "competition": 0.62},
    {"keyword": "데일리 크로스백", "change_pct": 41, "monthly_search": 17000, "competition": 0.45},
]

# 연관 키워드 확장 패턴 (Phase 160)
_RELATED_EXPANSIONS: Dict[str, List[str]] = {
    "유니클로": ["유니클로 히트텍", "유니클로 플리스", "유니클로 세일", "유니클로 울트라라이트"],
    "나이키": ["나이키 에어맥스", "나이키 덩크", "나이키 운동화", "나이키 조거 팬츠"],
    "직구": ["일본직구 추천", "직구 사이트", "해외직구 관세", "직구 배대지"],
    "패션": ["여성 패션", "남성 패션", "캐주얼 패션", "스트리트 패션"],
    "가방": ["크로스백", "백팩", "토트백", "미니백"],
}


def _make_trend_series(base_value: int, num_points: int, trend_factor: float = 0.0) -> List[int]:
    """기간별 mock 시계열 데이터 생성.

    Args:
        base_value: 기준 검색량
        num_points: 포인트 수
        trend_factor: 증감 추세 (-0.3 ~ +0.3)
    Returns:
        검색량 리스트 (오래된 것 → 최근 순)
    """
    rng = random.Random(abs(hash(str(base_value))) % (2**31))
    result = []
    for i in range(num_points):
        noise = rng.uniform(-0.12, 0.12)
        trend = trend_factor * (i / max(num_points - 1, 1))
        val = int(base_value * (1 + trend + noise))
        result.append(max(val, 0))
    return result


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
        # ROAS < 목표의 _NEGATIVE_KW_ROAS_RATIO 이하 → 네거티브 후보
        elif cost > 0 and (revenue / cost) < (_TARGET_ROAS * _NEGATIVE_KW_ROAS_RATIO):
            negatives.append(keyword)

    return list(set(negatives))


def keyword_optimizer_stats() -> Dict[str, Any]:
    """키워드 최적화 현황 (admin diagnostics용)."""
    return {
        "provider": _PROVIDER,
        "target_roas": _TARGET_ROAS,
        "db_keywords": len(_MOCK_KEYWORD_DB),
    }


# ---------------------------------------------------------------------------
# Phase 160 — 기간별 트렌드 / 급상승 / 연관 키워드
# ---------------------------------------------------------------------------


def get_keyword_trends(
    keywords: List[str],
    period: str = "month",
) -> List[Dict[str, Any]]:
    """기간별 키워드 검색량 시계열 반환.

    Args:
        keywords: 조회할 키워드 목록
        period: "realtime" | "day" | "week" | "month" | "year"

    Returns:
        [{
            "keyword": str,
            "monthly_search": int,
            "competition": float,
            "avg_cpc_krw": float,
            "product_count": int,
            "trend_pct": float,      # 전기간 대비 % (양수=증가)
            "series": List[int],     # 기간별 검색량 시계열
            "period": str,
        }]
    """
    if period not in _PERIOD_POINTS:
        period = "month"

    provider = os.getenv("KEYWORD_OPT_PROVIDER", "mock")
    if provider == "naver_searchad":
        try:
            return _get_naver_keyword_trends(keywords, period)
        except Exception as exc:
            logger.warning("네이버 검색광고 트렌드 조회 실패 → mock 사용: %s", exc)

    return _get_mock_keyword_trends(keywords, period)


def _get_mock_keyword_trends(keywords: List[str], period: str) -> List[Dict[str, Any]]:
    """mock 기반 기간별 트렌드 데이터."""
    num_points = _PERIOD_POINTS.get(period, 12)
    results = []
    for kw in keywords:
        db_entry = None
        for db_kw, data in _MOCK_KEYWORD_DB.items():
            if db_kw in kw or kw in db_kw:
                db_entry = data
                break
        if db_entry is None:
            db_entry = {"monthly_search": 5000, "competition": 0.5, "avg_cpc_krw": 200}

        base = db_entry["monthly_search"]
        # 기간별 단위 환산: realtime은 시간, day는 일
        if period == "realtime":
            base_unit = max(base // 720, 1)  # 월 → 시간 환산(~720시간)
        elif period == "day":
            base_unit = max(base // 30, 1)
        elif period == "week":
            base_unit = max(base // 4, 1)
        elif period == "year":
            base_unit = base * 12
        else:
            base_unit = base

        # 검색어에 따라 랜덤 트렌드 방향 결정
        rng = random.Random(abs(hash(kw)) % (2**31))
        trend_factor = rng.uniform(-0.25, 0.40)
        series = _make_trend_series(base_unit, num_points, trend_factor)
        # 전기간 대비 % (최근 절반 평균 vs 이전 절반 평균)
        half = max(len(series) // 2, 1)
        prev_avg = sum(series[:half]) / half if half else 1
        curr_avg = sum(series[half:]) / half if half else 1
        trend_pct = round(((curr_avg - prev_avg) / prev_avg * 100) if prev_avg > 0 else 0, 1)

        results.append({
            "keyword": kw,
            "monthly_search": db_entry["monthly_search"],
            "competition": round(db_entry["competition"], 2),
            "avg_cpc_krw": int(db_entry["avg_cpc_krw"]),
            "product_count": int(db_entry["monthly_search"] * db_entry["competition"] * 0.8),
            "trend_pct": trend_pct,
            "series": series,
            "period": period,
        })
    return results


def _get_naver_keyword_trends(keywords: List[str], period: str) -> List[Dict[str, Any]]:
    """네이버 검색광고 API를 통한 키워드 트렌드 조회.

    NAVER_SEARCHAD_API_KEY / NAVER_SEARCHAD_API_SECRET 환경변수 필요.
    미지원 기간(realtime)은 mock fallback.
    """
    import hashlib
    import hmac
    import time as _time
    import urllib.request

    api_key = os.getenv("NAVER_SEARCHAD_API_KEY", "")
    api_secret = os.getenv("NAVER_SEARCHAD_API_SECRET", "")
    if not api_key or not api_secret:
        raise ValueError("NAVER_SEARCHAD_API_KEY/SECRET 미설정")

    # 네이버 검색광고는 실시간/일 단위 지원 안 함 → mock fallback
    if period in ("realtime",):
        return _get_mock_keyword_trends(keywords, period)

    timestamp = str(int(_time.time() * 1000))
    signature_message = f"{timestamp}.GET./keywordstool"
    sig = hmac.new(
        api_secret.encode("utf-8"),
        signature_message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    results = []
    for kw in keywords:
        try:
            import urllib.parse
            qs = urllib.parse.urlencode({"hintKeywords": kw, "showDetail": 1})
            req = urllib.request.Request(
                f"https://api.naver.com/keywordstool?{qs}",
                headers={
                    "X-Timestamp": timestamp,
                    "X-API-KEY": api_key,
                    "X-Customer": os.getenv("NAVER_SEARCHAD_CUSTOMER_ID", ""),
                    "X-Signature": sig,
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            kw_list = data.get("keywordList", [])
            entry = next((k for k in kw_list if k.get("relKeyword") == kw), kw_list[0] if kw_list else None)
            if entry:
                pc = int(entry.get("monthlyPcQcCnt", 0) or 0)
                mo = int(entry.get("monthlyMobileQcCnt", 0) or 0)
                monthly_search = pc + mo
                competition = float(entry.get("compIdx", 0.5) or 0.5)
                avg_cpc = int(entry.get("plAvgDepth", 200) or 200)
            else:
                raise ValueError("API 결과 없음")
        except Exception as exc:
            logger.warning("네이버 키워드 '%s' 조회 실패 → mock: %s", kw, exc)
            mock = _get_mock_keyword_trends([kw], period)
            results.extend(mock)
            continue

        base = monthly_search if monthly_search > 0 else 5000
        num_points = _PERIOD_POINTS.get(period, 12)
        rng = random.Random(abs(hash(kw)) % (2**31))
        trend_factor = rng.uniform(-0.15, 0.30)
        series = _make_trend_series(base, num_points, trend_factor)
        half = max(len(series) // 2, 1)
        prev_avg = sum(series[:half]) / half if half else 1
        curr_avg = sum(series[half:]) / half if half else 1
        trend_pct = round(((curr_avg - prev_avg) / prev_avg * 100) if prev_avg > 0 else 0, 1)

        results.append({
            "keyword": kw,
            "monthly_search": monthly_search,
            "competition": round(competition, 2),
            "avg_cpc_krw": avg_cpc,
            "product_count": int(monthly_search * competition * 0.8),
            "trend_pct": trend_pct,
            "series": series,
            "period": period,
        })
    return results


def get_rising_keywords(limit: int = 8) -> List[Dict[str, Any]]:
    """급상승(라이저) 키워드 목록 반환.

    Returns:
        [{keyword, change_pct, monthly_search, competition}]
    """
    return list(_RISING_KEYWORDS[:limit])


def get_related_keywords(keyword: str) -> Dict[str, List[str]]:
    """연관/확장/롱테일 키워드 추천.

    Returns:
        {
            "related": [...],    # 연관 키워드
            "expanded": [...],   # 확장 키워드
            "longtail": [...],   # 롱테일 키워드
        }
    """
    related: List[str] = []
    # 데이터베이스에서 부분 매칭 연관어
    for db_kw in _MOCK_KEYWORD_DB:
        if db_kw != keyword and (db_kw in keyword or keyword in db_kw):
            related.append(db_kw)
    # 확장 패턴
    expanded: List[str] = []
    for key, expansions in _RELATED_EXPANSIONS.items():
        if key in keyword or keyword in key:
            expanded.extend(expansions)

    # 롱테일: "키워드 + 구매/추천/가격" 등 suffix 조합
    longtail_suffixes = ["추천", "구매", "가격", "할인", "인기", "직구", "브랜드"]
    longtail = [f"{keyword} {s}" for s in longtail_suffixes]

    return {
        "related": related[:6],
        "expanded": expanded[:6],
        "longtail": longtail[:6],
    }
