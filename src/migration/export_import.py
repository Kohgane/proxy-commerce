"""src/migration/export_import.py — Phase 42: JSON/CSV 내보내기/가져오기."""
import csv
import io
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ExportImport:
    """데이터 내보내기/가져오기.

    - JSON / CSV 내보내기
    - JSON / CSV 가져오기
    - 대량 가져오기
    """

    def export_json(self, records: List[dict], indent: int = 2) -> str:
        """JSON 문자열로 내보내기."""
        return json.dumps(records, ensure_ascii=False, indent=indent)

    def export_csv(self, records: List[dict], fields: Optional[List[str]] = None) -> str:
        """CSV 문자열로 내보내기."""
        if not records:
            return ''
        if not fields:
            fields = list(records[0].keys())
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
        return output.getvalue()

    def import_json(self, json_str: str) -> List[dict]:
        """JSON 문자열에서 가져오기."""
        data = json.loads(json_str)
        if isinstance(data, dict):
            # 단일 레코드
            return [data]
        return list(data)

    def import_csv(self, csv_str: str) -> List[dict]:
        """CSV 문자열에서 가져오기."""
        reader = csv.DictReader(io.StringIO(csv_str))
        return list(reader)

    def bulk_import(
        self,
        records: List[dict],
        store: Dict[str, dict],
        id_field: str = 'id',
        overwrite: bool = False,
    ) -> dict:
        """대량 가져오기.

        Args:
            records: 가져올 레코드 목록
            store: 대상 딕셔너리 저장소
            id_field: ID 필드명
            overwrite: True면 기존 레코드 덮어쓰기

        Returns:
            {'inserted': int, 'skipped': int, 'errors': List[str]}
        """
        inserted = 0
        skipped = 0
        errors = []
        for record in records:
            record_id = record.get(id_field)
            if not record_id:
                errors.append(f"ID 필드({id_field}) 없음: {record}")
                skipped += 1
                continue
            if record_id in store and not overwrite:
                skipped += 1
                continue
            store[record_id] = record
            inserted += 1
        logger.info("대량 가져오기: inserted=%d skipped=%d errors=%d", inserted, skipped, len(errors))
        return {'inserted': inserted, 'skipped': skipped, 'errors': errors}

    def export_to_file(self, records: List[dict], path: str, fmt: str = 'json') -> int:
        """파일로 내보내기. 내보낸 레코드 수 반환."""
        if fmt == 'json':
            content = self.export_json(records)
        elif fmt == 'csv':
            content = self.export_csv(records)
        else:
            raise ValueError(f"지원하지 않는 형식: {fmt}")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info("파일 내보내기: %s (%d건)", path, len(records))
        return len(records)

    def import_from_file(self, path: str, fmt: str = 'json') -> List[dict]:
        """파일에서 가져오기."""
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if fmt == 'json':
            return self.import_json(content)
        elif fmt == 'csv':
            return self.import_csv(content)
        raise ValueError(f"지원하지 않는 형식: {fmt}")
