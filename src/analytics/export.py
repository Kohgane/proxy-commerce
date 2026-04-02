"""src/analytics/export.py — Phase 29: Report Exporter."""

import csv
import io


class ReportExporter:
    """보고서 내보내기 클래스 (CSV, Google Sheets mock)."""

    def to_csv(self, data: list, filename: str = 'report.csv') -> str:
        """CSV 형식으로 내보내기.

        Args:
            data: list of dicts (모든 행은 동일한 키를 가져야 함)
            filename: 저장할 파일 이름 (사용하지 않을 경우 CSV 문자열 반환)

        Returns:
            CSV 문자열
        """
        if not data:
            return ''

        output = io.StringIO()
        fieldnames = list(data[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue()

    def to_google_sheets(self, data: list, sheet_name: str) -> dict:
        """Google Sheets로 내보내기 (mock 구현).

        Returns:
            {'success': True, 'sheet_name': str, 'rows_written': int}
        """
        return {
            'success': True,
            'sheet_name': sheet_name,
            'rows_written': len(data),
        }
