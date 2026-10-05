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
    assert "x5 핸드셰이크 스크립트 → set_x5referer GET HTTP 200 · x5sec 쿠키 받음" in r["log"][0]
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
    assert T.session_for("direct").proxies == {} and T.proxy_label() == "설정됨"   # 화면엔 자격·호스트 0
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
    assert 'data-role="mtop-via-proxy"' in h and 'value="proxy" checked' in h and "프록시(한국 주거 · 설정됨)" in h
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
    monkeypatch.setattr(T, "session_for", lambda via: fake)
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
    monkeypatch.setattr(T, "session_for", lambda via: FakeSession([_R(_fx("rgv587_punish.json"))]))
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
