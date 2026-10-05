"""L1(오너 2026-10-05) — 공개 론칭 페이지: 랜딩 · /pricing · /terms · /privacy · /contact · 공통 푸터.

카카오쇼핑(톡스토어)·ESM 심사자가 로그인 없이 서비스를 확인한다. 로그인 세션이면 / 는 기존처럼 콘솔.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def client():
    from src.order_webhook import app
    from src.public_site import stats
    stats.reset()
    return app.test_client()


def _h(c, path):
    r = c.get(path)
    return r.status_code, r.get_data(as_text=True)


def test_root_anonymous_is_landing_with_l1_sections(client):
    code, h = _h(client, "/")
    assert code == 200 and 'data-role="l1-summary"' in h and "해외 상품 링크 하나로" in h
    assert 'data-role="l1-stats"' in h and 'data-role="l1-shots"' in h and h.count("/public-static/l1/shot-") == 3
    assert 'data-role="cta-signup"' in h and 'href="/auth/signup"' in h and 'data-role="cta-contact"' in h
    for m in ("쿠팡", "네이버 스마트스토어", "Shopify", "WooCommerce"):
        assert f'data-role="market-live">{m}<' in h
    for m in ("지마켓·옥션(ESM)", "카카오 톡스토어", "11번가", "롯데온"):
        assert f'data-role="market-soon">{m} <span>준비 중</span>' in h
    assert 'data-role="site-footer"' in h and "사업자등록번호 217-21-25749" in h and "대표 고우진" in h
    # 가짜 KPI 목업(총 수집 128 · 오늘 12) 제거 — 숫자는 DB 실측만
    assert '<div class="v">128</div>' not in h and "Amazon" not in h


def test_root_logged_in_goes_to_console(client):
    with client.session_transaction() as s:
        s["user_id"] = "seller-l1"
    r = client.get("/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/seller/")


@pytest.mark.parametrize("path,marker", [("/pricing", "public-pricing"), ("/terms", "public-terms"),
                                         ("/privacy", "public-privacy"), ("/contact", "public-contact")])
def test_public_pages_200_with_footer(client, path, marker):
    code, h = _h(client, path)
    assert code == 200 and f'data-role="{marker}"' in h and "사업자등록번호 217-21-25749" in h
    assert "noindex" not in h and 'data-role="legal-version"' in h


def test_footer_hides_empty_env_and_shows_set_env(client, monkeypatch):
    for k in ("BIZ_MAILORDER_NO", "BIZ_ADDRESS", "CONTACT_EMAIL", "LEGAL_OWNER_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    _c, h = _h(client, "/terms")
    assert 'data-role="biz-mailorder"' not in h and "통신판매업신고번호" not in h
    assert 'data-role="biz-address"' not in h and 'data-role="biz-email"' not in h and "BIZ_" not in h
    monkeypatch.setenv("BIZ_MAILORDER_NO", "2026-서울강남-01234")
    monkeypatch.setenv("BIZ_ADDRESS", "서울특별시 어딘가 1")
    monkeypatch.setenv("CONTACT_EMAIL", "help@example.com")
    _c, h = _h(client, "/terms")
    assert "통신판매업신고번호 2026-서울강남-01234" in h and "주소 서울특별시 어딘가 1" in h and "mailto:help@example.com" in h


def test_stats_are_real_counts(client):
    from src.public_site import stats
    from src.seller_console import collect_history_store as S
    from src.db import market_registrations_pg as R
    stats.reset()
    before = stats.live()
    S.append(source="share_text", url="https://item.taobao.com/item.htm?id=1", seller_id="l1-stats", title="x",
             price="", currency="", extra={})
    stats.reset()
    after = stats.live()
    assert after["collected"] == before["collected"] + 1
    assert after["registered"] == sum(1 for r in R._MEM.values() if r.get("status") != "rejected")
    assert after["markets"] is None                         # 인메모리(개발)는 모름 → 화면 「—」(0으로 꾸미지 않음)
    _c, h = _h(client, "/")
    assert f'data-role="stat-collected">{after["collected"]:,}<' in h and 'data-role="stat-markets">—<' in h


def test_stats_failure_shows_dash(client, monkeypatch):
    from src.public_site import stats
    monkeypatch.setattr(stats, "_collected", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    stats.reset()
    _c, h = _h(client, "/")
    assert 'data-role="stat-collected">—<' in h


def test_terms_skeleton(client):
    _c, h = _h(client, "/terms")
    for must in ("제1조 서비스", "상품 등록 · 등록한 상품의 수정 · 주문 조회", "셀러가 검수 화면에서 확인하고 결정",
                 "타인의 마켓 API 키", "지식재산권을 침해하는 상품", "베타 기간으로 전 기능이 무료", "적용 30일 전",
                 "해지", "데이터", "마켓의 정책·카테고리·API 규격이 바뀌어", "API의 장애", "대한민국 법"):
        assert must in h, must


def test_privacy_skeleton(client):
    _c, h = _h(client, "/privacy")
    for must in ("이메일", "마켓 API 키", "상품 데이터", "구매자 정보", "암호화해 저장하고 평문으로 저장하지 않습니다",
                 "구매자 원본 정보는 저장하지 않습니다", "마켓 API 호출", "파파고", "DeepL", "Azure", "OpenAI",
                 "텐센트 클라우드", "Cloudinary", "온바운드", "싱가포르", "중국", "보유기간", "파기",
                 "열람·정정·삭제", "개인정보 보호책임자: <strong>고우진</strong>"):
        assert must in h, must


def test_effective_date_and_version_env(client, monkeypatch):
    monkeypatch.setenv("LEGAL_EFFECTIVE_DATE", "2026-11-01")
    monkeypatch.setenv("LEGAL_VERSION", "v1.1")
    _c, h = _h(client, "/privacy")
    assert "v1.1 · 시행일 2026-11-01" in h and "약관·개인정보처리방침 v1.1 (시행 2026-11-01)" in h
    _c, t = _h(client, "/privacy.txt")
    assert "v1.1" in t and "2026-11-01" in t


def test_pricing_beta_and_env(client, monkeypatch):
    monkeypatch.setenv("PLAN_FREE_MONTHLY_ITEMS", "250")
    _c, h = _h(client, "/pricing")
    assert "지금은 전 기능 무료(베타)입니다." in h and 'data-role="free-items">250건' in h
    assert 'data-role="pro-price">준비 중' in h and "결제하기" not in h and "toss" not in h.lower()
    monkeypatch.delenv("PLAN_FREE_MONTHLY_ITEMS", raising=False)
    assert 'data-role="free-items">100건' in _h(client, "/pricing")[1]


def test_contact_email_and_telegram(client, monkeypatch):
    for k in ("CONTACT_EMAIL", "LEGAL_OWNER_EMAIL", "CONTACT_TELEGRAM_URL"):
        monkeypatch.delenv(k, raising=False)
    _c, h = _h(client, "/contact")
    assert 'data-role="contact-none"' in h and "<form" not in h
    monkeypatch.setenv("CONTACT_EMAIL", "help@example.com")
    monkeypatch.setenv("CONTACT_TELEGRAM_URL", "https://t.me/gogabridj_bot")
    _c, h = _h(client, "/contact")
    assert 'data-role="contact-email"' in h and "mailto:help@example.com" in h
    assert 'href="https://t.me/gogabridj_bot"' in h and "<form" not in h
    monkeypatch.setenv("CONTACT_TELEGRAM_URL", "javascript:alert(1)")              # t.me 링크만
    assert 'data-role="contact-telegram"' not in _h(client, "/contact")[1]


def test_console_footer_and_service_info(client):
    with client.session_transaction() as s:
        s["user_id"] = "seller-l1"
        s["email"] = "seller@example.com"
    _c, h = _h(client, "/seller/me")
    assert 'data-role="site-footer"' in h and "사업자등록번호 217-21-25749" in h
    assert 'data-role="service-info"' in h and 'href="/terms"' in h and 'href="/pricing"' in h


def test_landing_shots_are_served(client):
    for name in ("shot-share", "shot-review", "shot-result"):
        r = client.get(f"/public-static/l1/{name}.png")
        assert r.status_code == 200 and r.data[:8] == b"\x89PNG\r\n\x1a\n"
