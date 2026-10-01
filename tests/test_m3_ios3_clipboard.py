"""M3-iOS-3(오너 2026-09-30) — 클립보드 입력 확정 · 경로 표시 · 키별 원문 로그.

오너 캡처: 「담지 못했어요 — 공유 내용이 비어서 왔습니다 … 받은 내용: (비어 있음)」.
타오바오 「复制链接(링크 복사)」은 iOS 공유 목록을 거치지 않는다 → 단축어를 직접 누르면 입력이 비어 온다.

  ① 단축어가 `src=share|clip`으로 길을 싣고, 결과 화면이 「경로: 공유 시트 / 클립보드」로 보인다
  ② 비었을 때 누가 안 넘겼는지 사유가 다르다(앱이 안 넘김 / 클립보드가 빔)
  ③ 서버 로그: title·text·url 키마다 원문 길이 + 앞 60자(스크럽 후) — `tk` 값은 없다
  ④ 로그인 왕복에도 src가 남는다
  ⑤ 화면 A = 링크 복사 길(기본) + 캡처 자리 a4 · 화면 C = 두 갈래(공유 시트·클립보드)
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

import pytest

TK = "nyXpT7VA7lt"
LINK = f"https://e.tb.cn/h.8IcTrtZuTU19ieN?tk={TK}"


@pytest.fixture
def client(monkeypatch):
    from src.collectors import link_diag
    monkeypatch.setattr(link_diag, "resolve_short_link", lambda url: {"ok": False, "reason": "offline"})
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-ios3"
    return c


@pytest.mark.parametrize("src,route,why", [
    ("share", "경로: 공유 시트", "이 앱이 공유에 내용을 넘기지 않았어요"),
    ("clip", "경로: 클립보드", "클립보드가 비어 있어요"),
])
def test_empty_input_names_who_did_not_hand_it_over(client, src, route, why):
    h = client.get(f"/seller/collect/share?src={src}&text=").get_data(as_text=True)
    assert 'data-state="failed"' in h and route in h and why in h and "받은 내용: (비어 있음)" in h


def test_old_shortcut_without_src_is_routed_by_server_and_told_to_reinstall(client):
    """T5(2026-09-30-H): 경로는 **서버가 정한다** — src 없는 옛 단축어도 「공유 시트」로 보이고, 재설치 안내가 뜬다."""
    h = client.get("/seller/collect/share?text=" + quote("新中式")).get_data(as_text=True)
    assert "경로: 공유 시트" in h and "「新中式」" in h and 'data-role="share-oldver"' in h


def test_parts_log_has_lengths_and_scrubbed_previews(client, caplog):
    with caplog.at_level(logging.INFO, logger="src.seller_console.views"):
        client.get("/seller/collect/share?src=share&title=" + quote("新中式") + "&url=" + quote(LINK, safe=""))
    line = next(r.getMessage() for r in caplog.records if "[share] parts" in r.getMessage())
    assert "route=share" in line and "title(len=3,q='新中式')" in line and "text(len=0," in line
    assert f"link(len={len(LINK)}," in line and "e.tb.cn/h.8IcTrtZuTU19ieN" in line
    assert all(TK not in r.getMessage() for r in caplog.records)


def test_login_round_trip_keeps_src():
    from src.order_webhook import app
    import src.seller_console.views as V
    old = V._AUTH_ENABLED
    V._AUTH_ENABLED = True
    try:
        r = app.test_client().get("/seller/collect/share?src=clip&text=" + quote(LINK, safe=""))
    finally:
        V._AUTH_ENABLED = old
    assert r.status_code == 302 and "src%3Dclip" in r.headers["Location"]


def test_install_screen_has_clipboard_default_step_and_slot():
    """T5: 링크 복사(复制链接) → 홈 화면 단축어 1탭이 기본 길이다."""
    from src.order_webhook import app
    h = app.test_client().get("/seller/guide/iphone").get_data(as_text=True)
    a3, a4 = h.index('data-role="step-a3"'), h.index('data-role="step-a4"')
    assert "复制链接" in h[a3:a4] and "홈 화면의 「고가브릿지로 수집」" in h[a4:a4 + 600] and 'data-role="shot-a4"' in h


def test_make_screen_is_three_actions_without_branch():
    """O(2026-10-01) 최종 구조: ① 공유 시트에서 받기(없으면 클립보드) ② URL 인코딩 ③ URL 열기 — 판단 로직 0.

    T5의 「클립보드 가져오기」 **단독 동작**은 URL 열기에서 빈 값이었다(오너 실측) — 동작 목록에 없어야 한다.
    """
    t = Path("src/seller_console/templates/guide_iphone_make.html").read_text(encoding="utf-8")
    acts = [t.index(f'data-role="act-{i}"') for i in (1, 2, 3)]
    assert acts == sorted(acts) and 'data-role="act-4"' not in t
    for s in ("「입력이 없는 경우」 = <strong>「클립보드 가져오기」</strong>", "<strong>「URL 인코딩」</strong>",
              "<strong>「URL 열기」</strong>", "텍스트 · 리치 텍스트 · Safari 웹 페이지 · URL", "「훑어보기」", "「앱 및 2개」",
              "「단축어 입력」", 'data-role="make-clip-mine"', 'cshot("c1")', 'cshot("c2")', 'cshot("c3")'):
        assert s in t, s
    body = t.split('data-role="make-actions"', 1)[1].split("</ol>", 1)[0]
    assert "「만약」</strong>" not in body and "<strong>「클립보드 가져오기」</strong> —" not in body
