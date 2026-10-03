"""V(오너 2026-10-03) — 스마트스토어 승인 = **토큰 실측**(수동 플래그 폐기) + 한도 실측.

  1 승인 판정 = 그 스토어 키로 커머스API 토큰을 실제로 발급해 본 결과(성공=승인). 실패는 응답 원문 그대로 — 「미승인」 짐작 문구 0
  2 옛 플래그(`SMARTSTORE_*_APPROVED`)는 아무 힘이 없다 — 켜도 토큰이 안 나오면 보류
  3 토큰이 나온 스토어만 products/search로 판매중·판매대기·품절 합계를 센다 → N/1,000 · 1,000이면 「보류 — 한도 1,000 도달」
  4 10분 캐시 · 「지금 다시 확인」은 캐시를 건너뛴다 · 결과는 app_state `smartstore:probe`(토큰 값은 어디에도 없음)
  5 /admin/diagnostics 블록: 셰고가 / 고코스모스 — 토큰 OK/실패(원문) · 상품 수 N/1,000 · 마지막 확인 시각
"""
from __future__ import annotations

import pytest

from src.seller_console import smartstore_routing as SR
from src.uploaders.naver_uploader import NaverSmartStoreUploader as N

_TOKEN = "tok-SECRET-VALUE-123"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("SMARTSTORE_LIVE_PROBE", "1")
    for k in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "NAVER_COMMERCE_CLIENT_ID", "NAVER_COMMERCE_CLIENT_SECRET",
              "NAVER_CHEZGOGA_SHIP_ADDRESS_ID", "NAVER_CHEZGOGA_RETURN_ADDRESS_ID",
              "NAVER_GOCOSMOS_SHIP_ADDRESS_ID", "NAVER_GOCOSMOS_RETURN_ADDRESS_ID",
              "NAVER_CHEZGOGA_CLIENT_ID", "NAVER_CHEZGOGA_CLIENT_SECRET", "NAVER_GOCOSMOS_CLIENT_ID", "NAVER_GOCOSMOS_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    SR.reset_cache()
    yield
    SR.reset_cache()


def _keys(monkeypatch, *stores):
    for st in stores:
        monkeypatch.setenv(f"NAVER_{st.upper()}_CLIENT_ID", f"{st}-id")
        monkeypatch.setenv(f"NAVER_{st.upper()}_CLIENT_SECRET", f"$2a$10${st}secretsalt0000000000")


def _naver(monkeypatch, *, ok_stores=(), fail_raw='HTTP 400: {"code":"InvalidRequest","message":"client_id 불일치"}', count=812):
    calls = []

    def tok(self):
        calls.append(("token", self.account))
        if self.account in ok_stores:
            return _TOKEN
        self.token_error = fail_raw
        return ""

    def api(self, m, p, data=None):
        calls.append((m, p, self.account))
        return {"totalElements": count} if count is not None else {"error": "네이버 거부 — HTTP 403 {\"code\":\"Forbidden\"}"}
    monkeypatch.setattr(N, "_get_access_token", tok)
    monkeypatch.setattr(N, "_api_request", api)
    return calls


def test_approval_is_a_live_token_issue_and_failure_shows_the_raw_response(monkeypatch):
    _keys(monkeypatch, "chezgoga", "gocosmos")
    calls = _naver(monkeypatch, ok_stores=("gocosmos",))
    cz, gc = SR.probe("chezgoga"), SR.probe("gocosmos")
    assert cz["ok"] is False and cz["state"] == "fail"
    assert SR.status_text("chezgoga") == '토큰 발급 실패 — HTTP 400: {"code":"InvalidRequest","message":"client_id 불일치"}'
    assert gc["ok"] is True and gc["count"] == 812 and gc["at"].endswith("KST")
    assert ("POST", "/v1/products/search", "gocosmos") in calls and ("POST", "/v1/products/search", "chezgoga") not in calls
    assert all(_TOKEN not in str(v) for v in (cz, gc))                   # 토큰 값은 결과에 없다
    for st in ("chezgoga", "gocosmos"):
        assert "미승인" not in SR.status_text(st) + SR.limit_state(st)["text"]


def test_no_keys_means_no_request_and_says_which_keys(monkeypatch):
    calls = _naver(monkeypatch, ok_stores=("chezgoga",))
    p = SR.probe("chezgoga")
    assert p["state"] == "no_creds" and not calls                         # 보낸 적 없음
    assert SR.status_text("chezgoga").startswith("키 없음 — NAVER_CHEZGOGA_CLIENT_ID/NAVER_CHEZGOGA_CLIENT_SECRET")


def test_the_old_manual_flags_have_no_power(monkeypatch):
    _keys(monkeypatch, "gocosmos")
    _naver(monkeypatch)
    for k in ("SMARTSTORE_APPROVED", "SMARTSTORE_GOCOSMOS_APPROVED"):
        monkeypatch.setenv(k, "1")
    assert SR.approved("gocosmos") is False


def test_probe_is_cached_ten_minutes_and_recheck_forces(monkeypatch):
    _keys(monkeypatch, "gocosmos")
    calls = _naver(monkeypatch, ok_stores=("gocosmos",))
    SR.probe("gocosmos"); SR.approved("gocosmos"); SR.limit_state("gocosmos")
    assert [c for c in calls if c[0] == "token"] == [("token", "gocosmos")]
    SR.probe("gocosmos", force=True)
    assert len([c for c in calls if c[0] == "token"]) == 2


def test_limit_full_and_count_failure_raw(monkeypatch):
    from src.seller_console.upload_dispatcher import UploadDispatcher
    _keys(monkeypatch, "chezgoga")
    _naver(monkeypatch, ok_stores=("chezgoga",), count=1000)
    r = UploadDispatcher().prevalidate({"title": "키보드", "price": "10", "images": ["/x.png"]}, ["smartstore:chezgoga"])[0]
    assert r.hold is True and r.message == "보류 — 한도 1,000 도달 (셰고가 1,000/1,000)"
    SR.reset_cache()
    _naver(monkeypatch, ok_stores=("chezgoga",), count=None)
    st = SR.limit_state("chezgoga")
    assert st["count"] is None and not st["full"] and 'Forbidden' in st["text"]   # 못 센 이유도 원문


def test_snapshot_kept_in_app_state_without_the_token(monkeypatch):
    from src.db import image_translate_queue_pg as Q
    _keys(monkeypatch, "chezgoga", "gocosmos")
    _naver(monkeypatch, ok_stores=("gocosmos",), count=5)
    monkeypatch.setenv("RENDER_SERVICE_NAME", "proxy-commerce")
    Q.state_set("smartstore:probe", {"proxy-commerce-sg": {"gocosmos": {"state": "no_creds"}}, "gocosmos": {"state": "old"}})
    SR.probe_all(force=True)
    snap = Q.state_get("smartstore:probe")
    mine = snap["proxy-commerce"]
    assert mine["gocosmos"]["count"] == 5 and mine["gocosmos"]["state"] == "ok"
    assert mine["chezgoga"]["state"] == "fail" and "client_id 불일치" in mine["chezgoga"]["raw"]
    assert snap["proxy-commerce-sg"]["gocosmos"]["state"] == "no_creds"     # 다른 서비스 기록은 덮지 않는다
    assert "gocosmos" not in snap                                           # 옛 평면 기록은 정리
    assert "proxy-commerce" in Q.state_get("smartstore:common_key")
    monkeypatch.setenv("RENDER_SERVICE_NAME", "proxy-commerce-sg")                 # 다른 서비스가 써도
    SR.identify_common_key(force=True)
    assert {"proxy-commerce", "proxy-commerce-sg"} <= set(Q.state_get("smartstore:common_key"))   # 서로 지우지 않는다
    assert _TOKEN not in str(snap)


def test_live_probe_off_says_so_and_sends_nothing(monkeypatch):
    _keys(monkeypatch, "gocosmos")
    calls = _naver(monkeypatch, ok_stores=("gocosmos",))
    monkeypatch.setenv("SMARTSTORE_LIVE_PROBE", "0")
    assert SR.approved("gocosmos") is False and not calls
    assert SR.status_text("gocosmos").startswith("실측 꺼짐 — ")


def _settle_boot_probe():
    """앱을 처음 import하면 부팅 실측 스레드가 돈다(이 파일은 실측을 켜 둔다) — 끝나길 기다리고 캐시를 비운다."""
    import threading
    for t in threading.enumerate():
        if t.name == "smartstore-boot-probe":
            t.join(timeout=30)
    SR.reset_cache()


def test_diagnostics_block_shows_both_stores(monkeypatch):
    from src.order_webhook import app
    _settle_boot_probe()
    _keys(monkeypatch, "chezgoga", "gocosmos")
    calls = _naver(monkeypatch, ok_stores=("gocosmos",), count=778)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner-v"; s["user_role"] = "admin"; s["email"] = "owner@example.com"
    h = c.get("/admin/diagnostics").get_data(as_text=True)
    assert 'data-role="ss-probe"' in h
    assert 'data-store="chezgoga"' in h and 'data-store="gocosmos"' in h
    assert "셰고가" in h and "고코스모스" in h and "토큰 OK" in h and "778/1,000" in h
    assert "client_id 불일치" in h and "KST" in h and _TOKEN not in h
    assert "NAVER_GOCOSMOS_CLIENT_ID · NAVER_GOCOSMOS_CLIENT_SECRET · MARKET_API_RELAY_URL" in h   # 섹션 1에 이름(값 아님)
    n = len([x for x in calls if x[0] == "token"])
    r = c.post("/admin/diagnostics/smartstore-recheck")
    assert r.status_code == 302 and len([x for x in calls if x[0] == "token"]) == n + 2   # 캐시 건너뛰고 둘 다 다시


# ── V 수정(오너 2026-10-03 14:45 실측: 승인 OK · 403 GW.IP_NOT_ALLOWED) ──────────────────────────────

def test_naver_calls_are_locked_to_the_relay_when_deployed(monkeypatch):
    """V1': 배포에서 릴레이 설정이 없으면 네이버는 **보내지 않는다**(직결 IP는 유동 — 허용 목록에 못 넣는다)."""
    import requests
    from src import market_relay as mr
    for k in ("MARKET_API_RELAY_URL", "MARKET_RELAY_URL", "MARKET_RELAY_TOKEN", "MARKET_RELAY_IP"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("APP_ENV", raising=False)
    sent = []
    monkeypatch.setattr(requests, "request", lambda *a, **k: sent.append(a) or None)
    with pytest.raises(mr.RelayRequired):
        mr.relay_request("POST", N._TOKEN_URL, data={}, market="smartstore")
    assert not sent
    assert mr.route_for("smartstore", N._TOKEN_URL)["via"] == "direct"
    monkeypatch.setenv("MARKET_API_RELAY_URL", "http://158.247.231.248/mkt")
    monkeypatch.setitem(mr._RELAY_IP_CACHE, "ip", None)        # 앞 테스트가 남긴 프로세스 캐시를 비운다
    r = mr.route_for("smartstore", N._TOKEN_URL)
    assert r == {"via": "relay", "host": "158.247.231.248", "ip": "158.247.231.248"}
    assert mr.route_text("smartstore") == "릴레이 경유(MARKET_API_RELAY_URL · 158.247.231.248 → 나가는 IP 158.247.231.248)"
    assert mr.route_for("coupang", "https://api-gateway.coupang.com/x") == r          # 쿠팡과 같은 관문


def test_probe_reports_the_actual_route(monkeypatch):
    from src import market_relay as mr
    monkeypatch.setenv("MARKET_API_RELAY_URL", "http://158.247.231.248/mkt")
    monkeypatch.setitem(mr._RELAY_IP_CACHE, "ip", None)
    monkeypatch.delenv("MARKET_RELAY_IP", raising=False)
    _keys(monkeypatch, "gocosmos")
    _naver(monkeypatch, ok_stores=("gocosmos",))
    assert SR.probe("gocosmos")["via"].startswith("릴레이 경유(MARKET_API_RELAY_URL · 158.247.231.248")


def test_store_reads_only_its_own_key_names(monkeypatch):
    """V1'': 스토어는 `NAVER_<STORE>_CLIENT_ID/SECRET`만 — 공용(로그인 OAuth와 같은 이름)·NAVER_COMMERCE_*로 떨어지지 않는다."""
    for k, v in {"NAVER_CLIENT_ID": "login-id", "NAVER_CLIENT_SECRET": "login-sec",
                 "NAVER_COMMERCE_CLIENT_ID": "common-id", "NAVER_COMMERCE_CLIENT_SECRET": "common-sec"}.items():
        monkeypatch.setenv(k, v)
    up = N(account="chezgoga")
    assert (up.client_id, up.client_secret) == ("", "")
    calls = _naver(monkeypatch, ok_stores=("chezgoga",))
    assert SR.status_text("chezgoga").startswith("키 없음 — NAVER_CHEZGOGA_CLIENT_ID/NAVER_CHEZGOGA_CLIENT_SECRET 를 설정")
    assert "(또는 공용" not in SR.status_text("chezgoga")
    assert not any(c[0] == "token" and c[1] == "chezgoga" for c in calls)
    _keys(monkeypatch, "chezgoga")
    assert N(account="chezgoga").client_id == "chezgoga-id"


def test_matrix_and_health_name_the_same_keys(monkeypatch):
    """V1''·V1''': 섹션 1(매트릭스)과 섹션 4(Health)가 같은 이름 · Health는 스토어별 2장(원문·N/1,000)."""
    from src.utils.env_catalog import API_REGISTRY
    from src.dashboard import admin_views as AV
    _keys(monkeypatch, "chezgoga", "gocosmos")
    _naver(monkeypatch, ok_stores=("gocosmos",), count=778)
    monkeypatch.setattr("src.seller_console.market_integration_diagnostics.run_market_diagnostic",
                        lambda m: {"market": m, "status": "token_missing", "steps": []})
    health = AV._build_market_health()
    assert "smartstore" not in health and {"smartstore_chezgoga", "smartstore_gocosmos"} <= set(health)
    gc, cz = health["smartstore_gocosmos"], health["smartstore_chezgoga"]
    assert gc["status"] == "connected" and "778/1,000" in gc["summary"] and gc["label"] == "스마트스토어 — 고코스모스"
    assert cz["status"] == "api_error" and "client_id 불일치" in cz["summary"]
    reg = {a.name: a.env_vars for a in API_REGISTRY}
    for st in ("chezgoga", "gocosmos"):
        assert set(health[f"smartstore_{st}"]["required_env"]) <= set(reg[f"naver_commerce_{st}"])
        assert "MARKET_API_RELAY_URL" in reg[f"naver_commerce_{st}"]


# ── V 추가(오너 2026-10-03 15:02): 공용 NAVER_COMMERCE_* = 어느 스토어 앱? → 실측 후 그 스토어로 승격 ─────────

def _common_naver(monkeypatch, *, book, count=1000):
    """공용 키(client_id='common-id')만 토큰이 나온다. 주소록 응답은 `book`."""
    calls = []

    def tok(self):
        calls.append(("token", self.account, self.client_id))
        if self.client_id == "common-id":
            return _TOKEN
        self.token_error = "HTTP 401: invalid_client"
        return ""

    def api(self, m, p, data=None):
        calls.append((m, p, self.account))
        if p.startswith("/v1/seller/addressbooks-for-page"):
            return book
        if p == "/v1/seller/channels":
            return [{"channelNo": 1, "name": "셰고가 스토어"}]
        return {"totalElements": count}
    monkeypatch.setattr(N, "_get_access_token", tok)
    monkeypatch.setattr(N, "_api_request", api)
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "common-id")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "$2a$10$commonsecretsalt00000000")
    return calls


def test_common_key_owner_is_measured_from_the_address_book_and_promoted(monkeypatch):
    calls = _common_naver(monkeypatch, book={"contents": [{"addressBookNo": 107519271}, {"addressBookNo": 107519270}]})
    ident = SR.identify_common_key()
    assert ident["state"] == "identified" and ident["store"] == "chezgoga"
    assert "107519271" in ident["evidence"] and "셰고가 스토어" in ident["channels_raw"]
    rows = {p["store"]: p for p in SR.probe_all()}
    cz, gc = rows["chezgoga"], rows["gocosmos"]
    assert cz["ok"] and cz["count"] == 1000 and cz["key_src"].startswith("NAVER_COMMERCE_* (실측: 주소록에 셰고가 주소 ID")
    assert gc["state"] == "no_creds"
    assert SR.status_text("gocosmos") == ("키 없음 — NAVER_GOCOSMOS_CLIENT_ID/NAVER_GOCOSMOS_CLIENT_SECRET 를 설정하세요"
                                          "(발급 요청은 보내지 않았어요) · NAVER_COMMERCE_*는 실측상 셰고가 앱")
    assert ("POST", "/v1/products/search", "chezgoga") in calls and ("POST", "/v1/products/search", "gocosmos") not in calls
    # 실제 업로드 경로도 같은 키(캐시만 — 네트워크 0)
    n = len(calls)
    assert N(account="chezgoga").client_id == "common-id" and N(account="gocosmos").client_id == ""
    assert len(calls) == n


def test_no_promotion_when_ambiguous_or_unmatched(monkeypatch):
    _common_naver(monkeypatch, book={"contents": [{"addressBookNo": 107519271}, {"addressBookNo": 107987297}]})
    assert SR.identify_common_key()["state"] == "ambiguous"
    assert not SR.approved("chezgoga") and not SR.approved("gocosmos") and SR.promoted_store() == ""
    SR.reset_cache()
    _common_naver(monkeypatch, book={"contents": [{"addressBookNo": 1075192710}]})          # 자릿수 겹침은 일치 아님
    assert SR.identify_common_key()["state"] == "none" and not SR.approved("chezgoga")


def test_own_store_keys_win_over_the_common_key(monkeypatch):
    calls = _common_naver(monkeypatch, book={"contents": [{"addressBookNo": 107519271}]})
    _keys(monkeypatch, "chezgoga")
    SR.probe("chezgoga")
    assert ("token", "chezgoga", "chezgoga-id") in calls and not any(c[0] == "token" and c[2] == "common-id" for c in calls)


def test_relay_2xx_body_is_read_not_crashed(monkeypatch):
    """10-03 운영 실측(싱가포르): 셰고가 토큰 OK 뒤 `AttributeError: 'RelayResponse' object has no attribute 'content'`.
    릴레이 경유 네이버 2xx가 전부 이 자리에서 터졌다 — 응답 래퍼가 `.content`를 안 가졌다."""
    from src import market_relay as mr
    monkeypatch.setenv("MARKET_API_RELAY_URL", "http://158.247.231.248/mkt")
    sent = []
    monkeypatch.setattr(mr, "_api_relay_send",
                        lambda method, url, headers, j, d, t: sent.append((method, url)) or mr.RelayResponse(200, '{"totalElements": 812}'))
    monkeypatch.setattr(N, "_get_access_token", lambda self: _TOKEN)
    _keys(monkeypatch, "chezgoga")
    assert N(account="chezgoga").count_products() == 812
    assert sent and sent[0][0] == "POST" and sent[0][1].endswith("/v1/products/search")
    assert mr.RelayResponse(204, "").content == b""
