"""정적 법률 페이지 Blueprint (Phase 150)."""
from __future__ import annotations

import os

from flask import Blueprint, Response, render_template

legal_bp = Blueprint("legal", __name__, template_folder="templates")

_OWNER_NAME = os.getenv("LEGAL_OWNER_NAME", "Kohgane")
_OWNER_EMAIL = os.getenv("LEGAL_OWNER_EMAIL", "shanks8@hanmail.net")
_LAST_UPDATED = os.getenv("LEGAL_PRIVACY_LAST_UPDATED", "2026-05-11")


@legal_bp.get("/privacy")
def privacy():
    return render_template(
        "legal/privacy.html",
        owner_name=_OWNER_NAME,
        owner_email=_OWNER_EMAIL,
        last_updated=_LAST_UPDATED,
    )


@legal_bp.get("/terms")
def terms():
    return render_template(
        "legal/terms.html",
        owner_name=_OWNER_NAME,
        owner_email=_OWNER_EMAIL,
        last_updated=_LAST_UPDATED,
    )


@legal_bp.get("/privacy.txt")
def privacy_txt():
    """개인정보처리방침 플레인 텍스트 버전 (크롤러/검증 도구용)."""
    content = (
        f"개인정보처리방침 / Privacy Policy\n"
        f"시행일: {_LAST_UPDATED}\n\n"
        f"수집 항목: 이메일, OAuth provider ID, IP 주소\n"
        f"이용 목적: 셀러 자동화 서비스 제공\n"
        f"보유 기간: 탈퇴 후 30일\n"
        f"제3자 제공: 서비스 운영 목적 범위에서만 처리\n"
        f"책임자: {_OWNER_NAME} <{_OWNER_EMAIL}>\n"
    )
    return Response(content, mimetype="text/plain; charset=utf-8")


@legal_bp.get("/terms.txt")
def terms_txt():
    """서비스 이용약관 플레인 텍스트 버전 (크롤러/검증 도구용)."""
    content = (
        f"서비스 이용약관 / Terms of Service\n"
        f"시행일: {_LAST_UPDATED}\n\n"
        f"본 서비스는 셀러 자동화 SaaS입니다.\n"
        f"불법 상품 등록 및 외부 마켓 약관 위반을 금지합니다.\n"
        f"책임자: {_OWNER_NAME} <{_OWNER_EMAIL}>\n"
    )
    return Response(content, mimetype="text/plain; charset=utf-8")
