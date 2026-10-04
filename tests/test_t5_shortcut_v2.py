"""T5(오너 2026-09-30-H) — 단축어 최종 고정: 동작 셋 · 판단 0 · `v=2&text=…&clip=…`.

  ① 서버가 text·clip을 둘 다 받아 판단한다(공유 글에 링크 있으면 그것 → 없으면 클립보드의 링크)
  ② 결과 화면 「경로」·로그도 서버 기준
  ③ Z2(2026-10-04) 개정: 「구버전」은 **v를 실제로 보냈고** 그 값이 오너가 적어 둔 링크 버전보다 낮을 때만.
     v 없이 온 공유(운영 실측: 오늘 담긴 6건 전부 `?text=`만)나 링크 버전 모름이면 안 띄운다 — 같은 링크로 다시 깔아도
     또 뜨던 무한 루프(오너 실측)
  ④ 단축어엔 「URL 인코딩」 수식이 없어 **인코딩 없이** 온다 — text 속 `&`가 갈라져도 되살린다
  ⑤ 로그인 왕복에도 v·고른 값이 남는다 · v별 도착 수가 화면 C에 보인다
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote, unquote

import pytest

SHARE = ("【淘宝】https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt CZ356 "
         "「新中式双人书桌靠墙长条桌简约现代学生写字学习桌实木办公电脑桌」 点击链接直接打开")
CLIP = "https://e.tb.cn/h.9ClipOnlyAbCd?tk=ClipTok9"
TITLE_ONLY = "新中式"


@pytest.fixture
def client(monkeypatch):
    from src.collectors import link_diag
    # 이 환경은 e.tb.cn에 못 나간다 — 클립보드 링크만 「펴졌다」고 둔다(운영에선 서버가 리다이렉트를 따라가 편다).
    monkeypatch.setattr(link_diag, "resolve_short_link", lambda url: (
        {"ok": True, "item_id": "812345678901", "price": "", "currency": "", "reason": ""}
        if "ClipOnly" in url else {"ok": False, "reason": "offline"}))
    from src.db import image_translate_queue_pg as st
    if hasattr(st, "reset_for_tests"):
        st.reset_for_tests()
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-t5"
    return c


def _q(v, text, clip):
    parts = []
    if v is not None:
        parts.append(f"v={v}")
    if text is not None:
        parts.append("text=" + quote(text, safe=""))
    if clip is not None:
        parts.append("clip=" + quote(clip, safe=""))
    return "/seller/collect/share?" + "&".join(parts)


def _state(h):
    m = re.search(r'data-role="share-state" data-state="(\w+)"', h)
    route = re.search(r'data-role="share-src">경로: ([^<]+)<', h)
    return (m.group(1) if m else "?", route.group(1).strip() if route else "",
            'data-role="share-oldver"' in h)


# (v, text, clip) → (상태, 경로(실패 때만 화면에 뜸), 구버전 안내)
MATRIX = [
    (None, SHARE, None, "draft", "", False),       # Z2: v 없이 와도 담기고, 구버전 안내는 안 뜬다(루프 원인)
    (None, None, CLIP, "draft", "", False),        # 판단은 서버 몫 — v가 없어도 clip은 읽는다
    ("1", SHARE, "", "draft", "", False),          # 링크 버전을 모르면(기본) 안 띄운다
    ("1", "", "", "failed", "둘 다 비어 있음", False),
    ("2", SHARE, "", "draft", "", False),
    ("2", "", CLIP, "draft", "", False),
    ("2", TITLE_ONLY, CLIP, "draft", "", False),   # 공유 글엔 제목만 — 클립보드의 링크로
    ("2", SHARE, CLIP, "draft", "", False),        # 둘 다 링크면 공유 글이 이긴다
    ("2", "", "", "failed", "둘 다 비어 있음", False),
]


@pytest.mark.parametrize("v,text,clip,state,route,oldver", MATRIX)
def test_version_by_input_matrix(client, v, text, clip, state, route, oldver):
    h = client.get(_q(v, text, clip)).get_data(as_text=True)
    got_state, got_route, got_old = _state(h)
    assert got_state == state and got_old == oldver, (got_state, got_route, got_old)
    if route:
        assert got_route == route
    if v == "2" and not text and not clip:
        # O(2026-10-01): v2는 text·clip이 같은 값(단축어 입력) — 「단축어가 보낸 글이 비어 있어요」 + 처리 단계.
        assert "단축어가 보낸 글이 비어 있어요" in h and "复制链接" in h and 'data-stage="recv"' in h


def test_clipboard_link_is_used_when_share_text_has_none(client, caplog):
    with caplog.at_level(logging.INFO, logger="src.seller_console.views"):
        client.get(_q("2", TITLE_ONLY, CLIP))
    line = next(r.getMessage() for r in caplog.records if "[share] parts" in r.getMessage())
    assert "v=2 route=clip" in line and "clip(len=" in line
    assert all("ClipTok9" not in r.getMessage() for r in caplog.records)      # tk 봉인


def test_unencoded_query_is_recovered(client, caplog):
    """단축어엔 URL 인코딩 수식이 없다 — `&`가 든 공유 글이 그대로 와도 text·clip을 되살린다."""
    raw_text = "【淘宝】https://item.taobao.com/item.htm?spm=a1&id=812345678901 「书桌」"
    url = "/seller/collect/share?v=2&text=" + raw_text + "&clip=" + CLIP
    with caplog.at_level(logging.INFO, logger="src.seller_console.views"):
        h = client.get(url).get_data(as_text=True)
    line = next(r.getMessage() for r in caplog.records if "[share] parts" in r.getMessage())
    assert "route=share" in line and 'data-state="draft"' in h and "书桌" in h


def test_login_round_trip_keeps_version_and_choice():
    from src.order_webhook import app
    import src.seller_console.views as V
    old = V._AUTH_ENABLED
    V._AUTH_ENABLED = True
    try:
        r = app.test_client().get(_q("2", "", CLIP))
    finally:
        V._AUTH_ENABLED = old
    nxt = unquote(r.headers["Location"])
    assert r.status_code == 302 and "v=2" in nxt and "ClipOnlyAbCd" in nxt and "src=clip" in nxt


def test_version_counts_show_on_make_screen(client):
    client.get(_q("2", SHARE, ""))
    client.get(_q(None, SHARE, None))
    from src.seller_console.help_settings import share_version_counts
    assert share_version_counts().get("v2", 0) >= 1 and share_version_counts().get("v0", 0) >= 1
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    h = c.get("/seller/guide/iphone/make").get_data(as_text=True)
    # Z2: 라벨은 「무엇이 왔나」만(v=2로 옴 · v 없이 옴) — 「옛 단축어」라고 단정하지 않는다 + 링크 버전 칸
    assert 'data-role="make-version-counts"' in h and "v=2로 옴" in h and "v 없이 옴(text만)" in h
    assert 'data-role="shortcut-version"' in h


def test_android_post_has_no_old_version_notice(client):
    h = client.post("/seller/collect/share", data={"title": "淘宝", "text": SHARE},
                    headers={"Sec-Fetch-Site": "none"}).get_data(as_text=True)
    assert 'data-state="draft"' in h and 'data-role="share-oldver"' not in h


def test_reinstall_notice_only_when_the_link_is_really_newer(client, monkeypatch):
    """Z2: 오너가 화면 C에 「이 링크의 단축어 v=2」를 적어 둔 뒤에만 — v=1을 **실어 보낸** 단축어에게 다시 설치를 권한다."""
    from src.seller_console import help_settings as H
    H.save_ios_shortcut_url("https://www.icloud.com/shortcuts/abcdef0123456789", "2")
    try:
        assert _state(client.get(_q("1", SHARE, "")).get_data(as_text=True))[2] is True
        assert _state(client.get(_q(None, SHARE, None)).get_data(as_text=True))[2] is False   # v 안 실음 = 판단 안 함
        assert _state(client.get(_q("2", SHARE, "")).get_data(as_text=True))[2] is False
    finally:
        H.save_ios_shortcut_url("")
