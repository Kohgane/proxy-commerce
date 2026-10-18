"""Y8(오너 2026-10-13) — 사전검증 보류 사유 AI 자동수정 · AI 공급자 Anthropic 우선(OpenAI 폴백).

재현 상품: 10-12 ICE(타오바오) — 옵션 값 「泡泡粉（2-3周发货）」 등 색 4개, 네이버 카테고리 후보 3개.
선주문 보류는 AI가 안 건드린다 — 오너가 「선주문 그래도 등록」을 누른 상태(`lead_time_override`)로 둔다.
대조(변화 0): 플리츠 세트(옵션 전부 해석됨 · 보류 없음).
흉내 낸 것: Anthropic 응답(`llm._call_anthropic` — 프롬프트를 보고 답), 마켓 HTTP(보류 판정은 실제 `readiness_holds`).
"""
from __future__ import annotations

import json
import logging

import pytest

VALS = ["泡泡粉（2-3周发货）", "黑色（2-3周发货）", "藏蓝色（2-3周发货）", "苔藓绿（2-3周发货）"]
CANDS = [{"id": "50000805", "name": "TV거치대"}, {"id": "50000806", "name": "모니터받침대"}, {"id": "50000807", "name": "거실장"}]
PL_OPTS = [{"name": "颜色分类", "values": ["黑色上衣", "黑色半裙"], "name_ko": "색상", "values_ko": ["블랙 상의", "블랙 스커트"]}]


def _ice_extra():
    return {"title": "北欧极简电视柜落地支架", "title_ko": "북유럽 미니멀 TV 스탠드", "price": "720", "currency": "CNY",
            "brand": "GENERIC", "images": ["https://img.alicdn.com/a.jpg"], "description": "북유럽 미니멀 TV 스탠드입니다.",
            "options": [{"name": "颜色分类", "name_ko": "색상", "values": list(VALS),
                         "values_ko": ["거품 파우더는 2~3주 후 발송", "검은색 2~3주", "곤색 2-3주 내 발송", "이끼색 2-3주 내 발송"]}],
            "skus": [{"spec": [v], "price": "720.0", "stock": 10, "sku_id": str(i)} for i, v in enumerate(VALS)],
            "lead_time_override": {"at": "2026-10-12T05:00:00+00:00"}}


class FakeAnthropic:
    """프롬프트를 보고 답한다 — 옵션 값 · 네이버 카테고리. 호출 기록."""

    def __init__(self, answers=None):
        self.calls = []
        self.answers = answers or {}

    def __call__(self, model, system, prompt, max_tokens, timeout, images=None):
        self.calls.append({"model": model, "prompt": prompt, "images": images})
        if "옵션 값(중국어 등 원문)" in prompt:
            ans = self.answers.get("option", {"values": {"泡泡粉": "버블 핑크", "藏蓝色": "네이비"}})
        elif "네이버 카테고리" in prompt:
            ans = self.answers.get("category", {"id": "50000805", "why": "TV를 올려 두는 받침"})
        elif "상세설명" in prompt:
            return {"text": "북유럽 감성의 미니멀 TV 스탠드예요.", "tokens_in": 900, "tokens_out": 120}
        else:
            ans = self.answers.get("other", {})
        return {"text": json.dumps(ans, ensure_ascii=False), "tokens_in": 400, "tokens_out": 60}


@pytest.fixture
def ai(monkeypatch):
    from src.ai import llm
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    fake = FakeAnthropic()
    monkeypatch.setattr(llm, "_call_anthropic", fake)
    return fake


@pytest.fixture
def naver_cats(monkeypatch):
    from src.uploaders import naver_categories as NC
    monkeypatch.setattr(NC, "pick", lambda p: ((str(p.get("naver_category_id")), "manual") if p.get("naver_category_id") else ("", "")))
    monkeypatch.setattr(NC, "suggest", lambda p: {"candidates": list(CANDS), "coupang": "TV거치대", "why": ""})
    monkeypatch.setattr(NC, "leaf_state", lambda cid, account="": "leaf")


def _fake_market(seen):
    from src.seller_console.upload_dispatcher import UploadDispatcher, PrevalidationResult, readiness_message

    def fake(self, pd, market):
        holds = [h for h in UploadDispatcher.readiness_holds(pd, market) if h.get("code") != "naver_required_detailContent"]
        seen.setdefault(market, []).append([h["fix"] for h in holds])
        if not holds:
            return PrevalidationResult(market=market, ok=True, message="사전검증 통과")
        return PrevalidationResult(market=market, ok=False, hold=True, message=readiness_message(holds),
                                   details=[h["line"] for h in holds],
                                   fixes=list(dict.fromkeys(h.get("fix", "") for h in holds if h.get("fix"))))
    return fake


def _setup(monkeypatch, seen):
    import src.seller_console.views as V
    from src.seller_console.upload_dispatcher import UploadDispatcher
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    monkeypatch.setattr(V, "_pv_auto_detail", lambda pd, data, results, force=False: (None, pd))
    monkeypatch.setattr(V, "_pv_auto_translate", lambda pd, data, results: (None, pd))
    monkeypatch.setattr(V, "_pv_prewarm_naver_detail", lambda pd, markets: False)
    monkeypatch.setattr(UploadDispatcher, "_prevalidate_market", _fake_market(seen))
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: UploadDispatcher())
    monkeypatch.setattr("src.services.coupang_image_check.hold", lambda *a, **k: None)
    monkeypatch.setattr("src.services.coupang_image_check.kick", lambda *a, **k: None)
    monkeypatch.setattr("src.services.coupang_image_check.rep_pending", lambda *a, **k: False)


def _client(sid):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = sid
    return c


def _item(sid, ex):
    from src.seller_console import collect_history_store as S
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=812345", seller_id=sid, title=ex["title_ko"], extra=ex)
    return iid[0] if isinstance(iid, tuple) else iid


def _saved(iid, sid):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_ids={sid})["extra_json"])


# ── 6. 10-12 ICE: 2회차에 쿠팡·네이버 통과 ───────────────────────────────────────────────────

def test_6_ice_passes_coupang_and_naver_on_second_check(monkeypatch, ai, naver_cats, caplog):
    from tests._pv_helper import prevalidate
    seen = {}
    _setup(monkeypatch, seen)
    sid = "y8-ice"
    iid = _item(sid, _ice_extra())
    c = _client(sid)
    product = {"title": "북유럽 미니멀 TV 스탠드", "title_ko": "북유럽 미니멀 TV 스탠드", "price": 720, "currency": "CNY",
               "brand": "GENERIC", "images": ["https://img.alicdn.com/a.jpg"], "description": "북유럽 미니멀 TV 스탠드입니다."}
    with caplog.at_level(logging.INFO):
        d = prevalidate(c, {"product": product, "item_id": iid, "markets": ["coupang", "smartstore"]})
    # 1차 사전검증: 쿠팡 = 옵션 값 미해석 · 네이버 = 카테고리 + 옵션 값
    assert seen["coupang"][0] == ["translate"]
    assert set(seen["smartstore"][0]) == {"naver_category", "translate"}
    # 2차 사전검증(AI 적용 뒤): 둘 다 통과 — 같은 잡 안에서
    assert seen["coupang"][1] == [] and seen["smartstore"][1] == []
    assert d["all_ok"], d["results"]
    a = d["ai_fix"]
    assert a["state"] == "done" and a["calls"] == 2 and len(a["rounds"]) == 1
    assert a["summary"]["line"] == "AI가 고쳤어요 — 옵션값 2개 · 카테고리 1개"
    assert {it["key"] for it in a["summary"]["items"]} == {"option_value:泡泡粉", "option_value:藏蓝色", "naver_category"}
    # 짧은 수정은 작은 모델(기본 claude-haiku-4-5)
    assert {x["model"] for x in ai.calls} == {"claude-haiku-4-5"}
    # 로그 한 줄: [AI] provider=anthropic model= tokens= usd=
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[AI] provider=")]
    assert len(lines) == 2 and all("provider=anthropic model=claude-haiku-4-5 tokens=400+60 usd=0.00070" in l for l in lines)
    s = _saved(iid, sid)
    assert s["option_value_overrides"] == {"泡泡粉": "버블 핑크", "藏蓝色": "네이비"}
    assert s["naver_category_id"] == "50000805"
    assert s["manual_fields"]["option_value:泡泡粉"].startswith("ai:")
    # 3. AI가 안 건드리는 것: 가격·브랜드(GENERIC)·「그래도 등록」·선주문(값의 발송 소요는 그대로 따로)
    assert s["price"] == "720" and s["currency"] == "CNY" and s["brand"] == "GENERIC"
    assert s["lead_time_override"] == {"at": "2026-10-12T05:00:00+00:00"}
    assert s["options"][0]["lead_time"]["泡泡粉"]["max_days"] == 21


def test_4_revert_rehold_and_no_second_ai_call(monkeypatch, ai, naver_cats):
    from tests._pv_helper import prevalidate
    seen = {}
    _setup(monkeypatch, seen)
    sid = "y8-rev"
    iid = _item(sid, _ice_extra())
    c = _client(sid)
    body = {"product": {"title": "북유럽 미니멀 TV 스탠드", "price": 720, "images": ["https://img.alicdn.com/a.jpg"],
                        "description": "북유럽 미니멀 TV 스탠드입니다."}, "item_id": iid, "markets": ["smartstore"]}
    assert prevalidate(c, body)["all_ok"]
    n = len(ai.calls)
    r = c.post(f"/seller/collect/{iid}/ai-fix/revert", json={"key": "naver_category"}).get_json()
    assert r["ok"] and r["summary"]["line"] == "AI가 고쳤어요 — 옵션값 2개"
    d = prevalidate(c, {**body, "product": {**body["product"], "naver_category_id": "50000805"}})   # 화면은 아직 AI 값을 들고 있다
    row = d["results"][0]
    assert row["hold"] and row["fixes"] == ["naver_category"]                 # 다시 보류
    assert len(ai.calls) == n                                                 # 되돌린 항목은 다시 묻지 않는다
    assert _saved(iid, sid)["naver_category_id"] == ""


def test_6_pleats_set_unchanged(monkeypatch, ai, naver_cats):
    """대조 — 옵션 다 해석되고 보류 없는 상품은 AI를 부르지 않고 기록도 그대로."""
    from tests._pv_helper import prevalidate
    seen = {}
    _setup(monkeypatch, seen)
    sid = "y8-pl"
    ex = {"title": "三宅褶皱套装", "title_ko": "플리츠 투피스 세트", "price": "199", "currency": "CNY",
          "images": ["https://img.alicdn.com/p.jpg"], "description": "플리츠 투피스 세트예요.",
          "options": json.loads(json.dumps(PL_OPTS)),
          "skus": [{"spec": ["黑色上衣"], "price": "199", "stock": 5}, {"spec": ["黑色半裙"], "price": "199", "stock": 5}]}
    iid = _item(sid, ex)
    before = _saved(iid, sid)
    d = prevalidate(_client(sid), {"product": {"title": "플리츠 투피스 세트", "price": 199, "images": ex["images"],
                                                "description": ex["description"]}, "item_id": iid, "markets": ["coupang"]})
    assert d["all_ok"] and not d.get("ai_fix") and ai.calls == []
    saved = _saved(iid, sid)
    # Y13-C 4: 잡 끝 「등록 준비 완료」 표시 칸(`pv_ready`)은 AI가 아니라 사전검증 결과 기록 — 그 밖은 한 글자도 안 바뀜
    assert saved.pop("pv_ready", {}).get("ok") is True
    assert saved == before


# ── 5. 가드 ────────────────────────────────────────────────────────────────────────────────

def test_5_guard_drops_cjk_ip_and_lost_numbers(monkeypatch, ai):
    from src.services import ai_fix as AF
    assert AF.guard("버블 핑크") == ""
    assert "한자" in AF.guard("버블 粉")
    assert "한자" in AF.guard("ブラック")
    assert "IP" in AF.guard("디즈니 TV 스탠드")
    ex = {}
    pd = {"options": [], "skus": []}
    task = {"kind": "option_value", "markets": ["coupang"], "values": ["粉色 120cm", "白色", "灰色"]}
    keys = AF._apply(task, {"values": {"粉色 120cm": "핑크", "白色": "화이트 白", "灰色": "그레이"}}, pd, ex, {})
    assert keys == ["option_value:灰色"]                                       # 숫자 잃음·한자 섞임은 버림
    assert set(ex["ai_fix_rejects"]) == {"option_value:粉色 120cm", "option_value:白色"}
    assert AF.plan({"skus": [{"spec": ["粉色 120cm"]}], "options": []}, ex,
                   [{"market": "coupang", "ok": False, "fixes": ["translate"]}]) == []   # 하루 동안 다시 안 묻는다


def test_2b_category_outside_candidates_is_dropped():
    from src.services import ai_fix as AF
    ex, pd = {}, {}
    assert AF._apply({"kind": "naver_category", "markets": ["smartstore"], "candidates": CANDS}, {"id": "99999"}, pd, ex, {}) == []
    assert "naver_category_id" not in ex


def test_2c_title_fix_is_886_with_y8_gate():
    """c(상품명)는 #886 `reject_autofix`가 고친다 — Y8 가드(IP·상표·원문에 없는 영문 이름)를 그 답에도 건다."""
    from src.services import reject_autofix as RAF
    before = {"title_field": "title_ko", "title": "TV 스탠드 50% 할인 1위", "coupang_name": "", "options": []}
    ch, pr = RAF._changes(before, {"title": "Xiaomi TV 스탠드", "coupang_name": "", "options": []})
    assert not ch and "영문 이름(Xiaomi)" in pr[0]
    ch, pr = RAF._changes(before, {"title": "디즈니 TV 스탠드", "coupang_name": "", "options": []})
    assert not ch and "상표" in pr[0]          # 새로 들어온 상표·IP는 #889 new_marks
    ch, pr = RAF._changes(before, {"title": "TV 스탠드 거실 거치대", "coupang_name": "", "options": []})
    assert not pr and ch[0]["after"] == "TV 스탠드 거실 거치대"


def test_2c_886_changes_in_one_line_and_per_item_revert():
    from src.services import ai_fix as AF
    from src.services import reject_autofix as RAF
    ex = {"reject_autofix": {"status": "done", "at": "t", "changes": [
        {"field": "title_ko", "label": "상품명", "before": "TV 스탠드 1위", "after": "TV 스탠드"},
        {"field": "coupang_name", "label": "쿠팡 상품명", "before": "스탠드 최저가", "after": "스탠드"}]}}
    AF._mark(ex, "naver_category", "naver_category", "TV거치대", "", "50000805", "", {})
    s = AF.summary(ex)
    assert s["line"] == "AI가 고쳤어요 — 카테고리 1개 · 상품명 2개"
    assert AF.revert(ex, "reject:0") and not ex["reject_autofix"].get("undone")
    pd = RAF.apply({"title_ko": "TV 스탠드 1위", "coupang_name": "스탠드 최저가"}, ex["reject_autofix"])
    assert pd["title_ko"] == "TV 스탠드 1위" and pd["coupang_name"] == "스탠드"      # 되돌린 칸만 원래 글자
    assert AF.summary(ex)["line"] == "AI가 고쳤어요 — 카테고리 1개 · 상품명 1개"
    assert AF.revert(ex, "reject:1") and ex["reject_autofix"]["undone"] is True


def test_2c_886_call_budget_log_and_openai_fallback(monkeypatch, caplog):
    """#886 호출도 Y8 공급자 규칙 — Anthropic 실패면 OpenAI(JSON)로 · 예산 · [AI] 로그."""
    from src.ai import llm
    from src.services import reject_autofix as RAF
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k2")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(TimeoutError("timed out")))
    monkeypatch.setattr(llm, "_call_openai", lambda *a, **k: {"text": json.dumps(
        {"fixable": True, "title": "TV 스탠드", "coupang_name": "", "options": [], "why": "1위 삭제"}, ensure_ascii=False),
        "tokens_in": 300, "tokens_out": 40})
    fields = {"title_field": "title_ko", "title": "TV 스탠드 1위", "coupang_name": "", "options": []}
    with caplog.at_level(logging.INFO):
        got, call = RAF._call(fields, [{"market": "coupang", "kind": "ad_claim", "line": "상품명 「1위」"}], 5)
    assert got["title"] == "TV 스탠드" and call["provider"] == "openai" and "timed out" in call["anthropic_error"]
    logs = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[AI]")]
    assert logs[0].startswith("[AI] provider=anthropic model=claude-sonnet-5 tokens=0+0") and "fail=" in logs[0]
    assert logs[1].startswith("[AI] provider=openai model=gpt-4o-mini tokens=300+40")


def test_2e_notice_origin_only_when_written():
    from src.services import ai_fix as AF
    t = {"kind": "notice", "markets": ["coupang"]}
    ex = {}
    assert AF._apply(t, {"origin": None}, {}, ex, {}) == [] and "origin" not in ex
    assert AF._apply(t, {"origin": "중국", "why": "产地 中国"}, {}, ex, {}) == ["notice:origin"] and ex["origin"] == "중국"


def test_2f_coupang_attr_values_and_plan_parse():
    from src.services import ai_fix as AF
    res = [{"market": "coupang", "ok": False, "error_code": "coupang_hold",
            "details": ["필수 옵션: 색상, 수량", "필수 옵션(택1): 사이즈 또는 용량 — 상품명에 없음"]}]
    tasks = AF.plan({}, {}, res)
    assert tasks == [{"kind": "coupang_attr", "markets": ["coupang"], "names": ["색상", "수량", "사이즈", "용량"]}]
    ex, pd = {}, {}
    keys = AF._apply(tasks[0], {"attributes": [{"name": "색상", "value": "블랙"}, {"name": "수량", "value": "1"}]}, pd, ex, {})
    assert keys == ["coupang_attr:색상", "coupang_attr:수량"]
    assert pd["coupang_attributes"] == [{"attributeTypeName": "색상", "attributeValueName": "블랙"},
                                        {"attributeTypeName": "수량", "attributeValueName": "1"}]


def test_overlay_uses_stored_fix_over_stale_screen():
    """등록도 사전검증이 본 값 — 화면이 AI 전 값을 보내도 저장본을 얹는다. 셀러가 그 뒤 손으로 바꾼 값은 둔다."""
    from src.services import ai_fix as AF
    ex = {}
    AF._mark(ex, "option_value:泡泡粉", "option_value", "", "", "버블 핑크", "", {})
    AF._mark(ex, "naver_category", "naver_category", "", "", "50000805", "", {})
    pd = AF.overlay({"option_value_overrides": {}, "naver_category_id": ""}, ex)
    assert pd["option_value_overrides"]["泡泡粉"] == "버블 핑크" and pd["naver_category_id"] == "50000805"
    pd2 = AF.overlay({"option_value_overrides": {"泡泡粉": "핑크 버블"}, "naver_category_id": "123"}, ex)
    assert pd2["option_value_overrides"]["泡泡粉"] == "핑크 버블" and pd2["naver_category_id"] == "123"


def test_max_calls_per_product(monkeypatch, ai):
    from src.services import ai_fix as AF
    monkeypatch.setattr(AF, "plan", lambda pd, ex, results: [{"kind": "notice", "markets": ["coupang"]}] * 9)
    out = AF.run_round({}, {}, [], calls_left=AF.MAX_CALLS)
    assert out["calls"] == 6 and AF.MAX_CALLS == 6 and AF.MAX_ROUNDS == 2


# ── 0. 공급자: Anthropic 우선 · OpenAI 폴백 · 예산 · 로그 ─────────────────────────────────────

def test_0_anthropic_first_then_openai(monkeypatch, caplog):
    from src.ai import llm
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k2")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    order = []

    def bad(*a, **k):
        order.append("anthropic")
        raise RuntimeError("overloaded")
    monkeypatch.setattr(llm, "_call_anthropic", bad)
    monkeypatch.setattr(llm, "_call_openai", lambda *a, **k: order.append("openai") or {"text": "{}", "tokens_in": 10, "tokens_out": 5})
    with caplog.at_level(logging.INFO):
        r = llm.complete("p", size="large", purpose="t")
    assert order == ["anthropic", "openai"] and r["provider"] == "openai" and r["model"] == "gpt-4o-mini"
    msgs = [x.getMessage() for x in caplog.records if x.getMessage().startswith("[AI]")]
    assert msgs[0].startswith("[AI] provider=anthropic model=claude-sonnet-5 tokens=0+0") and "fail=RuntimeError" in msgs[0]
    assert msgs[1].startswith("[AI] provider=openai model=gpt-4o-mini tokens=10+5")


def test_0_models_from_env(monkeypatch):
    from src.ai import llm
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("ANTHROPIC_MODEL_SMALL", "claude-haiku-5-5")
    assert llm.model_for("large") == "claude-sonnet-5-5" and llm.model_for("small") == "claude-haiku-5-5"
    monkeypatch.delenv("ANTHROPIC_MODEL")
    monkeypatch.delenv("ANTHROPIC_MODEL_SMALL")
    assert llm.model_for("large") == "claude-sonnet-5" and llm.model_for("small") == "claude-haiku-4-5"
    assert float(llm.cost_usd("claude-sonnet-5", 1_000_000, 1_000_000)) == 12.0


def test_0_budget_shared(monkeypatch, ai):
    from src.ai import llm
    from src.ai import budget as B
    monkeypatch.setattr(B.BudgetGuard, "can_spend", lambda self, estimated_cost_usd=0: False)
    monkeypatch.setattr(B.BudgetGuard, "_send_exceeded_alert", lambda self, used: None)
    r = llm.complete("p", purpose="t")
    assert r["text"] == "" and "BudgetExceededError" in r["error"] and ai.calls == []


def test_0_sdk_call_shape(monkeypatch):
    """공식 SDK 호출 모양 — Sonnet은 effort low, Haiku 4.5는 effort 없음(넣으면 400)."""
    import anthropic
    from src.ai import llm
    sent = []

    class Msgs:
        def create(self, **kw):
            sent.append(kw)

            class U:
                input_tokens, output_tokens = 3, 4

            class B:
                type, text = "text", "ok"
            return type("R", (), {"content": [B()], "usage": U(), "stop_reason": "end_turn"})()

    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: type("C", (), {"messages": Msgs()})())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert llm._call_anthropic("claude-sonnet-5", "sys", "hi", 100, 5)["text"] == "ok"
    assert llm._call_anthropic("claude-haiku-4-5", "", "hi", 100, 5)["tokens_out"] == 4
    assert sent[0]["output_config"] == {"effort": "low"} and sent[0]["system"] == "sys"
    assert "output_config" not in sent[1] and "system" not in sent[1] and "temperature" not in sent[0]


# ── 0. 상세 초안: Anthropic 우선 · 「OpenAI 크레딧 없음」은 Anthropic 실패 때만 ──────────────────

def test_0_detail_draft_anthropic(monkeypatch, ai):
    from src.seller_console.ai.translator import AITranslator
    res = AITranslator().generate_description({"title": "북유럽 미니멀 TV 스탠드", "options": [{"name": "색상", "values": ["블랙"]}]})
    assert res["provider"] == "anthropic" and res["draft_status"] == "anthropic"
    assert res["ai_call"]["model"] == "claude-sonnet-5"
    from src.seller_console.upload_dispatcher import detail_auto_note
    assert detail_auto_note({"detail_auto": res, "item_id": "i"})["line"] == "상세 자동 생성(AI) — 확인(바꾸기)"


def test_0_detail_draft_openai_credit_line_only_after_anthropic_fails(monkeypatch):
    from src.ai import llm
    from src.seller_console.ai.translator import AITranslator
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k2")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    class E(Exception):
        status_code = 529
    monkeypatch.setattr(llm, "_call_anthropic", lambda *a, **k: (_ for _ in ()).throw(E("overloaded_error")))
    import requests

    class R:
        status_code = 429
        text = '{"error":{"code":"insufficient_quota","message":"no credits remaining"}}'

        def raise_for_status(self):
            raise requests.HTTPError("429 insufficient_quota", response=self)

        def json(self):
            return json.loads(self.text)
    monkeypatch.setattr(requests, "post", lambda *a, **k: R())
    res = AITranslator().generate_description({"title": "북유럽 미니멀 TV 스탠드", "options": [{"name": "색상", "values": ["블랙"]}]})
    assert res["provider"] == "stub" and res["draft_code"] == "quota" and res["draft_code_anthropic"]
    assert res["draft_error"].startswith("Anthropic") and "OpenAI 크레딧 없음" in res["draft_error"]
    from src.seller_console.upload_dispatcher import detail_auto_note
    line = detail_auto_note({"detail_auto": res, "item_id": "i"})["line"]
    assert line.startswith("AI 초안 대신 기본 문장을 썼어요 — Anthropic") and "OpenAI 크레딧 없음" in line


def test_0_translate_chain_has_anthropic_before_openai(monkeypatch):
    from src.seller_console.ai.translator import AITranslator
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k2")
    monkeypatch.setenv("TRANSLATE_DISABLE_MYMEMORY", "1")
    ch = AITranslator()._provider_chain()
    assert ch.index("anthropic") == ch.index("openai") - 1
    monkeypatch.setenv("TRANSLATE_CHAIN_ORDER", "openai")
    assert AITranslator()._provider_chain() == ["anthropic", "openai"]
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert AITranslator()._provider_chain() == ["openai"]


def test_0_translate_anthropic_small_model(monkeypatch, ai):
    from src.seller_console.ai.translator import AITranslator
    ai.answers["other"] = {"title_ko": "북유럽 TV 스탠드", "description_ko": "블랙", "copy_coupang": "x"}
    monkeypatch.setenv("TRANSLATE_CHAIN_ORDER", "anthropic")
    out = AITranslator().translate_product({"title": "北欧电视柜", "description": "黑色"})
    assert out["provider"] == "anthropic" and out["title_ko"] == "북유럽 TV 스탠드"
    assert ai.calls[-1]["model"] == "claude-haiku-4-5"


# ── 2f'. 쿠팡 「메타 속성 고르기」 — 옵션 축 이름 → 그 카테고리 메타 속성(목록 안에서만) ─────────────────

def _f51_unknown_axis():
    from tests.test_f51_coupang_multi_sku import META, _product, _skus
    p = _product(_skus())
    p["options"] = [{"name": "尺码", "values": p["options"][0]["values"]}]           # 메타에 없는 축 이름(실물 617129397971)
    return META, p


def test_2f_axis_meta_pick_from_real_plan(ai):
    """실제 쿠팡 계획(`plan_for`)이 낸 「메타 속성 고르기」 재료 → AI가 목록 안에서 하나 → 다시 계획하면 그 보류가 사라진다."""
    from src.uploaders import coupang_options as O
    from src.services import ai_fix as AF
    META, p = _f51_unknown_axis()
    plan = O.plan_for(META["attributes"], p)
    assert plan["name_picks"] and plan["name_picks"][0]["choices"] == ["색상", "수량"]
    res = [{"market": "coupang:woojoo", "ok": False, "error_code": "coupang_hold", "details": plan["holds"],
            "name_picks": plan["name_picks"]}]
    [task] = [t for t in AF.plan(p, {}, res) if t["kind"] == "coupang_axis"]
    assert task["picks"][0]["orig"] == "尺码"
    ai.answers["other"] = {"picks": [{"orig": "尺码", "meta": "색상", "why": "값이 색 이름(白色 등)"}]}
    ex = {}
    out = AF.run_round(p, ex, res, calls_left=6)
    assert out["applied"] == ["coupang_axis:尺码"] and ex["coupang_option_names"] == {"尺码": "색상"}
    assert ex["manual_fields"]["coupang_axis:尺码"].startswith("ai:")
    plan2 = O.plan_for(META["attributes"], p)                                           # p에도 적용됨(이번 검증 재료)
    assert not plan2["name_picks"] and not any("메타 속성에 없어" in h for h in plan2["holds"])
    assert AF.summary(ex)["line"] == "AI가 고쳤어요 — 쿠팡 옵션 속성 1개"
    # 되돌리기 → 표에서 빠지고 다시 묻지 않는다(→ 다시 보류)
    assert AF.revert(ex, "coupang_axis:尺码") and ex["coupang_option_names"] == {}
    assert not [t for t in AF.plan(p, ex, res) if t["kind"] == "coupang_axis"]


def test_2f_axis_pick_outside_list_is_dropped():
    from src.services import ai_fix as AF
    t = {"kind": "coupang_axis", "markets": ["coupang"], "picks": [{"orig": "尺码", "label": "尺码", "candidate": "사이즈",
                                                                   "choices": ["색상", "수량"]}]}
    ex = {}
    assert AF._apply(t, {"picks": [{"orig": "尺码", "meta": "사이즈"}]}, {}, ex, {}) == []
    assert "coupang_option_names" not in ex and ex["ai_fix_rejects"]["coupang_axis:尺码"] == "목록 밖 이름"


def test_2f_precheck_hold_carries_name_picks():
    """실제 `CoupangUploader.precheck`(통신만 대역) → 「메타 속성 고르기」 재료가 판정 결과에 실린다(AI가 같은 재료로 고른다)."""
    from src.uploaders.coupang_uploader import CoupangUploader
    from tests.test_f51_coupang_multi_sku import META
    _, p = _f51_unknown_axis()

    class U(CoupangUploader):
        def _api_request(self, method, path, data=None, **kw):
            if "predict" in path:
                return {"data": {"predictedCategoryId": "69195", "predictedCategoryName": "충전 거치대"}}
            return {"data": META}

        def outbound_for_delivery(self):
            return "OB1", ""

        def is_agent_buy(self):
            return False
    up = U(access_key="ak", secret_key="sk", vendor_id="A1")
    out = up.precheck({**p, "title": p["title_ko"], "category_id": "69195"})
    assert out["ok"] is False and out["name_picks"][0]["orig"] == "尺码" and out["name_picks"][0]["choices"]
