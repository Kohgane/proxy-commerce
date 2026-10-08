"""Z9(오너 2026-10-09 01:21~01:23 KST, 플리츠 세트 · 셰고가) — 사전검증 25초 초과 + 쿠팡 메타 「없음/못 받음」 구분.

증거
- 폰 마켓 등록 모달: 「사전검증 시작 실패 — 200 prevalidate_timeout 사전검증이 25초 안에 끝나지 않았어요」.
  이 모달(편집 화면)은 #844 때도 **동기 입구**를 쳤다(비동기는 폰 카드 `_m5_flow`만) → 동기 입구 폐기, 전부 202 + 잡.
- Render slow_request 25011ms · segments db 49 · external 3502 · db_queries 12 — 21초가 어느 계측에도 안 잡혔다.
  계측 밖이던 자리: 잡 스레드(요청 로그는 202로 이미 찍힘) · 연결 여는 시간(`db_connect`) · urllib3 직접 호출(Cloudinary).
- 쿠팡 SKU 칸: 「옵션 패션의류/잡화 사이즈가 이 카테고리 메타 속성에 없어」 → 「넣은 값으로 다시 확인」 「통과」(같은 데이터).
- 「실시간 환율 · 2026-10-08 16:20 갱신」 — UTC 문자열을 그대로 잘라 보였다(01:21 KST = 16:21 UTC, 실제론 1분 전).
"""
from __future__ import annotations

import logging
import threading
import time

import pytest

from tests._pv_helper import prevalidate as _pv


class _R:
    def __init__(self, m, ok=True, **kw):
        self.market, self.ok = m, ok
        self.error_code = kw.get("error_code", "")
        self.message = kw.get("message", "통과")
        self.hint = ""
        self.reach_ok = self.reach_ms = None
        self.reach_detail = ""
        self.details = list(kw.get("details", []))
        self.action_url = ""
        self.hold = kw.get("hold", False)
        self.fixes = kw.get("fixes", [])
        self.rep_pending = kw.get("rep_pending", False)


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_PV_MARKET_TIMEOUT_SEC", 1.0)
    monkeypatch.setattr(V, "_PV_JOB_DEADLINE_SEC", 6.0)
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    monkeypatch.setattr(V, "_account_codes_forbidden", lambda m: None)


def _client(uid="z9-seller"):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid)
    return c


# ── 1. 동기 입구 폐기 — 데스크톱·폰 모달·폰 카드 모두 202 + 잡 ─────────────────────────────────────────

def test_modal_post_returns_202_without_holding_a_worker(monkeypatch):
    import src.seller_console.views as V

    class Slow:
        def prevalidate(self, product, markets):
            time.sleep(2.0)
            return [_R(m) for m in markets]
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: Slow())
    c = _client()                                                            # 앱 첫 로드는 재지 않는다
    t0 = time.time()
    r = c.post("/seller/collect/prevalidate", json={"product": {"title": "플리츠 세트"}, "markets": ["smartstore"]})
    assert r.status_code == 202 and time.time() - t0 < 1.0                  # Z8: 워커 스레드 1초 넘게 쥐지 않음
    assert r.get_json()["poll"].startswith("/seller/collect/prevalidate/job/")
    assert not hasattr(V, "_PV_SYNC_DEADLINE_SEC")


def test_modal_js_uses_the_job_and_renders_partial_rows():
    from pathlib import Path
    t = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    seg = t[t.index("async function runPrevalidate()"):t.index("function renderActionLink")]
    assert "data.poll" in seg and "d.pending" in seg and "d.state === 'running'" in seg
    assert "prevalidate_timeout" not in t                                    # 25초 문구 자리 없음
    r = t[t.index("function renderPrevalidateResults("):t.index("// ── 실제 업로드 ──")]
    assert 'data-role="prevalidate-pending"' in r and "확인하는 중…" in r and "검증 못 함" in r


def test_job_line_names_external_hosts_with_ms(monkeypatch, caplog):
    """잡 한 줄에 호스트별 ms — 「텐센트로 몇 초」가 로그에 남는다(요청 로그는 202로 이미 찍혀 못 싣는다)."""
    import src.seller_console.views as V
    from src.utils.perf import perf_note_external

    class Disp:
        def prevalidate(self, product, markets):
            perf_note_external("ocr.tencentcloudapi.com", 1234.5)          # 마켓별 스레드 안의 외부 호출
            return [_R(m) for m in markets]
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: Disp())
    caplog.set_level(logging.INFO, logger=V.logger.name)
    d = _pv(_client(), {"product": {"title": "플리츠 세트"}, "markets": ["coupang"]})
    perf = (V._pv_store().state_get(V._PV_JOB_KEY + d["job_id"]) or {}).get("perf") or {}
    assert perf["external_ms_by_host"]["ocr.tencentcloudapi.com"] == [1234.5, 1]
    line = next(r.getMessage() for r in caplog.records if "[PV] job=" in r.getMessage() and "done" in r.getMessage())
    assert "ocr.tencentcloudapi.com" in line and "1234.5" in line and "market:coupang" in line


def test_tencent_sdk_goes_through_requests_adapter():
    """텐센트 SDK(CommonClient)는 `requests.Session`을 쓴다 → Z8 공통 상한(connect 5/read 15)·계측 겹을 탄다."""
    import requests
    from tencentcloud.common.http.request import ProxyConnection
    assert isinstance(ProxyConnection("ocr.tencentcloudapi.com")._session, requests.Session)
    from src.services import ocr_tencent
    assert ocr_tencent.timeout_sec() <= 10                                  # HttpProfile(reqTimeout) — 기본 8초


# ── 2. 대표 사진 글자 판정(OCR)은 사전검증 임계 경로 밖 ──────────────────────────────────────────────

def test_rep_check_does_not_wait_and_says_pending(monkeypatch):
    from src.services import coupang_image_check as cic
    from src.seller_console.upload_dispatcher import UploadDispatcher
    cic.reset_cache()
    monkeypatch.setenv("COUPANG_IMAGE_CHECK", "1")
    gate = threading.Event()

    def slow_bytes(url):
        gate.wait(5)
        return b"", "느린 다운로드"
    monkeypatch.setattr(cic, "_bytes_for", slow_bytes)
    pd = {"title": "플리츠 세트", "price": 30000, "sell_price_krw": 30000, "images": ["https://img.example/rep-z9.jpg"]}
    t0 = time.time()
    holds = UploadDispatcher.readiness_holds(pd, "coupang")
    assert time.time() - t0 < 1.0                                            # 기다리지 않는다
    assert not any(h.get("fix") == "rep_image" for h in holds)               # 보류 아님
    assert cic.rep_pending(pd, "coupang") is True                            # 「대기 중」
    gate.set()
    assert cic.wait_done(["https://img.example/rep-z9.jpg"], until_ts=time.time() + 3)
    assert cic.rep_pending(pd, "coupang") is False
    cic.reset_cache()


def test_job_refreshes_the_row_when_rep_check_lands(monkeypatch):
    """대기 중으로 낸 쿠팡 줄 → 판정이 끝나면 잡이 그 마켓을 다시 재서 줄을 갈아 끼운다(카드는 폴링으로 받는다)."""
    import src.seller_console.views as V
    from src.services import coupang_image_check as cic
    state = {"done": False}

    class Disp:
        def prevalidate(self, product, markets):
            if not state["done"]:
                return [_R(m, rep_pending=True, details=["쿠팡 대표 사진 글자 판정 대기 중"]) for m in markets]
            return [_R(m, ok=False, hold=True, fixes=["rep_image"], message="대표 사진 텍스트 있음") for m in markets]

    def fake_wait(urls, until_ts, step=0.5):
        state["done"] = True
        return True
    monkeypatch.setattr(cic, "wait_done", fake_wait)
    monkeypatch.setattr(cic, "rep_url", lambda pd, m: "https://img.example/rep.jpg")
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: Disp())
    d = _pv(_client(), {"product": {"title": "플리츠 세트", "images": ["https://img.example/rep.jpg"]}, "markets": ["coupang"]})
    row = d["results"][0]
    assert row["hold"] and "rep_image" in row["fixes"] and row["rep_pending"] is False


# ── 3. 쿠팡 메타 「확인 못 함」(meta_unavailable) ≠ 「없음」 ─────────────────────────────────────────────

class _CU:
    """실제 `CoupangUploader`에 통신만 막은 대역 — 예측·메타가 시간 초과."""

    @staticmethod
    def make(meta_timeout=True, predict_timeout=False):
        import requests
        from src.uploaders.coupang_uploader import CoupangUploader

        class U(CoupangUploader):
            def _api_request(self, method, path, data=None, **kw):
                if "predict" in path:
                    if predict_timeout:
                        raise requests.exceptions.ReadTimeout("HTTPSConnectionPool: Read timed out. (read timeout=15)")
                    return {"data": {"predictedCategoryId": "69195", "predictedCategoryName": "여성 캐주얼 세트"}}
                if meta_timeout:
                    raise requests.exceptions.ReadTimeout("HTTPSConnectionPool: Read timed out. (read timeout=15)")
                return {"data": {"attributes": [{"attributeTypeName": "패션의류/잡화 사이즈", "required": "MANDATORY"}]}}

            def outbound_for_delivery(self):
                return "OB1", ""

            def is_agent_buy(self):
                return False
        return U(access_key="ak", secret_key="sk", vendor_id="A1")


def test_meta_timeout_is_meta_unavailable_not_absent():
    up = _CU.make(meta_timeout=True)
    out = up.precheck({"title": "플리츠 미니멀 여성 여름 세트", "options": [{"name": "패션의류/잡화 사이즈", "values": ["S", "M"]}]})
    assert out["meta_unavailable"] is True and out["category"] == "69195" and out["category_source"] == "predict"
    assert out["unavailable_line"].startswith("쿠팡 카테고리 메타 확인 못 함 — 다시 확인")
    assert "Read timed out" in out["unavailable_line"]
    assert not any("메타 속성에 없어" in h for h in out["holds"])           # 「없음」이라 말하지 않는다
    assert "69195" not in up._meta_cache                                     # 실패는 굳히지 않는다(다음 확인에서 다시)


def test_dispatcher_turns_it_into_check_failed_not_pass_not_hold(monkeypatch):
    from src.seller_console.upload_dispatcher import UploadDispatcher
    import src.channel_sync.coupang_uploader as CH
    import src.seller_console.views as V
    monkeypatch.setattr(CH, "precheck", lambda pd: {
        "ok": False, "meta_unavailable": True, "holds": ["카테고리 메타를 읽지 못했습니다"],
        "unavailable_line": "쿠팡 카테고리 메타 확인 못 함 — 다시 확인 (카테고리 69195 · ReadTimeout)"})
    d = UploadDispatcher()
    monkeypatch.setattr(d, "readiness_holds", lambda pd, m: [])
    monkeypatch.setattr("src.seller_console.market_cred_view.coupang_api_state", lambda: {"missing": [], "account": ""})
    monkeypatch.setattr("src.seller_console.market_cred_view.coupang_shipping_state", lambda acct: {"missing": [], "source": ""})
    monkeypatch.setattr("src.seller_console.market_cred_view.resolve_upload_account", lambda: "")
    r = d._prevalidate_market({"title": "플리츠 세트", "price": 30000, "images": []}, "coupang")
    assert r.error_code == "meta_unavailable" and r.ok is False and r.hold is False      # 통과 아님 · 멈춤(보류) 아님
    row = V._pv_dict(r)
    assert row["transport"] == "meta_unavailable" and row["message"].startswith("쿠팡 카테고리 메타 확인 못 함")


def test_predict_timeout_does_not_fall_back_to_saved_category_silently():
    up = _CU.make(meta_timeout=False, predict_timeout=True)
    out = up.precheck({"title": "플리츠 세트", "category_id": "11111",
                       "options": [{"name": "패션의류/잡화 사이즈", "values": ["S", "M"]}]})
    assert out["category_source"] == "saved" and out["meta_unavailable"] is True
    assert "저장된 카테고리 11111로는 판정하지 않아요" in out["unavailable_line"]


def test_absent_line_names_category_and_source():
    from src.uploaders.coupang_uploader import tag_meta_absent
    line = tag_meta_absent("옵션 「사이즈」이 이 카테고리 메타 속성에 없어 SKU별로 나눌 수 없습니다", "69195", "predict")
    assert line.endswith("(쿠팡 카테고리 69195 · 쿠팡 예측)")
    assert tag_meta_absent("다른 줄", "69195", "predict") == "다른 줄"


def test_option_block_meta_timeout_says_check_again(monkeypatch):
    import src.channel_sync.coupang_uploader as CH
    up = _CU.make(meta_timeout=True)
    monkeypatch.setattr(CH, "make_uploader", lambda: (up, ""))
    monkeypatch.setattr(CH, "prepared_input", lambda pd: dict(pd))
    monkeypatch.setattr(up, "prepare_product", lambda c: dict(c))
    monkeypatch.setattr(CH, "to_collected", lambda pd: dict(pd), raising=False)
    import src.channel_sync._channel_bridge as BR
    monkeypatch.setattr(BR, "to_collected", lambda pd: dict(pd))
    out = CH.option_form({"title": "플리츠 미니멀 여성 여름 세트", "options": [{"name": "패션의류/잡화 사이즈", "values": ["S", "M"]}],
                          "skus": [{"spec": ["S"], "price": 10}, {"spec": ["M"], "price": 10}]})
    assert out["meta_unavailable"] is True and out["name_picks"] == []
    assert out["holds"] and out["holds"][0].startswith("쿠팡 카테고리 메타 확인 못 함 — 다시 확인")
    assert not any("메타 속성에 없어" in h for h in out["holds"])


# ── 4. 스톨 감시 — 사전검증 경로 10초 ──────────────────────────────────────────────────────────────

def test_stall_limit_is_10s_for_prevalidate(monkeypatch):
    from src.utils import stall_guard as sg
    monkeypatch.delenv("STALL_DUMP_SEC", raising=False)
    monkeypatch.delenv("STALL_DUMP_SEC_PREVALIDATE", raising=False)
    assert sg.limit_for("/seller/collect/prevalidate") == 10 and sg.limit_for("pv_job:abcd") == 10
    assert sg.limit_for("pv_market:coupang:abcd") == 10 and sg.limit_for("/seller/dashboard") == 30
    sg.reset()
    sg.begin("pv_job:z9test")
    try:
        start = sg._ACTIVE[threading.get_ident()]["start"]
        assert sg.check_once(now=start + 9) == []
        lines = sg.check_once(now=start + 10.5)
        assert lines and "[STALL] path=pv_job:z9test" in lines[0]
    finally:
        sg.end()
        sg.reset()


# ── 5. 계측 밖이던 자리 ────────────────────────────────────────────────────────────────────────────

def test_urllib3_direct_calls_are_counted_once(monkeypatch):
    """Cloudinary SDK처럼 urllib3를 직접 쓰는 호출도 외부 호출로 — `requests`가 부른 건 한 번만."""
    import http.server
    import socketserver
    import requests
    import urllib3
    from src.utils import perf
    perf.install_external_probe()
    perf.install_urllib3_probe()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from src.order_webhook import app
    try:
        with app.test_request_context("/z9"):
            # 전체 실행에선 앞 테스트가 남긴 앱 컨텍스트(g)가 재사용될 수 있다 — 호출 전후 **차이**로 잰다
            before = perf.perf_external_ms_by_host()
            urllib3.PoolManager().request("GET", f"http://127.0.0.1:{port}/a")
            _s = requests.Session()
            _s.trust_env = False                                              # 다른 테스트가 남긴 프록시 env를 타지 않게
            _s.get(f"http://127.0.0.1:{port}/b")
            after = perf.perf_external_ms_by_host()
            n = lambda h: after.get(h, [0, 0])[1] - before.get(h, [0, 0])[1]
            assert n("127.0.0.1(urllib3)") == 1, after                        # urllib3 직접 1건
            assert n("127.0.0.1") == 1, after                                 # requests 1건(이중 계상 0)
    finally:
        srv.shutdown()


def test_db_connect_time_is_its_own_segment(monkeypatch):
    import sys
    import types
    from src.db import pg
    from src.utils import perf

    fake = types.SimpleNamespace(connect=lambda *a, **k: (time.sleep(0.05), object())[1])
    monkeypatch.setitem(sys.modules, "psycopg", fake)
    from src.order_webhook import app
    with app.test_request_context("/z9"):
        pg._connect("postgresql://x")
        assert perf.perf_snapshot()["db_connect"] >= 50


def test_job_thread_reads_borrow_pool_and_return(monkeypatch):
    """잡·마켓별 스레드(요청 스레드 아님)의 읽기 — 풀에서 빌리고 **같은 자리에서 반납**(1회용 연결 0)."""
    from src.db import pg

    class Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Conn:
        autocommit = False

        def cursor(self):
            return Cur()

    class Pool:
        def __init__(self):
            self.out = 0
            self.got = 0

        def getconn(self, timeout=None):
            self.out += 1
            self.got += 1
            return Conn()

        def putconn(self, c):
            self.out -= 1
    pool = Pool()
    monkeypatch.setattr(pg, "_persistent_pool", lambda: pool)
    monkeypatch.setattr(pg, "_request_read_conn", lambda: (None, False))
    monkeypatch.setattr(pg, "_connect", lambda *a, **k: pytest.fail("1회용 연결을 열었다"))
    for _ in range(3):
        with pg.query() as cur:
            assert cur is not None
    assert pool.got == 3 and pool.out == 0


# ── 6. 환율 표기 — KST · 묵었으면 「n시간 전 환율」 ─────────────────────────────────────────────────

def test_fx_time_is_kst_and_age():
    from datetime import datetime, timezone
    from src.price import fx_age
    now = datetime(2026, 10, 8, 16, 21, tzinfo=timezone.utc)                 # 01:21 KST
    assert fx_age("2026-10-08T16:20:00+00:00", now=now) == ("2026-10-09 01:20", 1)
    assert fx_age("2026-10-08T07:20:00Z", now=now) == ("2026-10-08 16:20", 541)
    assert fx_age("", now=now) == ("", None)


def test_fx_label_drops_realtime_when_stale(monkeypatch):
    from datetime import datetime, timedelta, timezone
    import src.seller_console.data_aggregator as DA
    from src.price import sell_fx_rates
    monkeypatch.delenv("FX_USE_LIVE", raising=False)
    old = (datetime.now(timezone.utc) - timedelta(hours=9, minutes=5)).isoformat()
    monkeypatch.setattr(DA, "get_fx_rates", lambda: {"CNY": 190.0, "USD": 1380.0, "source": "frankfurter",
                                                     "is_mock": False, "updated_at": old})
    _r, info = sell_fx_rates()
    assert info["CNY"]["label"] == "9시간 전 환율" and info["CNY"]["source"] == "stale"
    fresh = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(DA, "get_fx_rates", lambda: {"CNY": 190.0, "USD": 1380.0, "source": "frankfurter",
                                                     "is_mock": False, "updated_at": fresh})
    _r, info = sell_fx_rates()
    assert info["CNY"]["label"] == "실시간 환율" and info["CNY"]["updated_kst"]


def test_fx_js_prints_kst_not_raw_utc():
    from pathlib import Path
    t = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    seg = t[t.index("function kgpCpFx("):t.index("// 카테고리 자동 분류")]
    assert "updated_kst" in seg and "갱신(KST)" in seg and "slice(0, 16)" not in seg


# ── 7. 쿠팡 경로 표 없이 리프 이름만으로 맞춘 네이버 카테고리 = 「추정」 ─────────────────────────────────

def test_category_without_coupang_path_is_marked_estimated(monkeypatch):
    from src.uploaders import naver_categories as NC
    monkeypatch.setattr(NC, "tree", lambda *a, **k: {"leaves": {"50000816": "패션의류>여성의류>정장세트"}})
    monkeypatch.setattr(NC, "coupang_guess", lambda p: {"id": "69195", "name": "여성 정장세트", "path": "", "why": ""})
    out = NC.compute_suggestion({"title_ko": "플리츠 미니멀 여성 여름 정장 세트"})
    assert out["estimated"] is True
    monkeypatch.setattr(NC, "coupang_guess", lambda p: {"id": "69195", "name": "여성 캐주얼 세트",
                                                        "path": "패션의류잡화>여성패션>여성의류>정장/세트>여성 캐주얼 세트", "why": ""})
    assert NC.compute_suggestion({"title_ko": "플리츠 미니멀 여성 여름 정장 세트"})["estimated"] is False
