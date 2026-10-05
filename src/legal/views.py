"""정적 법률 페이지 Blueprint (Phase 150)."""
from __future__ import annotations

from flask import Blueprint, Response

legal_bp = Blueprint("legal", __name__, template_folder="templates")



# L1(오너 2026-10-05): /privacy · /terms 본문은 `src/public_site`(약관 골격·사업자 정보·시행일 변수)로 옮겼다.
#   여기엔 크롤러·검증 도구용 텍스트판만 남긴다(같은 시행일·버전).


@legal_bp.get("/privacy.txt")
def privacy_txt():
    """개인정보처리방침 플레인 텍스트 버전 (크롤러/검증 도구용) — 본문은 /privacy."""
    from src.public_site import site_info
    si = site_info.info()
    content = (
        f"개인정보처리방침 / Privacy Policy ({si['legal_version']})\n"
        f"시행일: {si['effective_date']}\n\n"
        f"처리 항목: 이메일, 로그인 제공자 식별값, 접속 IP, 마켓 API 키(암호화 저장), 상품 데이터,\n"
        f"  주문 처리 시 구매자 정보 조회(원본 미저장, 일부 가린 값만 보관)\n"
        f"보유 기간: 해지 후 30일 안에 파기(마켓 API 키는 삭제·해지 즉시)\n"
        f"처리 위탁·제3자: 연동 마켓 API, 네이버 파파고, DeepL, Azure, OpenAI, 텐센트 클라우드, Cloudinary, 온바운드, Render, Supabase\n"
        f"국외 이전: Render(싱가포르), 텐센트 클라우드·온바운드(중국)\n"
        f"개인정보 보호책임자: {si['privacy_officer']}{(' <' + si['email'] + '>') if si['email'] else ''}\n"
        f"전문: /privacy\n"
    )
    return Response(content, mimetype="text/plain; charset=utf-8")


@legal_bp.get("/terms.txt")
def terms_txt():
    """서비스 이용약관 플레인 텍스트 버전 (크롤러/검증 도구용) — 본문은 /terms."""
    from src.public_site import site_info
    si = site_info.info()
    content = (
        f"서비스 이용약관 / Terms of Service ({si['legal_version']})\n"
        f"시행일: {si['effective_date']}\n\n"
        f"해외 상품 수집·번역·검수·다마켓 등록 SaaS. 등록 책임은 검수 후 등록하는 셀러에게 있습니다.\n"
        f"마켓 API 키 위임 범위: 상품 등록·수정·주문 조회. 타인 키 사용·지재권 침해 상품 등록 금지.\n"
        f"요금: 베타 무료, 변경 시 30일 전 고지. 준거법: 대한민국.\n"
        f"운영: {si['name']} · 대표 {si['ceo']} · 사업자등록번호 {si['reg_no']}\n"
        f"전문: /terms\n"
    )
    return Response(content, mimetype="text/plain; charset=utf-8")
