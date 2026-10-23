"""Y15(오너 2026-10-22 순찰 29·합본) — 메모리 계단 기록 · 텐센트 세션 닫기 · 공유 사용자 출고지 · 소파≠빈백 · 어린이제품 보류.

운영 10-21 밤: 잡마다 프로세스 바닥 +8~34MB, 살아 있는 스레드 9→15/16. 원인은 미확인 — 여기서는
① 클라이언트 세션을 다 쓰면 닫고 ② 무거운 줄마다 앞뒤 MB·스레드·**새로 남은 스레드 이름**을 남긴다(다음 원인 특정용).
"""
import json
import threading

import pytest


# ---------------------------------------------------------------------------
# 텐센트 SDK 세션 — 호출마다 새 requests.Session, 닫지 않는다 → 다 쓰면 닫는다
# ---------------------------------------------------------------------------

class _Sess:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


class _FakeClient:
    made = []

    def __init__(self, *a, **k):
        self.request = type("R", (), {})()
        self.request.conn = type("C", (), {})()
        self.request.conn._session = _Sess()
        _FakeClient.made.append(self)

    def call_json(self, action, params):
        if params.get("boom"):
            raise RuntimeError("x")
        return {"Response": {"TextDetections": [], "TargetText": "번역"}}


def test_close_client_closes_sdk_session_and_never_raises():
    from src.services.image_translate_tencent import close_client
    c = _FakeClient()
    close_client(c)
    assert c.request.conn._session.closed == 1
    close_client(None)                                            # 모양이 달라도 조용히
    close_client(object())


def test_ocr_call_closes_session_even_on_error(monkeypatch):
    pytest.importorskip("tencentcloud")
    import tencentcloud.common.common_client as cc
    from src.services import image_translate_tencent as T
    from src.services import ocr_tencent as O
    monkeypatch.setattr(cc, "CommonClient", _FakeClient)
    monkeypatch.setattr(T, "_secret", lambda: ("a", "b"))
    _FakeClient.made.clear()
    O._call("aGk=")
    monkeypatch.setattr(_FakeClient, "call_json", lambda self, a, p: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        O._call("aGk=")
    assert [c.request.conn._session.closed for c in _FakeClient.made] == [1, 1]


def test_text_translate_closes_session(monkeypatch):
    pytest.importorskip("tencentcloud")
    import tencentcloud.common.common_client as cc
    from src.services import image_translate_tencent as T
    monkeypatch.setattr(cc, "CommonClient", _FakeClient)
    monkeypatch.setattr(T, "_secret", lambda: ("a", "b"))
    monkeypatch.setattr(T, "is_configured", lambda: True, raising=False)
    _FakeClient.made.clear()
    T.translate_text("你好")
    assert _FakeClient.made and all(c.request.conn._session.closed == 1 for c in _FakeClient.made)


# ---------------------------------------------------------------------------
# 재현: 치수 수집 3회 뒤 스레드 수 원복 + 무거운 줄 메모리 기록(op_job)
# ---------------------------------------------------------------------------

def _sofa_item(iid="4863d363-274a-431f-a8fe-4b4b531c9bd9"):
    ex = {"title": "懒人沙发", "title_ko": "빈백 소파", "images": ["https://img/1.jpg"],
          "detail_images": ["https://img/d1.jpg", "https://img/d2.jpg"]}
    return {"id": iid, "url": "https://item.taobao.com/item.htm?id=1", "extra_json": json.dumps(ex, ensure_ascii=False)}


def test_dims_fetch_three_runs_leave_no_threads(monkeypatch):
    """오너 「치수 수집 3회 뒤 스레드 수 원복」 — 온바운드·사진 OCR 경로를 세 번 돌려도 살아 있는 스레드가 늘지 않는다."""
    from src.services import dims_fetch as DF
    before = threading.active_count()
    for _ in range(3):
        out = DF.fetch(_sofa_item(), ob_call=lambda iid: {"item": {"props": [{"name": "尺寸", "value": "80*70*60cm"}]}},
                       ocr=lambda url: "尺寸 80×70×60cm")
        assert "dims_auto" in out
    assert threading.active_count() == before


def test_drain_records_heavy_op_memory_and_new_threads(monkeypatch):
    from src.services import oneshot_ops as O
    from src.db import image_translate_queue_pg as st
    from src.utils import rss, render_worker
    store = {O.QUEUE_KEY: {"rows": [{"op": "dims_fetch", "item_id": "4863d363"}, {"op": "thumb_probe", "item_id": "x"}]}}
    monkeypatch.setattr(st, "_enabled", lambda: False)          # 순찰 57: 원자 쓰기(state_update)도 같은 저장소
    monkeypatch.setattr(st, "_MEM_STATE", store)
    monkeypatch.setattr(rss, "read_mb", lambda: (250, 300))
    monkeypatch.setattr(rss, "release", lambda reason="": (262, 240))
    recs = []
    monkeypatch.setattr(render_worker, "record", lambda kind, **kw: recs.append(dict(kw, kind=kind)))
    left = []

    def _run(row):
        if row["op"] == "dims_fetch":                             # 잡 끝에도 살아 남는 스레드 하나를 흉내
            ev = threading.Event()
            th = threading.Thread(target=ev.wait, args=(2,), daemon=True, name="leftover-sdk")
            th.start()
            left.append(ev)
        return {"ok": True}
    monkeypatch.setattr(O, "_run", _run)
    O.drain()
    for ev in left:
        ev.set()
    assert len(recs) == 1                                         # 무거운 줄만 기록(가벼운 줄은 안 잰다)
    r = recs[0]
    assert r["kind"] == "op_job" and r["op"] == "dims_fetch" and r["item"] == "4863d363"
    assert (r["start_mb"], r["rel_before_mb"], r["rel_after_mb"]) == (250, 262, 240)
    assert r["threads_after"] == r["threads_before"] + 1 and r["new_threads"] == ["leftover-sdk"]


def test_drain_memory_record_failure_does_not_stop_queue(monkeypatch):
    from src.services import oneshot_ops as O
    from src.db import image_translate_queue_pg as st
    from src.utils import rss
    store = {O.QUEUE_KEY: {"rows": [{"op": "dims_fetch", "item_id": "a"}]}}
    monkeypatch.setattr(st, "_enabled", lambda: False)          # 순찰 57: 원자 쓰기(state_update)도 같은 저장소
    monkeypatch.setattr(st, "_MEM_STATE", store)
    monkeypatch.setattr(rss, "release", lambda reason="": 1 / 0)
    monkeypatch.setattr(O, "_run", lambda row: {"ok": True})
    out = O.drain()
    assert out["picked"] == 1 and out["rows"][0]["result"] == {"ok": True}


# ---------------------------------------------------------------------------
# 공유 사용자(구글 로그인 두 번째 계정) — 마켓 키 주인(오너) 계정의 출고지
# ---------------------------------------------------------------------------

def _creds(monkeypatch, shared: bool):
    from src.seller_console import market_credentials as MC
    from src.seller_console import market_pick
    import src.auth.identity as ident
    monkeypatch.setattr(ident, "OWNER_USER_ID", "owner-1")
    monkeypatch.setattr(market_pick, "session_is_shared", lambda admin=None: shared)
    # Y15 P0-2: 공유 판정 = 잡 주인 user_id(세션 무관) — google-2(두 번째 로그인)가 공유면 그 잡은 어디서 돌든 오너 저장값
    monkeypatch.setattr(MC, "seller_shared_reason",
                        lambda sid: "owner" if sid == "owner-1" else ("FAMILY_EMAILS" if shared and sid == "google-2" else ""))
    saved = {("owner-1", "coupang:gogane"): {"COUPANG_GOGANE_OVERSEAS_SHIPPING_PLACE_CODE": "77"}}
    monkeypatch.setattr(MC, "credential_env", lambda sid, m: dict(saved.get((sid, m), {})))
    monkeypatch.setattr(MC, "env_fallback_allowed", lambda: True)
    return MC


def test_shared_user_uses_owner_outbound_profile(monkeypatch):
    import os
    from flask import Flask, session
    MC = _creds(monkeypatch, shared=True)
    app = Flask(__name__)
    app.secret_key = "t"
    with app.test_request_context():
        session["user_id"] = "google-2"
        with MC.seller_market_env("google-2", ["coupang:gogane"]):
            assert os.environ.get("COUPANG_GOGANE_OVERSEAS_SHIPPING_PLACE_CODE") == "77"
    assert "COUPANG_GOGANE_OVERSEAS_SHIPPING_PLACE_CODE" not in os.environ


def test_non_shared_or_no_session_never_reads_owner_profile(monkeypatch):
    import os
    from flask import Flask, session
    app = Flask(__name__)
    app.secret_key = "t"
    MC = _creds(monkeypatch, shared=False)                        # 일반 가입자 — 자기 저장 키만(오너 확인 완료)
    with app.test_request_context():
        session["user_id"] = "seller-9"
        with MC.seller_market_env("seller-9", ["coupang:gogane"]):
            assert "COUPANG_GOGANE_OVERSEAS_SHIPPING_PLACE_CODE" not in os.environ
    MC = _creds(monkeypatch, shared=False)                        # Y15 P0-2: 판정은 잡 주인 — 공유 아닌 주인의 잡은 크론에서도 안 씀
    with MC.seller_market_env("google-2", ["coupang:gogane"]):
        assert "COUPANG_GOGANE_OVERSEAS_SHIPPING_PLACE_CODE" not in os.environ
    with app.test_request_context():                              # 세션이 누구든(오너 모양이어도) 잡 주인이 공유가 아니면 안 씀
        session["user_id"] = "someone-else"; session["user_role"] = "admin"
        with MC.seller_market_env("google-2", ["coupang:gogane"]):
            assert "COUPANG_GOGANE_OVERSEAS_SHIPPING_PLACE_CODE" not in os.environ


# ---------------------------------------------------------------------------
# 네이버 매핑 — 「소파」인데 빈백 신호 없으면 빈백 아님(805773b6 허리 보호 소파)
# ---------------------------------------------------------------------------

def test_sofa_without_beanbag_signal_maps_to_armchair_not_beanbag():
    from src.uploaders.category_rules import naver_fix
    r = naver_fix({"title_ko": "허리 보호 소형 소파, 1인용 소파", "title_src": "护腰小沙发人体工学懒人沙发"}, "77916")
    assert r and r["id"] == "50003291" and "빈백 아님" in r["why"]
    assert naver_fix({"title_ko": "빈백 소파 1인용", "title_src": "懒人沙发豆袋"}, "77916") is None   # 진짜 빈백은 그대로


# ---------------------------------------------------------------------------
# 어린이제품 표시(2f523fc1 바퀴 의자 「아기 전용 의자」) — 사전검증 보류 + 전송 차단, 인증 단정 없음
# ---------------------------------------------------------------------------

def test_child_product_flag_holds_every_market_and_blocks_dispatch():
    from src.seller_console.upload_dispatcher import UploadDispatcher, readiness_message
    pd = {"title": "바퀴 의자", "price": 30000, "images": ["https://img/1.jpg"], "child_product": "아기 전용 의자"}
    for m in ("coupang", "smartstore", "elevenst"):
        holds = UploadDispatcher.readiness_holds(pd, m)
        h = next(x for x in holds if x.get("code") == "child_product")
        assert h["fix"] == "block" and h["short"] == "어린이제품 — 오너 확인"
        assert "단정하지 않음" in h["line"] and "KC" not in h["line"]
    assert readiness_message([h]) == "사전검증 — 보류: 어린이제품 — 오너 확인"
    r = UploadDispatcher.__new__(UploadDispatcher)._dispatch_one(pd, "coupang")
    assert r.success is False and r.error_code == "child_product"


def test_child_product_is_an_owner_field_and_reaches_product_data():
    from src.services import oneshot_ops as O
    assert "child_product" in O.OWNER_FIELDS
    from src.seller_console.product_builder import build_product
    item = {"id": "2f523fc1", "title": "x", "extra_json": json.dumps({"title_ko": "바퀴 의자", "child_product": " 아기 전용 의자 "},
                                                                  ensure_ascii=False)}
    assert build_product(item, None, seller_id="u1")["child_product"] == "아기 전용 의자"


def test_option_retry_runs_translate_now_once_and_reports_left_values(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    from src.services import option_translate_auto as OT
    monkeypatch.setattr(D, "_item", lambda iid: ({"id": "d5af2185-full"}, "u2"))
    calls = []
    monkeypatch.setattr(OT, "translate_now", lambda uid, iid: calls.append((uid, iid)) or {"status": "failed", "reason": "1개 남음", "sent": 2})
    monkeypatch.setattr(OT, "_load", lambda iid, uid: ({}, {"option_translate_diag": {"values": {"左手黑": "번역기가 원문 그대로 돌려줌"}}}))
    r = O._run({"op": "option_retry", "item_id": "d5af2185"})
    assert calls == [("u2", "d5af2185-full")]
    assert r == {"ok": False, "status": "failed", "why": "1개 남음", "sent": 2, "left": {"左手黑": "번역기가 원문 그대로 돌려줌"}}
    assert "option_retry" not in O.HEAVY_OPS


def test_load_capacity_is_not_product_weight():
    """운영 10-22 ROME 1인 소파 `67cb4742`: 규격 「最大承重 200kg」을 실중량으로 읽어 「대형화물 · 실중량 200kg」 — 하중은 무게가 아니다."""
    from src.seller_console import shipping_ratio as S
    assert S._read_size({"title": "沙发", "detail_specs": [["最大承重", "200kg"]]}).get("weight_kg") == 0.0
    assert S._read_size({"title": "x", "detail_specs": [["最大承重", "200kg"], ["重量", "8kg"]]})["weight_kg"] == 8.0
    assert S._read_size({"title": "x", "description": "净重 12kg，可承重150kg · 최대 하중 120kg · max load 90 kg"})["weight_kg"] == 12.0


def test_slow_naver_cdn_prewarm_does_not_starve_market_window(monkeypatch):
    """운영 10-22 cdd8f42f: 네이버 상세 CDN 미리 올리기 57.8초가 잡 마감(60초)을 다 써 4곳 모두 「12초 안에 답이 없었어요」 —
    미리 올리기는 마켓 창 밖 일이다. 준비가 마감을 넘겨도 마켓은 제 창(여기선 1초)을 받는다."""
    import time
    import src.seller_console.views as V
    from src.seller_console.upload_dispatcher import UploadDispatcher, PrevalidationResult
    from tests._pv_helper import prevalidate
    monkeypatch.setattr(V, "_PV_JOB_DEADLINE_SEC", 0.3)
    monkeypatch.setattr(V, "_PV_MARKET_TIMEOUT_SEC", 1.0)
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    monkeypatch.setattr(V, "_pv_auto_detail", lambda pd, data, results, force=False: (None, pd))
    monkeypatch.setattr(V, "_pv_auto_translate", lambda pd, data, results: (None, pd))
    monkeypatch.setattr(V, "_pv_prewarm_naver_detail", lambda pd, markets: time.sleep(0.5) or True)

    def _slowish(self, pd, market):
        time.sleep(0.3)                                          # 마켓 응답 0.3초 — 창이 0.1초로 줄면 못 받는다
        return PrevalidationResult(market=market, ok=True, message="사전검증 통과")
    monkeypatch.setattr(UploadDispatcher, "_prevalidate_market", _slowish)
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: UploadDispatcher())
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y15-cdn"
    d = prevalidate(c, {"product": {"title": "x", "title_ko": "테스트 상품", "price": 10000, "currency": "KRW",
                                    "images": ["https://img.alicdn.com/a.jpg"]}, "markets": ["coupang"]})
    rows = d.get("results") or []
    assert rows and all("12초" not in str(r.get("message")) and "답이 없었어요" not in str(r.get("message")) for r in rows), rows


def test_zhonggu_style_is_vintage_not_used():
    """운영 10-22 KYLIA 흔들의자 15df5bbf 「中古摇椅」 → 「중고 흔들의자」 — 中古(风)는 빈티지 스타일, 헌 물건(二手)이 아니다."""
    from src.collectors.ko_polish import title_fix
    assert title_fix("KYLIA 중고 흔들의자 발코니", "KYLIA 中古摇椅阳台懒人椅") == "KYLIA 빈티지 흔들의자 발코니"
    assert title_fix("중고 흔들의자 9성 새것", "二手中古摇椅九成新") == "중고 흔들의자 9성 새것"      # 진짜 중고는 그대로


def test_risk_gate_furniture_snack_cart_and_eco_formula_are_not_food_or_drug():
    """운영 10-22: 티테이블 9874c0d7 「零食推车」(간식 카트)가 「수입식품」 보류 · 원목 수납장 805282aa 사진 글자 「环保配方」의
    오역 「환경 친화적 처방」이 「의약품 — 처방」 차단. 진짜 식품·의약품은 그대로 걸린다."""
    from src.services import risk_gate as R

    def labels(ex):
        return {h["label"] for h in R.scan(ex)["hits"]}
    assert "인증: 수입식품" not in labels({"title_ko": "티테이블", "description": "它能变身为沙发边柜休闲小桌、零食推车。"})
    assert "인증: 수입식품" in labels({"title_ko": "간식", "description": "进口零食大礼包"})
    assert "의약품·의료기기" not in labels({"title_ko": "원목 수납장", "description_ko": "임신 및 유아용 환경 친화적 처방"})
    assert "의약품·의료기기" in labels({"title_ko": "처방전 필요 의약품"})
