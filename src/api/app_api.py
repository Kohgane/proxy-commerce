"""앱 v1.1(오너 2026-11-23) — 아이폰 앱이 로그인된 웹뷰에서 부르는 두 입구.

· `POST /api/app/token` → `{"token": "kgp_…"}` — 공유 확장(쿠키 없음)이 `Authorization: Bearer`로 쓸 개인 토큰.
  personal_tokens 재사용(scope `collect.write`). 원문은 이 응답에만 — 저장은 해시뿐(기존 그대로).
· `POST /api/push/apns/register {token, env, bundle}` → 그 사용자의 기기로 등록(여러 대).

둘 다 **로그인 세션 필수**(미로그인 401 JSON). 다른 사이트가 이 입구를 부르지 못하게 `Sec-Fetch-Site`가
cross-site·same-site면 403 — 앱 웹뷰의 같은 출처 fetch는 `same-origin`이다.
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request, session

logger = logging.getLogger(__name__)

app_api_bp = Blueprint("app_api", __name__)


def _uid() -> str:
    try:
        return str(session.get("user_id") or session.get("user_email") or "").strip()
    except Exception:
        return ""


def _guard():
    if request.headers.get("Sec-Fetch-Site", "") in ("cross-site", "same-site"):
        return jsonify({"ok": False, "error": "다른 사이트에서 보낸 요청은 받지 않아요."}), 403
    if not _uid():
        return jsonify({"ok": False, "error": "로그인이 필요해요.", "login": "/auth/login"}), 401
    return None


@app_api_bp.post("/api/app/token")
def app_token():
    bad = _guard()
    if bad:
        return bad
    from src.auth.personal_tokens import TokenStoreCommitError, generate_token
    try:
        info = generate_token(_uid(), scopes=["collect.write"])
    except TokenStoreCommitError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception as exc:
        logger.warning("[app-token] 발급 실패: %s", type(exc).__name__)
        return jsonify({"ok": False, "error": "토큰을 만들지 못했어요 — 잠시 뒤 다시 열어 주세요."}), 503
    logger.info("[app-token] 아이폰 공유용 토큰 발급 user=%s", _uid())
    return jsonify({"ok": True, "token": info["raw_token"], "name": "iPhone 공유",
                    "expires_at": info.get("expires_at", "")})


@app_api_bp.post("/api/push/apns/register")
def apns_register():
    bad = _guard()
    if bad:
        return bad
    body = request.get_json(force=True, silent=True) or {}
    from src.notifications.apns import register
    res = register(_uid(), str(body.get("token") or ""), env=str(body.get("env") or "production"),
                   bundle=str(body.get("bundle") or ""))
    return jsonify(res), (200 if res.get("ok") else 400)
