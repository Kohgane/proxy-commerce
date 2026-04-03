"""src/segmentation/segment_exporter.py — 세그먼트 고객 목록 CSV 내보내기."""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List


class SegmentExporter:
    """세그먼트 고객 목록을 CSV 문자열로 내보내기."""

    DEFAULT_FIELDS = [
        "customer_id",
        "total_purchase_amount",
        "purchase_count",
        "days_since_last_purchase",
        "region",
        "channel",
    ]

    def export_csv(self, customers: List[Dict[str, Any]],
                   fields: List[str] = None) -> str:
        """고객 목록을 CSV 문자열로 변환."""
        fields = fields or self.DEFAULT_FIELDS
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore",
                                lineterminator="\n")
        writer.writeheader()
        for customer in customers:
            writer.writerow({f: customer.get(f, "") for f in fields})
        return output.getvalue()

    def export_segment(self, segment_name: str,
                       customers: List[Dict[str, Any]],
                       fields: List[str] = None) -> dict:
        """세그먼트 내보내기 결과 (CSV 문자열 + 메타 정보)."""
        csv_data = self.export_csv(customers, fields)
        return {
            "segment_name": segment_name,
            "record_count": len(customers),
            "csv": csv_data,
        }
