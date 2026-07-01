"""tests/test_v40_d2_passkey_privacy.py — v40-D(개정): 패스키 개인정보 보호 최우선.

재전송 addendum: 자격증명·생체정보 서버 평문 저장 절대 금지. 공개키·credentialId만.
- 저장 스키마에 private key/비밀번호/생체 필드 0. 지문·얼굴은 기기에만(WebAuthn 설계).
- 구글 로그인 중심 + 패스키(선택) 병행. UI에 개인정보 보호 명시.
"""
from __future__ import annotations

import os
from pathlib import Path


def test_store_schema_public_key_only():
    src = Path("src/auth/passkey_store.py").read_text(encoding="utf-8")
    # 저장 컬럼 = 공개키·credentialId·sign_count·라벨·시각만
    assert '_HEADER = ["credential_id", "user_id", "public_key", "sign_count", "label", "created_at", "last_used_at"]' in src
    # 개인키/비밀번호/생체 원본은 절대 저장 안 함
    for forbidden in ("private_key", "privateKey", "biometric", "fingerprint_data", "password"):
        assert forbidden not in src


def test_store_add_credential_signature_no_secret():
    # add_credential은 공개키만 받는다(개인키/생체 인자 없음)
    import inspect
    from src.auth import passkey_store
    params = set(inspect.signature(passkey_store.add_credential).parameters)
    assert "public_key" in params
    for forbidden in ("private_key", "biometric", "password", "secret"):
        assert forbidden not in params


def test_passkey_card_states_privacy():
    tpl = Path("src/seller_console/templates/personal_tokens.html").read_text(encoding="utf-8")
    assert "개인정보 보호" in tpl
    assert "이 기기에만" in tpl and "공개키" in tpl
    assert "평문 저장 0" in tpl


def test_google_login_primary_passkey_optional():
    login = Path("src/auth/templates/auth/login.html").read_text(encoding="utf-8")
    # 구글 로그인(중심) + 패스키(선택) 병행
    assert "/auth/google/start" in login
    assert "패스키로 로그인" in login


def test_stored_credential_is_public_only_at_runtime(monkeypatch):
    # 실제 저장 레코드에 공개키 외 비밀 필드가 섞이지 않음
    import src.auth.passkey_store as ps
    ps._in_memory[:] = []
    ps.add_credential(credential_id="cid1", user_id="u1", public_key="PUBKEY", sign_count=0, label="폰")
    rec = ps._in_memory[0]
    assert set(rec.keys()) == set(ps._HEADER)         # 정확히 스키마 필드만
    assert "PUBKEY" == rec["public_key"]
    assert not any("private" in k.lower() or "secret" in k.lower() for k in rec)
