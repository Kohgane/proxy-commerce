"""src/payment_recovery/recovery_report.py — 복구 보고서."""
from __future__ import annotations


class RecoveryReport:
    """복구 보고서 생성기."""

    def __init__(self) -> None:
        self._records: list[dict] = []

    def add_record(self, payment_id: str, recovered: bool, amount: float, error_code: str) -> None:
        """기록을 추가한다."""
        self._records.append({
            'payment_id': payment_id,
            'recovered': recovered,
            'amount': amount,
            'error_code': error_code,
        })

    def generate(self) -> dict:
        """보고서를 생성한다."""
        total = len(self._records)
        recovered = sum(1 for r in self._records if r['recovered'])
        failed = total - recovered
        total_amount = sum(r['amount'] for r in self._records)
        recovered_amount = sum(r['amount'] for r in self._records if r['recovered'])
        recovery_rate = recovered / total if total > 0 else 0.0

        error_counts: dict[str, int] = {}
        for r in self._records:
            ec = r['error_code']
            error_counts[ec] = error_counts.get(ec, 0) + 1
        top_errors = sorted(error_counts.items(), key=lambda x: -x[1])[:5]

        return {
            'total_failures': total,
            'recovered_count': recovered,
            'failed_count': failed,
            'recovery_rate': recovery_rate,
            'total_amount': total_amount,
            'recovered_amount': recovered_amount,
            'top_error_codes': [{'error_code': ec, 'count': cnt} for ec, cnt in top_errors],
        }
