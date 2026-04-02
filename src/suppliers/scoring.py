"""공급자 평가 점수."""

import logging

logger = logging.getLogger(__name__)


class SupplierScoring:
    """공급자 점수 계산 — 품질(40%), 납기(30%), 가격(30%)."""

    GRADE_THRESHOLDS = [
        ('A', 80.0),
        ('B', 60.0),
        ('C', 40.0),
        ('D', 0.0),
    ]

    def calculate_score(self, quality: float, delivery: float, price: float) -> float:
        """가중 평균 점수 계산.

        Args:
            quality: 품질 점수 (0~100)
            delivery: 납기 점수 (0~100)
            price: 가격 점수 (0~100)

        Returns:
            종합 점수 (0~100)
        """
        score = quality * 0.4 + delivery * 0.3 + price * 0.3
        logger.debug("공급자 점수: 품질=%f, 납기=%f, 가격=%f -> %f", quality, delivery, price, score)
        return round(score, 2)

    def get_grade(self, score: float) -> str:
        """점수에 따른 등급 반환."""
        for grade, threshold in self.GRADE_THRESHOLDS:
            if score >= threshold:
                return grade
        return 'D'
