"""src/seller_console/seller_trust.py — 타오바오 셀러 신뢰도 평가 (Phase 122).

TaobaoSellerTrustChecker: 별점/판매량/운영기간/부정리뷰율/응답시간 기반 신뢰도 점수화.
현재 구현은 mock 데이터 기반; 실연동은 Phase 124 PR에서 처리.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# 임계치 상수
# ---------------------------------------------------------------------------
_THRESHOLD_RATING = 4.7          # 별점 최소치
_THRESHOLD_SALES = 1000          # 누적 판매 최소치
_THRESHOLD_MONTHS = 12           # 운영 기간 최소 (월)
_THRESHOLD_NEG_REVIEW_PCT = 5.0  # 부정 리뷰 최대 비율 (%)
_THRESHOLD_RESPONSE_HOURS = 24   # 응답 시간 최대 (시간)


@dataclass
class TrustScore:
    """셀러 신뢰도 평가 결과."""

    seller_id: str
    score: float                   # 0~100
    grade: str                     # A / B / C / D
    rating: float = 0.0            # 별점 (5점 만점)
    total_sales: int = 0           # 누적 판매 수
    operating_months: int = 0      # 운영 기간 (월)
    neg_review_pct: float = 0.0    # 부정 리뷰 비율 (%)
    response_hours: float = 0.0    # 평균 응답 시간 (시간)
    passed: bool = True            # 임계치 통과 여부
    warnings: list = field(default_factory=list)  # 경고 메시지 목록

    def to_dict(self) -> Dict:
        """JSON 직렬화용 딕셔너리 반환."""
        return {
            "seller_id": self.seller_id,
            "score": round(self.score, 1),
            "grade": self.grade,
            "rating": self.rating,
            "total_sales": self.total_sales,
            "operating_months": self.operating_months,
            "neg_review_pct": self.neg_review_pct,
            "response_hours": self.response_hours,
            "passed": self.passed,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Mock 데이터 — Phase 124에서 실연동으로 교체
# ---------------------------------------------------------------------------
_MOCK_SELLERS: Dict[str, Dict] = {
    "taobao_seller_good": {
        "rating": 4.9,
        "total_sales": 5000,
        "operating_months": 36,
        "neg_review_pct": 1.2,
        "response_hours": 4.0,
    },
    "taobao_seller_ok": {
        "rating": 4.8,
        "total_sales": 1200,
        "operating_months": 18,
        "neg_review_pct": 3.5,
        "response_hours": 12.0,
    },
    "taobao_seller_bad": {
        "rating": 4.3,
        "total_sales": 200,
        "operating_months": 6,
        "neg_review_pct": 12.0,
        "response_hours": 48.0,
    },
}
_DEFAULT_MOCK = {
    "rating": 4.75,
    "total_sales": 2500,
    "operating_months": 24,
    "neg_review_pct": 2.0,
    "response_hours": 8.0,
}


class TaobaoSellerTrustChecker:
    """타오바오 셀러 신뢰도 평가기.

    evaluate(seller_id) → TrustScore (0~100점, 등급 A/B/C/D)

    점수 계산 방식:
      - 별점 (30점): rating / 5.0 * 30
      - 판매량 (25점): min(total_sales, 10000) / 10000 * 25
      - 운영기간 (20점): min(operating_months, 60) / 60 * 20
      - 부정리뷰 (15점): max(0, 1 - neg_review_pct / 20) * 15
      - 응답시간 (10점): max(0, 1 - response_hours / 72) * 10
    """

    def evaluate(self, seller_id: str) -> TrustScore:
        """셀러 신뢰도 평가.

        Args:
            seller_id: 타오바오 셀러 ID (또는 URL에서 추출한 식별자)

        Returns:
            TrustScore 인스턴스
        """
        # mock 데이터에서 셀러 정보 조회
        data = _MOCK_SELLERS.get(seller_id, _DEFAULT_MOCK)

        rating = float(data.get("rating", 4.5))
        total_sales = int(data.get("total_sales", 0))
        operating_months = int(data.get("operating_months", 0))
        neg_review_pct = float(data.get("neg_review_pct", 0.0))
        response_hours = float(data.get("response_hours", 24.0))

        # 점수 계산
        score_rating = (rating / 5.0) * 30
        score_sales = (min(total_sales, 10000) / 10000) * 25
        score_months = (min(operating_months, 60) / 60) * 20
        score_neg = max(0.0, 1.0 - neg_review_pct / 20.0) * 15
        score_resp = max(0.0, 1.0 - response_hours / 72.0) * 10
        score = score_rating + score_sales + score_months + score_neg + score_resp

        # 등급 결정
        if score >= 85:
            grade = "A"
        elif score >= 70:
            grade = "B"
        elif score >= 55:
            grade = "C"
        else:
            grade = "D"

        # 임계치 검사
        warnings = []
        passed = True
        if rating < _THRESHOLD_RATING:
            warnings.append(f"별점 {rating} < {_THRESHOLD_RATING} 기준 미달")
            passed = False
        if total_sales < _THRESHOLD_SALES:
            warnings.append(f"누적 판매 {total_sales} < {_THRESHOLD_SALES} 기준 미달")
            passed = False
        if operating_months < _THRESHOLD_MONTHS:
            warnings.append(f"운영기간 {operating_months}개월 < {_THRESHOLD_MONTHS}개월 기준 미달")
            passed = False
        if neg_review_pct > _THRESHOLD_NEG_REVIEW_PCT:
            warnings.append(f"부정리뷰 {neg_review_pct}% > {_THRESHOLD_NEG_REVIEW_PCT}% 기준 초과")
            passed = False
        if response_hours > _THRESHOLD_RESPONSE_HOURS:
            warnings.append(f"응답시간 {response_hours}h > {_THRESHOLD_RESPONSE_HOURS}h 기준 초과")
            passed = False

        return TrustScore(
            seller_id=seller_id,
            score=round(score, 1),
            grade=grade,
            rating=rating,
            total_sales=total_sales,
            operating_months=operating_months,
            neg_review_pct=neg_review_pct,
            response_hours=response_hours,
            passed=passed,
            warnings=warnings,
        )

    @staticmethod
    def extract_seller_id_from_url(url: str) -> Optional[str]:
        """타오바오 URL에서 셀러 ID 추출 (mock 구현).

        Args:
            url: 타오바오 상품 URL

        Returns:
            셀러 ID 문자열 또는 None
        """
        # mock: URL에 특정 패턴 포함 시 특정 seller_id 반환
        url_lower = url.lower()
        if "taobao" in url_lower or "1688" in url_lower or "tmall" in url_lower:
            # 실제 구현에서는 URL 파싱으로 shop/sellerNick 추출
            return "taobao_seller_ok"
        return None
