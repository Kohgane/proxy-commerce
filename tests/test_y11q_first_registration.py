"""Y11-Q(오너 2026-10-16 00:38~00:41) — VRSUK 첫 등록 후속 계약.

운영 근거(10-15 15:38~15:39 UTC `app_state detail_translate:recent`): 텐센트 TextTranslate 102회 전부 실패 — 최근 40줄 중
RequestLimitExceeded 28 · InvalidParameterValue 12. 1초 안에 4~13회가 몰렸다(묶음 5개 × 사전검증·등록·마켓 병렬).
AI 축약 3건은 열쇠가 **한국어 값**으로 저장돼(네이버 계획은 SKU 원문으로 찾는다) 재검증해도 25자 초과 그대로였고,
값도 「…아닐린 천연소」(낱말 중간 절단)·발받침 빠짐.
"""
import json
import time
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
VR = json.loads((FIX / "y11o_vrsuk_risk.json").read_text(encoding="utf-8"))
VRO = json.loads((FIX / "y11p_vrsuk_options.json").read_text(encoding="utf-8"))
SELL = {"6995.00": 3592100, "7183.00": 3683990, "8822.00": 4485110, "9913.00": 5018380,
        "10460.00": 5285750, "11535.00": 5811190}


def _vr(**kw):
    return {"title": "VRSUK", "options": VRO["options"],
            "skus": [dict(k, sell_price_krw=SELL[k["price"]]) for k in VRO["skus"]], **kw}


@pytest.fixture
def state(monkeypatch):
    import src.db.image_translate_queue_pg as st
    box = {}
    monkeypatch.setattr(st, "state_get", lambda k: dict(box.get(k) or {}))
    monkeypatch.setattr(st, "state_set", lambda k, v: box.__setitem__(k, json.loads(json.dumps(v))))
    return box


# ── 1. 텐센트 묶음 호출 · 초당 5회 · 백오프 · InvalidParameterValue 부검 ─────────────────────────────

class _Exc(Exception):
    def __init__(self, code, message=""):
        super().__init__(message)
        self.code, self.message = code, message


def _fake_client(monkeypatch, plan):
    """CommonClient 대역 — 호출마다 plan에서 하나씩(예외 또는 답). 호출 시각·본문을 남긴다."""
    import tencentcloud.common.common_client as cc
    import src.services.image_translate_tencent as TT
    calls = []

    class C:
        def __init__(self, *a, **k):
            pass

        def call_json(self, action, body):
            calls.append((time.monotonic(), body))
            step = plan.pop(0) if plan else None
            if isinstance(step, Exception):
                raise step
            src = body["SourceText"]
            return {"Response": {"TargetText": step if isinstance(step, str) else
                                 "\n".join(f"번역{i}" for i, _ in enumerate(src.split("\n")))}}
    monkeypatch.setattr(cc, "CommonClient", C)
    monkeypatch.setattr(TT, "is_configured", lambda: True)
    monkeypatch.setattr(TT, "_secret", lambda: ("id", "key"))
    monkeypatch.setattr(TT, "time", __import__("time"))
    return calls


def test_vrsuk_51_lines_go_in_one_call_not_five(monkeypatch, state):
    from src.uploaders import detail_translate as dt
    from src.uploaders.detail_ui_junk import strip_page_ui
    calls = _fake_client(monkeypatch, [])
    dt._CACHE.clear()
    dt._FAIL.clear()
    body = strip_page_ui(VR["description"])["text"]
    r = dt.translate_leftover(body)
    assert len(calls) == 1 and r["failed"] == 0 and r["translated"] >= 15          # 예전: 떨어진 줄마다 묶음 5개 → 5회 · Y11-W: 규격은 「키: 값」 짝(16)으로·내수·태그 짝은 번역 전에 빠짐
    assert len(calls[0][1]["SourceText"]) <= 2000


def test_throttle_five_per_second_and_backoff_on_rate_limit(monkeypatch, state):
    import src.services.image_translate_tencent as TT
    calls = _fake_client(monkeypatch, [_Exc("RequestLimitExceeded"), _Exc("RequestLimitExceeded"), "번역"])
    TT._TEXT_LAST[0] = 0.0
    r = TT.translate_text("实木")
    assert r["ok"] and r["attempts"] == 3 and len(calls) == 3
    gaps = [b[0] - a[0] for a, b in zip(calls, calls[1:])]
    assert gaps[0] >= 0.45 and gaps[1] >= 0.95                                # 0.5·1초 지수 백오프(+0.2초 간격 안)
    calls.clear()
    for _ in range(4):
        TT.translate_text("布艺")
    gaps = [b[0] - a[0] for a, b in zip(calls, calls[1:])]
    assert gaps and min(gaps) >= 0.19                                          # 초당 5회


def test_invalid_parameter_bisects_and_logs_which_line(monkeypatch, state):
    from src.uploaders import detail_translate as dt

    def fn(text):                                                              # 「\x07」이 든 줄만 거부
        if "坏" in text:
            return {"ok": False, "text": "", "why": "InvalidParameterValue",
                    "message": "SourceText contains illegal characters"}
        return {"ok": True, "text": "\n".join(f"옮김{i}" for i, _ in enumerate(text.split("\n"))), "why": ""}
    dt._CACHE.clear()
    dt._FAIL.clear()
    r = dt.translate_leftover("金属\n坏行\n实木\n布艺", translate_fn=fn)
    assert r["translated"] == 3 and r["failed"] == 1                           # 나쁜 줄 하나만 실패
    rows = state[dt.RECENT_KEY]["rows"]
    bad = [x for x in rows if "InvalidParameter" in x["why"]]
    assert bad and bad[-1]["message"].startswith("SourceText contains") and bad[-1]["lines_diag"][0]["text"] == "坏行"
    assert all("han" in d and "ctrl" in d and "len" in d for d in bad[0]["lines_diag"])


def test_control_chars_are_stripped_before_sending():
    from src.uploaders import detail_translate as dt
    assert dt.clean_line("实木\x07​ ") == "实木"
    assert dt.line_diag("实\x07木")["ctrl"] is True


# ── 1b. 이미 등록된 쿠팡 상세 갱신 · 막히면 「승인 후 자동 갱신」 큐 ──────────────────────────────────

class _FakeUp:
    def __init__(self, modify_ok=True, status="심사중"):
        self.modify_ok, self.status, self.bodies = modify_ok, status, []

    def get_product(self, sid):
        return {"sellerProductId": int(sid), "statusName": self.status,
                "items": [{"itemName": "a", "contents": [{"contentsType": "TEXT", "contentDetails": [{"content": "83cm"}]}]}]}

    def modify_product(self, body):
        self.bodies.append(body)
        if self.modify_ok:
            return {"success": True, "market_status": 200}
        return {"success": False, "error": "쿠팡 수정 거부: 승인 진행 중인 상품은 수정할 수 없습니다", "market_status": 400,
                "body": '{"code":"ERROR","message":"승인 진행 중인 상품은 수정할 수 없습니다"}'}

    def review_status(self, sid):
        return {"state": "approved" if self.status == "승인완료" else "pending"}

    def prepare_product(self, p):
        return p

    def _build_contents(self, p):
        return [{"contentsType": "TEXT", "contentDetails": [{"content": p.get("description_html") or "", "detailType": "TEXT"}]}]


def _item():
    ex = {"title": "椅子", "title_ko": "VRSUK 리클라이너", "description": "材质\n实木\n83cm", "description_ko": "",
          "price": "6995", "currency": "CNY",
          "uploaded": [{"market": "coupang:gogane", "account": "gogane", "product_id": "16415921785"},
                       {"market": "coupang:woojoo", "account": "woojoo", "product_id": "16415921921"}]}
    return {"id": "4ebaf1b8-cead-4645-b8aa-85f365be3f81", "extra_json": json.dumps(ex, ensure_ascii=False)}


def _patch_target(monkeypatch, ready=True):
    from src.services import coupang_detail_refresh as cdr

    def tgt(item, up, seller_id=""):
        contents = up._build_contents({"description_html": "재질\n원목\n83cm"})
        return {"ready": ready, "contents": contents, "hash": cdr._hash(contents), "translated": 2,
                "failed": 0 if ready else 2, "why": "" if ready else "RequestLimitExceeded"}
    monkeypatch.setattr(cdr, "target", tgt)


def test_refresh_sends_contents_only_and_records(monkeypatch, state):
    from src.services import coupang_detail_refresh as cdr
    _patch_target(monkeypatch)
    up = _FakeUp(modify_ok=True)
    saved = {}
    rows = cdr.refresh_item(_item(), make_up=lambda a: up, save=lambda ex: saved.update(ex))
    assert [r["ok"] for r in rows] == [True, True] and len(up.bodies) == 2
    b = up.bodies[0]
    assert b["items"][0]["contents"][0]["contentDetails"][0]["content"] == "재질\n원목\n83cm" and b["requested"] is True
    assert saved["coupang_detail_sync"]["coupang:gogane"]["ok"] and cdr.queue_rows() == []
    # 같은 상세는 다시 안 보낸다(재심사 두 번 금지)
    rows2 = cdr.refresh_item({**_item(), "extra_json": json.dumps(saved, ensure_ascii=False)}, make_up=lambda a: up)
    assert len(up.bodies) == 2 and all(r["state"] == "same" for r in rows2)


def test_refresh_blocked_in_review_goes_to_queue_with_raw_then_cron_sends_after_approval(monkeypatch, state):
    from src.services import coupang_detail_refresh as cdr
    _patch_target(monkeypatch)
    up = _FakeUp(modify_ok=False, status="심사중")
    rows = cdr.refresh_item(_item(), make_up=lambda a: up)
    assert not rows[0]["ok"] and rows[0]["market_status"] == 400 and "승인 진행 중" in rows[0]["body"]
    q = cdr.queue_rows()
    assert {r["market"] for r in q} == {"coupang:gogane", "coupang:woojoo"}
    assert q[0]["reason"] == "승인 후 자동 갱신" and "승인 진행 중" in q[0]["raw"]
    # 크론: 아직 검토 중 → 보내지 않고 기다림
    out = cdr.drain(lambda iid, sid: _item(), lambda iid, sid: (lambda ex: None), make_up=lambda a: up)
    assert out["sent"] == 0 and len(cdr.queue_rows()) == 2
    # 승인 → 보낸다 → 큐에서 빠짐
    up.status, up.modify_ok = "승인완료", True
    out = cdr.drain(lambda iid, sid: _item(), lambda iid, sid: (lambda ex: None), make_up=lambda a: up)
    assert out["ok"] == 2 and cdr.queue_rows() == []


def test_refresh_waits_when_translation_failed(monkeypatch, state):
    from src.services import coupang_detail_refresh as cdr
    _patch_target(monkeypatch, ready=False)
    up = _FakeUp()
    rows = cdr.refresh_item(_item(), make_up=lambda a: up)
    assert up.bodies == [] and rows[0]["state"] == "translate_wait"             # 규격 빠진 상세로 덮어쓰지 않는다
    assert cdr.queue_rows()[0]["reason"] == "번역 대기"


def test_cron_route_requires_secret(monkeypatch):
    from src.order_webhook import app
    monkeypatch.setenv("CRON_SECRET", "s3")
    c = app.test_client()
    assert c.post("/cron/coupang-detail-refresh").status_code == 403
    assert c.post("/cron/coupang-detail-refresh", headers={"X-Cron-Secret": "x"}).status_code == 403


# ── 2. AI 축약 — 열쇠는 SKU 원문 · 낱말 절단 금지 · 지킬 말 ────────────────────────────────────────

def test_long_option_values_keyed_by_raw_sku_spec():
    from src.services import ai_fix as af
    rows = af.long_option_values(_vr())
    assert [len(r["ko"]) for r in rows] == [28, 29, 30]
    assert all(r["src"] in {k["spec"][0] for k in VRO["skus"]} for r in rows)   # 원문 열쇠(한국어 값 아님)


def test_short_guard_rejects_live_bad_answers():
    from src.services.ai_fix import short_guard
    ko15 = "블랙 풀가죽 아닐린 가죽 / 발받침 포함 천연 소가죽"
    assert short_guard(ko15, "블랙 풀가죽 아닐린 천연소").startswith("단어 중간 절단")   # 운영 10-15 답
    assert "발받침" in short_guard("미스트 블루 반가죽 세미아닐린 가죽 / 발받침 포함", "미스트 블루 반가죽 세미아닐린")
    assert short_guard(ko15, "블랙 풀가죽 아닐린 발받침") == ""                       # 오너 예시
    assert "색상" in short_guard(ko15, "풀가죽 아닐린 발받침")


def test_stale_korean_keyed_fixes_dropped_and_reasked():
    """운영 VRSUK 저장값 그대로 — 한국어 열쇠 옛 축약은 지우고 SKU 원문 열쇠로 다시 묻는다."""
    from src.services import ai_fix as af

    class R:
        market, ok, fixes, details, message, error_code = "smartstore", False, ["option_short"], [], "", ""
    bad = {"미스트 블루 반가죽 세미아닐린 가죽 / 발받침 포함": "미스트 블루 반가죽 세미아닐린",
           "블랙 풀가죽 아닐린 가죽 / 발받침 포함 천연 소가죽": "블랙 풀가죽 아닐린 천연소"}
    ex = {"option_value_overrides": dict(bad),
          "ai_fixes": {"option_short:" + k: {"kind": "option_short", "after": v, "before": ""} for k, v in bad.items()}}
    pd = _vr(option_value_overrides=dict(bad))
    tasks = af.plan(pd, ex, [R()])
    t = next(x for x in tasks if x["kind"] == "option_short")
    assert ex["option_value_overrides"] == {} and not any(k.startswith("option_short:") for k in ex["ai_fixes"])
    assert all(r["src"] in {k["spec"][0] for k in VRO["skus"]} for r in t["rows"]) and len(t["rows"]) == 3
    # 좋은 답이 적용되면 네이버 계획이 바로 25자 안 → 재검증 통과 재료
    ans = {"values": {t["rows"][0]["ko"]: "미스트 블루 반가죽 세미아닐린 발받침",
                      t["rows"][1]["ko"]: "블랙 풀가죽 아닐린 발받침",
                      t["rows"][2]["ko"]: "베이지 풀가죽 아닐린 발받침"}}
    assert len(af._apply(t, ans, pd, ex, {"provider": "anthropic", "model": "haiku"})) == 3
    from src.uploaders import naver_options as no
    op = no.plan(pd, base_override=0)
    assert op["mode"] == "combo" and max(len(c["optionName1"]) for c in op["option_info"]["optionCombinations"]) <= 25


# ── 3. naver-recent — productStatusTypes·page·size ──────────────────────────────────────────────

def test_naver_recent_body_and_date_filter(monkeypatch):
    from src.uploaders import naver_uploader as NU
    up = NU.NaverSmartStoreUploader.__new__(NU.NaverSmartStoreUploader)
    sent = []

    def api(m, path, data=None):
        sent.append((m, path, data))
        return {"totalElements": 3, "contents": [
            {"originProductNo": 1, "channelProducts": [{"channelProductNo": 11, "name": "VRSUK 의자", "statusType": "SALE",
                                                        "regDate": "2026-10-15T15:39:01.000+09:00"}]},
            {"originProductNo": 2, "channelProducts": [{"channelProductNo": 22, "name": "옛 상품", "statusType": "SALE",
                                                        "regDate": "2026-09-01T10:00:00.000+09:00"}]}]}
    monkeypatch.setattr(up, "_api_request", api, raising=False)
    r = up.recent_products("2026-10-15", "2026-10-16")
    m, path, body = sent[0]
    assert (m, path) == ("POST", "/v1/products/search")
    assert set(body) == {"productStatusTypes", "page", "size"} and "REJECTION" in body["productStatusTypes"]
    assert [x["channel_no"] for x in r["rows"]] == ["11"] and r["scanned"] == 2 and len(sent) == 1


# ── 4. 실제로 나간 몸통 요약 ─────────────────────────────────────────────────────────────────────

def test_sent_summary_counts():
    from src.uploaders.coupang_uploader import CoupangUploader
    payload = {"displayCategoryCode": 77914, "items": [
        {"images": [{"imageType": "REPRESENTATION"}, {"imageType": "DETAIL"}],
         "contents": [{"contentsType": "TEXT", "contentDetails": [{"content": "83cm\n100x88x62cm\n85cm\n82cm\nvrsuk"}]}]}] * 16}
    s = CoupangUploader.sent_summary(payload)
    assert s == {**s, "category": "77914", "items": 16, "images": 2, "detail_lines": 5, "detail_head": "83cm"}
