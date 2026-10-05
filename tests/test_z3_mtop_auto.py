"""Z3 자동 경로(오너 2026-10-05) — x5 핸드셰이크 → 토큰 왕복 → getdetail · punish → (c) 수동 · 프록시는 mtop 경로에만.

네트워크 0: 녹화/재구성 응답(`tests/fixtures/taobao_mtop/`, 출처는 그 폴더 README)을 대역 세션이 순서대로 돌려준다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FX = Path(__file__).parent / "fixtures" / "taobao_mtop"


class _R:
    def __init__(self, text, status=200, cookies=None):
        self.text, self.status_code, self.set_cookies = text, status, cookies or {}

    def json(self):
        return json.loads(self.text)


class FakeSession:
    """requests.Session 흉내 — 응답 줄을 순서대로, Set-Cookie는 쿠키통에 쌓는다."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.cookies = {}
        self.calls = []

    def get(self, url, timeout=None, **kw):
        self.calls.append((url, dict(self.cookies)))
        r = self.replies.pop(0)
        self.cookies.update(r.set_cookies)
        return r


def _fx(name):
    return (FX / name).read_text(encoding="utf-8")


def test_x5_handshake_then_token_then_detail():
    from src.collectors import taobao_mtop as T
    s = FakeSession([
        _R(_fx("x5_referer.txt")),                                       # 1차: 핸드셰이크 스크립트(JSON 아님)
        _R("", 200, {"x5sec": "x5abc"}),                                 # set_x5referer GET → x5sec
        _R(_fx("token_empty.json"), 200, {"_m_h5_tk": "tok123_1700000000000"}),   # 2차: 토큰 비어 있음
        _R(_fx("getdetail_success.json")),                               # 3차: 서명 붙여 성공
    ])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "733241700286"})
    assert r["state"] == "ok" and [l for l in r["log"] if "차 요청" not in l][2].startswith("3차: HTTP 200 · ret=['SUCCESS")
    hs_url, hs_cookies = s.calls[1]
    assert "_____tmd_____/page/set_x5referer?rand=" in hs_url and "&x5referer=https%3A%2F%2Fh5api.m.taobao.com" in hs_url
    assert s.calls[2][1].get("x5sec") == "x5abc"                         # 같은 쿠키통으로 원 요청 재시도
    assert "sign=" in s.calls[3][0] and s.calls[3][1].get("_m_h5_tk", "").startswith("tok123")
    assert "x5 핸드셰이크 스크립트 → set_x5referer GET HTTP 200 · x5referer 꼬리 붙임 · x5 계열 쿠키 x5sec(헤더)" in r["log"][0]
    p = T.enrich_payload(r["json"], json.loads(_fx("getdesc_success.json")))
    assert p["title"] == "格斯潘懒人沙发单人卧室可躺可睡榻榻米" and len(p["images"]) == 5
    assert p["images"][0] == "https://img.alicdn.com/imgextra/i1/a1.jpg"
    assert p["options"] == [{"name": "颜色分类", "values": ["灰色", "米白"]}, {"name": "尺寸", "values": ["单人", "加大"]}]
    assert [k["spec"] for k in p["skus"]] == [["灰色", "单人"], ["灰色", "加大"], ["米白", "加大"], ["米白", "单人"]]
    assert [k["price"] for k in p["skus"]] == ["798", "898", "998", "898"] and p["skus"][0]["stock"] == "12"
    assert p["price"] == "798" and p["currency"] == "CNY"
    assert p["detail_images"] == ["https://img.alicdn.com/imgextra/d1.jpg", "https://img.alicdn.com/imgextra/d2.jpg"]


def test_recorded_prefix_is_recognised():
    """볼트에 남은 실측 앞부분(100자) 그대로도 핸드셰이크로 알아본다 — 재구성한 꼬리에 기대지 않는다."""
    from src.collectors import taobao_mtop as T
    real = ('var x5referer = encodeURIComponent(window.location.href);\r\nwindow.location.href = '
            '"https://h5api.m.taobao.com:443/h5/mtop.taobao.detail.getdetail/6.0/_____tmd_____/page/set_x5referer?x=1&x5referer=" + x5referer;')
    u = T.x5_handshake_url(real, "https://h5api.m.taobao.com/h5/x/6.0/?a=1")
    assert u.startswith("https://h5api.m.taobao.com:443/") and u.endswith("x5referer=https%3A%2F%2Fh5api.m.taobao.com%2Fh5%2Fx%2F6.0%2F%3Fa%3D1")
    assert T.x5_handshake_url('{"ret":["SUCCESS"]}', "u") == ""


def test_rgv587_punish_goes_manual_with_reason():
    from src.collectors import taobao_mtop as T
    s = FakeSession([_R(_fx("rgv587_punish.json"))])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert r["state"] == "blocked" and r["reason"].startswith("사람 확인(punish/captcha) 요구 — RGV587_ERROR")
    assert len(s.calls) == 1                                              # 막히면 더 두드리지 않는다


def test_three_tries_max():
    from src.collectors import taobao_mtop as T
    s = FakeSession([_R(_fx("token_empty.json"), 200, {"_m_h5_tk": "t_1"}) for _ in range(5)])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert r["state"] == "error" and len(s.calls) == 3 and "3회" in r["reason"]


def test_pacing_waits_two_to_three_seconds(monkeypatch):
    from src.collectors import taobao_mtop as T
    monkeypatch.setenv("TAOBAO_MTOP_GAP_SEC", "2-3")
    slept = []
    monkeypatch.setattr(T, "_sleep", lambda x: slept.append(x))
    T._LAST[0] = 0.0
    s = FakeSession([_R(_fx("token_empty.json"), 200, {"_m_h5_tk": "t_1"}), _R(_fx("getdetail_success.json"))])
    T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert len(slept) == 1 and 1.9 <= slept[0] <= 3.0                   # 첫 호출은 안 기다리고, 둘째부터 2~3초


def test_proxy_only_on_mtop_sessions(monkeypatch):
    from src.collectors import taobao_mtop as T
    monkeypatch.delenv("TAOBAO_PROXY_URL", raising=False)
    with pytest.raises(T.NoProxy):
        T.session_for("proxy")
    assert T.probe("733241700286", via="proxy")["reason"] == "프록시 미설정 — TAOBAO_PROXY_URL"
    monkeypatch.setenv("TAOBAO_PROXY_URL", "http://user:secret@kr.proxy.example:8000")
    s = T.session_for("proxy")
    assert s.proxies == {"http": "http://user:secret@kr.proxy.example:8000", "https": "http://user:secret@kr.proxy.example:8000"}
    assert s.trust_env is False
    assert T.session_for("direct").proxies == {} and T.proxy_label() == "설정됨 · 상품마다 고정 세션(lifetime 30m) · 국가 지정 없음 · 범위 mtop"
    # 이 env를 읽는 곳은 mtop 모듈 하나뿐 — 쿠팡·네이버·릴레이·업로더는 안 탄다
    hits = [p for p in Path("src").rglob("*.py") if "TAOBAO_PROXY_URL" in p.read_text(encoding="utf-8")]
    assert sorted(str(p) for p in hits) == ["src/collectors/taobao_mtop.py", "src/services/taobao_auto.py"]
    # 프록시 세션을 만드는 모듈(taobao_mtop)을 들여오는 곳 = 진단 화면·자동 경로뿐 — 마켓 업로더·릴레이는 안 들여온다
    from tests._ast_probe import importers_of
    # Z3-P: 이미지 내려받기(텐센트)는 SCOPE 판정(image_proxies)만 묻는다 — 기본 mtop이면 직결
    assert importers_of("taobao_mtop") == ["src/dashboard/admin_views.py", "src/services/image_translate_tencent.py",
                                           "src/services/taobao_auto.py"]


def test_diag_page_has_proxy_radio_and_never_prints_credentials(monkeypatch):
    from src.collectors import taobao_mtop as T
    monkeypatch.setenv("TAOBAO_PROXY_URL", "http://user:secret@kr.proxy.example:8000")
    monkeypatch.setattr(T, "probe", lambda q, via="direct": {"input": q, "item_id": "733241700286", "how": "주소의 id=", "log": ["1차: …"],
                                                           "detail": None, "desc_images": None, "via": T.VIAS[via],
                                                           "state": "blocked", "reason": "사람 확인(punish/captcha) 요구 — RGV587"})
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop", query_string={"q": "733241700286", "via": "proxy"}).get_data(as_text=True)
    assert 'data-role="mtop-via-proxy"' in h and 'value="proxy" checked' in h and "프록시(한국 주거 · 설정됨" in h
    assert "secret" not in h and "kr.proxy.example" not in h
    assert "(c) 수동" in h and "자동 경로: 꺼짐(TAOBAO_MTOP_AUTO)" in h


def _share_item(seller):
    from src.seller_console import collect_history_store as S
    ex = {"title": "格斯潘懒人沙发单人", "title_ko": "격스판 빈백 소파", "item_id_taobao": "733241700286",
          "enrich_state": "pending", "images": [], "uncollected": ["images", "options", "price"]}
    return S.append(source="share_text", url="https://item.taobao.com/item.htm?id=733241700286", seller_id=seller,
                    title="격스판 빈백 소파", price="", currency="", extra=ex)


def test_auto_run_fills_draft_through_same_merge(monkeypatch):
    from src.collectors import taobao_mtop as T
    from src.services import taobao_auto as A
    from src.seller_console import collect_history_store as S
    seller = "owner-z3-auto"
    iid = _share_item(seller)
    fake = FakeSession([_R(_fx("x5_referer.txt")), _R("", 200, {"x5sec": "x"}),
                        _R(_fx("token_empty.json"), 200, {"_m_h5_tk": "t_1"}), _R(_fx("getdetail_success.json")),
                        _R(_fx("getdesc_success.json"))])
    monkeypatch.setattr(T, "session_for", lambda via, **kw: fake)
    rec = A.run(seller, iid, via="relay")
    assert rec["state"] == "done" and rec["counts"] == {"images": 5, "skus": 4, "detail_images": 2}
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert len(ex["images"]) == 5 and len(ex["skus"]) == 4 and ex["price"] == "798" and ex["enrich_state"] == "done"
    assert ex["auto_enrich"]["state"] == "done" and ex["auto_enrich"]["route"] == "relay"


def test_auto_run_blocked_falls_to_manual_and_m5_says_why(monkeypatch):
    from src.collectors import taobao_mtop as T
    from src.services import taobao_auto as A
    seller = "owner-z3-manual"
    iid = _share_item(seller)
    monkeypatch.setattr(T, "session_for", lambda via, **kw: FakeSession([_R(_fx("rgv587_punish.json"))]))
    rec = A.run(seller, iid, via="direct")
    assert rec["state"] == "manual" and "RGV587" in rec["reason"]
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-auto-enrich" data-state="manual"' in h and "자동 수집 실패(punish) — 사람 확인(punish/captcha) 요구" in h
    assert "「사진 추가」·「옵션 직접 입력」" in h


def test_auto_is_off_by_default_and_kick_needs_flag(monkeypatch):
    from src.services import taobao_auto as A
    monkeypatch.delenv("TAOBAO_MTOP_AUTO", raising=False)
    assert A.enabled() is False and A.kick("u", "i") is False
    monkeypatch.setenv("TAOBAO_MTOP_AUTO", "1")
    started = []
    monkeypatch.setattr(A, "_safe_run", lambda u, i: started.append((u, i)))
    assert A.kick("u", "i") is True
    import time
    time.sleep(0.05)
    assert started == [("u", "i")]


# ── Z3-H(오너 2026-10-05 15:51 실측: set_x5referer GET 200 · x5sec 없음 ×3) ─────────────────────────────

def test_tail_is_appended_whatever_the_script_concatenates():
    """후보 1: 스크립트가 `+ x5referer`로 잇든 `+ encodeURIComponent(location.href)`로 잇든 — URL이 `x5referer=`로 끝나면
    원 요청 **전체 URL**을 encodeURIComponent 규칙으로 붙인다."""
    from src.collectors import taobao_mtop as T
    orig = "https://h5api.m.taobao.com/h5/mtop.taobao.detail.getdetail/6.0/?jsv=2.7.2&appKey=12574478&t=1&sign=ab&data=%7B%7D"
    for js in ('window.location.href = "https://h5api.m.taobao.com:443/h/_____tmd_____/page/set_x5referer?rand=1&uuid=u&_lgt_=g&x5referer=" + x5referer;',
               "location.href='https://h5api.m.taobao.com:443/h/_____tmd_____/page/set_x5referer?rand=1&x5referer=' + encodeURIComponent(window.location.href)",
               'window.location = "https://h5api.m.taobao.com:443/h/_____tmd_____/page/set_x5referer?x5referer=" + x5referer'):
        u = T.x5_handshake_url(js, orig)
        assert u.endswith("x5referer=https%3A%2F%2Fh5api.m.taobao.com%2Fh5%2Fmtop.taobao.detail.getdetail%2F6.0%2F%3Fjsv%3D2.7.2%26appKey%3D12574478%26t%3D1%26sign%3Dab%26data%3D%257B%257D"), js
    u = T.x5_handshake_url('window.location.href = "https://h5api.m.taobao.com/_____tmd_____/page/set_x5referer?a=1&x5referer=already";', orig)
    assert u.endswith("x5referer=already")                                # 이미 값이 있으면 덧붙이지 않는다


def test_x5sec_from_body_js_is_planted_and_retry_carries_it():
    """후보 2: 핸드셰이크 응답이 헤더가 아니라 본문 JS(document.cookie)로 x5sec을 심는 경우 — 쿠키통에 넣고 원 요청에 싣는다."""
    from src.collectors import taobao_mtop as T
    hs_body = ('<script>document.cookie = "x5sec=7b2268357469676865727d0a1234567890abcdef; path=/; domain=.taobao.com";'
               'window.location.replace(decodeURIComponent(x5referer));</script>')
    s = FakeSession([_R(_fx("x5_referer.txt")), _R(hs_body),
                     _R(_fx("token_empty.json"), 200, {"_m_h5_tk": "tok_1"}), _R(_fx("getdetail_success.json"))])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert r["state"] == "ok" and "x5 계열 쿠키 x5sec(본문 JS)" in r["log"][0]
    assert s.calls[2][1]["x5sec"].startswith("7b2268357469")                 # 재시도에 실렸다
    hd = r["handshakes"][0]
    assert hd["planted"] == ["x5sec"] and hd["tail"] is True and hd["status"] == 200
    assert "x5sec=<" in hd["body_head"] and "7b2268357469" not in hd["body_head"]   # 진단엔 값 대신 글자 수


def test_requests_jar_with_two_domains_does_not_crash():
    """후보 3: 같은 이름이 .taobao.com·h5api.m.taobao.com 둘에 있으면 requests `.get`이 CookieConflictError — 이름으로 읽는다."""
    import requests
    from src.collectors import taobao_mtop as T
    s = requests.Session()
    s.cookies.set("_m_h5_tk", "a_1", domain=".taobao.com", path="/")
    s.cookies.set("_m_h5_tk", "b_2", domain="h5api.m.taobao.com", path="/")
    with __import__("pytest").raises(requests.cookies.CookieConflictError):
        s.cookies.get("_m_h5_tk")
    assert T.cookie_value(s, "_m_h5_tk") in ("a_1", "b_2")
    assert sorted(T._cookie_domains(s)) == ["_m_h5_tk@.taobao.com/", "_m_h5_tk@h5api.m.taobao.com/"]


def test_relay_keeps_every_set_cookie_line():
    """후보 3(릴레이): mkt.php가 Set-Cookie를 여러 줄 다 돌려주고, 앱 쿠키통이 전부 받는다(첫 줄만이면 x5sec 누락)."""
    import src.market_relay as MR
    from src.collectors import taobao_mtop as T
    from pathlib import Path
    assert "$respSetCookie[] = trim(substr($l, 11));" in Path("relay/mkt.php").read_text(encoding="utf-8")
    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(MR, "_api_relay_send", lambda *a: MR.RelayResponse(200, "", headers={"Set-Cookie": [
        "cna=abc123456; Domain=.taobao.com; Path=/", "x5sec=7b22abcdef0123456789; Domain=.taobao.com; Path=/; HttpOnly"]}))
    try:
        rs = T.RelaySession()
        rs.request("https://h5api.m.taobao.com/x")
        assert rs.jar == {"cna": "abc123456", "x5sec": "7b22abcdef0123456789"}
    finally:
        mp.undo()


def test_handshake_to_slider_is_punish_not_retry():
    from src.collectors import taobao_mtop as T
    s = FakeSession([_R(_fx("x5_referer.txt")),
                     _R('<script>location.href="https://h5api.m.taobao.com/_____tmd_____/punish?x5secdata=zz&x5step=2"</script>')])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert r["state"] == "blocked" and r["kind"] == "punish" and "슬라이더" in r["reason"] and len(s.calls) == 2


def test_handshake_twice_without_cookie_says_so_and_diag_shows_headers_and_body(monkeypatch):
    from src.collectors import taobao_mtop as T
    hs_page = _R("<html><body>ok</body></html>")
    hs_page.headers = {"Content-Type": "text/html", "Set-Cookie": "t=abcdef123456; Domain=.taobao.com; Path=/"}
    s = FakeSession([_R(_fx("x5_referer.txt")), hs_page, _R(_fx("x5_referer.txt")), _R("<html/>"), _R(_fx("x5_referer.txt"))])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert r["state"] == "error" and r["kind"] == "x5_loop" and r["reason"].startswith("x5 루프") and len(r["handshakes"]) == 2
    hd = r["handshakes"][0]
    assert "Content-Type: text/html" in hd["headers"] and "Set-Cookie: t=<12자>; Domain=.taobao.com; Path=/" in hd["headers"]
    assert hd["body_head"] == "<html><body>ok</body></html>"
    monkeypatch.setattr(T, "probe", lambda q, via="direct": {"input": q, "item_id": "1", "how": "직접 입력", "log": r["log"], "detail": None,
                                                           "desc_images": None, "via": T.VIAS[via], "state": r["state"], "kind": r["kind"],
                                                           "reason": r["reason"], "handshakes": r["handshakes"]})
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop", query_string={"q": "1", "via": "direct"}).get_data(as_text=True)
    assert 'data-role="mtop-handshake"' in h and "Set-Cookie: t=&lt;12자&gt;; Domain=.taobao.com; Path=/" in h
    assert "abcdef123456" not in h and "응답 본문(전체" in h


# ── Z3-P 프록시 sticky ──────────────────────────────────────────────────────────

IPR_ROT = "http://u9fk2:Abc123xyz_country-kr@geo.iproyal.com:12321"
IPR_STICKY = "http://u9fk2:Abc123xyz_country-kr_session-Ad8BTgRy_lifetime-30m@geo.iproyal.com:12321"


@pytest.mark.parametrize("raw", [IPR_ROT, IPR_STICKY])
def test_proxy_url_normalised_from_either_form(monkeypatch, raw):
    """Z3-P: 오너가 session 붙은 값/안 붙은 값 어느 쪽을 넣어도 같은 base · 상품별 결정적 session."""
    from src.collectors import taobao_mtop as T
    monkeypatch.setenv("TAOBAO_PROXY_URL", raw)
    monkeypatch.delenv("TAOBAO_PROXY_SESSION_LIFETIME", raising=False)
    pp = T.proxy_parts()
    assert pp == {"scheme": "http", "user": "u9fk2", "base_pass": "Abc123xyz_country-kr", "host": "geo.iproyal.com",
                  "port": 12321, "country": "kr"}
    sid = T.session_id("733241700286")
    assert sid == T.session_id("733241700286") and sid != T.session_id("1077964821879") and re.fullmatch(r"[0-9a-f]{8}", sid)
    assert T.proxy_url(sid) == f"http://u9fk2:Abc123xyz_country-kr_session-{sid}_lifetime-30m@geo.iproyal.com:12321"
    assert T.proxy_url() == "http://u9fk2:Abc123xyz_country-kr@geo.iproyal.com:12321"            # 세션 없이 = 회전
    assert T.masked_proxy(sid) == f"http://u9fk2:Abc…@geo.iproyal.com:12321 · session {sid} · lifetime 30m"
    assert "123xyz" not in T.masked_proxy(sid) and "123xyz" not in T.proxy_label()
    monkeypatch.setenv("TAOBAO_PROXY_SESSION_LIFETIME", "10m")
    assert T.proxy_url(sid).endswith(f"_session-{sid}_lifetime-10m@geo.iproyal.com:12321")


def test_same_item_same_session_handshake_and_detail(monkeypatch):
    """같은 상품의 핸드셰이크·getdetail·getdesc는 한 세션(= 같은 IP) · 다른 상품은 다른 세션."""
    from src.collectors import taobao_mtop as T
    monkeypatch.setenv("TAOBAO_PROXY_URL", IPR_STICKY)
    made = []

    def fake_session_for(via, sticky=""):
        fs = FakeSession([_R(_fx("x5_referer.txt")), _R("", 200, {"x5secdata": "xd7b22abcdef0123456789"}),
                          _R(_fx("token_empty.json"), 200, {"_m_h5_tk": "t_1"}), _R(_fx("getdetail_success.json")),
                          _R(_fx("getdesc_success.json"))])
        made.append((via, sticky, fs))
        return fs
    monkeypatch.setattr(T, "session_for", fake_session_for)
    r1 = T.fetch("733241700286", "proxy")
    r2 = T.fetch("733241700286", "proxy")
    T.fetch("1077964821879", "proxy")
    assert r1["state"] == "ok" and r1["session"] == r2["session"] == T.session_id("733241700286")
    assert made[2][1] == T.session_id("1077964821879") != made[0][1]
    assert len(made[0][2].calls) == 5 and made[0][2] is not made[1][2]        # 한 상품의 5번 호출이 한 세션에서
    assert r1["bytes"] > 0


def test_scope_mtop_keeps_images_direct(monkeypatch):
    """SCOPE=mtop(기본)이면 이미지 내려받기에 proxies가 안 들어간다 · all이면 타오바오 이미지만."""
    from src.services import image_translate_tencent as TC
    monkeypatch.setenv("TAOBAO_PROXY_URL", IPR_STICKY)
    seen = []
    monkeypatch.setattr(TC, "_download", lambda url, proxies=None: (seen.append(proxies), b"\x89PNG" + b"0" * 64)[1])
    monkeypatch.delenv("TAOBAO_PROXY_SCOPE", raising=False)
    TC.fetch_image("https://img.alicdn.com/imgextra/i1/a.jpg")
    assert seen == [None]
    monkeypatch.setenv("TAOBAO_PROXY_SCOPE", "all")
    TC.fetch_image("https://img.alicdn.com/imgextra/i1/a.jpg")
    TC.fetch_image("https://res.cloudinary.com/x/a.jpg")                    # 타오바오 이미지가 아니면 all이어도 직결
    assert seen[1]["https"].startswith("http://u9fk2:") and seen[2] is None


def test_proxy_failures_are_not_ip_blocks():
    """407 → proxy_auth · 타임아웃 → proxy_timeout · 연결 실패 → proxy_conn (「IP 차단」과 다른 사유 코드)."""
    import requests
    from src.collectors import taobao_mtop as T

    class _PS(FakeSession):
        def __init__(self, exc=None, replies=()):
            super().__init__(list(replies))
            self.proxies = {"https": "http://u:p@geo.iproyal.com:12321"}
            self.exc = exc

        def get(self, url, timeout=None, **kw):
            if self.exc:
                raise self.exc
            return super().get(url, timeout=timeout)
    for exc, kind in ((requests.exceptions.ProxyError("Tunnel connection failed: 407 Proxy Authentication Required"), "proxy_auth"),
                      (requests.exceptions.ConnectTimeout("timed out"), "proxy_timeout"),
                      (requests.exceptions.ProxyError("Cannot connect to proxy"), "proxy_conn")):
        r = T.mtop_ex(_PS(exc), "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
        assert r["kind"] == kind, (exc, r)
    r = T.mtop_ex(_PS(replies=[_R("", 407)]), "mtop.taobao.detail.getdetail", {"itemNumId": "1"})   # HTTP 407 응답도
    assert r["kind"] == "proxy_auth" and r["reason"].startswith("프록시 인증 실패(407)")


def test_login_required_is_its_own_block_and_stages():
    from src.collectors import taobao_mtop as T
    login = _R('<script>var loginUrl="https://login.m.taobao.com/login.htm?redirectURL=xx&uuid=ab12"; location.href=loginUrl;</script>',
               200, {"x5secdata": "xd7b22abcdef0123456789"})
    s = FakeSession([_R(_fx("x5_referer.txt")), login])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert r["state"] == "blocked" and r["kind"] == "login_required"
    assert r["reason"] == "로그인 요구 — 익명 수집 불가(IP 무관). 외부 API 또는 로그인 쿠키 경로 필요."
    assert r["stages"] == {"rgv587": False, "script": True, "x5": True, "login": True, "detail": False}
    assert [ok for _n, ok in T.verdict(r["stages"])] == [True, True, True, False, False]


def test_route_proxy_without_url_fails_loudly(monkeypatch, caplog):
    from src.collectors import taobao_mtop as T
    from src.services import taobao_auto as A
    monkeypatch.delenv("TAOBAO_PROXY_URL", raising=False)
    monkeypatch.setenv("TAOBAO_MTOP_AUTO", "1")
    monkeypatch.setenv("TAOBAO_MTOP_ROUTE", "proxy")
    assert "relay2로 돌리지 않고" in A.startup_check()
    assert T.fetch("1", "proxy")["kind"] == "proxy_unset"
    monkeypatch.setenv("TAOBAO_MTOP_ROUTE", "relay2")
    assert A.route() == "relay"


def test_diag_proxy_shows_exit_ip_session_bytes_and_five_stages(monkeypatch):
    from src.collectors import taobao_mtop as T
    monkeypatch.setenv("TAOBAO_PROXY_URL", IPR_STICKY)
    monkeypatch.setattr(T, "exit_ip", lambda sticky="": {"ok": True, "ip": "121.134.5.6", "country": "KR", "bytes": 320})
    monkeypatch.setattr(T, "item_id_from", lambda arg, s=None: ("733241700286", "직접 입력"))
    monkeypatch.setattr(T, "session_for", lambda via, sticky="": FakeSession([
        _R(_fx("x5_referer.txt")), _R("", 200, {"x5secdata": "xd7b22abcdef0123456789"}),
        _R(_fx("token_empty.json"), 200, {"_m_h5_tk": "t_1"}), _R(_fx("getdetail_success.json")), _R(_fx("getdesc_success.json"))]))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop", query_string={"q": "733241700286", "via": "proxy"}).get_data(as_text=True)
    sid = T.session_id("733241700286")
    assert 'data-role="mtop-exit"' in h and "121.134.5.6" in h and "KR" in h
    assert f"session {sid}" in h and "Abc…" in h and "123xyz" not in h
    assert 'data-role="mtop-stages"' in h and h.count("○") >= 5 and 'data-role="mtop-bytes"' in h
    assert "TAOBAO_MTOP_ROUTE=proxy" in h and "TAOBAO_MTOP_AUTO=1" in h               # 숫자 나오면 전환 안내


def test_auto_proxy_records_bytes_and_session(monkeypatch):
    from src.collectors import taobao_mtop as T
    from src.services import taobao_auto as A
    from src.services import mtop_stats as MS
    monkeypatch.setenv("TAOBAO_PROXY_URL", IPR_STICKY)
    before = MS.summary(3)["total"].get("bytes", 0)
    seller = "owner-z3p"
    iid = _share_item(seller)
    monkeypatch.setattr(T, "session_for", lambda via, sticky="": FakeSession([_R(_fx("rgv587_punish.json"))]))
    rec = A.run(seller, iid, via="proxy")
    assert rec["state"] == "manual" and rec["session"] == T.session_id("733241700286") and rec["proxy_bytes"] > 0
    assert MS.summary(3)["total"]["bytes"] - before == rec["proxy_bytes"]


# ── Z3-C 집계 ───────────────────────────────────────────────────────────────────

def test_auto_stats_routes_first_ten_and_sample(monkeypatch):
    from src.collectors import taobao_mtop as T
    from src.services import taobao_auto as A
    from src.services import mtop_stats as MS
    from src.db import image_translate_queue_pg as st
    for k in ("mtop_auto:first10", "mtop_auto:recent", "mtop_auto:sample_detail"):
        st.state_set(k, {})
    before = MS.summary(3)["total"]
    seller = "owner-z3-stats"
    ok_item, rgv_item = _share_item(seller), _share_item(seller)
    monkeypatch.setattr(T, "session_for", lambda via, **kw: FakeSession([
        _R(_fx("x5_referer.txt")), _R("", 200, {"x5sec": "x"}), _R(_fx("token_empty.json"), 200, {"_m_h5_tk": "t_1"}),
        _R(_fx("getdetail_success.json")), _R(_fx("getdesc_success.json"))]))
    A.run(seller, ok_item, via="relay")
    monkeypatch.setattr(T, "session_for", lambda via, **kw: FakeSession([
        _R('{"ret":["RGV587_ERROR::SM::哎哟喂,被挤爆啦,请稍后重试!"],"data":{}}')]))
    A.run(seller, rgv_item, via="direct")
    s = MS.summary(3)
    assert s["total"]["tried"] - before["tried"] == 2 and s["total"]["ok"] - before["ok"] == 1
    assert s["total"]["rgv587"] - before["rgv587"] == 1 and s["routes"]["relay"]["rate"] == 100
    first = MS.first_items()
    assert [e["item_id"] for e in first] == [ok_item, rgv_item] and first[0]["state"] == "done" and first[1]["kind"] == "rgv587"
    assert first[0]["took_sec"] is not None and "→" not in first[0]["collected_kst"]
    smp = MS.sample()
    assert smp["raw"]["data"]["item"]["itemId"] == "733241700286" and smp["route"] == "relay"
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop").get_data(as_text=True)
    assert 'data-role="mtop-stats"' in h and "relay2(서울): 시도" in h and 'data-role="mtop-first"' in h
    d = c.get("/admin/diagnostics/taobao-mtop/sample.json")
    assert d.status_code == 200 and d.get_json()["data"]["item"]["title"].startswith("格斯潘")


# ── Z3-H2(오너 2026-10-05 17:04 실측: 꼬리 붙임 · GET 200 · 쿠키통 x5secdata@.taobao.com · 3차 스크립트) ───────

def _hs_page():
    r = _R(_fx("x5_handshake_jump.txt"), 200, {"x5secdata": "xd7b2268357469676865727d0a1234567890abcdef"})
    r.headers = {"Content-Type": "text/html;charset=UTF-8",
                 "Set-Cookie": ["x5secdata=xd7b2268357469676865727d0a1234567890abcdef; Domain=.taobao.com; Path=/"]}
    return r


def test_x5secdata_counts_and_retry_goes_to_jump_url():
    from src.collectors import taobao_mtop as T
    assert len(_fx("x5_handshake_jump.txt")) == 987
    s = FakeSession([_R(_fx("x5_referer.txt")), _hs_page(),
                     _R(_fx("token_empty.json"), 200, {"_m_h5_tk": "tok_1"}), _R(_fx("getdetail_success.json"))])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "733241700286"})
    assert r["state"] == "ok"
    first_api = s.calls[0][0]
    jump_call, jump_cookies = s.calls[2]
    assert jump_call == first_api + "&x5step=2&uuid=f2b9c8e1a7d34c6b&rand=Q9xk2TfR"   # 원 URL이 아니라 jump URL
    assert "x5secdata" in jump_cookies                                              # 재시도에 실렸다
    assert "x5 계열 쿠키 x5secdata(헤더) · jump URL 재현함 → 그 주소로 재시도" in r["log"][0]
    assert any(l.startswith("2차 요청: jump URL · 실은 x5 계열 쿠키 x5secdata") for l in r["log"])
    hd = r["handshakes"][0]
    assert hd["got"] == ["x5secdata"] and hd["jump"].endswith("uuid=f2b9c8e1a7d34c6b&rand=Q9xk2TfR")
    assert hd["body_len"] == 987 and len(hd["body_head"]) >= 980                     # 본문 전부(500자 컷 없음)
    assert T.enrich_payload(r["json"])["title"].startswith("格斯潘")


def test_still_script_after_handshakes_is_x5_loop_not_ip_reputation():
    """Z3-B: rand/uuid로 「IP 평판」을 점치던 판정은 폐기 — 로그인 표지 없이 다시 1단계 스크립트면 x5_loop."""
    from src.collectors import taobao_mtop as T
    same = _fx("x5_referer.txt")
    other = same.replace("rand=Q9xk2TfR", "rand=ZZnew111").replace("uuid=8b1f0c3e5d7a4e21", "uuid=99aa88bb77cc66dd")
    for third in (same, other):
        s = FakeSession([_R(same), _hs_page(), _R(same), _hs_page(), _R(third)])
        r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
        assert r["state"] == "error" and r["kind"] == "x5_loop" and r["reason"] == T.X5_LOOP_WHY
        assert not any("IP 평판" in l or "rand/uuid 1차" in l for l in r["log"]) and "IP 평판" not in r["reason"]


def test_jump_url_refuses_to_guess():
    from src.collectors import taobao_mtop as T
    hs = "https://h5api.m.taobao.com/h5/_____tmd_____/page/set_x5referer?rand=r&uuid=u&x5referer=https%3A%2F%2Fa.b%2F%3Fx%3D1"
    assert T.jump_url('var j = decodeURIComponent(x5referer) + "&u=1"; location.href = j;', hs) == "https://a.b/?x=1&u=1"
    assert T.jump_url("location.href = buildUrl(x5referer, Date.now());", hs) == ""      # 모르는 계산 → 재현 안 함
    assert T.x5_ids(hs) == ("r", "u")


def test_share_card_polls_auto_result_with_code(monkeypatch):
    """Z3-P 5): 자동 경로가 켜진 담기 — 담았어요 카드가 결과를 확인, 실패면 사유 코드까지."""
    from pathlib import Path
    from src.collectors import taobao_mtop as T
    from src.services import taobao_auto as A
    part = Path("src/seller_console/templates/_share_auto.html").read_text(encoding="utf-8")
    assert "/auto-enrich" in part and 'data-role="share-auto"' in part
    seller = "owner-z3p-card"
    iid = _share_item(seller)
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    monkeypatch.delenv("TAOBAO_MTOP_AUTO", raising=False)
    assert c.get(f"/seller/collect/{iid}/auto-enrich").get_json()["state"] == "off"
    monkeypatch.setenv("TAOBAO_MTOP_AUTO", "1")
    assert c.get(f"/seller/collect/{iid}/auto-enrich").get_json()["state"] == "running"
    monkeypatch.delenv("TAOBAO_PROXY_URL", raising=False)
    monkeypatch.setenv("TAOBAO_MTOP_ROUTE", "proxy")
    A.run(seller, iid)                                                    # 프록시 미설정 → 조용한 폴백 없이 실패 표기
    d = c.get(f"/seller/collect/{iid}/auto-enrich").get_json()
    assert d["state"] == "manual" and d["kind"] == "proxy_unset" and d["line"].startswith("자동 수집 실패(proxy_unset) — 프록시 미설정")


def test_share_route_card_shows_auto_block_when_kicked(monkeypatch):
    """L1 캡처 중 발견: share_collect_core가 `auto_enrich`를 결과에 안 실어 담았어요 카드가 자동 수집 줄을 한 번도 못 띄웠다."""
    from urllib.parse import quote
    from src.services import taobao_auto as A
    monkeypatch.setattr(A, "kick", lambda u, i: True)
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner-share-auto"
    text = "【淘宝】迷你除湿机 https://item.taobao.com/item.htm?id=667810641388 点击链接直接打开"
    h = c.get("/seller/collect/share?v=2&text=" + quote(text)).get_data(as_text=True)
    assert 'data-role="share-auto"' in h and 'data-role="share-enrich"' not in h
    # 끝나면 채워진 검수 화면으로 — 공유 주소 다시 불러오기(=중복 담기 「이미 담은 상품이에요」) 금지
    from pathlib import Path
    part = Path("src/seller_console/templates/_share_auto.html").read_text(encoding="utf-8")
    assert "location.replace('/seller/m/item/'" in part and "location.reload()" not in part
    monkeypatch.setattr(A, "kick", lambda u, i: False)                     # 꺼져 있으면 기존 안내 그대로
    h2 = c.get("/seller/collect/share?v=2&text=" + quote(text.replace("667810641388", "667810641399"))).get_data(as_text=True)
    assert 'data-role="share-auto"' not in h2 and 'data-role="share-enrich"' in h2
