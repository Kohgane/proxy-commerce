"""src/ab_testing/statistical_analyzer.py — 통계적 유의성 검정."""
from __future__ import annotations

import math
from typing import Optional


class StatisticalAnalyzer:
    """Z-test 기반 통계적 유의성 검정."""

    def z_test(self, n1: int, conv1: int, n2: int, conv2: int) -> dict:
        """두 변형의 전환율 Z-test.

        Args:
            n1: 변형1 노출 수
            conv1: 변형1 전환 수
            n2: 변형2 노출 수
            conv2: 변형2 전환 수

        Returns:
            z_score, p_value, significant (95% 수준)
        """
        if n1 == 0 or n2 == 0:
            return {"z_score": 0.0, "p_value": 1.0, "significant": False,
                    "cvr1": 0.0, "cvr2": 0.0, "lift": 0.0}

        p1 = conv1 / n1
        p2 = conv2 / n2
        p_pool = (conv1 + conv2) / (n1 + n2)

        se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
        if se == 0:
            return {"z_score": 0.0, "p_value": 1.0, "significant": False,
                    "cvr1": round(p1, 4), "cvr2": round(p2, 4), "lift": 0.0}

        z = (p2 - p1) / se
        p_value = self._z_to_p(z)
        lift = ((p2 - p1) / p1 * 100) if p1 > 0 else 0.0

        return {
            "z_score": round(z, 4),
            "p_value": round(p_value, 4),
            "significant": p_value < 0.05,
            "cvr1": round(p1, 4),
            "cvr2": round(p2, 4),
            "lift": round(lift, 2),
        }

    def _z_to_p(self, z: float) -> float:
        """Z-score → p-value (two-tailed) 근사."""
        # 표준 정규분포 CDF 근사 (Abramowitz & Stegun)
        abs_z = abs(z)
        t = 1.0 / (1.0 + 0.2316419 * abs_z)
        poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 +
               t * (-1.821255978 + t * 1.330274429))))
        phi = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * abs_z * abs_z) * poly
        p_one_tail = phi
        return min(1.0, 2 * p_one_tail)

    def sample_size(self, baseline_cvr: float, mde: float,
                    alpha: float = 0.05, power: float = 0.80) -> int:
        """필요 표본 수 계산 (각 변형당).

        Args:
            baseline_cvr: 기준 전환율 (예: 0.10)
            mde: 최소 감지 효과 (예: 0.02 → 2%)
            alpha: 유의 수준 (기본 0.05)
            power: 검정력 (기본 0.80)
        """
        if baseline_cvr <= 0 or mde <= 0:
            return 0
        z_alpha = 1.96  # alpha=0.05
        z_beta = 0.84   # power=0.80
        p1 = baseline_cvr
        p2 = baseline_cvr + mde
        se = math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
        n = ((z_alpha + z_beta) * se / mde) ** 2
        return max(1, math.ceil(n))
