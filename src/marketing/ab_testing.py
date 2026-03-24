"""src/marketing/ab_testing.py — A/B 테스팅 관리.

Google Sheets 기반 실험 결과 저장 및 통계 분석.

환경변수:
  AB_TESTING_ENABLED  — A/B 테스팅 활성화 여부 (기본 "0")
  GOOGLE_SHEET_ID     — Google Sheets ID
"""

import datetime
import logging
import math
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("AB_TESTING_ENABLED", "0") == "1"
_SHEET_NAME = os.getenv("AB_TESTING_SHEET_NAME", "ab_tests")
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

_HEADERS = [
    "experiment_name", "variant", "impressions", "conversions", "total_revenue", "updated_at",
]

try:
    from ..utils.sheets import open_sheet
except ImportError:
    open_sheet = None  # type: ignore


class ABTestManager:
    """A/B 테스트 관리자."""

    def __init__(self, sheet_id: str = "", sheet_name: str = ""):
        self._sheet_id = sheet_id or _SHEET_ID
        self._sheet_name = sheet_name or _SHEET_NAME

    def is_enabled(self) -> bool:
        """A/B 테스팅 활성화 여부를 반환한다."""
        return os.getenv("AB_TESTING_ENABLED", "0") == "1"

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _load(self) -> List[Dict[str, Any]]:
        """Google Sheets에서 실험 결과를 로드한다."""
        if open_sheet is None:
            return []
        try:
            ws = open_sheet(self._sheet_id, self._sheet_name)
            return [dict(r) for r in ws.get_all_records()]
        except Exception as exc:
            logger.warning("A/B 테스트 데이터 로드 실패: %s", exc)
            return []

    def _save_all(self, records: List[Dict[str, Any]]) -> None:
        """전체 레코드를 Google Sheets에 저장한다."""
        if open_sheet is None:
            return
        try:
            ws = open_sheet(self._sheet_id, self._sheet_name)
            ws.clear()
            ws.append_row(_HEADERS)
            for r in records:
                ws.append_row([str(r.get(h, "")) for h in _HEADERS])
        except Exception as exc:
            logger.warning("A/B 테스트 데이터 저장 실패: %s", exc)

    def _find_or_create(
        self, records: List[Dict[str, Any]], experiment_name: str, variant: str,
    ) -> Dict[str, Any]:
        """실험/변형 레코드를 찾거나 새로 생성한다."""
        for r in records:
            if r.get("experiment_name") == experiment_name and r.get("variant") == variant:
                return r
        new_record: Dict[str, Any] = {
            "experiment_name": experiment_name,
            "variant": variant,
            "impressions": 0,
            "conversions": 0,
            "total_revenue": 0.0,
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }
        records.append(new_record)
        return new_record

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def get_variant(self, experiment_name: str, customer_email: str) -> str:
        """실험 이름과 고객 이메일로 A/B 변형을 결정한다.

        해시 기반으로 일관된 변형을 반환한다.

        Args:
            experiment_name: 실험 이름.
            customer_email: 고객 이메일.

        Returns:
            'A' 또는 'B'.
        """
        key = experiment_name + customer_email
        return "A" if hash(key) % 100 < 50 else "B"

    def record_impression(self, experiment_name: str, variant: str) -> None:
        """노출을 기록한다.

        Args:
            experiment_name: 실험 이름.
            variant: 'A' 또는 'B'.
        """
        records = self._load()
        record = self._find_or_create(records, experiment_name, variant)
        record["impressions"] = int(record.get("impressions", 0) or 0) + 1
        record["updated_at"] = datetime.datetime.utcnow().isoformat()
        self._save_all(records)

    def record_conversion(self, experiment_name: str, variant: str, revenue: float = 0.0) -> None:
        """전환을 기록한다.

        Args:
            experiment_name: 실험 이름.
            variant: 'A' 또는 'B'.
            revenue: 전환 매출 (기본 0).
        """
        records = self._load()
        record = self._find_or_create(records, experiment_name, variant)
        record["conversions"] = int(record.get("conversions", 0) or 0) + 1
        record["total_revenue"] = float(record.get("total_revenue", 0) or 0) + revenue
        record["updated_at"] = datetime.datetime.utcnow().isoformat()
        self._save_all(records)

    def get_results(self, experiment_name: str) -> Dict[str, Any]:
        """실험 결과 통계를 반환한다.

        Z-검정으로 통계적 유의성을 계산한다 (|z| > 1.96이면 유의미).

        Args:
            experiment_name: 실험 이름.

        Returns:
            변형별 통계 및 유의성 여부.
        """
        records = self._load()
        stats: Dict[str, Any] = {
            "experiment_name": experiment_name,
            "A": {"impressions": 0, "conversions": 0, "total_revenue": 0.0, "conversion_rate": 0.0},
            "B": {"impressions": 0, "conversions": 0, "total_revenue": 0.0, "conversion_rate": 0.0},
            "is_significant": False,
        }

        for r in records:
            if r.get("experiment_name") != experiment_name:
                continue
            variant = r.get("variant")
            if variant not in ("A", "B"):
                continue
            impressions = int(r.get("impressions", 0) or 0)
            conversions = int(r.get("conversions", 0) or 0)
            revenue = float(r.get("total_revenue", 0) or 0)
            rate = conversions / impressions if impressions > 0 else 0.0
            stats[variant] = {
                "impressions": impressions,
                "conversions": conversions,
                "total_revenue": revenue,
                "conversion_rate": rate,
            }

        # Z-검정
        a = stats["A"]
        b = stats["B"]
        n1, p1 = a["impressions"], a["conversion_rate"]
        n2, p2 = b["impressions"], b["conversion_rate"]
        if n1 > 0 and n2 > 0:
            variance = p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2
            if variance > 0:
                z = (p1 - p2) / math.sqrt(variance)
                stats["is_significant"] = math.fabs(z) > 1.96

        return stats
