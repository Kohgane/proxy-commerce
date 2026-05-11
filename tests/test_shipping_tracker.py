from __future__ import annotations

from datetime import datetime, timedelta

from src.shipping.tracker import ShippingMonitor


def test_shipping_monitor_summary_defaults():
    monitor = ShippingMonitor()
    summary = monitor.summary()
    assert summary["tracking_count"] == 0
    assert "provider" in summary


def test_shipping_monitor_delay_and_lost_detection():
    monitor = ShippingMonitor()
    row = monitor.track("ord-1", "cj", "123", stage="출고")
    row["updated_at"] = datetime.utcnow() - timedelta(days=6)
    delayed = monitor.detect_delay()
    lost = monitor.detect_lost()
    assert len(delayed) == 1
    assert len(lost) == 1
