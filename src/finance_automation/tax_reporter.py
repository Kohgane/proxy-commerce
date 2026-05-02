"""src/finance_automation/tax_reporter.py — Phase 119: 세무 리포트 생성."""
from __future__ import annotations

import calendar
import csv
import io
import json
import logging
from decimal import Decimal

from .cost_aggregator import CostAggregator
from .ledger import Ledger
from .models import AccountCode, TaxReport

logger = logging.getLogger(__name__)

_VAT_RATE = Decimal('0.1')


class TaxReporter:
    """부가가치세 및 관세 세무 리포트 자동 생성.

    VAT 납부세액 = 매출 × 10%, VAT 매입세액 = COGS × 10%.
    """

    def __init__(self, ledger: Ledger, cost_aggregator: CostAggregator) -> None:
        self._ledger = ledger
        self._cost_agg = cost_aggregator

    def generate_report(self, period: str) -> TaxReport:
        """세무 리포트 생성.

        Args:
            period: YYYY-MM 형식의 과세 기간

        Returns:
            TaxReport
        """
        tb = self._ledger.trial_balance(period)

        revenue_credit = tb.get(AccountCode.REVENUE.value, {}).get('credit', Decimal('0'))
        cogs_debit = tb.get(AccountCode.COGS.value, {}).get('debit', Decimal('0'))

        vat_payable = (revenue_credit * _VAT_RATE).quantize(Decimal('1'))
        vat_receivable = (cogs_debit * _VAT_RATE).quantize(Decimal('1'))

        start = f'{period}-01'
        year, month = int(period[:4]), int(period[5:7])
        last_day = calendar.monthrange(year, month)[1]
        end = f'{period}-{last_day:02d}'
        cost_records = self._cost_agg.get_costs_by_period(start, end)
        customs_paid = sum(r.customs for r in cost_records)

        report = TaxReport(
            period=period,
            vat_payable=vat_payable,
            vat_receivable=vat_receivable,
            customs_paid=customs_paid,
            total_taxable=revenue_credit,
        )
        logger.info(
            "[세무] %s 리포트: VAT납부=%s VAT매입=%s 관세=%s",
            period, vat_payable, vat_receivable, customs_paid,
        )
        return report

    def export_json(self, report: TaxReport) -> str:
        """세무 리포트를 JSON 문자열로 직렬화.

        Args:
            report: TaxReport

        Returns:
            JSON 문자열
        """
        data = {
            'period': report.period,
            'vat_payable': str(report.vat_payable),
            'vat_receivable': str(report.vat_receivable),
            'customs_paid': str(report.customs_paid),
            'total_taxable': str(report.total_taxable),
        }
        return json.dumps(data, ensure_ascii=False)

    def export_csv(self, report: TaxReport) -> str:
        """세무 리포트를 CSV 문자열로 직렬화.

        Args:
            report: TaxReport

        Returns:
            CSV 문자열
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['항목', '금액'])
        writer.writerow(['과세 기간', report.period])
        writer.writerow(['VAT 납부세액', str(report.vat_payable)])
        writer.writerow(['VAT 매입세액 공제', str(report.vat_receivable)])
        writer.writerow(['관세 납부액', str(report.customs_paid)])
        writer.writerow(['총 과세 매출', str(report.total_taxable)])
        return output.getvalue()
