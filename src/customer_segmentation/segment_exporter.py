"""세그먼트 CSV 내보내기."""
from __future__ import annotations
import csv
import io

class SegmentExporter:
    def export_csv(self, customers: list[dict], fields: list[str] | None = None) -> str:
        if not customers:
            return ""
        fields = fields or list(customers[0].keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(customers)
        return buf.getvalue()
