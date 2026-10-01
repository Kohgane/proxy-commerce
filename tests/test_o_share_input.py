"""O(오너 2026-10-01) — share 입력 유실 · e.tb.cn 해석 · 단축어 최종 구조.

## 실측(이 PR이 확인한 것)
오너 재현 쿼리(iOS 「URL 인코딩」: `:`·`/`는 그대로, `?`→%3F·`=`→%3D·공백→%20·줄바꿈→%0A·CJK→UTF-8 %)를
  · Flask 테스트 클라이언트(로그인) · 로그아웃 → 로그인 화면 → `next`로 복귀 · **실 gunicorn(운영 설정)** 세 길에 넣었다
  → 셋 다 text 121자를 그대로 받아 「담았어요」. 서버 앱 층에선 비지 않는다.
대신 같이 찾은 결함 둘:
  ① 공유 버전별 도착 카운터 SQL이 PG에서 `IndeterminateDatatype`(형 없는 자리표시자) → except가 삼켜 **운영 기록 0건**
     → 「실기기에서 무엇이 도착했나」를 운영에서 볼 길이 없었다. 고치고, 도착 기록(길이만)을 따로 남긴다.
  ② 로그인 화면의 소셜 로그인 링크가 `next`를 **인코딩하지 않고** 붙였다 → share 주소의 `&v=2&src=…`가
     잘려 나갔다(로그아웃 상태에서 카카오·구글로 로그인하면 버전·경로를 잃는다).

## 계약
  1 오너 쿼리(iOS 인코딩) → 담김 · 처리 단계에 e.tb.cn 링크 · 경로 「단축어」 · 도착 기록(길이만)
  2 CJK·줄바꿈 `你好 test\\n世界` → 받은 글 길이 그대로 · 화면에 두 조각 그대로
  3 `hello` 회귀(받은 내용 「hello」)
  4 복구 로직은 `%`가 하나도 없는 원 쿼리에만(인코딩된 값은 표준 디코드 1회)
  5 로그아웃 도착도 기록(「로그인으로」) · 기록에 내용·tk가 없다
  6 e.tb.cn 본문 `var url = '…'; location.replace(url)` → 그 주소의 상품 번호(본문의 다른 상품 링크보다 먼저)
  7 소셜 로그인 링크의 next는 인코딩된다(`&v=2`가 살아 있다)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import pytest

ORIG = ("【淘宝】7天无理由退货 https://e.tb.cn/h.8DPCNppWAZAWzUT?tk=AwnsTobAumn HU926「创意Magsafe磁吸手机支架"
        "无线充电器底座手机磁吸充电桌面支架」\n点击链接直接打开 或者 淘宝搜索直接打开")


def ios_encode(s: str) -> str:
    """iOS 「URL 인코딩」 동작의 실측 모양 — `:`·`/`는 그대로, 나머지 예약·공백·줄바꿈·CJK는 %."""
    return quote(s, safe=":/")


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_translate_queue_pg as st
    st.reset_for_tests()
    yield


@pytest.fixture
def client():
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-o"
    return c


def _stages(h: str) -> dict:
    out = {}
    for key, ok, body in re.findall(r'<li data-stage="(\w+)" data-ok="(\w+)">(.*?)</li>', h, re.S):
        body = re.sub(r'<span class="sd-st-mark">.*?</span>', "", body, flags=re.S)   # 「완료」·「멈춤」 표시는 빼고
        out[key] = (ok, re.sub(r"\s+", " ", re.sub("<[^>]+>", "", body)).strip())
    return out


def test_owner_ios_encoded_query_is_received_and_collected(client):
    from src.seller_console.help_settings import share_arrivals
    q = f"v=2&text={ios_encode(ORIG)}&clip={ios_encode(ORIG)}"
    assert "%3Ftk%3D" in q and "https://e.tb.cn/" in q and "%0A" in q              # 오너가 전사한 모양 그대로
    h = client.get(f"/seller/collect/share?{q}").get_data(as_text=True)
    assert re.search(r'data-role="share-state"[^>]*>(담았어요|이미 담은 상품이에요)<', h)
    st = _stages(h)
    assert st["recv"][0] == "yes" and st["recv"][1].startswith(f"받은 글 {len(ORIG.strip())}자")
    assert st["link"] == ("yes", "링크 찾기 e.tb.cn")
    a = share_arrivals()[0]
    assert a["route"] == "단축어" and a["v"] == 2 and a["text_len"] == a["clip_len"] == len(ORIG.strip())
    assert a["stage"] == "saved" and a["authed"] is True
    assert "tk" not in json.dumps(a, ensure_ascii=False).replace("text_len", "")   # 내용·tk는 기록에 없다


def test_cjk_and_newline_are_kept(client):
    raw = "你好 test\n世界"
    h = client.get(f"/seller/collect/share?v=2&text={ios_encode(raw)}&clip={ios_encode(raw)}").get_data(as_text=True)
    m = re.search(r'data-role="share-raw">(.*?)<span', h, re.S)
    shown = re.sub(r"\s+", " ", m.group(1))
    assert "你好 test" in shown and "世界" in shown and shown.index("你好") < shown.index("世界")
    assert _stages(h)["recv"][1].startswith("받은 글 10자")                          # 줄바꿈 포함 그대로 받음
    assert "단축어" in h


def test_hello_regression(client):
    h = client.get("/seller/collect/share?v=2&text=&clip=hello").get_data(as_text=True)
    assert "받은 내용: 「hello」" in h and _stages(h)["link"][0] == "no"


def test_recovery_only_when_url_encode_action_was_not_used():
    from src.order_webhook import app
    from src.seller_console.views import _share_inputs
    # 「URL 인코딩」을 거친 값(`%3F`·`%3D`가 있다) + 낯선 키 — 되살리기 금지(표준 디코드 1회)
    with app.test_request_context("/seller/collect/share?v=2&text=%E4%BD%A0%20https://e.tb.cn/h.x%3Ftk%3DT&foo=bar&clip=x"):
        assert _share_inputs()["text"] == "你 https://e.tb.cn/h.x?tk=T"
    # 인코딩 동작 없는 옛 단축어: iOS가 공백·CJK만 %로, `?`·`=`·`&`는 그대로 — text 속 `&`가 되살아난다
    with app.test_request_context("/seller/collect/share?v=2&text=a%20b&c=d https://e.tb.cn/h.x?tk=T&clip=y"):
        assert _share_inputs()["text"] == "a b&c=d https://e.tb.cn/h.x?tk=T"
    # `%`가 하나도 없는 원 쿼리도 마찬가지
    with app.test_request_context("/seller/collect/share?v=2&text=a b&c=d&clip=y"):
        assert _share_inputs()["text"] == "a b&c=d"


def test_logged_out_arrival_is_recorded_and_next_keeps_text():
    from src.order_webhook import app
    import src.seller_console.views as V
    from src.seller_console.help_settings import share_arrivals
    old = V._AUTH_ENABLED
    V._AUTH_ENABLED = True
    try:
        r = app.test_client().get(f"/seller/collect/share?v=2&text={ios_encode(ORIG)}&clip={ios_encode(ORIG)}")
    finally:
        V._AUTH_ENABLED = old
    assert r.status_code == 302
    nxt = parse_qs(urlparse(r.headers["Location"]).query)["next"][0]
    assert parse_qs(urlparse(nxt).query)["text"][0] == ORIG.strip() and "v=2" in nxt
    a = share_arrivals()[0]
    assert a["stage"] == "login" and a["authed"] is False and a["text_len"] == len(ORIG.strip())


def test_tb_cn_js_redirect_target_wins():
    from src.collectors.link_diag import scan_body_for_item
    html = ("<html><head><title>淘宝</title></head><body>"
            "<a href=\"https://item.taobao.com/item.htm?id=111111111111\">추천</a>"
            "<script>var url = 'https://item.taobao.com/item.htm?ut_sk=1.x&id=809968335363&price=76.86&sourceType=item';"
            " location.replace(url);</script></body></html>")
    got = scan_body_for_item(html)
    assert got["body_item_id"] == "809968335363" and got["body_price"] == "76.86"


def test_social_login_links_encode_next(monkeypatch):
    from src.order_webhook import app
    import src.auth.views as AV
    monkeypatch.setattr(AV, "_provider_status", lambda p: {"is_configured": True, "reason": "", "setup_url": ""})
    nxt = "/seller/collect/share?text=" + quote(ORIG) + "&v=2&src=share"
    h = app.test_client().get("/auth/login?next=" + quote(nxt, safe="")).get_data(as_text=True)
    hrefs = re.findall(r'href="(/auth/(?:kakao|google|naver|apple)/start\?[^"]+)"', h)
    assert hrefs
    for href in hrefs:
        q = parse_qs(urlparse(href.replace("&amp;", "&")).query)
        assert q["next"][0] == nxt, href                                          # `&v=2&src=`가 잘리지 않는다


def test_result_screen_has_no_paste_popup_wording(client):
    h = client.get("/seller/collect/share?v=2&text=&clip=").get_data(as_text=True)
    assert "붙여넣기 허용" not in h and 'data-stage="recv"' in h and "단축어가 보낸 글이 비어 있어요" in h
