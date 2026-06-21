"""market_relay_server_v8.py — Bluehost 고정 IP 마켓 릴레이 (무상태).

Render 앱이 보낸 '이미 서명된 요청'을 받아 고정 IP(Bluehost)에서 그대로 전달하고
응답만 돌려준다. 쿠팡·네이버 OpenAPI의 호출 IP 화이트리스트 대응.

배포(Bluehost / 모든 고정 IP 호스트):
    pip install flask requests
    export MARKET_RELAY_TOKEN="아주-긴-랜덤-토큰"      # Render 앱의 MARKET_RELAY_TOKEN과 동일
    gunicorn -w 2 -b 0.0.0.0:8800 market_relay_server_v8:app   # 또는 호스트 WSGI/Passenger
  → HTTPS 도메인(예: https://relay.yourdomain.com)을 Render 앱 MARKET_RELAY_URL 에 설정.
  → 이 서버의 공인 IP(`curl https://api.ipify.org`)를 쿠팡/네이버 허용 IP에 등록.

보안/정직:
  - Bearer 토큰 + HMAC(timestamp+body) 검증, 5분 시계 오차 허용(재전송 차단).
  - 허용 호스트(쿠팡/네이버)만 포워딩. 자격증명/페이로드 미저장, 키·바디 로깅 금지.
  - 실제 마켓 응답의 status/body만 패스스루(가짜 성공 없음).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

_TOKEN = os.environ.get("MARKET_RELAY_TOKEN", "")
_MAX_SKEW = int(os.environ.get("MARKET_RELAY_MAX_SKEW", "300"))
# 허용 호스트(화이트리스트) — 쿠팡/네이버 OpenAPI 도메인만.
_ALLOW_HOST_SUFFIXES = tuple(
    h.strip() for h in (os.environ.get(
        "MARKET_RELAY_ALLOW_HOSTS",
        "coupang.com,api-gateway.coupang.com,commerce.naver.com,api.commerce.naver.com",
    ).split(",")) if h.strip()
)


@app.get("/healthz")
def healthz():
    return jsonify(ok=True)


@app.post("/relay")
def relay():
    if not _TOKEN:
        return jsonify(error="relay not configured"), 503
    if request.headers.get("Authorization", "") != f"Bearer {_TOKEN}":
        return jsonify(error="unauthorized"), 401

    ts = request.headers.get("X-Relay-Timestamp", "")
    sig = request.headers.get("X-Relay-Signature", "")
    raw = request.get_data() or b""
    try:
        if not ts or abs(time.time() - int(ts)) > _MAX_SKEW:
            return jsonify(error="stale timestamp"), 401
    except (TypeError, ValueError):
        return jsonify(error="bad timestamp"), 401
    expect = hmac.new(_TOKEN.encode(), (ts + raw.decode("utf-8")).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return jsonify(error="bad signature"), 401

    try:
        spec = json.loads(raw)
    except ValueError:
        return jsonify(error="bad json"), 400

    url = spec.get("url", "")
    host = urlparse(url).netloc.lower()
    if not host or not any(host == h or host.endswith("." + h) or host.endswith(h) for h in _ALLOW_HOST_SUFFIXES):
        return jsonify(error="host not allowed"), 403

    try:
        resp = requests.request(
            spec.get("method", "GET"),
            url,
            headers=spec.get("headers") or {},
            data=(spec.get("body") or None),
            timeout=int(os.environ.get("MARKET_RELAY_TIMEOUT", "30")),
        )
        return jsonify(status=resp.status_code, body=resp.text)
    except requests.RequestException as exc:
        # 키/바디 로깅 금지 — 예외 타입만.
        return jsonify(status=502, body=json.dumps({"relay_error": type(exc).__name__})), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8800")))
