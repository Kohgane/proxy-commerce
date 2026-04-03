"""src/data_exchange/export_manager.py — 내보내기 관리자."""
from __future__ import annotations

import datetime
import json


class ExportManager:
    """데이터 내보내기 관리자."""

    def export(self, data: list, format_: str = "json", template_id: str = "") -> dict:
        """데이터를 지정 형식으로 내보낸다."""
        if format_ == "json":
            content = json.dumps(data, ensure_ascii=False)
        elif format_ == "csv":
            if data and isinstance(data[0], dict):
                headers = ",".join(data[0].keys())
                rows = [",".join(str(v) for v in row.values()) for row in data]
                content = "\n".join([headers] + rows)
            else:
                content = "\n".join(str(item) for item in data)
        else:
            content = str(data)

        return {
            "format": format_,
            "records": len(data),
            "content": content,
            "template_id": template_id,
            "exported_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
