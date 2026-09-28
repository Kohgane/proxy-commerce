"""M3-iOS 보충(오너 2026-09-28) — 「아이폰에서 수집하기」 화면 A·B(공개)·C(오너) · 결과 화면 · 빈 결과 가짜 성공.

  ① 화면 A(설치하기)·B(사용하기)는 **로그인 없이** 열린다 · 오너 문구 그대로 · 캡처 자리 6개
  ② 설치 링크는 관리자 설정값(iCloud 단축어 링크만) — 비어 있으면 버튼 대신 「준비 중」
  ③ 화면 C는 관리자만
  ④ 결과 화면 = 큰 글자 + 버튼 2개(목록 보기 · 하나 더 담기)
  ⑤ 수집 코어가 **빈 결과**(제목·사진·가격 모두 없음)를 저장해 ok를 내던 가짜 성공 — 저장 0 · 사이트 사유
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


@pytest.fixture
def anon():
    import src.seller_console.views as V
    from src.order_webhook import app
    old = V._AUTH_ENABLED
    V._AUTH_ENABLED = True                      # 로그인 강제 상태에서도 공개로 열려야 한다
    try:
        yield app.test_client()
    finally:
        V._AUTH_ENABLED = old


@pytest.fixture(autouse=True)
def _clean_state():
    from src.db import image_translate_queue_pg as st
    if hasattr(st, "reset_for_tests"):
        st.reset_for_tests()
    yield


def test_install_page_is_public_and_verbatim(anon, monkeypatch):
    monkeypatch.delenv("IOS_SHORTCUT_URL", raising=False)
    r = anon.get("/seller/guide/iphone")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    for s in ("아이폰으로 상품 담기 — 처음 한 번만 설정", "아래 파란 버튼을 누르세요.",
              "화면에 「고가브릿지로 수집」이 뜨면 맨 아래 「단축어 추가」를 누르세요.",
              "이 단축어는 상품 주소를 고가브릿지에 보내는 일만 합니다.",
              "사파리(나침반 모양 앱)를 열고", "kohganepercentiii.com", "크롬 앱이 아니라 꼭 사파리여야 합니다.",
              "끝. 이제 아래 「사용하기」대로 하면 됩니다."):
        assert s in h, s
    assert 'data-role="install-soon"' in h and 'data-role="install-link"' not in h   # 링크 없으면 준비 중
    assert all(f'data-role="shot-{k}"' in h for k in ("a1", "a2", "a3"))


def test_use_page_is_public_and_verbatim(anon):
    h = anon.get("/seller/guide/iphone/use").get_data(as_text=True)
    for s in ("상품 담는 법", "타오바오 앱에서 담고 싶은 상품을 엽니다.", "오른쪽 위 「分享(공유)」를 누릅니다.",
              "나오는 목록을 옆으로 밀어 「고가브릿지로 수집」을 누릅니다.", "「담았어요」 화면이 나오면 성공입니다.",
              "컴퓨터에서 고가수집기를 켜면 나머지 사진과 옵션이 자동으로 채워집니다.", "안 될 때",
              "로그인하면 자동으로 이어집니다.", "(淘口令)", "공유 → 텔레그램 → 「고가브릿지 봇」 → 보내기. 똑같이 담깁니다."):
        assert s in h, s
    assert all(f'data-role="shot-{k}"' in h for k in ("b1", "b2", "b3"))


def test_install_link_is_an_admin_setting(monkeypatch):
    from src.order_webhook import app
    from src.seller_console.help_settings import ios_shortcut_url
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    page = c.get("/seller/guide/iphone/make").get_data(as_text=True)
    assert "「URL 열기」" in page and "https://kohganepercentiii.com/seller/collect/share?text=" in page
    assert "「공유 시트 유형」에서 「URL」과 「텍스트」만 체크." in page and "「iCloud 링크 복사」" in page
    bad = c.post("/seller/guide/iphone/make", data={"shortcut_url": "https://evil.example/x"}).get_data(as_text=True)
    assert 'data-role="make-err"' in bad and ios_shortcut_url() == ""
    ok = "https://www.icloud.com/shortcuts/0123456789abcdef0123456789abcdef"
    c.post("/seller/guide/iphone/make", data={"shortcut_url": ok})
    assert ios_shortcut_url() == ok
    h = app.test_client().get("/seller/guide/iphone").get_data(as_text=True)
    assert f'href="{ok}"' in h and 'data-role="install-soon"' not in h
    c.post("/seller/guide/iphone/make", data={"shortcut_url": ""})
    assert ios_shortcut_url() == ""


def test_make_page_is_admin_only():
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "seller-1", "seller"
    assert c.get("/seller/guide/iphone/make").status_code == 403
    assert c.post("/seller/guide/iphone/make", data={"shortcut_url": ""}).status_code == 403


def test_capture_slot_shows_a_file_when_the_owner_adds_one(anon, tmp_path, monkeypatch):
    import src.seller_console.views as V
    (tmp_path / "b2.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr(V, "_IPHONE_SHOTS_DIR", str(tmp_path))
    h = anon.get("/seller/guide/iphone/use").get_data(as_text=True)
    assert 'src="/seller/static/help/iphone/b2.png"' in h and h.count("화면 사진 준비 중") == 2


def test_empty_scrape_is_not_saved_anywhere(monkeypatch):
    """페이지를 못 읽으면 수집기는 빈 결과를 준다 — 그걸 「수집됨」으로 저장하던 가짜 성공."""
    import src.api.extension_api as ext
    from src.seller_console import collect_history_store as S

    class _Empty:
        title, images, price, currency = "", [], None, "USD"

    monkeypatch.setattr(ext, "_dispatcher_collect", lambda: (lambda url: _Empty()))
    before = len(S.list_items(seller_ids={"u-empty"}, days=30, limit=50) or [])
    r = ext.collect_one_url("https://www.temu.com/kr/goods.html?goods_id=601099512345", seller_id="u-empty")
    assert r["ok"] is False and r["error"].startswith("테무(www.temu.com)는 서버에서 상품 페이지를 읽을 수 없어요")
    assert len(S.list_items(seller_ids={"u-empty"}, days=30, limit=50) or []) == before

    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-empty"
    h = c.get("/seller/collect/share?text=https://www.temu.com/kr/goods.html?goods_id=601099512345").get_data(as_text=True)
    assert 'data-state="failed"' in h and "테무(www.temu.com)" in h
    assert len(S.list_items(seller_ids={"u-empty"}, days=30, limit=50) or []) == before


def test_result_screen_is_big_text_and_two_buttons():
    t = Path("src/seller_console/templates/collect_share_result.html").read_text(encoding="utf-8")
    assert t.count("sd-btn\"") == 2 and "목록 보기" in t and "하나 더 담기" in t
    for tpl in ("guide_iphone.html", "guide_iphone_make.html", "collect_share_result.html"):
        s = Path("src/seller_console/templates/" + tpl).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", s) and not re.search(r"[\U0001F300-\U0001FAFF]", s), tpl
