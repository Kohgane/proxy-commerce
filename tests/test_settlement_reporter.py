from __future__ import annotations

from src.settlement.reporter import SettlementReporter


def test_monthly_report_calculates_expected_deposit():
    reporter = SettlementReporter()
    report = reporter.monthly_report(
        "2026-05",
        rows=[
            {
                "channel": "coupang",
                "gross_sales_krw": 100000,
                "fee_krw": 10000,
                "ads_krw": 5000,
                "shipping_krw": 3000,
                "refund_krw": 2000,
            }
        ],
    )
    assert report["total_sales_krw"] == 100000
    assert report["total_expected_deposit_krw"] == 80000
    assert report["by_channel"]["coupang"] == 80000


def test_export_csv_has_headers_and_data():
    reporter = SettlementReporter()
    csv_text = reporter.export_csv(
        "2026-05",
        rows=[{"channel": "naver", "gross_sales_krw": 50000, "fee_krw": 5000}],
    )
    assert "month,channel,gross_sales_krw" in csv_text
    assert "2026-05,naver,50000" in csv_text
