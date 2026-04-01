"""tests/test_crm_segmentation.py — RFM 분석 + 세그먼트 분류 테스트."""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _dt(days_ago):
    return (datetime.now(tz=timezone.utc) - timedelta(days=days_ago)).isoformat()


def _customer(
    email="test@example.com",
    total_orders=1,
    total_spent_krw=100000,
    first_order_days_ago=10,
    last_order_days_ago=10,
    segment="NEW",
):
    return {
        "email": email,
        "name": "테스트",
        "total_orders": total_orders,
        "total_spent_krw": total_spent_krw,
        "first_order_date": _dt(first_order_days_ago),
        "last_order_date": _dt(last_order_days_ago),
        "segment": segment,
        "country": "KR",
    }


class TestClassify:
    def _make_seg(self, **kwargs):
        from src.crm.segmentation import CustomerSegmentation
        return CustomerSegmentation(
            vip_min_orders=3,
            vip_min_spent=1000000,
            at_risk_days=90,
            dormant_days=180,
        )

    def test_dormant_customer(self):
        """마지막 주문 180일+ 경과 시 DORMANT여야 한다."""
        seg = self._make_seg()
        c = _customer(last_order_days_ago=200, total_orders=5)
        assert seg.classify(c) == "DORMANT"

    def test_at_risk_customer(self):
        """마지막 주문 90일+ 경과, 2회+ 구매 시 AT_RISK여야 한다."""
        seg = self._make_seg()
        c = _customer(last_order_days_ago=100, total_orders=3, total_spent_krw=200000)
        result = seg.classify(c)
        assert result == "AT_RISK"

    def test_vip_customer(self):
        """최근 30일 내 3회+ 구매, 100만원+ 시 VIP여야 한다."""
        seg = self._make_seg()
        c = _customer(
            last_order_days_ago=5,
            total_orders=5,
            total_spent_krw=2000000,
        )
        assert seg.classify(c) == "VIP"

    def test_loyal_customer(self):
        """최근 60일 내 2회+ 구매 시 LOYAL이어야 한다."""
        seg = self._make_seg()
        c = _customer(
            last_order_days_ago=30,
            total_orders=3,
            total_spent_krw=300000,
        )
        assert seg.classify(c) == "LOYAL"

    def test_new_customer(self):
        """첫 주문 30일 이내 시 NEW여야 한다."""
        seg = self._make_seg()
        c = _customer(
            last_order_days_ago=5,
            first_order_days_ago=5,
            total_orders=1,
            total_spent_krw=50000,
        )
        assert seg.classify(c) == "NEW"

    def test_dormant_takes_priority_over_at_risk(self):
        """DORMANT가 AT_RISK보다 우선해야 한다."""
        seg = self._make_seg()
        c = _customer(last_order_days_ago=200, total_orders=5)
        assert seg.classify(c) == "DORMANT"


class TestSegmentAllCustomers:
    def test_all_segments_returned(self):
        """segment_all_customers 반환값에 모든 세그먼트 키가 있어야 한다."""
        from src.crm.segmentation import CustomerSegmentation, SEGMENTS
        seg = CustomerSegmentation()
        customers = [
            _customer("a@a.com", last_order_days_ago=5, first_order_days_ago=5, total_orders=1),
        ]
        result = seg.segment_all_customers(customers=customers, notify_changes=False)
        for s in SEGMENTS:
            assert s in result

    def test_returns_email_lists(self):
        """각 세그먼트 값이 이메일 리스트여야 한다."""
        from src.crm.segmentation import CustomerSegmentation
        seg = CustomerSegmentation()
        customers = [_customer("x@x.com")]
        result = seg.segment_all_customers(customers=customers, notify_changes=False)
        for val in result.values():
            assert isinstance(val, list)

    def test_segment_summary_structure(self):
        """get_segment_summary 반환값에 count, avg_spent_krw, avg_orders가 있어야 한다."""
        from src.crm.segmentation import CustomerSegmentation
        seg = CustomerSegmentation()
        customers = [_customer()]
        summary = seg.get_segment_summary(customers=customers)
        for seg_info in summary.values():
            assert "count" in seg_info
            assert "avg_spent_krw" in seg_info
            assert "avg_orders" in seg_info

    def test_empty_customers(self):
        """빈 고객 목록 시 모든 세그먼트 count가 0이어야 한다."""
        from src.crm.segmentation import CustomerSegmentation
        seg = CustomerSegmentation()
        summary = seg.get_segment_summary(customers=[])
        for info in summary.values():
            assert info["count"] == 0
