"""src/data_exchange/import_manager.py — 가져오기 관리자."""
from __future__ import annotations

import datetime
import json


class ImportManager:
    """데이터 가져오기 관리자."""

    def import_data(self, content: str, format_: str = "json") -> dict:
        """콘텐츠를 파싱하여 가져온다."""
        errors: list[str] = []
        records: list = []

        try:
            if format_ == "json":
                parsed = json.loads(content)
                records = parsed if isinstance(parsed, list) else [parsed]
            elif format_ == "csv":
                lines = [l for l in content.strip().splitlines() if l]
                if lines:
                    headers = [h.strip() for h in lines[0].split(",")]
                    for line in lines[1:]:
                        values = [v.strip() for v in line.split(",")]
                        records.append(dict(zip(headers, values)))
            else:
                errors.append(f"지원하지 않는 형식: {format_}")
        except Exception as exc:
            errors.append(f"파싱 오류: {type(exc).__name__}")

        valid = len(records)
        invalid = len(errors)

        return {
            "format": format_,
            "records_processed": valid + invalid,
            "records_valid": valid,
            "records_invalid": invalid,
            "errors": errors,
            "imported_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
