"""V41-1(오너 2026-10-28 15:32 「간결·임팩트」 + 14:18/15:32 레인 네이밍) — 사이드바·탑바 정리 + 레인 셋(로드·오션·레일) 계약."""
from __future__ import annotations

import os
import re

import pytest

from src import lane as L

BASE = open("src/seller_console/templates/_base.html", encoding="utf-8").read()
APP_CSS = open("src/static/app.css", encoding="utf-8").read()
CONSOLE_CSS = open("src/seller_console/static/console.css", encoding="utf-8").read()


@pytest.fixture()
def client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-v41"; s["user_email"] = "v41@test.local"; s["user_role"] = "seller"
        yield c


def _drawer(html: str) -> str:
    i = html.find('id="sidebarDrawer"'); j = html.find("</nav>", i)
    return html[i:j]


# ── 레인 셋 ──────────────────────────────────────────────────────────────────

def test_three_lanes_with_owner_names():
    assert set(L.LANES) == {"import", "export", "rail"} and L.LANE_ORDER == ("import", "export", "rail")
    assert L.LANES["import"]["name_ko"] == "로드" and L.LANES["export"]["name_ko"] == "오션" and L.LANES["rail"]["name_ko"] == "레일"
    r = L.LANES["rail"]
    assert r["lang"] == "ko" and r["currency"] == "KRW" and r["sourcing"] == "domestic"
    assert r["target_markets"] == ["coupang", "smartstore", "elevenst"]       # 수입 레인과 같은 국내 마켓(같은 등록 코드)
    assert L.normalize_lane("rail") == "rail" and L.get_lane("rail", "en-US") == "rail"
    assert L.default_lane_for("ko-KR") == "import" and L.default_lane_for("en-US") == "export"   # 기본값 불변


def test_lane_set_rail_cookie(client):
    r = client.get("/lane/set?lane=rail&next=/seller/dashboard")
    assert r.status_code == 302
    cookies = " ".join(r.headers.getlist("Set-Cookie"))
    assert "kgp_lane=rail" in cookies and "kgp_currency=KRW" in cookies and "kgp_lang=" not in cookies


def test_gate_renders_three_cards_same_mark(client):
    html = client.get("/lane").get_data(as_text=True)
    for lid, name in (("import", "로드"), ("export", "오션"), ("rail", "레일")):
        assert f'data-lane="{lid}"' in html and f"/lane/set?lane={lid}" in html and name in html
    assert html.count('class="lane-card-mark"') == 3                      # 다리 마크는 셋 다 같다
    assert "운영할 방식을 선택하세요" in html and "레인 고르기" in html
    assert not re.search(r"lane-card[^>]*style=", html)                    # 인라인 스타일 0 — 토큰 단일소스


def test_lane_accent_tokens_reference_existing_tokens_only():
    for name in ("--lane-road-accent", "--lane-ocean-accent", "--lane-rail-accent"):
        m = re.search(rf"{name}:\s*([^;]+);", APP_CSS)
        assert m and m.group(1).strip().startswith("var(--"), name       # 새 색 발명 0
    assert not re.search(r"\.lane-card[^{]*\{[^}]*#[0-9a-fA-F]{3,6}", APP_CSS)   # 하드코딩 hex 0


# ── 사이드바 = 메뉴만 ───────────────────────────────────────────────────────

def test_sidebar_first_screen_is_menu_only(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    d = _drawer(html)
    more_at = d.find('id="sidebarMore"')
    assert more_at > 0
    head = d[:more_at]
    # 접힌 「계정·더보기」 위에는 메뉴 말고 다른 글자가 없다
    for noise in ("개인정보처리방침", "이용약관", "/auth/logout", "홈 화면에 앱 설치", "사업자등록번호", "내 작업공간 ·"):
        assert noise not in head, noise
    # 요소는 그대로 — 접힌 안에 있다(F21 로그아웃 · L1 사업자 정보 · F30 관리자 · 언어)
    tail = d[more_at:]
    for keep in ("/auth/logout", "data-role=\"site-footer\"", "개인정보처리방침", "kgp-sheet-lang"):
        assert keep in tail, keep
    assert 'data-role="console-brand"' in head and 'data-role="brand-lane"' in head   # 로고 + 레인 워드마크
    assert "셀러 콘솔 ·" not in head.replace('class="visually-hidden">셀러 콘솔', "")   # 꼬리표는 보이지 않는다


def test_topbar_one_accent_avatar_only(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    i = html.find('class="console-topbar"'); j = html.find("</header>", i)
    top = html[i:j]
    assert 'pc-badge pc-badge-on">셀러' not in top                           # 「셀러」 뱃지 제거
    assert "console-topbar-account" in top and "console-avatar" in top     # 계정 = 아바타
    before_menu = re.sub(r'(aria-label|title)="[^"]*"', "", top.split("dropdown-menu")[0])
    assert "v41@test.local" not in before_menu                              # 이메일은 메뉴 밖에 글자로 안 보인다(접근성 라벨만)
    assert 'data-role="lane-switch"' in top and "로드 ▾" in top              # 레인 이름으로 바꾸기
    assert "btn-group-sm" not in top                                        # 언어 버튼 쌍은 메뉴 안으로


def test_brand_lane_wordmark_follows_cookie(client):
    client.set_cookie("kgp_lane", "rail")
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "console-brand-lane-rail" in html and ">레일<" in html


def test_every_new_class_has_a_css_home():
    for cls in ("console-brand-mark", "console-brand-name", "console-brand-lane", "console-topbar-lane", "console-topbar-account",
                "console-avatar-sm", "console-sidebar-more", "console-sidebar-more-summary", "console-lane-switch"):
        assert f".{cls}" in CONSOLE_CSS, cls
    for cls in ("lane-gate", "lane-grid", "lane-card", "lane-card-accent", "lane-card-mark", "lane-card-keystone", "lane-card-name", "lane-card-cta"):
        assert f".{cls}" in APP_CSS, cls
