"""AF1(오너 2026-10-13 「ANTHROPIC_API_KEY 들어갔다, 사전검증에 반려사유 자동수정 붙여라」) 계약.

- Claude 호출은 Messages API 그대로(헤더·모델·JSON 스키마 출력) · 키 없음/DRY_RUN/예산 = 부르지 않음(가짜 성공 0).
- 사전검증이 낸 사유(표시광고·원문 남음·옵션 값 미해석·영문 제목)만 고친다 · 답은 같은 판정으로 다시 잰다.
- 고친 것은 `extra.auto_fix`에만 — 원래 칸 그대로 · 사전검증·등록이 같은 자리에서 얹는다 · 셀러가 고친 칸은 셀러 글.
- 되돌리기 = 그 상품은 끔 · 같은 재료 실패는 6시간 다시 부르지 않음.
"""
from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KEY = "sk-ant-api03-TESTKEY-DO-NOT-LEAK"


# ── 공통 ────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _budget(monkeypatch):
    """서버 월 예산 기록은 시트 대신 목록에(실 시트 0)."""
    from src.ai import budget as B
    spent = []
    monkeypatch.setattr(B.AISpendSheets, "month_to_date", lambda self: Decimal("0"))
    monkeypatch.setattr(B.AISpendSheets, "append", lambda self, rec: spent.append(rec))
    monkeypatch.setenv("ANTHROPIC_RETRY_BACKOFF_SEC", "0")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("PREVALIDATE_AUTOFIX", raising=False)
    return spent


class _Resp:
    def __init__(self, status, data=None, text=""):
        self.status_code, self._data = status, data
        self.text = text or (json.dumps(data, ensure_ascii=False) if data is not None else "")

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


def _ok_body(obj, model="claude-sonnet-5-5", stop="end_turn", in_tok=1200, out_tok=300):
    return {"id": "msg_x", "type": "message", "role": "assistant", "model": model, "stop_reason": stop,
            "content": [{"type": "thinking", "thinking": "…", "signature": "s"},
                        {"type": "text", "text": json.dumps(obj, ensure_ascii=False)}],
            "usage": {"input_tokens": in_tok, "output_tokens": out_tok}}


# ── 1. Claude 클라이언트 ────────────────────────────────────────────────────────────────

def test_claude_request_shape_and_meta(monkeypatch, _budget):
    import requests
    from src.ai import claude_client as cc
    monkeypatch.setenv("ANTHROPIC_API_KEY", f'  "{KEY}"  ')            # 따옴표·공백 섞여도 env_str로 정제
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json, timeout=timeout)
        return _Resp(200, _ok_body({"ok": True, "word": "다리"}))

    monkeypatch.setattr(requests, "post", fake_post)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
    obj, meta = cc.messages_json("sys", "user", schema, max_tokens=321, note="t")
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    h = seen["headers"]
    assert h["x-api-key"] == KEY and h["anthropic-version"] == "2023-06-01" and h["content-type"] == "application/json"
    b = seen["body"]
    assert b["model"] == "claude-sonnet-5-5" and b["max_tokens"] == 321 and b["system"] == "sys"
    assert b["messages"] == [{"role": "user", "content": "user"}]
    assert b["output_config"]["format"] == {"type": "json_schema", "schema": schema}
    assert b["output_config"]["effort"] == "low"
    assert "temperature" not in b and "thinking" not in b                 # 지원 안 하는 매개변수 0
    assert obj == {"ok": True, "word": "다리"}                             # thinking 블록 건너뛰고 text 블록
    assert meta["in_tok"] == 1200 and meta["out_tok"] == 300 and meta["model"] == "claude-sonnet-5-5"
    assert abs(meta["cost_usd"] - (1200 * 2 + 300 * 10) / 1e6) < 1e-9     # Sonnet 5.5 = $2/$10 per MTok
    assert _budget and _budget[0]["provider"] == "anthropic" and _budget[0]["tokens"] == 1500


def test_claude_model_env_and_haiku_price(monkeypatch):
    import requests
    from src.ai import claude_client as cc
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(200, _ok_body({"ok": True}, model="claude-haiku-5-5",
                                                                                in_tok=1_000_000, out_tok=0)))
    _obj, meta = cc.messages_json("s", "u", {"type": "object"})
    assert meta["model"] == "claude-haiku-5-5" and abs(meta["cost_usd"] - 0.10) < 1e-9


def test_claude_unavailable_without_key_or_dry_run(monkeypatch):
    import requests
    from src.ai import claude_client as cc
    called = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: called.append(1))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(cc.ClaudeUnavailable):
        cc.messages_json("s", "u", {"type": "object"})
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    with pytest.raises(cc.ClaudeUnavailable):
        cc.messages_json("s", "u", {"type": "object"})
    assert not cc.configured() and called == []                          # 부른 척 0


def test_claude_budget_blocks_call(monkeypatch):
    import requests
    from src.ai import budget as B
    from src.ai import claude_client as cc
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setattr(B.BudgetGuard, "can_spend", lambda self, estimated_cost_usd=None: False)
    called = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: called.append(1))
    with pytest.raises(cc.ClaudeUnavailable, match="예산"):
        cc.messages_json("s", "u", {"type": "object"})
    assert called == []


def test_claude_retry_once_on_429_then_error_without_key(monkeypatch):
    import requests
    from src.ai import claude_client as cc
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    seq = [_Resp(429, text='{"type":"error","error":{"type":"rate_limit_error"}}'), _Resp(200, _ok_body({"ok": True}))]
    monkeypatch.setattr(requests, "post", lambda *a, **k: seq.pop(0))
    obj, _ = cc.messages_json("s", "u", {"type": "object"})
    assert obj == {"ok": True} and seq == []                              # 1회 다시 → 성공
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(529, text='{"error":{"type":"overloaded_error"}}'))
    with pytest.raises(cc.ClaudeError) as ei:
        cc.messages_json("s", "u", {"type": "object"})
    assert ei.value.status == 529 and KEY not in str(ei.value) and KEY not in ei.value.body
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(401, text='{"error":{"type":"authentication_error"}}'))
    with pytest.raises(cc.ClaudeError) as ei:
        cc.messages_json("s", "u", {"type": "object"})
    assert ei.value.status == 401


def test_claude_refusal_and_non_json_are_errors(monkeypatch):
    import requests
    from src.ai import claude_client as cc
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(200, _ok_body({"ok": True}, stop="refusal")))
    with pytest.raises(cc.ClaudeError, match="refusal"):
        cc.messages_json("s", "u", {"type": "object"})
    body = _ok_body({})
    body["content"] = [{"type": "text", "text": "그냥 글"}]
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(200, body))
    with pytest.raises(cc.ClaudeError, match="스키마"):
        cc.messages_json("s", "u", {"type": "object"})


def test_ping_reports_without_key_value(monkeypatch):
    import requests
    from src.ai import claude_client as cc
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = cc.ping()
    assert p["ok"] is False and p["unavailable"] is True
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(200, _ok_body({"ok": True, "word": "다리"})))
    p = cc.ping()
    assert p["ok"] is True and p["model"] == "claude-sonnet-5-5" and "ms" in p and "cost_usd" in p
    assert KEY not in json.dumps(p, ensure_ascii=False)


# ── 2. 사유 모으기 · 판정 · 얹기 ─────────────────────────────────────────────────────────

class _Row:
    def __init__(self, market, ok=False, error_code="", hold=False, fixes=(), details=()):
        self.market, self.ok, self.error_code, self.hold = market, ok, error_code, hold
        self.fixes, self.details = list(fixes), list(details)


def test_collect_only_text_fixable_reasons():
    from src.seller_console import pv_autofix as A
    pd = {"title": "의자 55% 할인 9.28-10.05", "title_ko": "의자 55% 할인 9.28-10.05",
          "options": [{"name": "색상", "values_ko": ["블랙 최저가", "화이트"]}]}
    assert A.collect(pd, [_Row("woocommerce", ok=True)]) is None                       # 통과만
    assert A.collect(pd, [_Row("coupang", error_code="ip_trademark_risk")]) is None    # 상표 위험 — 오너 판단
    assert A.collect(pd, [_Row("smartstore", hold=True, fixes=["ship_ratio"])]) is None  # 배송비 — 글자 문제 아님
    req = A.collect(pd, [_Row("coupang", error_code="ad_claim_risk")])
    assert req["markets"] == ["coupang"] and req["title_ko"] == pd["title_ko"]
    assert req["values"] == ["블랙 최저가"] and req["hash"]
    assert any("표시광고" in x for x in req["lines"])
    en = A.collect({"title": "의자"}, [_Row("shopify", error_code="title_not_english")])
    assert en["need_en"] is True and "Shopify 영문 제목 없음" in en["lines"]


def test_collect_foreign_segments_for_translate_hold():
    from src.seller_console import pv_autofix as A
    pd = {"title": "의자", "title_ko": "의자", "coupang_name": "임스 의자 加大款",
          "options": [{"name": "颜色", "name_ko": "색상", "values": ["黑色"], "values_ko": ["블랙"]}]}
    req = A.collect(pd, [_Row("coupang", error_code="coupang_hold", details=["원문(외국어)이 남은 칸: 쿠팡 상품명"])])
    assert req and "加大款" in req["segments"] and any("원문" in x for x in req["lines"])


def test_judge_rechecks_answers_with_same_rules():
    from src.seller_console import pv_autofix as A
    req = {"title_ko": "의자 55% 할인 9.28-10.05", "coupang_name": "", "values": ["블랙 최저가"],
           "segments": ["加大款"], "unresolved": ["黑色XL码"], "need_en": True, "title_en": ""}
    ans = {"title_ko": "의자 할인 최저가", "coupang_name": "", "title_en": "Lounge Chair Oil Leather",
           "values": [{"before": "블랙 최저가", "after": "블랙"}, {"before": "남의 값", "after": "x"}],
           "translations": [{"before": "加大款", "after": "빅사이즈"}, {"before": "黑色XL码", "after": "黑色 XL"}]}
    changes, rejected = A.judge(req, ans)
    kinds = {(c["kind"], c.get("field") or c.get("before") or c.get("src")) for c in changes}
    assert ("field", "title_en") in kinds and ("value", "블랙 최저가") in kinds and ("text", "加大款") in kinds
    assert not any(c.get("field") == "title_ko" for c in changes)       # 판촉어가 남은 답은 버린다
    assert any(x.startswith("상품명: 표시광고") for x in rejected)
    assert any("옵션 원문" in x and "한자" in x for x in rejected)     # 원문이 남은 번역은 버린다
    assert not any(c.get("before") == "남의 값" for c in changes)       # 묻지 않은 값은 무시
    ok, rej = A.judge(req, {**ans, "title_ko": "원목 라운지 의자", "title_en": "원목 의자"})
    assert any(c.get("field") == "title_ko" and c["after"] == "원목 라운지 의자" for c in ok)
    assert not any(c.get("field") == "title_en" for c in ok)            # 영문 제목에 한글 → 버림
    _ok, rej = A.judge(req, {**ans, "title_en": "Eames Lounge Chair"})
    assert any("영문 제목: 상표 이름이 새로" in x for x in rej)           # 한국어 제목에 없던 상표(Eames=임스)


def test_judge_rejects_trademark_names_the_pipeline_strips():
    """파이프라인이 일부러 지우는 상표(가구 레플리카·영화/캐릭터 IP)를 답이 되살리면 버린다."""
    from src.seller_console import pv_autofix as A
    req = {"title_ko": "라운지 체어 오일 가죽 55% 할인", "coupang_name": "", "values": ["블랙 최저가"],
           "segments": ["迪士尼杯"], "unresolved": [], "need_en": False, "title_en": ""}
    ans = {"title_ko": "임스 라운지 체어 오일 가죽", "coupang_name": "", "title_en": "",
           "values": [{"before": "블랙 최저가", "after": "허먼밀러 블랙"}],
           "translations": [{"before": "迪士尼杯", "after": "디즈니 컵"}]}
    changes, rejected = A.judge(req, ans)
    assert changes == []
    assert any("상품명" in x and "상표 이름이 새로" in x and "임스" in x for x in rejected)
    assert any("옵션 값" in x and "허먼밀러" in x for x in rejected)
    assert any("원문" in x and "디즈니" in x for x in rejected)
    keep = {"title_ko": "임스 라운지 체어 55% 할인"}                       # 원래 있던 상표는 「새로」가 아니다
    ok, _ = A.judge({**req, **keep, "values": [], "segments": []},
                    {**ans, "title_ko": "임스 라운지 체어", "values": [], "translations": []})
    assert ok and ok[0]["after"] == "임스 라운지 체어"
    assert "새로 넣지 않는다" in A.SYSTEM


def _ex(changes, **kw):
    return {"auto_fix": {"v": 1, "at": "2026-10-13T00:00:00+00:00", "changes": changes, "undone": False}, **kw}


def test_apply_before_equality_and_seller_wins():
    from src.seller_console import pv_autofix as A
    ch = [{"kind": "field", "field": "title_ko", "before": "의자 55% 할인", "after": "임스 라운지 의자"},
          {"kind": "field", "field": "coupang_name", "before": "의자 최저가", "after": "임스 의자"},
          {"kind": "value", "before": "블랙 최저가", "after": "블랙"},
          {"kind": "override", "src": "黑色XL码", "after": "블랙 XL"},
          {"kind": "text", "before": "加大款", "after": "빅사이즈"}]
    pd = {"title": "의자 55% 할인", "title_ko": "의자 55% 할인", "coupang_name": "의자 최저가",
          "description": "사이즈 加大款 있음", "keywords": ["加大款 의자"],
          "options": [{"name_ko": "색상", "values_ko": ["블랙 최저가", "화이트"]}],
          "option_values_ko": {"黑色": "블랙 최저가"}}
    out = A.apply(pd, _ex(ch))
    assert out["title_ko"] == out["title"] == "임스 라운지 의자"
    assert out["coupang_name"] == "임스 의자" and out["coupang_name_source"] == "autofix"
    assert out["options"][0]["values_ko"] == ["블랙", "화이트"] and out["option_values_ko"] == {"黑色": "블랙"}
    assert out["option_value_overrides"] == {"黑色XL码": "블랙 XL"}
    assert out["description"] == "사이즈 빅사이즈 있음" and out["keywords"] == ["빅사이즈 의자"]
    assert out["auto_fix_applied"] >= 5
    assert pd["title_ko"] == "의자 55% 할인" and pd["options"][0]["values_ko"][0] == "블랙 최저가"  # 입력은 그대로
    assert A.apply(out, _ex(ch)) == out                                 # 여러 번 얹어도 같다
    # 셀러가 그 뒤 손으로 고친 칸은 셀러 글
    seller = dict(pd, title_ko="셀러가 고친 이름", coupang_name="셀러 쿠팡명",
                  option_value_overrides={"黑色XL码": "셀러 블랙"})
    s_out = A.apply(seller, _ex(ch))
    assert s_out["title_ko"] == "셀러가 고친 이름" and s_out["coupang_name"] == "셀러 쿠팡명"
    assert s_out["option_value_overrides"] == {"黑色XL码": "셀러 블랙"}


def test_apply_respects_undo_and_off():
    from src.seller_console import pv_autofix as A
    ch = [{"kind": "field", "field": "title_ko", "before": "의자 55% 할인", "after": "임스 의자"}]
    pd = {"title_ko": "의자 55% 할인"}
    undone = _ex(ch)
    undone["auto_fix"]["undone"] = True
    assert A.apply(pd, undone) == pd
    assert A.apply(pd, _ex(ch, auto_fix_off=True)) == pd
    assert A.apply(pd, {}) == pd


def test_should_skip_same_failed_input_for_6h_and_merge():
    from datetime import datetime, timedelta, timezone
    from src.seller_console import pv_autofix as A
    req = {"hash": "h1"}
    now = datetime.now(timezone.utc)
    ex = {"auto_fix_try": {"input_hash": "h1", "status": "failed", "at": now.isoformat()}}
    assert A.should_skip(req, ex)["status"] == "failed"
    assert A.should_skip({"hash": "h2"}, ex) is None                    # 재료가 바뀌면 다시 부른다
    ex["auto_fix_try"]["at"] = (now - timedelta(hours=7)).isoformat()
    assert A.should_skip(req, ex) is None                               # 6시간 지나면 다시
    ex["auto_fix_try"].update(status="done", at=now.isoformat())
    assert A.should_skip(req, ex) is None                               # 성공한 시도는 막지 않는다
    a = {"kind": "value", "before": "a", "after": "A"}
    b = {"kind": "value", "before": "b", "after": "B"}
    m = A.merge(_ex([a]), {"at": "t", "changes": [b, {"kind": "value", "before": "a", "after": "A2"}],
                           "ai_call": {"model": "claude-sonnet-5-5"}})
    assert {c["after"] for c in m["changes"]} == {"A2", "B"} and m["undone"] is False and m["model"] == "claude-sonnet-5-5"


def test_run_statuses(monkeypatch):
    from src.ai import claude_client as cc
    from src.seller_console import pv_autofix as A
    req = {"hash": "h", "lines": ["표시광고 위험 문구 「55% 할인」"], "markets": ["coupang"],
           "title_ko": "의자 55% 할인", "coupang_name": "", "values": [], "segments": [], "unresolved": [], "need_en": False}

    def _unavail(*a, **k):
        raise cc.ClaudeUnavailable("ANTHROPIC_API_KEY 없음")
    monkeypatch.setattr(cc, "messages_json", _unavail)
    assert A.run(req)["status"] == "unavailable"

    def _err(*a, **k):
        raise cc.ClaudeError("Claude HTTP 500 — x", status=500, body="x")
    monkeypatch.setattr(cc, "messages_json", _err)
    r = A.run(req)
    assert r["status"] == "failed" and r["ai_call"]["status"] == 500
    meta = {"model": "claude-sonnet-5-5", "ms": 900, "in_tok": 1, "out_tok": 1, "cost_usd": 0.0001, "stop_reason": "end_turn"}
    monkeypatch.setattr(cc, "messages_json", lambda *a, **k: ({"title_ko": "의자 최저가", "coupang_name": "", "title_en": "",
                                                              "values": [], "translations": []}, meta))
    assert A.run(req)["status"] == "rejected"
    monkeypatch.setattr(cc, "messages_json", lambda *a, **k: ({"title_ko": "원목 라운지 의자", "coupang_name": "", "title_en": "",
                                                              "values": [], "translations": []}, meta))
    r = A.run(req)
    assert r["status"] == "done" and r["changes"][0]["after"] == "원목 라운지 의자" and r["ai_call"]["model"] == meta["model"]
    c = A.card(r)
    assert c["n"] == 1 and "상품명" in c["lines"][0] and c["model"] == "claude-sonnet-5-5"


# ── 3. 사전검증 잡 통합 ─────────────────────────────────────────────────────────────────

class _PvRow:
    def __init__(self, m, ok=True, **kw):
        self.market, self.ok = m, ok
        self.error_code = kw.get("error_code", "")
        self.message = kw.get("message", "통과")
        self.hint = ""
        self.reach_ok = self.reach_ms = None
        self.reach_detail = ""
        self.details = kw.get("details", [])
        self.action_url = ""
        self.hold = kw.get("hold", False)
        self.fixes = kw.get("fixes", [])


class _AdDisp:
    """실 판정과 같은 규칙(`ban_hits`) — 이름에 판촉어가 있으면 ad_claim_risk, 없으면 통과."""

    def __init__(self):
        self.seen = []

    def prevalidate(self, product, markets):
        from src.collectors.ko_polish import ban_hits
        out = []
        for m in markets:
            name = str(product.get("title_ko") or product.get("title") or "")
            self.seen.append((m, name))
            hits = ban_hits(name)
            out.append(_PvRow(m, ok=False, error_code="ad_claim_risk", message="표시광고 위험 문구",
                              details=[f"상품명에 표시광고 위험 문구 「{h}」" for h in hits]) if hits else _PvRow(m))
        return out


@pytest.fixture
def pv(monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_PV_MARKET_TIMEOUT_SEC", 2.0)
    monkeypatch.setattr(V, "_PV_JOB_DEADLINE_SEC", 30.0)
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    monkeypatch.setattr(V, "_account_codes_forbidden", lambda m: None)
    disp = _AdDisp()
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: disp)
    return disp


def _client(uid):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid)
    return c


def _item(uid, title):
    from src.seller_console import collect_history_store as chs
    return chs.append(source="test", url=f"https://example.com/af1/{uid}/{time.time()}", title=title,
                      price="100", currency="KRW", extra={"title_ko": title}, seller_id=uid)


def _extra(uid, iid):
    from src.seller_console import collect_history_store as chs
    return json.loads((chs.get(iid, seller_id=uid) or {}).get("extra_json") or "{}")


def _check(c, iid, title, markets=("woocommerce",)):
    from tests._pv_helper import prevalidate
    return prevalidate(c, {"product": {"title": title, "title_ko": title, "price": "100", "currency": "KRW"},
                           "markets": list(markets), "item_id": iid, "async": True})


def _claude_ok(monkeypatch, after, calls):
    from src.ai import claude_client as cc

    def fake(system, user, schema, **kw):
        calls.append(user)
        return ({"title_ko": after, "coupang_name": "", "title_en": "", "values": [], "translations": []},
                {"model": "claude-sonnet-5-5", "ms": 800, "in_tok": 900, "out_tok": 60, "cost_usd": 0.0024,
                 "stop_reason": "end_turn"})
    monkeypatch.setattr(cc, "messages_json", fake)


def test_job_fixes_ad_claim_and_rechecks(monkeypatch, pv):
    uid, bad = "af1-seller-a", "임스 라운지 의자 55% 할인 9.28-10.05"
    iid = _item(uid, bad)
    calls = []
    _claude_ok(monkeypatch, "임스 라운지 의자", calls)
    c = _client(uid)
    j = _check(c, iid, bad)
    assert len(calls) == 1 and "55% 할인" in calls[0]
    af = j["auto_fix"]
    assert af["status"] == "done" and af["n"] == 1 and "임스 라운지 의자" in af["lines"][0]
    assert any("표시광고" in x for x in af["reasons"]) and af["model"] == "claude-sonnet-5-5"
    row = [r for r in j["results"] if r["market"] == "woocommerce"][0]
    assert row["ok"] is True                                              # 고친 뒤 같은 판정으로 다시 → 통과
    assert pv.seen[-1] == ("woocommerce", "임스 라운지 의자")
    ex = _extra(uid, iid)
    assert ex["title_ko"] == bad                                          # 원래 칸 그대로
    assert ex["auto_fix"]["changes"][0]["after"] == "임스 라운지 의자" and ex["auto_fix"]["undone"] is False
    assert ex["auto_fix_try"]["status"] == "done" and ex["auto_fix_try"]["ai_call"]["model"] == "claude-sonnet-5-5"
    assert KEY not in json.dumps(ex, ensure_ascii=False)
    # 다시 사전검증(화면은 아직 옛 이름을 보냄) → 저장된 수정을 얹어 통과 · Claude는 다시 안 부른다
    j2 = _check(c, iid, bad)
    assert len(calls) == 1 and j2["all_ok"] and not j2.get("auto_fix")


def test_job_unavailable_is_honest(monkeypatch, pv):
    uid, bad = "af1-seller-b", "의자 최저가 55% 할인"
    iid = _item(uid, bad)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    j = _check(_client(uid), iid, bad)
    assert j["auto_fix"]["status"] == "unavailable" and "ANTHROPIC_API_KEY" in j["auto_fix"]["error"]
    row = j["results"][0]
    assert row["ok"] is False and row["error_code"] == "ad_claim_risk"    # 고친 척 0 — 원래 사유 그대로
    assert "auto_fix" not in _extra(uid, iid)


def test_job_skips_same_failed_input(monkeypatch, pv):
    from src.ai import claude_client as cc
    uid, bad = "af1-seller-c", "의자 55% 할인"
    iid = _item(uid, bad)
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise cc.ClaudeError("Claude HTTP 500 — overloaded", status=500, body="")
    monkeypatch.setattr(cc, "messages_json", boom)
    c = _client(uid)
    assert _check(c, iid, bad)["auto_fix"]["status"] == "failed"
    j = _check(c, iid, bad)
    assert len(calls) == 1 and j["auto_fix"]["status"] == "skipped" and j["auto_fix"]["skipped_from"] == "failed"


def test_job_respects_env_off(monkeypatch, pv):
    uid, bad = "af1-seller-d", "의자 55% 할인"
    iid = _item(uid, bad)
    monkeypatch.setenv("PREVALIDATE_AUTOFIX", "0")
    calls = []
    _claude_ok(monkeypatch, "의자", calls)
    j = _check(_client(uid), iid, bad)
    assert calls == [] and not j.get("auto_fix") and j["results"][0]["error_code"] == "ad_claim_risk"


def test_undo_turns_off_then_on(monkeypatch, pv):
    uid, bad = "af1-seller-e", "임스 의자 55% 할인"
    iid = _item(uid, bad)
    calls = []
    _claude_ok(monkeypatch, "임스 의자", calls)
    c = _client(uid)
    assert _check(c, iid, bad)["auto_fix"]["status"] == "done"
    r = c.post(f"/seller/collect/{iid}/auto-fix/undo", json={})
    assert r.status_code == 200 and r.get_json()["ok"] and "1건" in r.get_json()["message"]
    ex = _extra(uid, iid)
    assert ex["auto_fix"]["undone"] is True and ex["auto_fix_off"] is True and ex["auto_fix"]["undone_at"]
    j = _check(c, iid, bad)
    assert len(calls) == 1 and j["auto_fix"]["status"] == "off"           # 끈 상품은 부르지 않는다
    assert j["results"][0]["error_code"] == "ad_claim_risk"              # 되돌린 수정은 얹지 않는다
    r = c.post(f"/seller/collect/{iid}/auto-fix/on", json={})
    assert r.status_code == 200 and r.get_json()["ok"]
    ex = _extra(uid, iid)
    assert ex["auto_fix_off"] is False and "auto_fix_try" not in ex
    j = _check(c, iid, bad)
    assert len(calls) == 2 and j["auto_fix"]["status"] == "done" and j["all_ok"]


def test_undo_route_guards(monkeypatch, pv):
    uid = "af1-seller-f"
    iid = _item(uid, "의자")
    c = _client(uid)
    assert c.post(f"/seller/collect/{iid}/auto-fix/delete", json={}).status_code == 400
    assert c.post("/seller/collect/nope-404/auto-fix/undo", json={}).status_code == 404
    other = _client("af1-intruder")
    assert other.post(f"/seller/collect/{iid}/auto-fix/undo", json={}).status_code == 404   # 남의 상품 0


def test_upload_path_applies_same_fix(monkeypatch):
    """등록(`/collect/upload`)과 사전검증이 지나는 `_outbound_images`가 같은 수정을 얹는다."""
    import flask
    import src.seller_console.views as V
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs
    uid, bad = "af1-seller-g", "의자 55% 할인"
    iid = _item(uid, bad)
    ex = _extra(uid, iid)
    ex["auto_fix"] = {"v": 1, "at": "t", "undone": False,
                      "changes": [{"kind": "field", "field": "title_ko", "before": bad, "after": "임스 의자"}]}
    chs.update(iid, seller_id=uid, extra_json=json.dumps(ex, ensure_ascii=False))
    monkeypatch.setattr(V, "_ensure_outward", lambda it: it)
    with app.test_request_context("/seller/collect/upload", method="POST"):
        flask.session["user_id"] = uid
        pd, _w, _rc = V._outbound_images({"title": bad, "title_ko": bad, "images": []}, iid)
    assert pd["title_ko"] == "임스 의자" and pd["title"] == "임스 의자" and pd["auto_fix_applied"] == 2


# ── 4. 화면 · 관리자 ────────────────────────────────────────────────────────────────────

def test_templates_render_auto_fix_card():
    desk = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    for role in ("renderAutoFix", "pv-autofix-running", "pv-autofix-done", "pv-autofix-undo", "pv-autofix-on",
                 "pv-autofix-failed", "/auto-fix/"):
        assert role in desk, role
    phone = (ROOT / "src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    for role in ("m5-auto-fix", "m5-autofix-undo", "m5-autofix-on", "d.auto_fix", "/auto-fix/"):
        assert role in phone, role
    import re
    block = phone[phone.index("AF1(오너 2026-10-13)"):phone.index("pvOrder.forEach(function (m) { h += pvRowHtml(m); });")]
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", block)                    # 하드코딩 색 0
    assert not re.search(r"[\U0001F300-\U0001FAFF]", block)               # 이모지 0


def test_admin_ping_route(monkeypatch):
    import requests
    from src.order_webhook import app
    c = app.test_client()
    assert c.post("/admin/diagnostics/claude-ping").status_code in (302, 401, 403)   # 비로그인 차단
    with c.session_transaction() as s:
        s.update(user_id="af1-admin", user_role="admin", email="admin@example.com")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = c.post("/admin/diagnostics/claude-ping").get_json()
    assert d["ok"] is False and d["unavailable"] is True
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(401, text='{"error":{"type":"authentication_error"}}'))
    d = c.post("/admin/diagnostics/claude-ping").get_json()
    assert d["ok"] is False and d["status"] == 401 and KEY not in json.dumps(d)
    html = c.get("/admin/diagnostics").get_data(as_text=True)
    assert 'data-role="claude-ping"' in html and "claudePingOut" in html
