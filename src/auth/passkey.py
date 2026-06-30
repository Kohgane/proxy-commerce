"""src/auth/passkey.py — v40-D: 패스키(WebAuthn/FIDO2) 등록·인증.

비밀번호 대신 기기 저장 공개키로 로그인(지문·Face·기기 PIN). 피싱·유출에 강함. 구글 OAuth와 병행.
- 등록: 로그인 후 "이 기기에 패스키 등록" → navigator.credentials.create() → 서버가 공개키·credentialId 저장.
- 인증: navigator.credentials.get() → 서버가 서명 검증 → 세션 수립.
보안: 챌린지 1회용(세션 바인딩)·origin/RP ID 검증·자격증명 서버에만. 폴백: 미지원/미등록 → 구글/이메일.

webauthn 미설치/오류 시 라우트는 정직한 503(가짜 성공 0). 자세한 의존성은 requirements.txt.
"""
from __future__ import annotations

import base64
import logging
import os

from flask import Blueprint, jsonify, request, session

logger = logging.getLogger(__name__)

passkey_bp = Blueprint("passkey", __name__, url_prefix="/auth/passkey")


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _rp_id() -> str:
    """RP ID = 등록 origin의 호스트(포트 제외). env WEBAUTHN_RP_ID로 고정 가능(프로덕션 도메인)."""
    forced = os.getenv("WEBAUTHN_RP_ID", "").strip()
    if forced:
        return forced
    host = (request.host or "localhost").split(":")[0]
    return host


def _origin() -> str:
    forced = os.getenv("WEBAUTHN_ORIGIN", "").strip()
    if forced:
        return forced
    # Origin 헤더 우선(브라우저가 보낸 실제 origin), 없으면 request.host_url 기반.
    return request.headers.get("Origin") or request.host_url.rstrip("/")


def _rp_name() -> str:
    try:
        from src.utils.branding import get_brand_name_ko
        return get_brand_name_ko()
    except Exception:
        return "고가브릿지"


def _require_login():
    return session.get("user_id") or session.get("user_email")


# ---------------------------------------------------------------------------
# 등록(Registration) — 로그인 사용자가 이 기기에 패스키 생성
# ---------------------------------------------------------------------------

@passkey_bp.post("/register/options")
def register_options():
    uid = _require_login()
    if not uid:
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    try:
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria, ResidentKeyRequirement,
            UserVerificationRequirement, PublicKeyCredentialDescriptor,
        )
        from . import passkey_store
    except Exception as exc:
        logger.warning("webauthn 미설치/로드 실패: %s", exc)
        return jsonify({"ok": False, "error": "패스키 모듈을 사용할 수 없습니다(서버 설정 필요)."}), 503

    existing = passkey_store.list_for_user(str(uid), user_ids={session.get("user_id"), session.get("user_email")})
    exclude = []
    for c in existing:
        try:
            exclude.append(PublicKeyCredentialDescriptor(id=_b64url_decode(c["credential_id"])))
        except Exception:
            pass

    opts = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=str(uid).encode("utf-8"),
        user_name=str(session.get("user_email") or uid),
        user_display_name=str(session.get("user_name") or session.get("user_email") or uid),
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    session["_pk_reg_challenge"] = _b64url(opts.challenge)
    import json as _json
    return jsonify({"ok": True, "options": _json.loads(options_to_json(opts))})


@passkey_bp.post("/register/verify")
def register_verify():
    uid = _require_login()
    if not uid:
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    challenge_b64 = session.pop("_pk_reg_challenge", "")
    if not challenge_b64:
        return jsonify({"ok": False, "error": "등록 세션이 만료됐어요. 다시 시도해 주세요."}), 400
    try:
        from webauthn import verify_registration_response
        from . import passkey_store
    except Exception as exc:
        logger.warning("webauthn 로드 실패: %s", exc)
        return jsonify({"ok": False, "error": "패스키 모듈을 사용할 수 없습니다."}), 503

    data = request.get_json(force=True, silent=True) or {}
    cred = data.get("credential")
    label = (data.get("label") or "이 기기").strip()[:40]
    try:
        verification = verify_registration_response(
            credential=cred,
            expected_challenge=_b64url_decode(challenge_b64),
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
        )
    except Exception as exc:
        logger.warning("패스키 등록 검증 실패: %s", exc)
        return jsonify({"ok": False, "error": "패스키 검증에 실패했어요. 다시 시도해 주세요."}), 400

    ok = passkey_store.add_credential(
        credential_id=_b64url(verification.credential_id),
        user_id=str(uid),
        public_key=_b64url(verification.credential_public_key),
        sign_count=int(getattr(verification, "sign_count", 0) or 0),
        label=label,
    )
    if not ok:
        return jsonify({"ok": False, "error": "패스키 저장에 실패했어요."}), 502
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# 인증(Authentication) — 패스키로 로그인
# ---------------------------------------------------------------------------

@passkey_bp.post("/login/options")
def login_options():
    try:
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import UserVerificationRequirement
    except Exception as exc:
        logger.warning("webauthn 로드 실패: %s", exc)
        return jsonify({"ok": False, "error": "패스키 모듈을 사용할 수 없습니다."}), 503
    # usernameless(디스커버러블) — allow_credentials 비움. 기기가 자체 자격증명 선택.
    opts = generate_authentication_options(
        rp_id=_rp_id(),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    session["_pk_auth_challenge"] = _b64url(opts.challenge)
    import json as _json
    return jsonify({"ok": True, "options": _json.loads(options_to_json(opts))})


@passkey_bp.post("/login/verify")
def login_verify():
    challenge_b64 = session.pop("_pk_auth_challenge", "")
    if not challenge_b64:
        return jsonify({"ok": False, "error": "로그인 세션이 만료됐어요. 다시 시도해 주세요."}), 400
    try:
        from webauthn import verify_authentication_response
        from . import passkey_store
    except Exception as exc:
        logger.warning("webauthn 로드 실패: %s", exc)
        return jsonify({"ok": False, "error": "패스키 모듈을 사용할 수 없습니다."}), 503

    data = request.get_json(force=True, silent=True) or {}
    cred = data.get("credential") or {}
    cred_id = cred.get("id") or cred.get("rawId") or ""
    stored = passkey_store.get_by_credential_id(cred_id)
    if not stored:
        return jsonify({"ok": False, "error": "등록되지 않은 패스키예요. 구글/이메일로 로그인해 주세요."}), 400

    try:
        verification = verify_authentication_response(
            credential=cred,
            expected_challenge=_b64url_decode(challenge_b64),
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            credential_public_key=_b64url_decode(stored["public_key"]),
            credential_current_sign_count=int(stored.get("sign_count", 0) or 0),
        )
    except Exception as exc:
        logger.warning("패스키 인증 검증 실패: %s", exc)
        return jsonify({"ok": False, "error": "패스키 검증에 실패했어요."}), 400

    passkey_store.update_sign_count(cred_id, int(verification.new_sign_count))

    # 세션 수립(해당 user_id로). user_store에서 프로필 조회, 없으면 최소 세션.
    user_id = str(stored.get("user_id"))
    try:
        from .user_store import get_store
        user = get_store().find_by_id(user_id)
    except Exception:
        user = None
    try:
        from .views import establish_session
        if user is not None:
            establish_session(user, remember=True)
        else:
            session["user_id"] = user_id
            session["user_role"] = "seller"
            session.permanent = True
    except Exception as exc:
        logger.warning("패스키 세션 수립 실패: %s", exc)
        session["user_id"] = user_id
        session.permanent = True
    return jsonify({"ok": True, "redirect": "/seller/dashboard"})


# ---------------------------------------------------------------------------
# 관리 — 내 패스키 목록/삭제
# ---------------------------------------------------------------------------

@passkey_bp.get("/list")
def list_my():
    uid = _require_login()
    if not uid:
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    from . import passkey_store
    items = passkey_store.list_for_user(
        str(uid), user_ids={session.get("user_id"), session.get("user_email")})
    out = [{"credential_id": c.get("credential_id"), "label": c.get("label"),
            "created_at": c.get("created_at"), "last_used_at": c.get("last_used_at")} for c in items]
    return jsonify({"ok": True, "passkeys": out})


@passkey_bp.post("/delete")
def delete_my():
    uid = _require_login()
    if not uid:
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    from . import passkey_store
    data = request.get_json(force=True, silent=True) or {}
    cid = (data.get("credential_id") or "").strip()
    if not cid:
        return jsonify({"ok": False, "error": "credential_id가 필요합니다."}), 400
    ok = passkey_store.delete_credential(cid, user_ids={session.get("user_id"), session.get("user_email")})
    if not ok:
        return jsonify({"ok": False, "error": "삭제할 패스키를 찾지 못했어요."}), 200
    return jsonify({"ok": True})
