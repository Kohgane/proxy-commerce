"""Z3-B(오너 2026-10-05) — 판정 코드(login_required · rgv587 · x5_loop · ok) + 외부 공급자 onebound 어댑터.

네트워크 0. 판정은 `tests/fixtures/taobao_mtop/`의 재구성·실측 본문, 공급자 파서는 `fixtures/providers/onebound_item_get.json`
(재구성 — 실응답 받으면 그 파일만 교체하고 이 테스트를 다시 돌린다).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_z3_mtop_auto import FakeSession, _R, _fx, _share_item

ONEBOUND_FX = Path(__file__).parent.parent / "fixtures" / "providers" / "onebound_item_get.json"


def _onebound_text():
    return ONEBOUND_FX.read_text(encoding="utf-8")


# ── 1) 판정 코드 ─────────────────────────────────────────────────────────────────

def test_987_char_login_jump_body_is_login_required():
    """오너 실측: 핸드셰이크 GET 200 · x5secdata 받음 · 본문 987자에 login_jump → login_required(IP 무관), 거기서 멈춤."""
    from src.collectors import taobao_mtop as T
    body = _fx("x5_handshake_body.txt")
    assert len(body) == 987 and "login_jump" in body and T.login_required(body)
    hs = _R(body, 200, {"x5secdata": "xd7b2268357469676865727d0a1234567890abcdef"})
    s = FakeSession([_R(_fx("x5_referer.txt")), hs])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "733241700286"})
    assert r["kind"] == "login_required" and r["state"] == "blocked" and len(s.calls) == 2      # 재시도 안 함
    assert r["reason"] == "로그인 요구 — 익명 수집 불가(IP 무관). 외부 API 또는 로그인 쿠키 경로 필요."
    assert r["stages"] == {"rgv587": False, "script": True, "x5": True, "login": True, "detail": False}
    assert [ok for _n, ok in T.verdict(r["stages"])] == [True, True, True, False, False]


@pytest.mark.parametrize("marker", ["login_jump", "https://login.m.taobao.com/login.htm?x=1",
                                    "https://login.taobao.com/member/login.jhtml?redirectURL=a"])
def test_login_markers_are_exactly_the_three(marker):
    from src.collectors import taobao_mtop as T
    assert T.login_required(f"<script>location='{marker}'</script>")
    assert not T.login_required("<script>var x = 'loginUrl';</script>")          # 표지 셋 밖은 추측으로 넓히지 않음


def test_rgv587_json_and_body():
    from src.collectors import taobao_mtop as T
    r = T.mtop_ex(FakeSession([_R(_fx("rgv587_punish.json"))]), "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert r["kind"] in ("rgv587", "punish")
    j = T.mtop_ex(FakeSession([_R('{"ret":["RGV587_ERROR::SM::哎哟喂,被挤爆啦"],"data":{}}')]),
                  "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert j["kind"] == "rgv587" and j["stages"]["rgv587"]
    b = T.mtop_ex(FakeSession([_R("<html>RGV587_ERROR 被挤爆啦</html>")]), "mtop.taobao.detail.getdetail", {"itemNumId": "1"})
    assert b["kind"] == "rgv587"


def test_json_detail_is_ok():
    from src.collectors import taobao_mtop as T
    s = FakeSession([_R(_fx("token_empty.json"), 200, {"_m_h5_tk": "t_1"}), _R(_fx("getdetail_success.json"))])
    r = T.mtop_ex(s, "mtop.taobao.detail.getdetail", {"itemNumId": "733241700286"})
    assert r["kind"] == "ok" and r["stages"]["detail"]


def test_stats_have_per_code_columns(monkeypatch):
    from src.services import mtop_stats as MS
    before = MS.summary(3)["routes"].get("proxy", {})
    MS.record("proxy", "login_required")
    MS.record("proxy", "x5_loop")
    after = MS.summary(3)["routes"]["proxy"]
    assert after["login_required"] - before.get("login_required", 0) == 1
    assert after["x5_loop"] - before.get("x5_loop", 0) == 1
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop").get_data(as_text=True)
    assert 'data-code="login_required"' in h and "로그인 요구" in h and 'data-code="x5_loop"' in h and "x5 루프" in h
    assert "IP 평판" not in h


def test_exit_line_for_every_route(monkeypatch):
    from src.collectors import taobao_mtop as T
    monkeypatch.setattr(T, "exit_ip", lambda sticky="": {"ok": True, "ip": "121.134.5.6", "country": "KR", "bytes": 300})
    assert T.exit_line("proxy", "abcd1234")["how"].startswith("프록시 경유 icanhazip")
    monkeypatch.setenv("MARKET_RELAY_IP", "203.0.113.7")
    rl = T.exit_line("relay2")
    assert rl["ip"] == "203.0.113.7" and "실측 아님" in rl["how"]
    assert "꺼짐" in T.exit_line("direct")["how"]                                  # 테스트는 네트워크 0(conftest)

    class _Resp:
        status_code, text = 200, "198.51.100.4\n"
    import requests
    monkeypatch.setenv("TAOBAO_EXIT_IP_CHECK", "1")
    monkeypatch.setattr(requests, "get", lambda url, timeout=None: _Resp())
    d = T.exit_line("direct")
    assert d["ip"] == "198.51.100.4" and d["how"] == "이 서버 직결 icanhazip 실측"


def test_diag_proxy_login_required_shows_exit_and_conclusion(monkeypatch):
    """완료 조건 1: 프록시 실측에 출구 IP 줄 + login_required 결론 줄."""
    from src.collectors import taobao_mtop as T
    from tests.test_z3_mtop_auto import IPR_STICKY
    monkeypatch.setenv("TAOBAO_PROXY_URL", IPR_STICKY)
    monkeypatch.setattr(T, "exit_ip", lambda sticky="": {"ok": True, "ip": "121.134.5.6", "country": "KR", "bytes": 320})
    monkeypatch.setattr(T, "item_id_from", lambda arg, s=None: ("733241700286", "직접 입력"))
    monkeypatch.setattr(T, "session_for", lambda via, sticky="": FakeSession([
        _R(_fx("x5_referer.txt")), _R(_fx("x5_handshake_body.txt"), 200, {"x5secdata": "xd7b22abcdef0123456789"})]))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop", query_string={"q": "733241700286", "via": "proxy"}).get_data(as_text=True)
    assert 'data-role="mtop-exit"' in h and "121.134.5.6" in h and "프록시 경유 icanhazip 실측" in h
    assert 'data-role="mtop-conclusion"' in h and "로그인 요구 — 익명 수집 불가(IP 무관)" in h
    assert "× ④ 로그인 요구 없음" in h


# ── 2) onebound 공급자 ──────────────────────────────────────────────────────────

def test_onebound_parser_fixture_all_keys():
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider as P
    p = P.normalize(json.loads(_onebound_text()))
    mtop_keys = set(T.enrich_payload({"data": {}}).keys())
    assert mtop_keys <= set(p.keys())                                   # 뒤 파이프라인이 받는 키 전부
    assert isinstance(p["price"], float) and p["price"] == 39.9 and p["currency"] == "CNY"
    assert p["images"][0] == "https://img.alicdn.com/imgextra/i1/0/O1CN01main.jpg" and len(p["images"]) == 3   # pic_url 중복 제거
    assert p["detail_images"] == ["https://img.alicdn.com/imgextra/i4/0/O1CN01desc1.jpg",
                                  "https://img.alicdn.com/imgextra/i4/0/O1CN01desc2.jpg"]
    assert p["options"] == [{"name": "颜色分类", "values": ["白色", "黑色"]}, {"name": "尺码", "values": ["S", "M"]}]
    assert [k["spec"] for k in p["skus"]] == [["白色", "S"], ["白色", "M"], ["黑色", "S"], ["黑色", "M"]]
    assert all(isinstance(k["price"], float) for k in p["skus"]) and p["skus"][1]["stock"] == 0
    assert p["source_path"] == "onebound" and p["parse_notes"] == []


def test_onebound_unknown_sku_shape_is_reported_not_guessed():
    from src.collectors import taobao_provider as P
    raw = json.loads(_onebound_text())
    raw["item"]["skus"] = [{"price": "1"}]                             # 확인 안 된 모양
    p = P.normalize(raw)
    assert p["skus"] == [] and p["parse_notes"] and "실응답 확인" in p["parse_notes"][0]


def _keys(monkeypatch, cap="100"):
    monkeypatch.setenv("ONEBOUND_KEY", "kkk_test_key_1234")
    monkeypatch.setenv("ONEBOUND_SECRET", "sss_test_secret_5678")
    monkeypatch.setenv("ONEBOUND_DAILY_CAP", cap)


def test_onebound_daily_cap_holds(monkeypatch):
    from src.collectors import taobao_provider as P
    from src.db import option_translate_queue_pg as q
    _keys(monkeypatch, cap="2")
    used = P.used_today()
    monkeypatch.setenv("ONEBOUND_DAILY_CAP", str(used + 1))
    calls = []
    tr = lambda url, params: (calls.append(params["num_iid"]) or (200, _onebound_text()))
    assert P.fetch_detail("733241700286", transport=tr)["state"] == "ok"
    r = P.fetch_detail("733241700286", transport=tr)
    assert r["state"] == "manual" and r["kind"] == "provider_cap" and r["reason"].startswith("일일 한도")
    assert calls == ["733241700286"]                                    # 한도 넘으면 호출 자체를 안 함
    assert q.day_count(P._day_key()) == used + 1


def test_onebound_keys_missing_and_boot_warning(monkeypatch):
    from src.collectors import taobao_provider as P
    from src.services import taobao_auto as A
    monkeypatch.delenv("ONEBOUND_KEY", raising=False)
    monkeypatch.delenv("ONEBOUND_SECRET", raising=False)
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    assert "키 미설정" in A.startup_check() and A.enabled()
    r = P.fetch_detail("1", transport=lambda u, p: pytest.fail("키 없으면 호출 안 함"))
    assert r["state"] == "manual" and "키 미설정" in r["reason"]
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop").get_data(as_text=True)
    assert 'data-role="mtop-via-provider"' in h and "키 미설정 — ONEBOUND_KEY · ONEBOUND_SECRET" in h


def test_onebound_error_code_is_provider_fail(monkeypatch):
    from src.collectors import taobao_provider as P
    _keys(monkeypatch)
    r = P.fetch_detail("1", transport=lambda u, p: (200, '{"error":"item-not-found","reason":"商品不存在","error_code":"2000"}'))
    assert r["state"] == "manual" and r["kind"] == "provider_fail" and "error_code 2000" in r["reason"]


def test_auto_onebound_fills_share_draft_and_never_calls_mtop(monkeypatch):
    """완료 조건 2: 공급자 onebound + 키 → 담기 1건이 가격·옵션·사진까지 자동으로(같은 병합)."""
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider as P
    from src.services import taobao_auto as A
    from src.services import mtop_stats as MS
    from src.seller_console import collect_history_store as S
    _keys(monkeypatch)
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    monkeypatch.delenv("TAOBAO_MTOP_AUTO", raising=False)
    monkeypatch.setattr(T, "fetch", lambda *a, **k: pytest.fail("onebound면 mtop을 부르지 않는다"))
    real_call = P.call
    monkeypatch.setattr(P, "call", lambda iid, transport=None: real_call(iid, transport=lambda u, p: (200, _onebound_text())))
    before = MS.summary(3)["routes"].get("onebound", {}).get("ok", 0)
    seller = "owner-z3b"
    iid = _share_item(seller)
    rec = A.run(seller, iid)
    assert rec["state"] == "done" and rec["route"] == "onebound" and rec["kind"] == "ok"
    assert rec["counts"] == {"images": 3, "skus": 4, "detail_images": 2} and rec["provider_bytes"] > 0
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert len(ex["images"]) == 3 and len(ex["skus"]) == 4 and "parse_notes" not in ex
    assert MS.summary(3)["routes"]["onebound"]["ok"] - before == 1
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"] = seller
    assert c.get(f"/seller/collect/{iid}/auto-enrich").get_json()["state"] == "done"


def test_auto_onebound_failure_goes_manual_with_code(monkeypatch):
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider as P
    from src.services import taobao_auto as A
    _keys(monkeypatch)
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    monkeypatch.setattr(T, "fetch", lambda *a, **k: pytest.fail("mtop 재시도 금지"))
    monkeypatch.setattr(P, "call", lambda iid, transport=None: {"ok": False, "kind": "provider_cap",
                                                                "why": "일일 한도 — 오늘 100건 다 씀(ONEBOUND_DAILY_CAP), 내일 다시",
                                                                "raw": None, "ms": 0, "size": 0})
    seller = "owner-z3b-fail"
    iid = _share_item(seller)
    rec = A.run(seller, iid)
    assert rec["state"] == "manual" and rec["kind"] == "provider_cap"
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"] = seller
    d = c.get(f"/seller/collect/{iid}/auto-enrich").get_json()
    assert d["state"] == "manual" and d["line"].startswith("자동 수집 실패(provider_cap) — 일일 한도")


def test_diag_provider_radio_shows_raw_masked_norm_and_billing(monkeypatch):
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider as P
    from src.db import image_translate_queue_pg as st
    st.state_set(P._SAMPLE, {})
    _keys(monkeypatch)
    raw = json.loads(_onebound_text())
    raw["api_info"] = "secret=sss_test_secret_5678"                     # 응답에 시크릿이 섞여 와도
    monkeypatch.setattr(T, "item_id_from", lambda arg, s=None: ("733241700286", "직접 입력"))
    real_call = P.call
    monkeypatch.setattr(P, "call", lambda iid, transport=None: real_call(iid, transport=lambda u, p: (200, json.dumps(raw))))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop", query_string={"q": "733241700286", "via": "provider"}).get_data(as_text=True)
    assert 'data-role="provider-norm"' in h and "옵션 颜色分类: 白色 / 黑色" in h and "가격 39.9 CNY" in h
    assert 'data-role="provider-raw"' in h and "sss_test_secret_5678" not in h and "kkk_test_key_1234" not in h
    assert "과금 단위: 상품 1건 = item_get 호출 1회" in h
    d = c.get("/admin/diagnostics/taobao-mtop/onebound-sample.json")
    assert d.status_code == 200 and d.get_json()["item"]["num_iid"] == "733241700286"
    assert "sss_test_secret_5678" not in d.get_data(as_text=True)


def test_z3l_memo_names_no_cookie_guess():
    """Z3-L은 설계 메모만 — 쿠키 이름은 실측 뒤(추측 금지)."""
    memo = (Path(__file__).parent.parent / "docs" / "z3-l.md").read_text(encoding="utf-8")
    assert "실측" in memo and "구현하지 않음" in memo
