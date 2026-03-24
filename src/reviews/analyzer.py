"""src/reviews/analyzer.py — 리뷰 분석기.

제품별 평균 평점, 키워드 빈도 분석, 부정 리뷰 감지, 주간 트렌드 분석.
외부 NLP 라이브러리 없이 정규식 기반으로 구현한다.

환경변수:
  REVIEW_NEGATIVE_THRESHOLD  — 부정 리뷰 기준 평점 (기본 "2")
  TELEGRAM_BOT_TOKEN         — 텔레그램 봇 토큰
  TELEGRAM_CHAT_ID           — 텔레그램 채팅 ID
"""

import datetime
import logging
import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_NEGATIVE_THRESHOLD = int(os.getenv("REVIEW_NEGATIVE_THRESHOLD", "2"))

# 불용어 목록 (한글/영어 기본 불용어)
_STOPWORDS_KO = {
    "이", "가", "을", "를", "은", "는", "에", "의", "도", "로",
    "으로", "와", "과", "이고", "하고", "이나", "나", "도", "만",
    "에서", "부터", "까지", "한테", "께", "이다", "이에요", "예요",
}
_STOPWORDS_EN = {
    "the", "a", "an", "is", "it", "in", "on", "at", "to", "for",
    "of", "and", "or", "but", "not", "i", "my", "me", "was", "be",
    "this", "that", "with", "as", "are", "very", "so", "just",
}
_STOPWORDS = _STOPWORDS_KO | _STOPWORDS_EN


class ReviewAnalyzer:
    """리뷰 데이터 분석기."""

    def __init__(self, collector=None):
        self._collector = collector

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def average_rating_by_sku(
        self, reviews: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """제품(SKU)별 평균 평점을 계산한다.

        Args:
            reviews: 리뷰 목록.

        Returns:
            {product_sku: average_rating} 딕셔너리.
        """
        totals: Dict[str, List[int]] = defaultdict(list)
        for r in reviews:
            sku = str(r.get("product_sku", "")).strip()
            try:
                rating = int(r.get("rating", 0))
            except (ValueError, TypeError):
                continue
            if sku and 1 <= rating <= 5:
                totals[sku].append(rating)
        return {
            sku: round(sum(ratings) / len(ratings), 2)
            for sku, ratings in totals.items()
        }

    def keyword_frequency(
        self, reviews: List[Dict[str, Any]], top_n: int = 20
    ) -> List[tuple]:
        """리뷰 텍스트에서 키워드 빈도를 분석한다.

        정규식 기반 토큰화 (한글 2음절+, 영어 3글자+).

        Args:
            reviews: 리뷰 목록.
            top_n: 상위 N개 키워드 반환.

        Returns:
            [(keyword, count), ...] 리스트 (빈도 내림차순).
        """
        counter: Counter = Counter()
        for r in reviews:
            text = str(r.get("text", ""))
            tokens = self._tokenize(text)
            counter.update(tokens)
        return counter.most_common(top_n)

    def detect_negative_reviews(
        self,
        reviews: List[Dict[str, Any]],
        threshold: Optional[int] = None,
        notify: bool = True,
    ) -> List[Dict[str, Any]]:
        """부정적 리뷰(평점 ≤ threshold)를 감지하고 텔레그램으로 알린다.

        Args:
            reviews: 리뷰 목록.
            threshold: 부정 리뷰 기준 평점 (기본: 환경변수 REVIEW_NEGATIVE_THRESHOLD).
            notify: 텔레그램 알림 발송 여부.

        Returns:
            부정 리뷰 목록.
        """
        thr = threshold if threshold is not None else _NEGATIVE_THRESHOLD
        negative = [
            r for r in reviews
            if int(r.get("rating", 5)) <= thr
        ]
        if negative and notify:
            self._notify_negative(negative)
        return negative

    def weekly_rating_trend(
        self, reviews: List[Dict[str, Any]], weeks: int = 4
    ) -> Dict[str, Dict[str, float]]:
        """제품별 주간 평점 트렌드를 계산한다.

        Args:
            reviews: 리뷰 목록.
            weeks: 분석할 주 수 (기본 4주).

        Returns:
            {product_sku: {week_label: avg_rating}} 딕셔너리.
        """
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        weekly: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))

        for r in reviews:
            sku = str(r.get("product_sku", "")).strip()
            if not sku:
                continue
            created_at = str(r.get("created_at", ""))
            try:
                dt = datetime.datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                continue
            diff_days = (now - dt).days
            if diff_days > weeks * 7:
                continue
            week_num = diff_days // 7
            week_label = f"W-{week_num}"
            try:
                rating = int(r.get("rating", 0))
            except (ValueError, TypeError):
                continue
            weekly[sku][week_label].append(rating)

        result: Dict[str, Dict[str, float]] = {}
        for sku, weeks_data in weekly.items():
            result[sku] = {
                week: round(sum(ratings) / len(ratings), 2)
                for week, ratings in weeks_data.items()
            }
        return result

    def generate_review_summary(
        self,
        reviews: Optional[List[Dict[str, Any]]] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """전체 리뷰 요약 딕셔너리를 생성한다.

        Args:
            reviews: 리뷰 목록 (None이면 collector에서 로드).
            days: 분석 기간 (일).

        Returns:
            요약 딕셔너리.
        """
        if reviews is None:
            if self._collector is not None:
                reviews = self._collector.get_reviews()
            else:
                reviews = []

        # 기간 필터
        cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=days)
        filtered = []
        for r in reviews:
            try:
                dt = datetime.datetime.fromisoformat(
                    str(r.get("created_at", "")).replace("Z", "+00:00")
                )
                if dt >= cutoff:
                    filtered.append(r)
            except (ValueError, TypeError):
                filtered.append(r)

        total = len(filtered)
        avg_rating = (
            round(sum(int(r.get("rating", 0)) for r in filtered) / total, 2)
            if total else 0.0
        )
        by_rating: Dict[int, int] = {i: 0 for i in range(1, 6)}
        for r in filtered:
            try:
                key = int(r.get("rating", 0))
                if 1 <= key <= 5:
                    by_rating[key] += 1
            except (ValueError, TypeError):
                pass

        negative_count = len(self.detect_negative_reviews(filtered, notify=False))

        return {
            "period_days": days,
            "total_reviews": total,
            "average_rating": avg_rating,
            "by_rating": by_rating,
            "negative_count": negative_count,
            "top_keywords": self.keyword_frequency(filtered, top_n=10),
            "avg_by_sku": self.average_rating_by_sku(filtered),
        }

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> List[str]:
        """텍스트를 토큰으로 분리한다 (정규식 기반)."""
        # 한글 2음절 이상 단어 추출
        ko_tokens = re.findall(r"[가-힣]{2,}", text)
        # 영어 3글자 이상 단어 추출
        en_tokens = re.findall(r"[a-zA-Z]{3,}", text.lower())
        tokens = ko_tokens + en_tokens
        return [t for t in tokens if t not in _STOPWORDS]

    def _notify_negative(self, negative_reviews: List[Dict[str, Any]]) -> None:
        """부정 리뷰를 텔레그램으로 알린다."""
        try:
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if not token or not chat_id:
                return
            count = len(negative_reviews)
            skus = list({r.get("product_sku", "") for r in negative_reviews})[:3]
            text = (
                f"⭐ *부정 리뷰 감지*\n\n"
                f"건수: {count}건\n"
                f"제품: {', '.join(skus)}\n"
                f"최저 평점: {min(int(r.get('rating', 5)) for r in negative_reviews)}"
            )
            import requests
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as exc:
            logger.warning("텔레그램 알림 실패: %s", exc)
