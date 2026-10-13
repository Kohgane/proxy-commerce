"""반려 사유 자동 수정(오너 2026-10-13 — 「ANTHROPIC_API_KEY 들어갔다, 사전검증에 반려사유 자동수정 붙여라」).

사전검증이 **글자로 풀 보류**(표시광고 위험 문구 · 상품명에 남은 원문 · 그 마켓에서 받았던 반려 사유)로 멈추면
Claude로 그 칸만 고치고 다시 잰다. 계약:
1. 사유는 글자 사유만 모은다 — 상표·라이선스 보류, 사진 규격·애플 사전승인 반려는 묻지 않는다.
2. 고친 값은 우리 판정(표시광고 0 · 한자·가나 0 · 100자 · 옵션 값 개수)을 다시 통과해야 쓴다.
3. 등록·다음 사전검증은 **같은 기록**을 싣는다 — 화면 값이 원래 값 그대로일 때만(셀러가 고친 칸은 셀러가 이긴다), 되돌리면 안 싣는다.
4. 키가 없거나 실패하면 지금처럼 보류 — 실패 사유를 그대로(가짜 성공 0). 같은 재료로는 한 번만 묻는다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.services import reject_autofix as RAF


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


PD = {"title_ko": "무선 충전기 판매 1위 맥세이프 거치대", "coupang_name": "무선 충전기 최저가 거치대",
      "options": [{"name": "색상", "values": ["黑", "白"], "values_ko": ["블랙 50% 할인", "화이트"]}]}


def _ad_row(m="coupang:woojoo"):
    return _R(m, ok=False, error_code="ad_claim_risk", message="표시광고 위험 문구",
              details=["상품명에 표시광고 위험 문구 「최저가」 — 빼고 등록해 주세요",
                       "옵션 값에 표시광고 위험 문구 「50% 할인」 — 빼고 등록해 주세요"])


def _good_fix(fields, reasons, timeout):
    return ({"fixable": True, "title": "무선 충전기 맥세이프 거치대", "coupang_name": "무선 충전기 거치대",
             "options": [{"name": "색상", "values_ko": ["블랙", "화이트"]}], "why": "표시광고 문구 삭제"},
            {"provider": "anthropic", "model": "m", "error": ""})


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("REJECT_AUTOFIX_ENABLED", raising=False)


# ── 1. 사유 모으기 ─────────────────────────────────────────────────────────────────────

def test_collect_takes_only_text_reasons():
    rows = [_ad_row(),
            _R("coupang:gogane", ok=False, error_code="coupang_hold",
               details=["원문(외국어)이 남은 칸: 상품명 「手机壳 케이스」 — 한국어로 옮긴 뒤 등록합니다(원문을 대신 보내지 않음)",
                        "필수 구매옵션 「수량」 값 없음"]),
            _R("smartstore:chezgoga", ok=False, hold=True, fixes=["translate"],
               details=["마켓에 나갈 칸에 한자·가나가 남았어요: 상품명 「手机壳」"]),
            _R("shopify", ok=False, hold=True, fixes=["trademark"],
               details=["영화·게임·애니 IP(漫威)가 원문 제목에 있어요 — 상품명에선 지웠고, …"])]
    got = RAF.collect(PD, rows, {})
    kinds = [(r["market"], r["kind"]) for r in got]
    assert ("coupang:woojoo", "ad_claim") in kinds and kinds.count(("coupang:woojoo", "ad_claim")) == 2
    assert ("coupang:gogane", "foreign_name") in kinds and ("smartstore:chezgoga", "foreign_name") in kinds
    assert not any(m == "shopify" for m, _k in kinds)                          # 상표·라이선스 보류는 글자로 풀지 않는다
    assert not any("구매옵션" in r["line"] for r in got)                        # 속성·옵션 보류도 아님


def test_past_rejection_only_text_kinds():
    extra = {"uploaded": [
        {"market": "coupang:woojoo", "review": {"state": "rejected", "comment": "상품명에 과장 표현(최고급)이 포함되어 반려합니다"}},
        {"market": "coupang:woojoo", "review": {"state": "rejected", "comment": "대표이미지는 최소 500*500 이상"}},
        {"market": "coupang:gogane", "review": {"state": "approved", "comment": ""}}],
        "uploaded_removed": [{"market": "coupang:woojoo", "review": {"state": "rejected", "comment": "상표권 침해 신고 접수"}}]}
    got = RAF.past_rejections(extra, ["coupang:woojoo"], PD)
    assert [r["line"] for r in got] == ["지난 반려 사유: 상품명에 과장 표현(최고급)이 포함되어 반려합니다"]
    assert RAF.past_rejections(extra, ["shopify"], PD) == []                    # 이번에 안 재는 마켓 사유는 안 묻는다


# ── 2. 실행·검증 ───────────────────────────────────────────────────────────────────────

def test_no_key_is_skipped_not_fake_success(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    rec = RAF.run(PD, RAF.collect(PD, [_ad_row()], {}))
    assert rec["status"] == "skipped" and "ANTHROPIC_API_KEY" in rec["error"] and rec["changes"] == []


def test_good_fix_changes_only_offending_fields(monkeypatch):
    monkeypatch.setattr(RAF, "_call", _good_fix)
    rec = RAF.run(PD, RAF.collect(PD, [_ad_row()], {}))
    assert rec["status"] == "done", rec
    ch = {(c["field"], c.get("index")): (c["before"], c["after"]) for c in rec["changes"]}
    assert ch[("title_ko", None)] == (PD["title_ko"], "무선 충전기 맥세이프 거치대")
    assert ch[("coupang_name", None)] == (PD["coupang_name"], "무선 충전기 거치대")
    assert ch[("option", 0)] == ("블랙 50% 할인", "블랙")
    assert ("option", 1) not in ch                                            # 안 바뀐 값은 기록하지 않는다


@pytest.mark.parametrize("bad,why", [
    ({"title": "무선 충전기 오늘만 30% 할인"}, "표시광고"),
    ({"title": "无线 충전기"}, "한자"),
    ({"title": "가" * 120}, "100자"),
    ({"options": [{"name": "색상", "values_ko": ["블랙"]}]}, "개수"),
    ({"options": [{"name": "색상", "values_ko": ["화이트", "화이트"]}]}, "겹쳐요"),
])
def test_fix_that_breaks_our_rules_is_refused(monkeypatch, bad, why):
    def call(fields, reasons, timeout):
        g, a = _good_fix(fields, reasons, timeout)
        return {**g, **bad}, a
    monkeypatch.setattr(RAF, "_call", call)
    rec = RAF.run(PD, RAF.collect(PD, [_ad_row()], {}))
    assert rec["status"] == "failed" and why in rec["error"] and rec["changes"] == []


def test_not_fixable_and_api_error_are_honest(monkeypatch):
    reasons = RAF.collect(PD, [_ad_row()], {})
    monkeypatch.setattr(RAF, "_call", lambda f, r, t: ({"fixable": False, "title": "", "coupang_name": "", "options": [],
                                                       "why": "사진 규격 문제"}, {"error": ""}))
    assert RAF.run(PD, reasons)["status"] == "nochange"
    monkeypatch.setattr(RAF, "_call", lambda f, r, t: (None, {"error": "HTTP 401 invalid x-api-key"}))
    rec = RAF.run(PD, reasons)
    assert rec["status"] == "failed" and "401" in rec["error"]


def test_same_input_is_asked_once(monkeypatch):
    calls = []
    monkeypatch.setattr(RAF, "_call", lambda f, r, t: (calls.append(1), _good_fix(f, r, t))[1])
    reasons = RAF.collect(PD, [_ad_row()], {})
    first = RAF.run(PD, reasons)
    again = RAF.run(PD, reasons, previous=first)
    assert again["status"] == "cached" and len(calls) == 1


def test_daily_cap(monkeypatch):
    monkeypatch.setenv("REJECT_AUTOFIX_DAILY_CAP", "0")
    monkeypatch.setattr(RAF, "_call", _good_fix)
    rec = RAF.run(PD, RAF.collect(PD, [_ad_row()], {}))
    assert rec["status"] == "skipped" and "상한" in rec["error"]


def test_call_uses_forced_tool_and_key_header(monkeypatch):
    seen = {}

    class _Resp:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout):
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["body"] = json.loads(req.data.decode("utf-8"))
        seen["timeout"] = timeout
        out = {"content": [{"type": "tool_use", "name": "apply_fixes", "input": {"fixable": True, "title": "x"}}],
               "usage": {"input_tokens": 10, "output_tokens": 5}}
        return _Resp(json.dumps(out).encode())
    monkeypatch.setattr(RAF.urllib.request, "urlopen", fake_urlopen)
    got, ai = RAF._call(RAF.current_fields(PD), [{"market": "m", "kind": "ad_claim", "line": "l"}], 7)
    assert got == {"fixable": True, "title": "x"} and ai["tokens"] == {"in": 10, "out": 5}
    assert seen["headers"]["x-api-key"] == "sk-ant-test" and seen["headers"]["anthropic-version"] == RAF.API_VERSION
    assert seen["body"]["tool_choice"] == {"type": "tool", "name": "apply_fixes"} and seen["timeout"] == 7
    assert "sk-ant" not in json.dumps(ai, ensure_ascii=False)                  # 키는 기록에 남지 않는다


# ── 3. 싣기(등록·다음 사전검증) ─────────────────────────────────────────────────────────────

def _done_rec(monkeypatch):
    monkeypatch.setattr(RAF, "_call", _good_fix)
    return RAF.run(PD, RAF.collect(PD, [_ad_row()], {}))


def test_apply_when_screen_value_is_original(monkeypatch):
    out = RAF.apply(PD, _done_rec(monkeypatch))
    assert out["title_ko"] == "무선 충전기 맥세이프 거치대" and out["coupang_name"] == "무선 충전기 거치대"
    assert out["options"][0]["values_ko"] == ["블랙", "화이트"] and PD["options"][0]["values_ko"][0] == "블랙 50% 할인"
    assert out["reject_autofix"]["status"] == "done"


def test_seller_edit_wins_and_undo_stops(monkeypatch):
    rec = _done_rec(monkeypatch)
    edited = {**PD, "coupang_name": "셀러가 직접 고친 이름"}
    out = RAF.apply(edited, rec)
    assert out["coupang_name"] == "셀러가 직접 고친 이름" and out["title_ko"] == "무선 충전기 맥세이프 거치대"
    assert RAF.apply(PD, {**rec, "undone": True}) == PD


# ── 4. 사전검증 잡 끝까지 ───────────────────────────────────────────────────────────────

class _Disp:
    """쿠팡 우주대행: 실을 이름에 표시광고 문구가 있으면 ad_claim_risk, 없으면 통과(실제 판정 함수 `ban_hits`)."""
    def __init__(self):
        self.calls = []

    def prevalidate(self, product, markets):
        from src.collectors.ko_polish import ban_hits
        self.calls.append((list(markets), product.get("coupang_name")))
        out = []
        for m in markets:
            hits = ban_hits(product.get("coupang_name") or "")
            if hits:
                out.append(_R(m, ok=False, error_code="ad_claim_risk", message="표시광고 위험 문구",
                              details=[f"상품명에 표시광고 위험 문구 「{hits[0]}」 — 빼고 등록해 주세요"]))
            else:
                out.append(_R(m))
        return out


def _item(seller):
    from src.seller_console import collect_history_store as S
    ex = {"title": "충전기", "title_ko": PD["title_ko"], "price": "30", "currency": "CNY",
          "images": ["https://img.alicdn.com/a.jpg"]}
    iid = S.append(source="extension", url=f"https://item.taobao.com/item.htm?id={int(time.time() * 1000)}",
                   seller_id=seller, title="충전기", price="30", currency="CNY", extra=ex)
    return iid[0] if isinstance(iid, tuple) else iid


def _client(seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def _poll(c, url):
    for _ in range(100):
        j = c.get(url).get_json()
        if j["state"] == "done":
            return j
        time.sleep(0.1)
    pytest.fail(f"잡이 안 끝남: {j}")


def test_job_fixes_rechecks_and_undo(monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_PV_MARKET_TIMEOUT_SEC", 2.0)
    monkeypatch.setattr(V, "_PV_JOB_DEADLINE_SEC", 30.0)
    monkeypatch.setattr(V, "_account_codes_forbidden", lambda m: None)
    monkeypatch.setattr(V, "_pv_registered_rows", lambda iid, m: {})
    monkeypatch.setattr(RAF, "_call", _good_fix)
    # Y10: 「무선 충전기」는 리스크 게이트(전파·전기용품 KC)가 먼저 세운다 — 여기선 반려 자동 수정만 본다(게이트는 test_y10_risk_gate)
    monkeypatch.setattr(V, "_risk_scan_for", lambda *a, **k: {"hits": [], "waiting": 0, "skip": {}})

    def outbound(pd, iid):                      # 실제 `_outbound_images`의 「저장 기록 싣기」 줄과 같은 동작(이미지·도달 생략)
        it = V._get_owned_item(iid) or {}
        ex = json.loads(it.get("extra_json") or "{}") or {}
        if isinstance(ex.get("reject_autofix"), dict):
            pd.update(RAF.apply(pd, ex["reject_autofix"]))
        return pd, [], None
    monkeypatch.setattr(V, "_outbound_images", outbound)
    disp = _Disp()
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: disp)
    seller = f"raf-{time.time_ns()}"
    iid = _item(seller)
    c = _client(seller)
    product = {k: json.loads(json.dumps(v)) for k, v in PD.items()}

    r = c.post("/seller/collect/prevalidate", json={"product": product, "markets": ["coupang:woojoo"], "item_id": iid})
    j = _poll(c, r.get_json()["poll"])
    row = j["results"][0]
    assert j["auto_fix"]["status"] == "done", j["auto_fix"]
    assert row["ok"] and [c["after"] for c in j["auto_fix"]["changes"]] == ["무선 충전기 맥세이프 거치대", "무선 충전기 거치대", "블랙"]
    assert [x[1] for x in disp.calls] == [PD["coupang_name"], "무선 충전기 거치대"]         # 그 마켓만 다시 쟀다
    assert "ai_call" not in j["auto_fix"]                                                # 호출 원문은 카드에 안 싣는다
    from src.seller_console import collect_history_store as S
    rec = json.loads(S.get(iid, seller_id=seller)["extra_json"])["reject_autofix"]
    assert rec["status"] == "done" and rec["changes"] and rec["ai_call"]["provider"] == "anthropic"   # 기록엔 원문과 같이

    # 같은 화면 값으로 다시 사전검증 → 저장 기록이 실려 첫 판정부터 통과(Claude 다시 안 부름)
    monkeypatch.setattr(RAF, "_call", lambda *a: pytest.fail("같은 재료로 다시 물었다"))
    r = c.post("/seller/collect/prevalidate", json={"product": product, "markets": ["coupang:woojoo"], "item_id": iid})
    j = _poll(c, r.get_json()["poll"])
    assert j["results"][0]["ok"] and j["auto_fix"]["status"] == "applied" and j["auto_fix"]["changes"]   # 되돌리기는 계속 보인다

    # 되돌리기 → 원래 글자로 다시 보류(같은 재료라 다시 고치지 않는다)
    u = c.post(f"/seller/collect/{iid}/reject-autofix/undo", json={})
    assert u.status_code == 200 and u.get_json()["ok"]
    r = c.post("/seller/collect/prevalidate", json={"product": product, "markets": ["coupang:woojoo"], "item_id": iid})
    j = _poll(c, r.get_json()["poll"])
    assert j["results"][0]["error_code"] == "ad_claim_risk" and j["auto_fix"]["undone"] is True


def test_undo_without_record_is_404():
    seller = f"raf-{time.time_ns()}"
    iid = _item(seller)
    r = _client(seller).post(f"/seller/collect/{iid}/reject-autofix/undo", json={})
    assert r.status_code == 404 and not r.get_json()["ok"]


def test_cards_render_auto_fix_and_undo():
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "pvAutoFix = d.auto_fix || pvAutoFix" in m5 and 'data-role="m5-autofix-undo"' in m5
    assert "/reject-autofix/undo" in m5 and "/reject-autofix/undo" in pv
    assert "renderAutoFix(autoFix)" in pv and "d.auto_fix, d.ai_fix)" in pv and 'data-role="pv-autofix-undo"' in pv


def test_outbound_images_real_function_applies_saved_fix(monkeypatch):
    """`_outbound_images` 실함수 — 저장 기록을 싣는다(이미지 번역본·도달 확인은 이 상품에 없음/생략)."""
    import src.seller_console.views as V
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    rec = _done_rec(monkeypatch)
    seller = f"raf-{time.time_ns()}"
    iid = _item(seller)
    it = S.get(iid, seller_id=seller)
    ex = json.loads(it["extra_json"] or "{}")
    ex["reject_autofix"] = rec
    S.update(iid, seller_id=seller, extra_json=json.dumps(ex, ensure_ascii=False))
    monkeypatch.setattr(V, "_ensure_outward", lambda it: it)
    from src.services import image_reachability as _reach
    monkeypatch.setattr(_reach, "check_all", lambda urls, labels=None: None)
    product = {k: json.loads(json.dumps(v)) for k, v in PD.items()}
    with app.test_request_context():
        from flask import session
        session["user_id"] = seller
        out, _w, _rc = V._outbound_images(product, iid)
    assert out["coupang_name"] == "무선 충전기 거치대" and out["options"][0]["values_ko"][0] == "블랙"


def test_past_rejection_not_reasked_once_fix_is_applied(monkeypatch):
    extra = {"uploaded": [{"market": "coupang:woojoo",
                           "review": {"state": "rejected", "comment": "상품명에 과장 표현(최고급)이 포함되어 반려합니다"}}]}
    rows = [_R("coupang:woojoo")]
    reasons = RAF.collect(PD, rows, extra)
    assert [r["kind"] for r in reasons] == ["past_rejection"]
    monkeypatch.setattr(RAF, "_call", _good_fix)
    rec = RAF.run(PD, reasons)
    applied = RAF.apply(PD, rec)
    assert RAF.collect(applied, rows, extra) == []                              # 고친 글자가 실린 뒤엔 같은 반려로 다시 안 묻는다
    assert RAF.collect(RAF.apply(PD, {**rec, "undone": True}), rows, extra)     # 되돌리면 사유는 다시 보인다(묻는 건 sig 캐시가 막는다)
