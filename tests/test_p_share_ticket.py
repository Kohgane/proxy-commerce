"""P(오너 2026-10-01) — iOS 「URL 열기」 절단 대응: 이중 인코딩 수용(P1) + URL을 버리는 티켓 길(P2).

운영 도착 기록(10-01 10:35 UTC): v=2 · 쿼리 9자(`v=2&text=`) · keys `text,v` · text 0 · clip 0 · 로그인 예.
단축어 미리보기엔 전체 URL이 있었다 → 아이폰이 브라우저로 넘길 때 `text=` 직후(첫 비ASCII 앞)에서 잘랐다.
영문만(hello·Codhsvxh)은 통과. 서버는 #807 재현대로 무죄.

  P1 1 두 번 인코딩된 复制链接 원문 → 담았어요 · 도착 기록 디코드 +1
     2 한 번 인코딩·영문·hello 회귀(추가 디코드 0)
  P2 3 POST 본문 CJK·줄바꿈 원문 → 응답은 ASCII URL 한 줄(v=3&t=) → GET(로그인) → 담았어요 · 도착 기록 티켓 · v3 카운트
     4 로그아웃이면 로그인으로 — next엔 원문 대신 티켓만, 로그인 뒤 담김
     5 만료·위조(모양 틀림)·없는 티켓 → 사유 문구(가짜 성공 0)
     6 IP당 분당 10건 — 11번째는 err=rate 주소 · 다른 IP는 통과
     7 빈 글 → err=empty · 다른 사이트에서 보낸 POST는 403
     8 원문(tk)은 로그에 안 남는다(길이만)
"""
from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

import pytest

ORIG = ("【淘宝】7天无理由退货 https://e.tb.cn/h.8DPCNppWAZAWzUT?tk=AwnsTobAumn HU926「创意Magsafe磁吸手机支架"
        "无线充电器底座手机磁吸充电桌面支架」\n点击链接直接打开 或者 淘宝搜索直接打开")
TK = "AwnsTobAumn"


def enc1(s):            # iOS 「URL 인코딩」 실측 모양 — `:`·`/`는 그대로
    return quote(s, safe=":/")


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_translate_queue_pg as st
    from src.db import option_translate_queue_pg as oq
    st.reset_for_tests()
    oq.reset_for_tests()
    yield


@pytest.fixture
def client():
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-p"
    return c


def _state(h):
    m = re.search(r'data-role="share-state"[^>]*>([^<]*)<', h)
    return m.group(1) if m else ""


# ── P1 ────────────────────────────────────────────────────────────────────────

def test_double_encoded_original_is_collected(client):
    from src.seller_console.help_settings import share_arrivals
    twice = enc1(enc1(ORIG))
    assert twice.isascii() and "%25E3" in twice                                   # URL에 비ASCII 0
    h = client.get(f"/seller/collect/share?v=2&text={twice}&clip={twice}").get_data(as_text=True)
    assert _state(h) in ("담았어요", "이미 담은 상품이에요")
    a = share_arrivals()[0]
    assert a["decodes"] == 1 and a["text_len"] == len(ORIG.strip()) and a["stage"] == "saved"


@pytest.mark.parametrize("raw,decodes", [(ORIG, 0), ("hello", 0), ("Codhsvxh", 0)])
def test_single_encoded_and_english_regress(client, raw, decodes):
    from src.seller_console.help_settings import share_arrivals
    q = enc1(raw)
    h = client.get(f"/seller/collect/share?v=2&text={q}&clip={q}").get_data(as_text=True)
    a = share_arrivals()[0]
    assert a["decodes"] == decodes and a["text_len"] == len(raw.strip())
    if raw == "hello":
        assert "받은 내용: 「hello」" in h


def test_decode_again_unit():
    from src.seller_console.share_tickets import decode_again
    assert decode_again(unquote(enc1(enc1(ORIG)))) == (ORIG, 1)
    assert decode_again("abc%41def") == ("abc%41def", 0)                         # 풀어도 사람 글이 안 되면 그대로
    assert decode_again(unquote(enc1(enc1(enc1("你好"))))) == ("你好", 2)          # 표준 1회 뒤 최대 2회 더
    four = unquote(enc1(enc1(enc1(enc1("你好")))))
    assert decode_again(four) == (four, 0)                                        # 그 이상은 안 푼다(사람 글 안 됨 → 원래 값)


# ── P2 ────────────────────────────────────────────────────────────────────────

def _ticket_url(resp):
    body = resp.get_data(as_text=True)
    assert resp.mimetype == "text/plain" and body.count("\n") == 1 and body.isascii()
    u = urlparse(body.strip())
    assert u.path == "/seller/collect/share" and len(body) < 120
    return u


def test_share_in_ticket_roundtrip(client):
    from src.order_webhook import app
    from src.seller_console.help_settings import share_arrivals, share_version_counts
    u = _ticket_url(app.test_client().post("/seller/collect/share-in", data={"text": ORIG}))
    q = parse_qs(u.query)
    assert q["v"] == ["3"] and re.fullmatch(r"[A-Za-z0-9_-]{12,40}", q["t"][0])
    h = client.get(f"{u.path}?{u.query}").get_data(as_text=True)
    assert _state(h) == "담았어요"
    a = share_arrivals()[0]
    assert a["ticket"] is True and a["v"] == 3 and a["text_len"] == len(ORIG.strip()) and a["stage"] == "saved"
    assert share_version_counts().get("v3") == 1
    # 새로고침(같은 티켓) — 같은 상품으로 이어진다(새 행 0)
    assert _state(client.get(f"{u.path}?{u.query}").get_data(as_text=True)) == "이미 담은 상품이에요"


def test_logged_out_ticket_goes_through_login_with_ticket_only():
    from src.order_webhook import app
    import src.seller_console.views as V
    u = _ticket_url(app.test_client().post("/seller/collect/share-in", data={"text": ORIG}))
    old = V._AUTH_ENABLED
    V._AUTH_ENABLED = True
    try:
        r = app.test_client().get(f"{u.path}?{u.query}")
        assert r.status_code == 302
        nxt = parse_qs(urlparse(r.headers["Location"]).query)["next"][0]
        assert parse_qs(urlparse(nxt).query)["t"] == parse_qs(u.query)["t"] and "text=" not in nxt
        c = app.test_client()
        with c.session_transaction() as s:
            s["user_id"] = "u-p2"
        assert _state(c.get(nxt).get_data(as_text=True)) == "담았어요"          # 로그인 뒤에 저장
    finally:
        V._AUTH_ENABLED = old


@pytest.mark.parametrize("t,msg", [("short", "주소가 망가져서"), ("A" * 16, "10분이 지나")])
def test_bad_or_unknown_ticket_fails_honestly(client, t, msg):
    h = client.get(f"/seller/collect/share?v=3&t={t}").get_data(as_text=True)
    assert _state(h) == "담지 못했어요" and msg in h


def test_expired_ticket(client):
    from datetime import datetime, timedelta, timezone
    from src.order_webhook import app
    from src.db import image_translate_queue_pg as st
    u = _ticket_url(app.test_client().post("/seller/collect/share-in", data={"text": ORIG}))
    t = parse_qs(u.query)["t"][0]
    v = st.state_get("share_ticket:" + t)
    v["exp"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    st.state_set("share_ticket:" + t, v)
    h = client.get(f"{u.path}?{u.query}").get_data(as_text=True)
    assert _state(h) == "담지 못했어요" and "10분이 지나" in h


def test_rate_limit_per_ip():
    from src.order_webhook import app
    c = app.test_client()
    got = [_ticket_url(c.post("/seller/collect/share-in", data={"text": "x https://e.tb.cn/h.a"},
                              headers={"X-Forwarded-For": "203.0.113.9"})).query for _ in range(11)]
    assert all("t=" in q for q in got[:10]) and "err=rate" in got[10]
    other = _ticket_url(c.post("/seller/collect/share-in", data={"text": "y https://e.tb.cn/h.b"},
                               headers={"X-Forwarded-For": "203.0.113.10"})).query
    assert "t=" in other


def test_json_and_plain_text_bodies_are_accepted(client):
    from src.order_webhook import app
    c = app.test_client()
    for kw in ({"json": {"text": ORIG}}, {"data": ORIG.encode("utf-8"), "content_type": "text/plain; charset=utf-8"}):
        u = _ticket_url(c.post("/seller/collect/share-in", **kw))
        assert "t=" in u.query
        assert _state(client.get(f"{u.path}?{u.query}").get_data(as_text=True)) in ("담았어요", "이미 담은 상품이에요")


def test_empty_and_cross_site():
    from src.order_webhook import app
    c = app.test_client()
    assert "err=empty" in _ticket_url(c.post("/seller/collect/share-in", data={"text": "  "})).query
    r = c.post("/seller/collect/share-in", data={"text": ORIG}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_share_in_does_not_log_the_text(caplog):
    from src.order_webhook import app
    with caplog.at_level(logging.INFO):
        app.test_client().post("/seller/collect/share-in", data={"text": ORIG})
    assert TK not in caplog.text and "e.tb.cn/h.8DPCNppWAZAWzUT" not in caplog.text
