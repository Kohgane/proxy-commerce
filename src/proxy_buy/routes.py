"""POST /proxy/quote — 해외 구매자 공개 견적 (api_gate 밖, 허용 도메인 + IP당 호출 제한)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

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
