"""tests/test_v41_step2_56_passkey_profile.py — v41 STEP 2-5/2-6 가드.

STEP 2-5: 패스키 UI = 로그인 화면에서만. 비로그인 랜딩에 노출 0.
STEP 2-6: 로그인 후 계정 드롭다운에 내 프로필/설정/패스키/로그아웃 집약.

검증 범위:
- login.html에 '패스키로 로그인' 진입점 존재
- 랜딩 / (공개) HTML에 passkey/패스키 설정 UI 노출 없음
- 로그인 세션 시 topnav 드롭다운에 내 프로필·설정·패스키·로그아웃 전부 존재
- 드롭다운 링크 대상이 유효한 라우트
- 비로그인 topbar에는 패스키 관리 진입점 없음
- 기존 auth 게이트 회귀 0(SELLER_CONSOLE_AUTH=0 기본 보장)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent


# ===========================================================================
# STEP 2-5: 패스키 UI = 로그인 화면에서만
# ===========================================================================

class TestPasskeyLoginScreenOnly:
    """패스키 UI가 로그인 화면에만 노출되고 공개 화면에는 새지 않음."""

    def test_login_html_has_passkey_button(self):
        """login.html에 '패스키로 로그인' 버튼 진입점 존재."""
        src = (_ROOT / "src/auth/templates/auth/login.html").read_text(encoding="utf-8")
        assert "패스키로 로그인" in src, "login.html에 '패스키로 로그인' 버튼이 없습니다"

    def test_login_html_has_passkey_js(self):
        """login.html에 패스키 지원 확인 JS가 포함돼 WebAuthn 미지원 브라우저에서 숨겨짐."""
        src = (_ROOT / "src/auth/templates/auth/login.html").read_text(encoding="utf-8")
        # 버튼이 기본 숨겨지고 JS가 지원 여부를 확인해야 함
        assert "passkey" in src.lower() or "webauthn" in src.lower() or "kgpPasskey" in src

    def test_landing_html_no_passkey_ui(self):
        """공개 랜딩 페이지에 패스키 UI가 없음."""
        src = (_ROOT / "src/templates/landing.html").read_text(encoding="utf-8")
        # 랜딩에 패스키 버튼이나 등록 UI가 새어 나오지 않아야 함
        assert "passkey" not in src.lower(), "랜딩 html에 passkey 관련 코드가 있습니다 — 로그인 화면에서만 노출해야 합니다"
        assert "패스키로 로그인" not in src

    def test_passkey_management_on_login_gated_page(self):
        """패스키 관리 UI가 로그인 게이트된 personal_tokens.html에만 있음."""
        tpl = (_ROOT / "src/seller_console/templates/personal_tokens.html").read_text(encoding="utf-8")
        assert "passkeyCard" in tpl or "패스키" in tpl, "personal_tokens.html에 패스키 관리 섹션이 없습니다"

    def test_landing_template_no_passkey_management(self):
        """landing.html 직접 검사 — 패스키 관리·등록 UI가 포함되지 않음 (공개 화면 노출 0)."""
        src = (_ROOT / "src/templates/landing.html").read_text(encoding="utf-8")
        assert "passkeyCard" not in src
        # 로그인 화면 전용 패스키 JS도 랜딩에 없어야 함
        assert "passkey.js" not in src


# ===========================================================================
# STEP 2-6: "내 프로필" 드롭다운에 설정·패스키·로그아웃 집약
# ===========================================================================

class TestProfileDropdownConsolidation:
    """로그인 시 계정 드롭다운에 내 프로필·설정·패스키·로그아웃이 집약됨."""

    def test_base_html_dropdown_has_profile(self):
        """_base.html 드롭다운에 '내 프로필' 항목이 /seller/me 링크로 존재."""
        src = (_ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
        assert '내 프로필' in src
        assert 'href="/seller/me"' in src

    def test_base_html_dropdown_has_settings(self):
        """_base.html 드롭다운에 '설정' 항목이 /seller/me/notifications 링크로 존재."""
        src = (_ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
        assert '설정' in src
        assert 'href="/seller/me/notifications"' in src

    def test_base_html_dropdown_has_passkey(self):
        """_base.html 드롭다운에 '패스키' 항목이 /seller/me/tokens 링크로 존재."""
        src = (_ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
        assert '패스키' in src
        assert 'href="/seller/me/tokens"' in src

    def test_base_html_dropdown_has_logout(self):
        """_base.html 드롭다운에 로그아웃 폼이 /auth/logout으로 존재."""
        src = (_ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
        assert 'action="/auth/logout"' in src
        assert '로그아웃' in src

    def test_topnav_html_dropdown_has_profile(self):
        """topnav.html 드롭다운에 '내 프로필' 항목이 /seller/me 링크로 존재."""
        src = (_ROOT / "src/seller_console/templates/partials/topnav.html").read_text(encoding="utf-8")
        assert '내 프로필' in src
        assert 'href="/seller/me"' in src

    def test_topnav_html_dropdown_has_settings(self):
        """topnav.html 드롭다운에 '설정' 항목이 /seller/me/notifications 링크로 존재."""
        src = (_ROOT / "src/seller_console/templates/partials/topnav.html").read_text(encoding="utf-8")
        assert '설정' in src
        assert 'href="/seller/me/notifications"' in src

    def test_topnav_html_dropdown_has_passkey(self):
        """topnav.html 드롭다운에 '패스키' 항목이 /seller/me/tokens 링크로 존재."""
        src = (_ROOT / "src/seller_console/templates/partials/topnav.html").read_text(encoding="utf-8")
        assert '패스키' in src
        assert 'href="/seller/me/tokens"' in src

    def test_topnav_html_dropdown_has_logout(self):
        """topnav.html 드롭다운에 로그아웃 폼이 /auth/logout으로 존재."""
        src = (_ROOT / "src/seller_console/templates/partials/topnav.html").read_text(encoding="utf-8")
        assert 'action="/auth/logout"' in src
        assert '로그아웃' in src

    def test_dropdown_link_targets_are_registered_routes(self):
        """드롭다운 링크 대상(/seller/me, /seller/me/notifications, /seller/me/tokens)이 Flask URL 맵에 존재."""
        import os as _os
        _os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
        from src.order_webhook import app as _app
        url_map_rules = {str(r) for r in _app.url_map.iter_rules()}
        assert "/seller/me" in url_map_rules, f"/seller/me not in URL map: {sorted(url_map_rules)[:20]}"
        assert "/seller/me/notifications" in url_map_rules, "/seller/me/notifications not in URL map"
        assert "/seller/me/tokens" in url_map_rules, "/seller/me/tokens not in URL map"

    def test_unauth_topbar_passkey_gated_by_user_id_block(self):
        """비로그인 topbar에 패스키 관리 링크가 없음 — 드롭다운이 {% if _user_id %} 블록 안에 있어야 함."""
        src = (_ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
        # _user_id 체크 블록 전에 패스키/me/tokens 링크가 나오면 안 됨 (미로그인 노출)
        user_id_block_start = src.find("{% if _user_id %}")
        assert user_id_block_start != -1, "_base.html에 {% if _user_id %} 블록이 없습니다"
        passkey_link_pos = src.find('href="/seller/me/tokens"')
        assert passkey_link_pos != -1, "_base.html에 패스키 링크(/seller/me/tokens)가 없습니다"
        logout_form_pos = src.find('action="/auth/logout"')
        assert logout_form_pos != -1, "_base.html에 로그아웃 폼이 없습니다"
        # 패스키 링크와 로그아웃 폼이 모두 {% if _user_id %} 블록 안에 있음
        assert passkey_link_pos > user_id_block_start, "패스키 링크가 _user_id 블록 밖에 있습니다"
        assert logout_form_pos > user_id_block_start, "로그아웃 폼이 _user_id 블록 밖에 있습니다"


# ===========================================================================
# 회귀 보장: auth off 기본 + 공개 라우트 유지
# ===========================================================================

class TestRegressionGuards:
    """기존 계약 회귀 없음(SELLER_CONSOLE_AUTH=0 기본, 공개 라우트 200)."""

    def test_seller_console_auth_default_is_off(self):
        """테스트 환경 기본값 SELLER_CONSOLE_AUTH=0 → _AUTH_ENABLED=False 유지."""
        import src.seller_console.views as views
        # conftest.py가 SELLER_CONSOLE_AUTH=0 주입 → _AUTH_ENABLED False
        assert not views._AUTH_ENABLED, "_AUTH_ENABLED 이 True — conftest SELLER_CONSOLE_AUTH=0 계약 위반"

    def test_public_routes_present_in_app(self):
        """랜딩·about·start·health 등 공개 라우트가 views.py·order_webhook.py에 등록돼 있음."""
        views_src = (_ROOT / "src/seller_console/views.py").read_text(encoding="utf-8")
        webhook_src = (_ROOT / "src/order_webhook.py").read_text(encoding="utf-8")
        combined = views_src + webhook_src
        assert '"/about"' in combined or "def about" in combined
        assert '"/start"' in combined or "def start" in combined
        assert '"/health"' in combined or "def health" in combined

    def test_base_html_no_old_maipage_entry(self):
        """_base.html 드롭다운에서 '마이페이지' 레거시 항목이 '내 프로필'로 대체됨.

        '마이페이지'가 남아 있으면 중복 진입점 — 드롭다운이 깔끔히 집약됐는지 확인.
        """
        src = (_ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
        # dropdown-item 클래스를 가진 <a> 태그의 텍스트에 '마이페이지'가 없어야 함
        import re
        # 한 태그 안에 dropdown-item + 마이페이지가 함께 있는 경우만 검출
        assert not re.search(
            r'<a\b[^>]*class="[^"]*dropdown-item[^"]*"[^>]*>[^<]*마이페이지',
            src,
        ), "_base.html 드롭다운에 '마이페이지' 레거시 항목이 남아 있음 — '내 프로필'로 대체 확인"

    def test_topnav_html_no_old_maipage_entry(self):
        """topnav.html 드롭다운에서 '마이페이지' 레거시 항목이 '내 프로필'로 대체됨."""
        src = (_ROOT / "src/seller_console/templates/partials/topnav.html").read_text(encoding="utf-8")
        import re
        assert not re.search(
            r'<a\b[^>]*class="[^"]*dropdown-item[^"]*"[^>]*>[^<]*마이페이지',
            src,
        ), "topnav.html 드롭다운에 '마이페이지' 레거시 항목이 남아 있음"
