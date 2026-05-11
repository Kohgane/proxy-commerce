"""src/settlement/reporter.py — 월별 정산 리포트 (Phase 146)."""
from __future__ import annotations

import csv
import io
import os


class SettlementReporter:
    def __init__(self) -> None:
        self.tax_rate_pct = float(os.getenv("SETTLEMENT_TAX_RATE_PCT", "10"))
        self.report_email = os.getenv("SETTLEMENT_REPORT_EMAIL", "")

    def collect_monthly_data(self, month: str, rows: list[dict] | None = None) -> list[dict]:
        rows = rows or []
        normalized = []
        for row in rows:
            gross = int(row.get("gross_sales_krw") or 0)
            fees = int(row.get("fee_krw") or 0)
            ads = int(row.get("ads_krw") or 0)
            shipping = int(row.get("shipping_krw") or 0)
            refunds = int(row.get("refund_krw") or 0)
            net = gross - fees - ads - shipping - refunds
            normalized.append(
                {
                    "month": month,
                    "channel": str(row.get("channel") or "mock"),
                    "gross_sales_krw": gross,
                    "fee_krw": fees,
                    "ads_krw": ads,
                    "shipping_krw": shipping,
                    "refund_krw": refunds,
                    "expected_deposit_krw": net,
                    "tax_invoice_krw": round(net * (self.tax_rate_pct / 100)),
                    "card_sales_krw": gross,
                }
            )
        return normalized

    def monthly_report(self, month: str, rows: list[dict] | None = None) -> dict:
        data = self.collect_monthly_data(month, rows=rows)
        total_sales = sum(x["gross_sales_krw"] for x in data)
        total_net = sum(x["expected_deposit_krw"] for x in data)
        by_channel = {x["channel"]: x["expected_deposit_krw"] for x in data}
        return {
            "month": month,
            "rows": data,
            "total_sales_krw": total_sales,
            "total_expected_deposit_krw": total_net,
            "by_channel": by_channel,
            "next_settlement_date": "-",
        }

    def export_csv(self, month: str, rows: list[dict] | None = None) -> str:
        report = self.monthly_report(month, rows=rows)
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=[
                "month",
                "channel",
                "gross_sales_krw",
                "fee_krw",
                "ads_krw",
                "shipping_krw",
                "refund_krw",
                "expected_deposit_krw",
                "tax_invoice_krw",
                "card_sales_krw",
            ],
        )
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow(row)
        return buf.getvalue()

    def export_excel_xml(self, month: str, rows: list[dict] | None = None) -> str:
        report = self.monthly_report(month, rows=rows)
        head = (
            '<?xml version="1.0"?>'
            '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
            'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
            '<Worksheet ss:Name="settlement"><Table>'
            "<Row>"
            "<Cell><Data ss:Type=\"String\">month</Data></Cell>"
            "<Cell><Data ss:Type=\"String\">channel</Data></Cell>"
            "<Cell><Data ss:Type=\"String\">gross_sales_krw</Data></Cell>"
            "<Cell><Data ss:Type=\"String\">fee_krw</Data></Cell>"
            "<Cell><Data ss:Type=\"String\">ads_krw</Data></Cell>"
            "<Cell><Data ss:Type=\"String\">shipping_krw</Data></Cell>"
            "<Cell><Data ss:Type=\"String\">refund_krw</Data></Cell>"
            "<Cell><Data ss:Type=\"String\">expected_deposit_krw</Data></Cell>"
            "<Cell><Data ss:Type=\"String\">tax_invoice_krw</Data></Cell>"
            "<Cell><Data ss:Type=\"String\">card_sales_krw</Data></Cell>"
            "</Row>"
        )
        rows_xml = ""
        for row in report["rows"]:
            rows_xml += (
                "<Row>"
                f"<Cell><Data ss:Type=\"String\">{row['month']}</Data></Cell>"
                f"<Cell><Data ss:Type=\"String\">{row['channel']}</Data></Cell>"
                f"<Cell><Data ss:Type=\"Number\">{row['gross_sales_krw']}</Data></Cell>"
                f"<Cell><Data ss:Type=\"Number\">{row['fee_krw']}</Data></Cell>"
                f"<Cell><Data ss:Type=\"Number\">{row['ads_krw']}</Data></Cell>"
                f"<Cell><Data ss:Type=\"Number\">{row['shipping_krw']}</Data></Cell>"
                f"<Cell><Data ss:Type=\"Number\">{row['refund_krw']}</Data></Cell>"
                f"<Cell><Data ss:Type=\"Number\">{row['expected_deposit_krw']}</Data></Cell>"
                f"<Cell><Data ss:Type=\"Number\">{row['tax_invoice_krw']}</Data></Cell>"
                f"<Cell><Data ss:Type=\"Number\">{row['card_sales_krw']}</Data></Cell>"
                "</Row>"
            )
        return head + rows_xml + "</Table></Worksheet></Workbook>"
