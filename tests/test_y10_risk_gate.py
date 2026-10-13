"""Y10(오너 2026-10-13) 리스크 게이트 — 「상품 뭐에 걸릴 거 같으면 다 빼자. 사전검증에서 체크해서 유저한테 확인시키고 선택권을 주자.」

재현: VRSUK 라운지체어 `4ebaf1b8` 운영 저장값(`tests/fixtures/y10_4ebaf1b8_extra.json`) — 상품명은 깨끗했지만
원문 상세 리뷰(「伊姆斯躺椅」)·참수(型号 「伊姆斯躺椅-油蜡皮」)·검색어(「이임스」「Eames」)·사진 속 글자(갤러리 3·4
「Zaha Hadid」, 상세 8 「Eames Chair」)에 디자인 상표가 있었다. 예전 게이트는 통과시켰다.
"""
from __future__ import annotations

import copy
import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "y10_4ebaf1b8_extra.json")


def _ex():
    with open(FIX, encoding="utf-8") as f:
        d = json.load(f)
    d.pop("_doc", None)
    return d


@pytest.fixture(autouse=True)
def _fresh_state():
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    yield
    q.reset_for_tests()


def _item(sid, ex):
    from src.seller_console import collect_history_store as S
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id=sid,
                   title=ex.get("title_ko") or "x", price="129", currency="CNY", extra=ex)
    return iid[0] if isinstance(iid, tuple) else iid


def _client(sid):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = sid
    return c


def _saved(iid, sid):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_ids={sid})["extra_json"])


# ── 7. VRSUK: 보류 「상표/디자인 — 상품명 0, 본문 1, 참수 1, 이미지 3장」 ─────────────────────────────

def test_vrsuk_is_held_with_where_and_image_numbers():
    from src.services import risk_gate as R
    sc = R.scan(_ex())
    hold = {h["label"]: h for h in sc["hits"] if h["grade"] == "hold"}
    assert set(hold) == {"임스", "자하 하디드"}
    eames, zaha = hold["임스"], hold["자하 하디드"]
    assert eames["cat"] == "상표/디자인" and {"Eames", "伊姆斯", "이임스"} <= set(eames["found"])
    assert R.where_line(eames) == "상품명 0 · 검색어 2 · 본문 1 · 참수 1 · 이미지 1장(상세 8)"
    assert R.where_line(zaha) == "상품명 0 · 이미지 2장(사진 3 · 사진 4)"
    # 등록 몸통은 번역이 없으면 description_ko = 원문 복사본 — 두 번 세지 않는다(캡처에서 「본문 2 · 참수 2」로 나왔다)
    body = dict(_ex()); body["description_ko"] = body["description"]
    assert R.where_line(next(h for h in R.scan(body)["hits"] if h["label"] == "임스")) == R.where_line(eames)
    assert len(eames["images"]) + len(zaha["images"]) == 3                     # 이미지 3장
    shorts = [h["short"] for h in R.holds(sc)]
    assert len(shorts) == 2 and all(s.startswith("위험(보류) — 상표/디자인") for s in shorts)


def test_vrsuk_strip_then_recheck_passes_with_three_images_out():
    """「빼고 등록」 → 낱말이 상품명·검색어·본문·참수에서 빠지고, 걸린 3장(사진 3·4 · 상세 8)은 등록에서 빠진다 → 재검증 통과."""
    from src.services import image_translate_store as S
    from src.services import risk_gate as R
    sid = "y10-vr"
    ex = _ex()
    iid = _item(sid, ex)
    c = _client(sid)
    g0, d0 = len(S.effective_images(ex, kind="gallery")), len(S.effective_images(ex, kind="detail"))
    for key in ("tm:임스", "tm:자하 하디드"):
        d = c.post(f"/seller/collect/{iid}/risk-decision", json={"key": key, "action": "strip"}).get_json()
        assert d["ok"], d
    saved = _saved(iid, sid)
    assert R.holds(R.scan(saved)) == []                                         # 재검증 — 보류 0
    assert "Eames" not in saved["keywords"] and "이임스" not in saved["keywords"]
    assert "伊姆斯" not in saved["description"] and "躺椅-油蜡皮" in saved["description"]    # 낱말만 뺀다
    assert g0 - len(S.effective_images(saved, kind="gallery")) == 2              # 사진 3·4
    assert d0 - len(S.effective_images(saved, kind="detail")) == 1               # 상세 8
    out = [e["idx"] for e in saved["images_ko"] if e.get("risk_exclude")] + \
          [e["idx"] for e in saved["detail_images_ko"] if e.get("risk_exclude")]
    assert sorted(out) == [2, 3, 7]


def test_prevalidate_holds_then_passes_after_strip():
    """사전검증 몸통(`_risk`) — 옛 상표 보류 대신 게이트 보류. 뺀 뒤엔 그 보류가 없다."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.services import risk_gate as R
    ex = _ex()
    pd = {"title_ko": ex["title_ko"], "price": 129, "images": ex["images"], "_risk": R.scan(ex)}
    holds = UploadDispatcher.readiness_holds(pd, "coupang")
    risk = [h for h in holds if h["fix"] == "risk"]
    assert len(risk) == 2 and not [h for h in holds if h["fix"] == "trademark"]
    for h in [x for x in R.scan(ex)["hits"] if x["grade"] == "hold"]:
        R.decide(ex, h["key"], "strip")
    pd["_risk"] = R.scan(ex)
    assert not [h for h in UploadDispatcher.readiness_holds(pd, "coupang") if h["fix"].startswith("risk")]


# ── 대조 ───────────────────────────────────────────────────────────────────────────────────

def test_pleats_set_unchanged():
    """플리츠 세트(옛 대조 샘플) — 위험 0, 보류 0."""
    from src.services import risk_gate as R
    ex = {"title": "三宅褶皱套装", "title_ko": "플리츠 투피스 세트", "description": "플리츠 투피스 세트예요.",
          "options": [{"name": "颜色分类", "name_ko": "색상", "values": ["黑色上衣", "黑色半裙"], "values_ko": ["블랙 상의", "블랙 스커트"]}]}
    sc = R.scan(ex)
    assert sc["hits"] == [] and R.holds(sc) == []


def test_health_supplement_is_caution_only():
    """건기식(오너: 인허가 보유) — 주의만, 보류 0. 「식품」(수입식품 보류)이 「건강기능식품」 안에서 잡히지 않는다."""
    from src.services import risk_gate as R
    ex = {"title_ko": "비타민C 1000 건강기능식품 120정", "description_ko": "하루 1정 섭취하는 영양제예요.", "keywords": ["비타민", "영양제"]}
    sc = R.scan(ex)
    assert {h["grade"] for h in sc["hits"]} == {"caution"}
    assert [h["label"] for h in sc["hits"]] == ["건강기능식품(인허가 보유)"]
    assert R.holds(sc) == []


def test_word_boundaries_do_not_misfire():
    from src.services import risk_gate as R
    ex = {"title_ko": "뉴욕 타임스 스타일 원목 책상", "description_ko": "Supreme quality? no — supreme comfort chair"}
    labels = [h["label"] for h in R.scan(ex)["hits"]]
    assert "임스" not in labels                                                 # 「타임스」 속 「임스」
    assert "슈프림" not in labels                                               # 소문자 일반어(대소문자 구분 항목)


# ── 등급·버튼 ──────────────────────────────────────────────────────────────────────────────

def test_block_grade_has_no_allow():
    from src.services import risk_gate as R
    ex = {"title_ko": "가정용 의료기기 저주파 마사지기"}
    h = next(h for h in R.scan(ex)["hits"] if h["grade"] == "block")
    assert h["can_allow"] is False
    r = R.decide(ex, h["key"], "allow")
    assert not r["ok"] and "차단" in r["error"]
    assert R.holds(R.scan(ex))[0]["fix"] == "risk_block"


def test_allow_records_and_releases_hold():
    from src.services import risk_gate as R
    ex = _ex()
    for h in [x for x in R.scan(ex)["hits"] if x["grade"] == "hold"]:
        assert R.decide(ex, h["key"], "allow", by="owner")["ok"]
    assert R.holds(R.scan(ex)) == []
    assert ex["risk_decisions"]["tm:임스"]["action"] == "allow" and ex["risk_decisions"]["tm:임스"]["by"] == "owner"


def test_skip_puts_chip_and_holds():
    from src.services import risk_gate as R
    sid = "y10-skip"
    iid = _item(sid, _ex())
    c = _client(sid)
    d = c.post(f"/seller/collect/{iid}/risk-decision", json={"key": "", "action": "skip", "reason": "상표/디자인 Eames"}).get_json()
    assert d["ok"] and d["risk"]["skip"]["reason"] == "상표/디자인 Eames"
    saved = _saved(iid, sid)
    assert R.holds(R.scan(saved))[0]["short"] == "등록 보류: 상표/디자인 Eames"
    html = c.get("/seller/collect/history").get_data(as_text=True)
    assert "등록 보류: 상표/디자인 Eames" in html
    assert c.post(f"/seller/collect/{iid}/risk-decision", json={"key": "", "action": "reset"}).get_json()["ok"]
    assert not _saved(iid, sid).get("risk_skip")


# ── 6. 이미지 검사 대기 ─────────────────────────────────────────────────────────────────────

def test_waiting_for_image_text():
    from src.services import risk_gate as R
    sc = R.scan({"title_ko": "원목 의자"}, pending_images=3)
    h = R.holds(sc)
    assert [x["short"] for x in h] == ["이미지 검사 대기 3장"] and h[0]["fix"] == "risk_wait"


def test_pending_queue_pages_count_as_waiting():
    from src.db import image_translate_queue_pg as q
    import src.seller_console.views as V
    q.enqueue("u", "y10-wait", [("detail", 0), ("detail", 1)])
    assert V._risk_pending_images("y10-wait") == 2


# ── 4. 학습 ────────────────────────────────────────────────────────────────────────────────

def test_allow_twice_becomes_candidate_and_strip_is_remembered():
    from src.services import risk_gate as R
    for _ in range(2):
        ex = {"title_ko": "다이슨 호환 거치대"}
        assert R.decide(ex, "tm:다이슨", "allow")["ok"]
    assert [c["label"] for c in R.allow_candidates()] == ["다이슨"]
    R.confirm_allow("다이슨")
    assert "다이슨" not in [h["label"] for h in R.scan({"title_ko": "다이슨 호환 거치대"})["hits"]]
    # 「빼고 등록」은 그 낱말의 기본 동작 — 다음 상품은 자동으로 뺀다
    ex1 = {"title_ko": "레고 호환 블록 수납함"}
    R.decide(ex1, "tm:레고", "strip")
    ex2 = {"title_ko": "레고 블록 정리함"}
    assert R.auto_apply(ex2) == ["레고"]
    assert "레고" not in ex2["title_ko"] and ex2["risk_decisions"]["tm:레고"]["auto"] is True
    assert R.holds(R.scan(ex2)) == []


def test_settings_lists_candidates_and_confirms():
    from src.services import risk_gate as R
    for _ in range(2):
        R.decide({"title_ko": "다이슨 호환 거치대"}, "tm:다이슨", "allow")
    c = _client("y10-set")
    html = c.get("/seller/settings").get_data(as_text=True)
    assert "위험 검사에서 빼 줄 이름" in html and "다이슨" in html
    d = c.post("/seller/settings/risk-allow", json={"label": "다이슨", "on": True}).get_json()
    assert d["ok"] and "다이슨" in d["allow"] and d["candidates"] == []


# ── 등록 입구·AI 순서 ──────────────────────────────────────────────────────────────────────

def test_upload_refused_until_decided():
    sid = "y10-up"
    ex = _ex()
    iid = _item(sid, ex)
    c = _client(sid)
    r = c.post("/seller/collect/upload", json={"product": {"title": ex["title_ko"], "price": 129}, "markets": ["coupang"],
                                                "item_id": iid})
    d = r.get_json()
    assert r.status_code == 409 and d["risk"]["count"] == 2 and "위험 항목을 먼저 정해 주세요" in d["error"]


def test_upload_body_gets_strip_even_if_screen_is_stale():
    """「빼고 등록」 뒤 화면이 옛 상품명을 들고 와도 서버가 다시 뺀다(저장된 결정이 정본)."""
    from src.services import risk_gate as R
    ex = {"title_ko": "레고 블록 정리함", "keywords": ["레고", "수납"]}
    R.decide(ex, "tm:레고", "strip")
    pd = {"title_ko": "레고 블록 정리함", "keywords": ["레고", "수납"]}
    R.enforce(pd, ex)
    assert pd["title_ko"] == "블록 정리함" and pd["keywords"] == ["수납"]


def test_ai_fixes_wait_until_risk_is_decided(monkeypatch):
    """게이트가 먼저 — 결정 안 된 보류가 있으면 AI(반려 자동 수정·Y8)는 돌지 않고 카드에 위험 블록이 실린다."""
    import src.seller_console.views as V
    from tests._pv_helper import prevalidate
    called = []
    monkeypatch.setattr(V, "_pv_ai_fix", lambda *a, **k: called.append("ai") or (a[3], a[1]))
    monkeypatch.setattr(V, "_pv_auto_fix", lambda *a, **k: called.append("auto") or (None, a[1], []))
    from src.seller_console.upload_dispatcher import UploadDispatcher, PrevalidationResult, readiness_message
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: UploadDispatcher())
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))       # 외부 도달 확인 안 함(네트워크 0)

    def _readiness_only(self, pd, market):                                          # 마켓 키 없이 재료 판정만
        holds = UploadDispatcher.readiness_holds(pd, market)
        return PrevalidationResult(market=market, ok=not holds, hold=bool(holds),
                                   message=readiness_message(holds) if holds else "사전검증 통과")
    monkeypatch.setattr(UploadDispatcher, "_prevalidate_market", _readiness_only)
    sid = "y10-ai"
    ex = _ex()
    iid = _item(sid, ex)
    d = prevalidate(_client(sid), {"product": {"title": ex["title_ko"], "price": 129, "images": ex["images"]},
                                   "item_id": iid, "markets": ["coupang"]})
    assert called == []
    assert d["risk"]["count"] == 2 and d["risk"]["ai_waits"] is True
    row = d["results"][0]
    assert row["hold"] and "위험(보류)" in row["message"]


# ── Y10-B(오너 2026-10-13): 인증 등급 조정 — 전기·전파·어린이 = 주의 + 본문 맨 위 KC 고지 ─────────────────

CHARGER = {"title_ko": "무선 충전기 맥세이프 거치대 15W", "description_ko": "책상 위에 두고 쓰는 무선 충전 거치대예요.",
           "keywords": ["무선충전기", "거치대"]}


def test_wireless_charger_is_caution_with_kc_notice_not_hold():
    from src.services import risk_gate as R
    sc = R.scan(CHARGER)
    assert {h["label"]: h["grade"] for h in sc["hits"]} == {"KC 고지문 넣음(전기용품)": "caution", "KC 고지문 넣음(전파·무선)": "caution"}
    assert R.holds(sc) == []
    assert R.notice_kinds(sc) == {"kc": ["KC 고지문 넣음(전기용품)", "KC 고지문 넣음(전파·무선)"], "voltage": True}


def test_grades_after_y10b():
    from src.services import risk_gate as R
    g = lambda t: {h["label"]: h["grade"] for h in R.scan({"title_ko": t})["hits"]}
    assert g("어린이 원목 블록 장난감") == {"KC 고지문 넣음(어린이제품)": "caution"}
    assert g("블루투스 스피커") == {"KC 고지문 넣음(전파·무선)": "caution"}
    assert g("가정용 의료기기 저주파 마사지기")["의약품·의료기기"] == "block"           # 차단 유지
    assert g("수입 식품 간식 세트") == {"인증: 수입식품": "hold"}                          # 식품 보류 유지
    assert g("건기식 원료 분말 1kg")["인증: 건기식 원료 수입"] == "hold"                   # 원료 수입 보류
    assert g("건강기능식품 비타민 120정") == {"건강기능식품(인허가 보유)": "caution"}      # 완제품 주의
    assert g("화장품 세럼 30ml") == {"화장품(인허가 보유)": "caution"}


def test_kc_notice_goes_on_top_once_for_korean_markets():
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE, VOLTAGE_TITLE
    from src.seller_console.upload_dispatcher import korea_kc_notice
    from src.services import risk_gate as R
    pd = dict(CHARGER, description="책상 위에 두고 쓰는 무선 충전 거치대예요.",
              description_html="<p>책상 위에 두고 쓰는 무선 충전 거치대예요.</p>", kc_notice_kinds=R.notice_kinds(R.scan(CHARGER)))
    out = korea_kc_notice(pd, "coupang:woojoo")
    assert out["description"].startswith(PURCHASE_AGENT_NOTICE + "\n" + VOLTAGE_TITLE)
    assert out["description"].endswith("책상 위에 두고 쓰는 무선 충전 거치대예요.")
    assert out["description_html"].startswith('<p class="kgp-agent-notice">') and VOLTAGE_TITLE in out["description_html"]
    assert out["kc_notice"] == {"kc": ["KC 고지문 넣음(전기용품)", "KC 고지문 넣음(전파·무선)"], "voltage": True}
    again = korea_kc_notice(out, "smartstore")
    assert again["description"].count(PURCHASE_AGENT_NOTICE) == 1 and again["description"].count(VOLTAGE_TITLE) == 1
    assert korea_kc_notice(pd, "shopify") is pd                                      # 국내 마켓만
    plug = korea_kc_notice(dict(pd, plug_notice=True), "coupang")                    # 플러그 안내가 이미 붙었으면 전압 안내 생략
    assert VOLTAGE_TITLE not in plug["description"] and plug["kc_notice"]["voltage"] is False
    plain = korea_kc_notice({"title_ko": "원목 의자", "description": "튼튼해요."}, "coupang")
    assert "kc_notice" not in plain and plain["description"] == "튼튼해요."


def test_kc_notice_in_market_payload():
    """등록 몸통(마켓별 조립)을 지나면 맨 위에 붙어 있다 — 사전검증·등록이 같은 조립."""
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = dict(CHARGER, title="무선 충전기 맥세이프 거치대 15W", price=19900, images=["https://img.alicdn.com/a.jpg"],
              description="책상 위에 두고 쓰는 무선 충전 거치대예요.")
    payload, _loc = UploadDispatcher._payload_for_market(pd, "coupang")
    assert str(payload.get("description") or "").startswith(PURCHASE_AGENT_NOTICE)


def test_auto_strip_is_only_for_trademark_character_design():
    """오너(2026-10-13): 「빼고 등록」 자동 적용은 상표/캐릭터/디자인에만 — 인증·과장 카테고리는 매번 묻는다."""
    from src.services import risk_gate as R
    # 상표(캐릭터) — 기억해서 다음 상품은 자동으로 뺀다
    R.decide({"title_ko": "산리오 쿠로미 파우치"}, "tm:산리오", "strip")
    nxt = {"title_ko": "쿠로미 키링"}
    assert R.auto_apply(nxt) == ["산리오"] and "쿠로미" not in nxt["title_ko"]
    # 인증(수입식품 보류) — 빼고 등록을 골라도 기억하지 않는다 → 다음 상품에서 다시 묻는다
    first = {"title_ko": "수입 식품 간식 세트"}
    assert R.decide(first, "cert:food", "strip")["ok"]
    again = {"title_ko": "식품 선물 세트"}
    assert R.auto_apply(again) == []
    assert [h["short"] for h in R.holds(R.scan(again))] == ["위험(보류) — 인증: 수입식품: 식품"]
    assert "default" not in (R.learned().get("cert:food") or {})
    # 레플리카 의심(상표와 같이 나온 신호)도 자동으로 빼지 않는다
    R.decide({"title_ko": "임스 스타일 라운지체어", "description_ko": "임스 스타일"}, "replica", "strip")
    rep = {"title_ko": "임스 스타일 의자"}
    assert "레플리카 의심" not in R.auto_apply(rep)
