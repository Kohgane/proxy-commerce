"""POST /proxy/quote — 해외 구매자 공개 견적 (api_gate 밖, 허용 도메인 + IP당 호출 제한)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

import os
import re

from flask import Blueprint, jsonify, request

from .service import make_quote

bp = Blueprint("proxy_buy", __name__, url_prefix="/proxy")

_LIMIT, _WINDOW = 10, 600  # IP당 10분 10회
_hits = defaultdict(deque)
_lock = threading.Lock()


def _allowed(ip: str) -> bool:
    now = time.time()
    with _lock:
        q = _hits[ip]
        while q and now - q[0] > _WINDOW:
            q.popleft()
        if len(q) >= _LIMIT:
            return False
        q.append(now)
        return True


@bp.route("/quote", methods=["POST"])
def quote():
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0]).strip()
    if not _allowed(ip):
        return jsonify({"ok": False, "status": "rate_limited"}), 429
    d = request.get_json(silent=True) or {}
    url = str(d.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "status": "bad_request", "message": "url is required"}), 400
    opts = d.get("options") or {}
    try:
        w = float(opts["weight_kg"]) if opts.get("weight_kg") is not None else None
    except (TypeError, ValueError):
        w = None
    res = make_quote(url, country=str(d.get("country") or "US")[:2], weight_kg=w)
    return jsonify(res), (200 if res.get("ok") or res.get("status") in
                         ("manual_review", "unsupported_site", "prohibited", "over_cap") else 400)


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _admin_ok() -> bool:
    secret = os.getenv("CRON_SECRET")
    return bool(secret) and request.headers.get("X-Cron-Secret", "") == secret


@bp.route("/request", methods=["POST"])
def request_order():
    """구매자 주문 요청 — 견적이 quoted일 때만 승인 큐에 쌓는다(결제·구매는 승인 후, 자동 없음)."""
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0]).strip()
    if not _allowed(ip):
        return jsonify({"ok": False, "status": "rate_limited"}), 429
    d = request.get_json(silent=True) or {}
    email = str(d.get("email") or "").strip()
    url = str(d.get("url") or "").strip()
    if not url or not _EMAIL.match(email):
        return jsonify({"ok": False, "status": "bad_request", "message": "url and valid email are required"}), 400
    try:
        w = float(d["weight_kg"]) if d.get("weight_kg") is not None else None
    except (TypeError, ValueError):
        w = None
    res = make_quote(url, country=str(d.get("country") or "US")[:2], weight_kg=w)
    if res.get("status") != "quoted":
        return jsonify(res), 200
    from . import ledger
    from .service import current_fx
    row = ledger.enqueue(source_url=url, total_usd=res["total_usd"], title=res.get("title", ""),
                         email=email, price_krw=res.get("price_krw", 0), fx=current_fx() or 0)
    try:
        from src.notifications.telegram import send_telegram
        send_telegram(f"구매대행 승인 대기: {res.get('title','')[:40]} ${res['total_usd']} ({email})", urgency="info")
    except Exception:  # 알림 실패가 접수를 막지 않는다
        pass
    return jsonify({"ok": True, "status": "received", "request_id": row["id"],
                    "message": "Request received. We will confirm by email before any payment."}), 200


@bp.route("/admin/queue", methods=["GET"])
def admin_queue():
    if not _admin_ok():
        return jsonify({"ok": False}), 403
    from . import ledger
    return jsonify({"ok": True, "queue": ledger.queue()})


@bp.route("/admin/<order_id>/decide", methods=["POST"])
def admin_decide(order_id):
    if not _admin_ok():
        return jsonify({"ok": False}), 403
    d = request.get_json(silent=True) or {}
    to = str(d.get("to") or "")
    if to not in ("approved", "refused", "cancelled", "purchased", "shipped", "delivered"):
        return jsonify({"ok": False, "message": "invalid state"}), 400
    from . import ledger
    try:
        row = ledger.transition(order_id, to, purchase_ref=str(d.get("purchase_ref") or ""),
                                purchase_krw=d.get("purchase_krw"), carrier=str(d.get("carrier") or ""),
                                tracking_no=str(d.get("tracking_no") or ""), note=str(d.get("note") or ""))
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 409
    return jsonify({"ok": True, "order": row})
