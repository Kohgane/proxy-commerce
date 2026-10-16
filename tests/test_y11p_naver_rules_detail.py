"""Y11-P(오너 2026-10-15 19:01) — VRSUK 등록 실패 2종 계약.

1. 쿠팡 멈춤: 상세 원문이 타오바오 페이지 글자 통째(탭 라벨·구매평·문답) → 탭 라벨·남의 글 블록을 빼고, 남은 한자 줄은
   등록 직전 텐센트 텍스트 번역(사전검증·등록 같은 함수 `apply_outbound_text`) · 카드 「원문 n칸 자동 번역」.
2. 네이버 400: optionName1 25자 초과(옵션 14·15·16) · 옵션가 범위 ±50%(-1,796,050~1,796,050 @ 판매가 3,592,100)
   → 사전검증이 **등록과 같은 재료**(SKU별 판매가)로 잰다 · AI 축약 · 판매가 기준 재설정 · 안 되면 분할 제안(오너 확인 뒤에만).
"""
import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
VR = json.loads((FIX / "y11o_vrsuk_risk.json").read_text(encoding="utf-8"))
VRO = json.loads((FIX / "y11p_vrsuk_options.json").read_text(encoding="utf-8"))

# CNY 원가 → 스마트스토어 판매가(10원 올림) — 400 응답의 판매가 3,592,100에 맞춘 추정(환율 역산 · 실측 아님)
SELL = {"6995.00": 3592100, "7183.00": 3683990, "8822.00": 4485110, "9913.00": 5018380,
        "10460.00": 5285750, "11535.00": 5811190}


def _vr_product(**kw):
    skus = [dict(k, sell_price_krw=SELL[k["price"]]) for k in VRO["skus"]]
    return {"title": "VRSUK 리클라이너", "title_ko": "VRSUK 리클라이너", "options": VRO["options"], "skus": skus, **kw}


# ── 1. 상세 — 탭 라벨·남의 글 블록 ───────────────────────────────────────────────────────────────

def test_strip_page_ui_removes_tabs_reviews_qna_keeps_specs():
    from src.uploaders.detail_ui_junk import strip_page_ui, is_tab_label
    r = strip_page_ui(VR["description"])
    for gone in ("用户评价", "看了又看", "好颜郎", "送老公的", "问大家", "质量怎样", "查看全部评价", "查看全部问答", "店铺活动"):
        assert gone not in r["text"], gone
    assert "金属" in r["text"] and "框架材质" in r["text"]        # 규격표(상품 정보)는 남는다 — 번역 대상
    assert r["blocks"] == 2 and r["labels"] >= 5
    for lab in ("用户评价", "用户评价·35", "累计评论(1200)", "月销量 1000+", "宝贝详情", "举报", "店铺推荐", "收藏宝贝"):
        assert is_tab_label(lab), lab
    assert not is_tab_label("用户评价很好 质量不错")                 # 라벨로 시작해도 문장이면 라벨 아님


def test_block_without_end_drops_only_start_line():
    from src.uploaders.detail_ui_junk import strip_page_ui
    r = strip_page_ui("问大家·1\n这个椅子很舒服\n尺寸 83cm")
    assert "这个椅子很舒服" in r["text"] and "问大家" not in r["text"]


def _fake_tr(calls):
    def fn(text):
        calls.append(text)
        return {"ok": True, "text": "\n".join("번역:" + ln for ln in text.split("\n")), "why": ""}
    return fn


def _ko_tr(calls):
    """한글만 돌려주는 가짜 번역기(줄 수 그대로) — 마켓에 나갈 글자에 한자가 0인지 재려고."""
    def fn(text):
        calls.append(text)
        return {"ok": True, "text": "\n".join(f"옮긴 줄 {len(calls)}-{i}" for i, _ in enumerate(text.split("\n"))), "why": ""}
    return fn


def test_translate_leftover_counts_lines_and_keeps_korean():
    from src.uploaders import detail_translate as dt
    calls = []
    r = dt.translate_leftover("소파 설명\n金属\n框架材质\n83cm\n实木", translate_fn=_fake_tr(calls))
    assert r["translated"] == 3 and r["failed"] == 0
    assert r["text"].split("\n") == ["소파 설명", "번역:金属", "번역:框架材质", "83cm", "번역:实木"]
    assert len(calls) == 1                                          # Y11-Q: 떨어진 줄도 2,000자 한 묶음(호출 1회)
    assert calls[0] == "金属\n框架材质\n实木"


def test_translate_mismatch_inserts_block_and_failure_keeps_original():
    from src.uploaders import detail_translate as dt
    sent = []
    r = dt.translate_leftover("甲\n乙\n丙", translate_fn=lambda t: (sent.append(t) or
                                                                    {"ok": True, "text": "가 나 다" if "\n" in t else "옮김", "why": ""}))
    # Y11-Q: 돌아온 줄 수가 다르면 반으로 나눠 다시(번호로 끼울 수 있을 때까지) — 줄을 옮겨 붙이지 않는다
    assert r["text"] == "옮김\n옮김\n옮김" and r["translated"] == 3 and sent[0] == "甲\n乙\n丙"
    r2 = dt.translate_leftover("丁\n戊", translate_fn=lambda t: {"ok": False, "text": "", "why": "LimitExceeded"})
    assert r2["failed"] == 2 and r2["translated"] == 0 and r2["text"] == "丁\n戊" and r2["why"] == "LimitExceeded"


def test_outbound_vrsuk_korean_only_with_note(monkeypatch):
    """사전검증·등록이 지나는 `apply_outbound_text` — 쿠팡이 보는 상세에 한자 0 · 카드 줄 「원문 n칸 자동 번역」."""
    from src.uploaders import detail_translate as dt
    from src.seller_console.upload_dispatcher import apply_outbound_text
    from src.collectors.ko_polish import has_foreign
    calls = []
    monkeypatch.setattr(dt, "_default_translate", _ko_tr(calls))
    monkeypatch.setattr("src.services.image_translate_tencent.is_configured", lambda: True)
    dt._CACHE.clear()
    pd = apply_outbound_text({"title": "VRSUK", "description": VR["description"], "description_ko": ""})
    assert not has_foreign(pd["description"])
    assert pd["description"].count("옮긴 줄") >= 30                     # 규격표 줄이 버려지지 않고 옮겨졌다
    assert len(calls) >= 1 and all("用户评价" not in c and "好颜郎" not in c for c in calls)   # 남의 글은 번역에 안 보낸다
    n = pd["detail_auto_translated"]
    assert n >= 30 and pd["detail_translate_failed"] == 0 and pd["detail_page_ui_removed"] == 35   # Y11-W: + 내수 속성 14줄(키 7 + 값 7: 배송·설치 도시·택시 운송·예약판매…)
    assert dt.note(pd).startswith(f"원문 {n}칸 자동 번역")
    # 두 번 지나도 같은 값(사전검증 잡 → prevalidate → 등록) · 번역 호출 더 없음
    before = len(calls)
    pd2 = apply_outbound_text(pd)
    assert pd2["description"] == pd["description"] and len(calls) == before
    assert pd2["detail_auto_translated"] == n                          # 0으로 덮어쓰지 않는다


def test_outbound_without_tencent_key_drops_han_like_before(monkeypatch):
    from src.uploaders import detail_translate as dt
    from src.seller_console.upload_dispatcher import apply_outbound_text
    from src.collectors.ko_polish import has_foreign
    monkeypatch.setattr("src.services.image_translate_tencent.is_configured", lambda: False)
    pd = apply_outbound_text({"title": "VRSUK", "description": VR["description"], "description_ko": ""})
    assert not has_foreign(pd["description"])
    assert "detail_auto_translated" not in pd and dt.note(pd) == ""


def test_coupang_contents_no_foreign_after_outbound(monkeypatch):
    """쿠팡 상세 칸(브리지 description_html ← description)에 원문이 남지 않는다 — 19:01 멈춤의 그 칸."""
    from src.uploaders import detail_translate as dt
    from src.seller_console.upload_dispatcher import apply_outbound_text
    from src.channel_sync._channel_bridge import to_collected
    from src.uploaders.coupang_uploader import CoupangUploader
    monkeypatch.setattr(dt, "_default_translate", _ko_tr([]))
    monkeypatch.setattr("src.services.image_translate_tencent.is_configured", lambda: True)
    dt._CACHE.clear()
    raw = {"title": "VRSUK 리클라이너", "description": VR["description"], "price": "6995", "currency": "CNY",
           "sell_price_krw": 3592100}

    def probe(pd):
        body = to_collected(pd)["description_html"]
        return [f for f in CoupangUploader.foreign_fields(
            {"sellerProductName": "VRSUK 리클라이너", "items": [{"contents": [{"contentDetails": [{"content": body}]}]}]})
                if f[0] == "상세"]

    assert probe(raw) and probe(raw)[0][1].startswith("用户评价")        # 고치기 전: 19:01 그 값
    assert probe(apply_outbound_text(raw)) == []


# ── 2. 네이버 옵션 규칙 ─────────────────────────────────────────────────────────────────────────

def test_price_range_matches_measured_400():
    from src.uploaders.naver_options import price_range
    assert price_range(3592100) == (-1796050, 1796050)              # 19:01 응답 원문
    assert price_range(5000) == (-2500, 5000) and price_range(1000) == (0, 1000)   # 판매자센터 안내(미실측)


def test_vrsuk_name_len_hold_options_14_15_16():
    from src.uploaders import naver_options as no
    op = no.plan(_vr_product())
    assert op["mode"] == "hold" and op["reason_code"] == no.REASON_NAME_LEN
    assert [len(x) for x in op["long_names"]] == [28, 29, 30]
    assert "25자" in op["why"]


@pytest.fixture
def state(monkeypatch):
    """운영 DB `app_state` 대역(기준가 규칙·실측 기록·번역 호출 기록)."""
    import src.db.image_translate_queue_pg as st
    box = {}
    monkeypatch.setattr(st, "state_get", lambda k: dict(box.get(k) or {}))
    monkeypatch.setattr(st, "state_set", lambda k, v: box.__setitem__(k, dict(v)))
    return box


_SHORT = {VRO["skus"][13]["spec"][0]: "미스트블루 반가죽 세미아닐린/발받침",
          VRO["skus"][14]["spec"][0]: "블랙 풀가죽 아닐린/발받침 소가죽",
          VRO["skus"][15]["spec"][0]: "베이지 풀가죽 아닐린/발받침 소가죽"}


def test_vrsuk_after_shortening_base_moves_into_range(state):
    """Y11P-1(오너 승인): 규칙이 비어 있으면 최소 허용값 3,874,130 먼저 · 대체 4,485,110(옵션 판매가)."""
    from src.uploaders import naver_options as no
    op = no.plan(_vr_product(option_value_overrides=_SHORT))
    assert op["mode"] == "combo"
    assert (op["sale_price"], op["base_how"]) == (3874130, "calc")             # 최고 5,811,190 ÷ 1.5 올림
    assert (op["base_alt"], op["base_alt_how"]) == (4485110, "option")
    lo, hi = no.price_range(op["sale_price"])
    prices = [c["price"] for c in op["option_info"]["optionCombinations"]]
    assert all(lo <= p <= hi for p in prices) and 0 not in prices               # 0원 옵션 없음 — 그래서 실측
    assert sorted({op["sale_price"] + p for p in prices}) == sorted(set(SELL.values()))   # 옵션마다 판매가 그대로
    assert "3,874,130원(최소 허용값)으로 먼저" in no.base_note(op) and "4,485,110원으로 바로 다시" in no.base_note(op)
    assert all(len(c["optionName1"]) <= 25 for c in op["option_info"]["optionCombinations"])
    # 규칙이 정해지면 그쪽만(대체 없음)
    state[no.BASE_RULE_KEY] = {"rule": "option"}
    op2 = no.plan(_vr_product(option_value_overrides=_SHORT))
    assert (op2["sale_price"], op2["base_alt"]) == (4485110, 0) and 0 in [c["price"] for c in op2["option_info"]["optionCombinations"]]
    state[no.BASE_RULE_KEY] = {"rule": "calc"}
    assert no.plan(_vr_product(option_value_overrides=_SHORT))["sale_price"] == 3874130


class _FakeNaver:
    """등록 몸통만 잰다 — 첫 POST에 줄 응답을 고른다."""
    STOCK_QUANTITY = 999

    def __init__(self, first):
        self.first, self.sent = first, []

    def post(self, payload):
        self.sent.append(payload)
        if len(self.sent) == 1 and self.first:
            return self.first
        return {"originProductNo": 9001, "smartstoreChannelProductNo": 8001}


def _run_upload(monkeypatch, first):
    from src.uploaders import naver_uploader as NU
    up = NU.NaverSmartStoreUploader.__new__(NU.NaverSmartStoreUploader)
    up.account, up.image_upload_enabled = "chezgoga", False
    fake = _FakeNaver(first)
    monkeypatch.setattr(up, "_api_request", lambda m, path, data=None: fake.post(data), raising=False)
    monkeypatch.setattr(up, "_build_product_payload",
                        lambda p: {"salePrice": p["_option_plan"]["sale_price"]}, raising=False)
    import src.uploaders.naver_detail as ND
    monkeypatch.setattr(ND, "judge", lambda html, u, sku="": {"ok": True, "html": "<p>본문</p>"})
    import src.uploaders.naver_categories as NC
    monkeypatch.setattr(NC, "pick", lambda p: ("50003682", "manual"))
    monkeypatch.setattr(NC, "hold", lambda *a, **k: None)
    monkeypatch.setattr(up, "find_template_leaks", lambda payload: [], raising=False)
    monkeypatch.setattr(up, "_access_token", lambda: "t", raising=False)
    prod = dict(_vr_product(option_value_overrides=_SHORT), sku="VR", item_id="4ebaf1b8", description_html="<p>본문</p>")
    return up.upload_product(prod), fake


_400 = json.dumps({"code": "BAD_REQUEST", "message": "Invalid", "invalidInputs": [
    {"name": "originProduct.detailAttribute.optionInfo.optionCombinations", "type": "NotValid",
     "message": "옵션가가 0원인 옵션이 1개 이상 있어야 합니다."}]}, ensure_ascii=False)


def test_naver_calc_rejected_retries_option_in_same_flow_and_fixes_rule(monkeypatch, state):
    from src.uploaders import naver_options as no
    out, fake = _run_upload(monkeypatch, {"error": "HTTP 400", "http_status": 400, "body": _400})
    assert [p["salePrice"] for p in fake.sent] == [3874130, 4485110]
    assert out["success"] and out["channel_product_no"] == "8001"
    pb = out["base_probe"]
    assert pb["retried"] and pb["second_ok"] and "0원인 옵션" in pb["first_error"]
    assert state[no.BASE_RULE_KEY]["rule"] == "option"                          # 통과한 쪽으로 고정
    assert "거부해서 4,485,110원(옵션 판매가)으로 다시 보내 등록" in no.probe_line(pb)
    assert "0원인 옵션" in no.probe_line(pb)                                     # 거부 원문 앞부분


def test_naver_calc_accepted_fixes_calc(monkeypatch, state):
    from src.uploaders import naver_options as no
    out, fake = _run_upload(monkeypatch, None)
    assert [p["salePrice"] for p in fake.sent] == [3874130]
    assert out["base_probe"]["first_ok"] and state[no.BASE_RULE_KEY]["rule"] == "calc"
    assert "3,874,130원(최소 허용값)으로 등록" in no.probe_line(out["base_probe"])


def test_naver_unrelated_400_no_retry_no_rule(monkeypatch, state):
    from src.uploaders import naver_options as no
    body = json.dumps({"invalidInputs": [{"name": "originProduct.leafCategoryId", "type": "NotValid", "message": "x"}]})
    out, fake = _run_upload(monkeypatch, {"error": "HTTP 400", "http_status": 400, "body": body})
    assert len(fake.sent) == 1 and not out["success"]                          # 카테고리 거부는 기준가를 바꿔도 같은 답
    assert no.BASE_RULE_KEY not in state and state[no.BASE_PROBE_KEY]["rows"][-1]["related"] is False


def test_split_proposal_and_owner_confirm():
    from src.uploaders import naver_options as no
    skus = [{"spec": ["A 반가죽"], "sku_id": "1", "sell_price_krw": 10000, "stock": 3},
            {"spec": ["B 반가죽"], "sku_id": "2", "sell_price_krw": 11000, "stock": 3},
            {"spec": ["C 풀가죽 오토만 세트"], "sku_id": "3", "sell_price_krw": 50000, "stock": 3}]
    p = {"title": "라운지체어", "options": [{"name": "색상", "values": ["A 반가죽", "B 반가죽", "C 풀가죽 오토만 세트"]}], "skus": skus}
    op = no.plan(p)
    assert op["mode"] == "hold" and op["reason_code"] == no.REASON_SPLIT and len(op["split"]) == 2
    assert "나눠 등록할까요" in op["why"]
    assert not no.split_approved(p, op)                                   # 확인 전엔 나누지 않는다
    p2 = dict(p, naver_split_ok={"sig": no.split_sig(op["split"])})
    assert no.split_approved(p2, no.plan(p2))
    parts = no.split_products(p2, op)
    assert [len(x["skus"]) for x in parts] == [2, 1]
    assert parts[1]["title"].startswith("라운지체어 (") and all(no.plan(x)["mode"] == "combo" or len(x["skus"]) == 1 for x in parts)
    assert no.split_approved(dict(p, naver_split_ok={"sig": "다른 묶음"}), op) is False


def test_naver_required_holds_uses_sku_prices(monkeypatch):
    """사전검증 = 등록과 같은 재료 — 예전엔 SKU별 판매가 없이 재서 「통과」 → 등록 400."""
    from src.seller_console import upload_dispatcher as ud
    from src.channel_sync import coupang_uploader as cu
    monkeypatch.setattr(cu, "with_sku_prices", lambda pd, market="coupang": _vr_product())
    monkeypatch.setattr(ud, "naver_detail_verdict", lambda pd: {"ok": True, "dropped": []})
    monkeypatch.setattr(ud, "naver_payload_holds", lambda pd, iid: [])
    pd = {"title": "VRSUK", "skus": VRO["skus"], "options": VRO["options"]}
    holds = ud.naver_required_holds(pd)
    h = [x for x in holds if x["code"] == "naver_option_name_len"]
    assert h and h[0]["fix"] == "option_short" and len(h[0]["long_names"]) == 3
    assert "AI 축약" in ud.readiness_message(holds)


def test_smartstore_upload_split_only_after_confirm(monkeypatch):
    from src.channel_sync import smartstore_uploader as ss
    from src.uploaders import naver_options as no
    skus = [{"spec": ["A"], "sku_id": "1", "sell_price_krw": 10000, "stock": 3},
            {"spec": ["B"], "sku_id": "2", "sell_price_krw": 50000, "stock": 3}]
    base = {"title": "의자", "options": [{"name": "색상", "values": ["A", "B"]}], "skus": skus}
    op = no.plan(base)
    sent = []
    monkeypatch.setattr(ss, "make_uploader", lambda: object())
    monkeypatch.setattr("src.channel_sync.coupang_uploader.with_sku_prices", lambda pd, market="coupang": pd)
    monkeypatch.setattr(ss, "run_upload", lambda up, pd, **kw: (sent.append(pd["title"]) or
                                                                {"product_id": str(len(sent)), "channel_product_no": "9" + str(len(sent))}))
    out = ss.upload(base)                                                 # 확인 전 → 나누지 않고 한 번(업로더가 보류)
    assert sent == ["의자"] and "split_products" not in out
    sent.clear()
    out = ss.upload(dict(base, naver_split_ok={"sig": no.split_sig(op["split"])}))
    assert len(sent) == 2 and sent == ["의자", "의자 (구성 2)"]
    assert [x["channel_product_no"] for x in out["split_products"]] == ["91", "92"]


# ── 2b. AI 축약 ───────────────────────────────────────────────────────────────────────────────

class _R:
    def __init__(self, market, fixes):
        self.market, self.ok, self.fixes, self.details, self.message, self.error_code = market, False, fixes, [], "", ""


def test_ai_fix_option_short_apply_summary_revert():
    from src.services import ai_fix as af
    pd = _vr_product()
    ex = {}
    tasks = af.plan(pd, ex, [_R("smartstore", ["option_short"])])
    t = next(x for x in tasks if x["kind"] == "option_short")
    assert [len(r["ko"]) for r in t["rows"]] == [28, 29, 30]
    ans = {"values": {t["rows"][0]["ko"]: "미스트블루 반가죽 세미아닐린/발받침",
                      t["rows"][1]["ko"]: "블랙 풀가죽 아닐린/발받침 소가죽",
                      t["rows"][2]["ko"]: "블랙 풀가죽 아닐린/발받침 소가죽"}}      # 셋째는 둘째와 겹침 → 버림
    done = af._apply(t, ans, pd, ex, {"provider": "anthropic", "model": "haiku"})
    assert len(done) == 2
    assert "다른 옵션 값과 같아짐" in json.dumps(ex.get("ai_fix_rejects"), ensure_ascii=False)
    assert af.summary(ex)["line"] == "AI가 고쳤어요 — 옵션값 2개 축약"
    key = done[0]
    assert af.revert(ex, key)
    assert key.split(":", 1)[1] not in ex["option_value_overrides"] and key in ex["ai_fix_blocked"]


def test_ai_fix_option_short_rejects_over_cap():
    from src.services import ai_fix as af
    pd = _vr_product()
    ex = {}
    t = next(x for x in af.plan(pd, ex, [_R("smartstore", ["option_short"])]) if x["kind"] == "option_short")
    done = af._apply(t, {"values": {r["ko"]: r["ko"] for r in t["rows"]}}, pd, ex, {})
    assert done == [] and "25자 초과" in json.dumps(ex["ai_fix_rejects"], ensure_ascii=False)


def test_prevalidation_result_carries_split_field():
    from src.seller_console.upload_dispatcher import PrevalidationResult, UploadResult, DispatchResult
    assert PrevalidationResult(market="smartstore", ok=False).naver_split == []
    d = DispatchResult(product_url="", results=[UploadResult(market="smartstore", success=True, message="ok",
                                                              split_products=[{"channel_product_no": "1"}])]).to_dict()
    assert d["results"][0]["split_products"] == [{"channel_product_no": "1"}]


def test_tencent_text_calls_recorded_without_text(monkeypatch):
    """Y11P-2 — 실호출마다 운영 DB 한 줄(글자 수·줄 수·성공·사유·ms) · 글 내용은 안 남긴다 · 캐시 적중은 안 센다."""
    from src.uploaders import detail_translate as dt
    import src.db.image_translate_queue_pg as st
    box = {}
    monkeypatch.setattr(st, "state_get", lambda k: box.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: box.__setitem__(k, v))
    dt._CACHE.clear()
    dt.translate_leftover("金属\n实木", translate_fn=lambda t: {"ok": True, "text": "금속\n원목", "why": ""})
    dt.translate_leftover("金属\n实木", translate_fn=lambda t: {"ok": True, "text": "금속\n원목", "why": ""})
    dt.translate_leftover("布艺", translate_fn=lambda t: {"ok": False, "text": "", "why": "FailedOperation.NoFreeAmount"})
    rec = box[dt.RECENT_KEY]
    assert rec["total"] == 2 and rec["failed"] == 1
    assert rec["rows"][0] == {**rec["rows"][0], "chars": 5, "lines": 2, "ok": True}
    assert rec["rows"][1]["why"] == "FailedOperation.NoFreeAmount"
    assert "金属" not in str(rec) and "금속" not in str(rec)


# ── Y11P-2 번역 실패: 60초 뒤 1회 재시도 · 규격 줄은 쿠팡 보류 + 「다시 번역」 ─────────────────────────────

class _Flaky:
    """처음 n번 실패(텐센트 응답 코드) 뒤 성공 — 호출 수를 센다."""

    def __init__(self, fails):
        self.fails, self.calls = fails, 0

    def __call__(self, text):
        self.calls += 1
        if self.calls <= self.fails:
            return {"ok": False, "text": "", "why": "FailedOperation.ServiceIsolate"}
        return {"ok": True, "text": "\n".join(f"옮긴 줄 {i}" for i, _ in enumerate(text.split("\n"))), "why": ""}


@pytest.fixture
def tr(monkeypatch, state):
    from src.uploaders import detail_translate as dt
    monkeypatch.setattr("src.services.image_translate_tencent.is_configured", lambda: True)
    monkeypatch.setenv("DETAIL_TRANSLATE_RETRY_SEC", "1")
    dt._CACHE.clear()
    dt._FAIL.clear()
    return dt


def _wait(cond, sec=4.0):
    import time
    end = time.monotonic() + sec
    while time.monotonic() < end and not cond():
        time.sleep(0.05)
    return cond()


def test_failed_chunk_retries_once_after_delay_then_cache(tr, monkeypatch):
    f = _Flaky(1)
    monkeypatch.setattr(tr, "_default_translate", f)
    r = tr.translate_leftover("설명\n这款很好看\n非常舒服")
    assert r["failed"] == 2 and r["retry_pending"] == 2 and r["spec_failed"] == [] and f.calls == 1
    r2 = tr.translate_leftover("설명\n这款很好看\n非常舒服")              # 기다리는 동안은 다시 안 묻는다
    assert f.calls == 1 and r2["retry_pending"] == 2
    assert _wait(lambda: f.calls == 2)                                      # 재시도 1회
    assert _wait(lambda: not tr._FAIL)
    r3 = tr.translate_leftover("설명\n这款很好看\n非常舒服")
    assert r3["translated"] == 2 and r3["failed"] == 0 and f.calls == 2      # 캐시


def test_retry_also_fails_then_final_and_drop_note(tr, monkeypatch):
    f = _Flaky(5)
    monkeypatch.setattr(tr, "_default_translate", f)
    tr.translate_leftover("这款很好看")
    assert _wait(lambda: f.calls == 2) and _wait(lambda: (tr._FAIL.get(next(iter(tr._FAIL), "")) or {}).get("state") == "final")
    r = tr.translate_leftover("这款很好看")
    assert r["failed"] == 1 and r["retry_pending"] == 0 and f.calls == 2       # final — 10분 동안 다시 안 묻는다
    assert tr.note({"detail_translate_failed": 1, "detail_translate_why": r["why"]}) == \
        "원문 1칸은 번역하지 못해 뺐어요(FailedOperation.ServiceIsolate)"
    assert "60초 뒤 한 번 더" in tr.note({"detail_translate_failed": 1, "detail_translate_retry_pending": 1})


def test_spec_lines_failed_hold_coupang_not_drop(tr, monkeypatch):
    from src.seller_console.upload_dispatcher import apply_outbound_text, UploadDispatcher, PrevalidationResult
    f = _Flaky(99)
    monkeypatch.setattr(tr, "_default_translate", f)
    pd = apply_outbound_text({"title": "VRSUK", "description": VR["description"], "description_ko": ""})
    spec = pd["detail_translate_spec_failed"]
    assert spec and any("材质" in x for x in spec) and pd["detail_translate_retry_pending"] > 0
    line = tr.spec_hold_line(pd)
    assert line.startswith("보류: 상세 규격") and "「다시 번역」" in line and "60초 뒤" in line
    # 쿠팡 등록: 빼고 보내지 않는다(전송 0)
    res = UploadDispatcher()._upload_coupang(pd)
    assert not res.success and res.error_code == tr.SPEC_HOLD_CODE
    # 사전검증: 쿠팡 통과 → 보류 + 「다시 번역」 · 네이버는 그대로(그 줄만 뺌)
    monkeypatch.setattr(UploadDispatcher, "_prevalidate_market",
                        lambda self, p, m: PrevalidationResult(market=m, ok=True, message="사전검증 통과"))
    rs = UploadDispatcher().prevalidate(dict(pd), ["coupang", "smartstore"])
    cp = next(r for r in rs if r.market == "coupang")
    assert cp.hold and cp.error_code == tr.SPEC_HOLD_CODE and "retranslate" in cp.fixes
    assert next(r for r in rs if r.market == "smartstore").ok


def test_non_spec_failure_drops_and_passes(tr, monkeypatch):
    from src.seller_console.upload_dispatcher import apply_outbound_text
    from src.collectors.ko_polish import has_foreign
    monkeypatch.setattr(tr, "_default_translate", _Flaky(99))
    pd = apply_outbound_text({"title": "X", "description": "좋은 의자\n这款很好看", "description_ko": ""})
    assert pd["detail_translate_spec_failed"] == [] and tr.spec_hold_line(pd) == ""
    assert not has_foreign(pd["description"]) and "좋은 의자" in pd["description"]


def test_retranslate_now_ignores_wait(tr, monkeypatch):
    f = _Flaky(1)
    monkeypatch.setattr(tr, "_default_translate", f)
    tr.translate_leftover("材质\n实木")
    assert f.calls == 1
    o = tr.outbound("材质\n实木", force=True)                                  # 「다시 번역」 — 60초 안 기다림
    assert f.calls == 2 and o["failed"] == 0 and o["translated"] == 2


def test_retranslate_route(tr, monkeypatch):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    f = _Flaky(1)
    monkeypatch.setattr(tr, "_default_translate", f)
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=9", seller_id="y11p-rt", title="의자",
                   price="10", currency="CNY", extra={"title": "椅子", "description": "材质\n实木", "description_ko": ""})
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="y11p-rt", user_email="y11p-rt@example.com", user_role="seller")
    r1 = c.post(f"/seller/collect/{iid}/detail-retranslate", json={}).get_json()
    assert r1["ok"] is False and r1["spec_failed"] == 1 and "다시 눌러" in r1["error"]
    r2 = c.post(f"/seller/collect/{iid}/detail-retranslate", json={}).get_json()
    assert r2["ok"] is True and r2["translated"] == 2 and f.calls == 2
