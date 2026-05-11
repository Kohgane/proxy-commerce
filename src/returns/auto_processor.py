"""src/returns/auto_processor.py — 반품/환불 자동 처리 (Phase 146)."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ReturnRequest:
    request_id: str
    market: str
    order_id: str
    reason: str
    amount_krw: int
    status: str = "requested"


class ReturnsAutoProcessor:
    def __init__(self) -> None:
        self.auto_approve_enabled = os.getenv("RETURNS_AUTO_APPROVE_ENABLED", "1") == "1"
        self.auto_approve_max_krw = int(os.getenv("RETURNS_AUTO_APPROVE_MAX_KRW", "50000"))
        reasons = os.getenv("RETURNS_AUTO_APPROVE_REASONS", "defective,wrong_item")
        self.auto_approve_reasons = {x.strip() for x in reasons.split(",") if x.strip()}
        self._requests: list[ReturnRequest] = []
        self._history: list[dict] = []

    @staticmethod
    def classify_reason(text: str) -> str:
        t = (text or "").lower()
        if "불량" in t or "defect" in t:
            return "defective"
        if "오배송" in t or "wrong" in t:
            return "wrong_item"
        if "변심" in t or "mind" in t:
            return "change_of_mind"
        return "other"

    def collect_market_requests(self, rows: list[dict] | None = None) -> list[dict]:
        rows = rows or []
        for i, row in enumerate(rows, start=1):
            reason = self.classify_reason(str(row.get("reason", "")))
            req = ReturnRequest(
                request_id=str(row.get("request_id") or f"RET-{i:04d}"),
                market=str(row.get("market") or "mock"),
                order_id=str(row.get("order_id") or f"ORD-{i:04d}"),
                reason=reason,
                amount_krw=int(row.get("amount_krw") or 0),
            )
            self._requests.append(req)
        return [r.__dict__.copy() for r in self._requests]

    def refund_policy(self, req: ReturnRequest) -> dict:
        shipping_deduction = 6000 if req.reason == "change_of_mind" else 0
        refund_amount = max(req.amount_krw - shipping_deduction, 0)
        return {
            "shipping_deduction_krw": shipping_deduction,
            "refund_amount_krw": refund_amount,
        }

    def can_auto_approve(self, req: ReturnRequest) -> bool:
        if not self.auto_approve_enabled:
            return False
        if req.amount_krw > self.auto_approve_max_krw:
            return False
        return req.reason in self.auto_approve_reasons

    def process(self) -> dict:
        approved = 0
        manual = 0
        for req in self._requests:
            policy = self.refund_policy(req)
            if self.can_auto_approve(req):
                req.status = "approved"
                approved += 1
            else:
                req.status = "manual_review"
                manual += 1
            self._history.append(
                {
                    "request_id": req.request_id,
                    "order_id": req.order_id,
                    "reason": req.reason,
                    "status": req.status,
                    "refund_amount_krw": policy["refund_amount_krw"],
                }
            )
        return {"approved": approved, "manual_review": manual}

    def list_requests(self, reason: str = "", status: str = "") -> list[dict]:
        out = self._history if self._history else [r.__dict__.copy() for r in self._requests]
        if reason:
            out = [x for x in out if x.get("reason") == reason]
        if status:
            out = [x for x in out if x.get("status") == status]
        return out

    def summary_24h(self) -> dict:
        processed = self.list_requests()
        approved = len([x for x in processed if x.get("status") == "approved"])
        manual = len([x for x in processed if x.get("status") != "approved"])
        return {
            "requests_24h": len(processed),
            "auto_approved_24h": approved,
            "manual_queue_24h": manual,
            "avg_minutes": "-",
        }
