from __future__ import annotations

from src.returns.auto_processor import ReturnRequest, ReturnsAutoProcessor


def test_classify_reason():
    p = ReturnsAutoProcessor()
    assert p.classify_reason("상품 불량") == "defective"
    assert p.classify_reason("오배송 받음") == "wrong_item"
    assert p.classify_reason("단순변심") == "change_of_mind"


def test_auto_approve_rule_and_policy():
    p = ReturnsAutoProcessor()
    req = ReturnRequest("RET-1", "mock", "ORD-1", "defective", 40000)
    assert p.can_auto_approve(req) is True
    policy = p.refund_policy(req)
    assert policy["shipping_deduction_krw"] == 0
    assert policy["refund_amount_krw"] == 40000


def test_collect_process_and_summary():
    p = ReturnsAutoProcessor()
    p.collect_market_requests(
        [
            {"request_id": "RET-1", "order_id": "ORD-1", "reason": "불량", "amount_krw": 40000},
            {"request_id": "RET-2", "order_id": "ORD-2", "reason": "단순변심", "amount_krw": 40000},
        ]
    )
    result = p.process()
    assert result["approved"] == 1
    assert result["manual_review"] == 1
    summary = p.summary_24h()
    assert summary["requests_24h"] == 2
