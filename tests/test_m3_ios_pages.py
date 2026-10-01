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
    """T5(오너 2026-09-30-H)로 설치하기 화면을 다시 썼다 — 중국 유저 초보 기준 4단계 + 안 될 때 3줄."""
    monkeypatch.delenv("IOS_SHORTCUT_URL", raising=False)
    r = anon.get("/seller/guide/iphone")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    for s in ("아이폰으로 상품 담기 — 처음 한 번만 설정", "「단축어 추가」", "「分享(공유)」 → 「复制链接(링크 복사)」",
              "홈 화면의 「고가브릿지수집」", "안 될 때", "단축어가 구버전입니다", 'data-role="install-stages"'):
        assert s in h, s
    assert 'data-role="install-soon"' in h and 'data-role="install-link"' not in h   # 링크 없으면 준비 중
    assert all(f'data-role="shot-{k}"' in h for k in ("a1", "a2", "a3")) and 'data-role="shot-a4"' not in h
    # P(10-01) 오너 결정: 붙여넣기 허용 창 단계(옛 2단계) 삭제 — 그 창은 안 뜬다(실측).
    assert "붙여넣기를 허용하겠습니까" not in h
    # O(2026-10-01) 실측: 붙여넣기 허용 창은 뜨지 않았다 — 「허용 안 함」 안내 줄은 뺐다.
    assert 'data-role="install-paste-denied"' not in h


def test_use_page_is_public_and_verbatim(anon):
    h = anon.get("/seller/guide/iphone/use").get_data(as_text=True)
    for s in ("상품 담는 법", "타오바오 앱에서 담고 싶은 상품을 엽니다.", "오른쪽 위 「分享(공유)」를 누릅니다.",
              "나오는 목록을 옆으로 밀어 「고가브릿지수집」을 누릅니다.", "「담았어요」 화면이 나오면 성공입니다.",
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
    # M3-iOS-3(2026-09-30): 두 갈래(공유 시트·클립보드)가 src로 길을 싣는다.
    # T5(2026-09-30-H): 동작 셋 — `v=2&text=[단축어 입력]&clip=[클립보드]`.
    assert "「URL 열기」" in page and "https://kohganepercentiii.com/seller/collect/share?v=2&amp;u=" in page
    # O(2026-10-01): 두 자리 모두 「URL 인코딩」 결과 토큰 — 클립보드는 ①의 「입력이 없는 경우」로만.
    # P(10-01): 두 번 인코딩 — 두 자리 모두 ③(두 번째 인코딩) 결과. 티켓 방식(share-in) 안내도 같은 화면에.
    assert "u=<b>[③ 결과]</b>&amp;text=<b>[⑤ 결과]</b>" in page                          # Q: u가 앞
    assert "https://kohganepercentiii.com/seller/collect/share-in" in page
    assert "「공유 시트에 표시」 켬" in page and "「iCloud 링크 복사」" in page and 'data-role="make-arrivals"' in page
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
