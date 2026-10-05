"""Z3 자동 경로(오너 2026-10-05) — x5 핸드셰이크 → 토큰 왕복 → getdetail · punish → (c) 수동 · 프록시는 mtop 경로에만.

네트워크 0: 녹화/재구성 응답(`tests/fixtures/taobao_mtop/`, 출처는 그 폴더 README)을 대역 세션이 순서대로 돌려준다.
"""
from __future__ import annotations

import json
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
    assert r["state"] == "ok" and len(r["log"]) == 3
    hs_url, hs_cookies = s.calls[1]
    assert "_____tmd_____/page/set_x5referer?rand=" in hs_url and "&x5referer=https%3A%2F%2Fh5api.m.taobao.com" in hs_url
    assert s.calls[2][1].get("x5sec") == "x5abc"                         # 같은 쿠키통으로 원 요청 재시도
    assert "sign=" in s.calls[3][0] and s.calls[3][1].get("_m_h5_tk", "").startswith("tok123")
    assert "x5 핸드셰이크 스크립트 → set_x5referer GET HTTP 200 · x5referer 꼬리 붙임 · x5sec 쿠키 받음(헤더)" in r["log"][0]
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
    assert T.session_for("direct").proxies == {} and T.proxy_label() == "설정됨 · sticky 표기 없음(그대로 사용)"   # 화면엔 자격·호스트 0
    # 이 env를 읽는 곳은 mtop 모듈 하나뿐 — 쿠팡·네이버·릴레이·업로더는 안 탄다
    hits = [p for p in Path("src").rglob("*.py") if "TAOBAO_PROXY_URL" in p.read_text(encoding="utf-8")]
    assert sorted(str(p) for p in hits) == ["src/collectors/taobao_mtop.py", "src/services/taobao_auto.py"]
    # 프록시 세션을 만드는 모듈(taobao_mtop)을 들여오는 곳 = 진단 화면·자동 경로뿐 — 마켓 업로더·릴레이는 안 들여온다
    from tests._ast_probe import importers_of
    assert importers_of("taobao_mtop") == ["src/dashboard/admin_views.py", "src/services/taobao_auto.py"]


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
    assert 'data-role="m5-auto-enrich" data-state="manual"' in h and "자동 수집 실패 — 사람 확인(punish/captcha) 요구" in h
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
    assert r["state"] == "ok" and "x5sec 쿠키 받음(본문 JS)" in r["log"][0]
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
    assert r["state"] == "error" and r["kind"] == "empty" and "x5sec 미발급" in r["reason"] and len(r["handshakes"]) == 2
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
    assert "abcdef123456" not in h and "본문 앞 500자" in h


# ── Z3-P 프록시 sticky ──────────────────────────────────────────────────────────

def test_proxy_sticky_session_changes_per_item(monkeypatch):
    from src.collectors import taobao_mtop as T
    monkeypatch.setenv("TAOBAO_PROXY_URL", "http://user1:pass_country-kr_session-AAAAAAAA_lifetime-30m@geo.example:12321")
    assert T.proxy_label() == "설정됨 · 건마다 sticky 세션 교체"
    a = T.session_for("proxy", sticky="k3m9p2xa").proxies["https"]
    b = T.session_for("proxy", sticky="q8w2e4rt").proxies["https"]
    assert "_session-k3m9p2xa_lifetime-30m@" in a and "_session-q8w2e4rt_" in b and "AAAAAAAA" not in a + b
    seen = []
    monkeypatch.setattr(T, "session_for", lambda via, sticky="": (seen.append(sticky), FakeSession([_R(_fx("rgv587_punish.json"))]))[1])
    T.fetch("1", "proxy")
    T.fetch("2", "proxy")
    assert len(seen) == 2 and seen[0] != seen[1] and all(len(x) == 8 for x in seen)   # 건마다 새 세션


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
