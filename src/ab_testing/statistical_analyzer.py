"""src/ab_testing/statistical_analyzer.py — 통계적 유의성 분석."""
import logging
import math
from typing import Dict

logger = logging.getLogger(__name__)


class StatisticalAnalyzer:
    """Z-검정으로 통계적 유의성 계산."""

    def z_test(
        self,
        control_conversions: int,
        control_total: int,
        treatment_conversions: int,
        treatment_total: int,
        significance_level: float = 0.05,
    ) -> Dict:
        if control_total == 0 or treatment_total == 0:
            return {'z_score': 0.0, 'p_value': 1.0, 'is_significant': False}
        p_control = control_conversions / control_total
        p_treatment = treatment_conversions / treatment_total
        p_pool = (control_conversions + treatment_conversions) / (control_total + treatment_total)
        if p_pool in (0, 1):
            return {'z_score': 0.0, 'p_value': 1.0, 'is_significant': False}
        se = math.sqrt(p_pool * (1 - p_pool) * (1 / control_total + 1 / treatment_total))
        if se == 0:
            return {'z_score': 0.0, 'p_value': 1.0, 'is_significant': False}
        z_score = (p_treatment - p_control) / se
        p_value = 2 * (1 - self._normal_cdf(abs(z_score)))
        return {
            'z_score': round(z_score, 4),
            'p_value': round(p_value, 4),
            'is_significant': p_value < significance_level,
        }

    def _normal_cdf(self, z: float) -> float:
        """표준 정규 누적 분포 함수 근사."""
        return 0.5 * (1 + math.erf(z / math.sqrt(2)))
