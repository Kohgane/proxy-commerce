"""M3-iOS 실측 결함(오너 2026-09-28) — 아이폰 공유 → 서버엔 제목 3자만 도착.

타오바오 앱의 iOS 공유 입력 = **제목 텍스트 + URL 두 조각**. 단축어가 「URL 열기」에 「단축어 입력」을
그대로 넣자 첫 조각(제목)만 갔고, 결과 화면은 「길이 3자, 링크 조각 0」만 말해 무엇이 왔는지 몰랐다.

  ① 실패 화면에 **받은 원문 앞 60자**(스크럽 먼저 · 자르기 나중) — `tk`·쿠키는 안 보인다
  ② 서버 로그에도 받은 쿼리(스크럽) — `tk` 값은 로그에 없다
  ③ `/collect/share`가 `text=`뿐 아니라 `title=`·`url=`도 받아 **셋을 합쳐** 파싱(이미 든 조각은 다시 안 붙임)
  ④ 화면 C = 4동작(공유 시트 받기 → 「입력에서 URL 가져오기」 → 「URL 인코딩」 → 「URL 열기」)
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

import pytest

LINK = "https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt"
TK = "nyXpT7VA7lt"


@pytest.fixture
def client(monkeypatch):
    from src.collectors import link_diag
    monkeypatch.setattr(link_diag, "resolve_short_link", lambda url: {"ok": False, "reason": "offline"})
    from src.order_webhook import app
    return app.test_client()


def _login(c, seller):
    with c.session_transaction() as s:
        s["user_id"] = seller


def _rows(seller):
    from src.seller_console import collect_history_store as S
    return list(S.list_items(seller_ids={seller}, days=30, limit=50) or [])


def test_failure_screen_shows_what_arrived(client):
    """오너 실측 재현: 제목 3자만 왔다 → 사유 문장 + 받은 원문 그대로."""
    _login(client, "u-ios-fix-1")
    h = client.get("/seller/collect/share?text=" + quote("新中式")).get_data(as_text=True)
    assert 'data-state="failed"' in h and "길이 3자" in h
    assert 'data-role="share-raw"' in h and "받은 내용: 「新中式」" in h
    assert _rows("u-ios-fix-1") == []


def test_raw_preview_is_scrubbed_before_cut():
    from src.seller_console.views import share_raw_preview
    p = share_raw_preview(f"新中式 {LINK}")
    assert TK not in p and "tk=" not in p and p == "新中式 https://e.tb.cn/h.8IcTrtZuTU19ieN"
    long = "가" * 70 + f" https://x.example/a?cookie2={'s' * 30}"
    p = share_raw_preview(long)
    assert len(p) == 61 and p.endswith("…") and "sss" not in p
    # 자르기를 먼저 하면 잘린 비밀 조각이 스크럽을 빠져나간다 — 경계에 걸친 비밀도 안 보인다
    edge = "나" * 40 + " https://x.example/p?_tb_token_=" + "Z" * 40
    assert "ZZZ" not in share_raw_preview(edge)
    assert share_raw_preview("") == ""


def test_title_and_url_keys_are_combined(client, monkeypatch):
    """단축어가 URL을 `url=`로 따로 보내도 담긴다(제목만 `title=`) — 셋을 합쳐 파싱."""
    from src.collectors import link_diag
    monkeypatch.setattr(link_diag, "resolve_short_link",
                        lambda url: {"ok": True, "item_id": "812345678901", "price": "", "currency": "",
                                     "reason": ""})
    seen = {}
    import src.api.extension_api as ext
    real = ext.share_collect_core

    def _spy(raw, **k):
        seen["raw"] = raw
        return real(raw, **k)

    monkeypatch.setattr(ext, "share_collect_core", _spy)
    _login(client, "u-ios-fix-2")
    h = client.get("/seller/collect/share?title=" + quote("新中式") + "&url=" + quote(LINK, safe="")).get_data(as_text=True)
    assert seen["raw"] == f"新中式 {LINK}"            # 제목 → 링크 순서
    assert 'data-state="draft"' in h
    rows = _rows("u-ios-fix-2")
    assert len(rows) == 1 and "812345678901" in rows[0]["url"]


def test_combine_does_not_duplicate_parts(client, monkeypatch):
    """안드로이드 PWA는 text에 제목+링크를 담아 title·url을 **같이** 보낸다 — 두 번 붙이지 않는다."""
    seen = {}
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "share_collect_core",
                        lambda raw, **k: (seen.setdefault("raw", raw), ({"ok": False, "error": "x"}, {}))[1])
    _login(client, "u-ios-fix-3")
    text = f"【淘宝】{LINK} CZ356 「新中式双人书桌」"
    client.post("/seller/collect/share", data={"title": "新中式双人书桌", "text": text, "url": LINK})
    assert seen["raw"] == text


def test_server_log_records_scrubbed_query(client, caplog):
    _login(client, "u-ios-fix-4")
    with caplog.at_level(logging.INFO, logger="src.seller_console.views"):
        client.get("/seller/collect/share?text=" + quote("新中式") + "&url=" + quote(LINK, safe=""))
    lines = [r.getMessage() for r in caplog.records if "[share] in" in r.getMessage()]
    assert lines and "keys=text,url" in lines[0] and "新中式" in lines[0] and "e.tb.cn/h.8IcTrtZuTU19ieN" in lines[0]
    assert all(TK not in r.getMessage() for r in caplog.records)


def test_make_page_is_three_actions():
    """동작 셋 — O(2026-10-01) 최종: 공유 시트에서 받기(없으면 클립보드) → URL 인코딩 → URL 열기. 판단은 서버가 한다."""
    t = Path("src/seller_console/templates/guide_iphone_make.html").read_text(encoding="utf-8")
    acts = [t.index(f'data-role="act-{i}"') for i in (1, 2, 3)]
    assert acts == sorted(acts)
    for s in ("공유 시트에서 받기", "「클립보드 가져오기」", "「URL 인코딩」", "「URL 열기」", "[URL 인코딩된 텍스트]"):
        assert s in t, s
    # 「단축어 입력」을 URL 열기에 바로 넣던 옛 순서는 없다(그게 제목 3자만 보냈다)
    assert "「단축어 입력」 토큰을 누르면" not in t


def test_access_logs_do_not_carry_the_query():
    """앱 요청 로그·gunicorn 접근 로그 둘 다 공유 링크의 `tk`를 안 남긴다(둘 다 쿼리를 통째로 남기고 있었다)."""
    from src.middleware.request_logger import _safe_query
    qs = "text=%E6%96%B0%E4%B8%AD%E5%BC%8F&url=https%3A%2F%2Fe.tb.cn%2Fh.8IcTrtZuTU19ieN%3Ftk%3DnyXpT7VA7lt"
    s = _safe_query(qs)
    assert TK not in s and "e.tb.cn/h.8IcTrtZuTU19ieN" in s and "新中式" in s
    assert "abc123" not in _safe_query("token=abc123&page=2") and "page=2" in _safe_query("token=abc123&page=2")
    assert _safe_query("") == ""
    # 로그인 복귀 주소(`next=`)는 공유 쿼리를 한 번 더 인코딩해 싣는다 — 두 겹이어도 `tk`는 안 남는다
    from urllib.parse import urlencode
    nxt = urlencode({"next": "/seller/collect/share?" + urlencode({"text": f"新中式 {LINK}"})})
    assert TK not in _safe_query(nxt) and "e.tb.cn/h.8IcTrtZuTU19ieN" in _safe_query(nxt)
    fmt = '\'%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(M)sms "%(a)s"\''
    for f in ("gunicorn.conf.py", "scripts/start_render.sh"):
        t = Path(f).read_text(encoding="utf-8")
        assert fmt in t, f                               # 두 곳이 같은 값(경로만 · Referer 없음)
        t = "\n".join(ln for ln in t.splitlines() if not ln.lstrip().startswith("#"))   # 주석의 설명은 빼고
        assert "%(r)s" not in t and "%(f)s" not in t and "%(q)s" not in t, f
