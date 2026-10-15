"""Y11-O(오너 2026-10-15 15:45 KST 캡처) — VRSUK 4ebaf1b8 등록을 막던 4건 + 빈 응답.

운영 근거(운영 DB 2026-10-15):
- 위험 게이트: 「상표/디자인 Zaha Hadid — 사진 3 · 상세 9 · 상세 25」 · 「브랜드 블랙리스트 향수 — 상세 4」.
  사진 3·상세 9 = 통째 거꾸로(rot180) 소품 사진(책 표지 「Zaha Hadid IS THAT YUD…」) — 예전 코드는 소품 글자를 한 줄로 이어 붙여
  빼려다 장 글자 어디에도 없는 줄이라 못 뺐다(상표가 그대로 셌다). 상세 25 「Zaha Hadid」 상자(사진의 0.21%)는 같은 책의 책등 —
  OCR 기울기·확신 값이 없어 소품 표시가 안 됐다. 그 뒤 자동 「빼고 등록」이 세 장을 등록에서 뺐다(risk_exclude).
  「향수」 = COUPANG_BLACKLIST85(env)의 보통명사가 쿠폰 사진(상세 4 — 판촉으로 이미 등록 제외) 증정품 「고급 광석 향수*1」에 걸린 것.
- 네이버 카테고리: 쿠팡 77989 「학생의자/사무용의자」 → 후보가 가구/인테리어 · 디지털/가전 · 여가/생활편의로 1단계부터 갈려 실패.
- 503: 다듬기 24장을 웹 프로세스 안에서 그린 직후 사전검증 — 인스턴스 417 → 490MB(상한 460, detail_judge에서 멈춤).
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "y11o_vrsuk_risk.json")
VRSUK = json.load(open(FIX, encoding="utf-8"))
BL85 = VRSUK["risk_decisions"]["blacklist"]["names"]          # 운영 env 목록 그대로(빼고 등록 결정에 저장된 이름 151개)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    monkeypatch.setattr("src.pipeline.coupang_replicate.load_blacklist85", lambda: {"terms": list(BL85)})
    yield
    q.reset_for_tests()


def _before_owner_actions():
    """오너 15:45 화면 직전 상태 — 자동 「빼고 등록」의 사진 제외와 쿠폰 상자 지우기(06:45) 전."""
    ex = copy.deepcopy(VRSUK)
    for k in ("images_ko", "detail_images_ko"):
        for e in ex[k]:
            e.pop("risk_exclude", None)
    for e in ex["detail_images_ko"]:
        if e["idx"] == 3:
            e.pop("edit", None)
    return ex


# ── 2. 소품 규칙 ────────────────────────────────────────────────────────────────────────────

def test_vrsuk_zaha_hadid_is_only_a_prop_note_now():
    from src.services import risk_gate as RG
    sc = RG.scan(_before_owner_actions())
    assert [h["key"] for h in sc["hits"]] == []                              # 예전: tm:자하 하디드(사진 3·상세 9·상세 25) + blacklist(상세 4)
    notes = {(n["where"], n["found"]) for n in sc["notes"]}
    assert {("사진 3", "Zaha Hadid"), ("상세 9", "Zaha Hadid"), ("상세 25", "Zaha Hadid")} <= notes


def test_whole_prop_pages_and_echo_box_values():
    """보고용 값 — 사진 3·상세 9는 장 전체가 소품(rot180, 상자 없음), 상세 25는 t3 「Zaha Hadid」(103×42, 1440×1442의 0.21%)가
    같은 상품의 통째 소품 사진 글자와 같아 소품. 같은 장 다른 상자(「A proposito di VRSUK」 30×251)는 소품이 아니다."""
    from src.services import prop_text as PT
    from src.services import risk_gate as RG
    ex = _before_owner_actions()
    g3 = next(e for e in ex["images_ko"] if e["idx"] == 2)
    d9 = next(e for e in ex["detail_images_ko"] if e["idx"] == 8)
    d25 = next(e for e in ex["detail_images_ko"] if e["idx"] == 24)
    assert RG._whole_prop(g3) and RG._whole_prop(d9) and not RG._whole_prop(d25)
    assert g3["box_frame"] == d9["box_frame"] == "rot180" and not g3["boxes"] and not d9["boxes"]
    known = PT.echo_texts(ex)
    props = {b["src"] for b in d25["boxes"] if PT.echoes(b, d25["box_size"], known)}
    assert "Zaha Hadid" in props and "A proposito di VRSUK" not in props and "Italia" not in props
    zh = next(b for b in d25["boxes"] if b["src"] == "Zaha Hadid")
    assert (zh["w"], zh["h"]) == (103, 42) and d25["box_size"] == [1440, 1442]


def test_prop_boxes_are_subtracted_one_by_one():
    """예전 버그: 소품 상자 글자를 「src tgt src tgt」 한 줄로 이어 붙여 빼려 했다 — 그 줄은 장 글자에 없어 상표가 다시 셌다."""
    from src.services import risk_gate as RG
    e = {"idx": 0, "status": "done", "box_size": [1000, 1000], "source_text": "책 표지 Zaha Hadid 의자 설명",
         "target_text": "책 표지 자하 하디드 의자 설명",
         "boxes": [{"src": "Zaha Hadid", "tgt": "자하 하디드", "prop": True, "w": 50, "h": 20}]}
    imgs = RG._images({"detail_images_ko": [e], "detail_images": ["https://img/a.jpg"]})
    assert imgs and "Zaha" not in imgs[0][3] and "하디드" not in imgs[0][3]


def test_strip_never_excludes_prop_only_photo():
    from src.services import risk_gate as RG
    ex = _before_owner_actions()
    h = {"names": ["Zaha Hadid"], "case": False, "cat": "상표/디자인", "found": ["Zaha Hadid"],
         "images": [{"kind": "gallery", "idx": 2, "name": "사진 3"}, {"kind": "detail", "idx": 8, "name": "상세 9"}]}
    RG.strip_extra(ex, h)
    assert not any(e.get("risk_exclude") for e in ex["images_ko"] + ex["detail_images_ko"])


def test_heal_unexcludes_the_three_photos_auto_strip_took():
    from src.services import risk_gate as RG
    ex = copy.deepcopy(VRSUK)
    assert [e["idx"] for e in ex["images_ko"] + ex["detail_images_ko"] if e.get("risk_exclude")] == [2, 8, 24]
    assert RG.heal_prop_excludes(ex) == ["사진 3", "상세 9", "상세 25"]
    assert not any(e.get("risk_exclude") for e in ex["images_ko"] + ex["detail_images_ko"])
    assert RG.heal_prop_excludes(ex) == []                                    # 두 번 해도 같다


def test_heal_keeps_exclusion_when_word_is_outside_props():
    from src.services import risk_gate as RG
    ex = copy.deepcopy(VRSUK)
    d25 = next(e for e in ex["detail_images_ko"] if e["idx"] == 24)
    d25["source_text"] += " Zaha Hadid 디자인 의자"                            # 소품 밖 글자에도 있으면 그대로 둔다
    assert "상세 25" not in RG.heal_prop_excludes(ex)


def test_strip_with_nothing_to_change_says_no_change(monkeypatch):
    import src.seller_console.views as V
    from src.services import risk_gate as RG
    monkeypatch.setattr(V, "_get_owned_item", lambda iid: {"extra_json": json.dumps({"title_ko": "의자"})})
    monkeypatch.setattr(RG, "decide", lambda ex, key, action, **k: {"ok": True, "hit": {"images": []}, "changed": False})
    monkeypatch.setattr("src.seller_console.collect_history_store.update", lambda *a, **k: True)
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11o"
    d = c.post("/seller/collect/x1/risk-decision", json={"key": "tm:x", "action": "strip"}).get_json()
    assert d["ok"] and d["changed"] is False and d["image_line"].startswith("변경 없음")


def test_decide_reports_changed_flag():
    from src.services import risk_gate as RG
    ex = {"title_ko": "Eames 라운지 의자", "keywords": ["Eames"]}
    sc = RG.scan(ex)
    key = next(h["key"] for h in sc["hits"] if "Eames" in h["found"])
    r = RG.decide(ex, key, "strip", by="t")
    assert r["ok"] and r["changed"] is True and "Eames" not in ex["title_ko"]


def test_skip_hint_when_skip_reason_is_now_only_a_prop_note():
    from src.services import risk_gate as RG
    ex = copy.deepcopy(VRSUK)
    RG.heal_prop_excludes(ex)
    sc = RG.scan(ex)
    assert sc["skip"]["reason"] == "상표/디자인 Zaha Hadid"
    hint = RG.skip_hint(sc)
    assert "자하 하디드" in hint and "참고" in hint and "보류 풀기" in hint
    line = RG.holds(sc)[0]["line"]
    assert line.startswith("「등록 안 함」으로 보류한 상품이에요") and hint not in line      # 마켓 줄마다 되풀이하지 않는다
    assert RG.card(sc)["skip_hint"] == hint                                       # 위험 블록 「보류 풀기」 옆 한 번


# ── 3. 블랙리스트 「향수」 ─────────────────────────────────────────────────────────────────────

def test_blacklist_common_nouns_are_not_brand_tokens():
    from src.services import risk_gate as RG
    kept = RG.brand_filter(BL85)
    dropped = [t for t in BL85 if t not in kept]
    assert {"향수", "니치향수", "캔들", "향초", "화장품", "건강기능식품", "건기식", "상표권"} <= set(dropped)
    assert {"nike", "adidas", "Memo Paris", "아디다스", "나이키", "애플", "몽클레르"} <= set(kept)
    assert RG.brand_token("Le Creuset™") and RG.brand_token("코카콜라®")
    assert not RG.brand_token("향수", brands=set(), common={"향수"})


def test_coupon_photo_4_is_not_scanned_and_perfume_no_longer_hits():
    from src.services import risk_gate as RG
    ex = _before_owner_actions()
    d4 = next(e for e in ex["detail_images_ko"] if e["idx"] == 3)
    assert d4["exclude"].startswith("판촉·스토어 문구")                         # 등록 제외된 쿠폰 사진
    assert not any(i[2] == "상세 4" for i in RG._images(ex))
    d4["source_text"] += " nike"                                              # 영문 브랜드라도 안 나가는 사진엔 보류를 걸지 않는다
    assert not any(h["key"] == "blacklist" for h in RG.scan(ex)["hits"])
    ex["title_ko"] += " 향수"                                                  # 보통명사는 상품명에 있어도 브랜드 보류 아님
    assert not any(h["key"] == "blacklist" for h in RG.scan(ex)["hits"])
    ex["title_ko"] += " nike"
    assert any(h["key"] == "blacklist" and h["found"] == ["nike"] for h in RG.scan(ex)["hits"])


def test_enforce_does_not_strip_common_noun_from_saved_blacklist_decision():
    from src.services import risk_gate as RG
    pd = {"title_ko": "의자 향수 받침 nike", "description_ko": "향수"}
    RG.enforce(pd, {"risk_decisions": {"blacklist": VRSUK["risk_decisions"]["blacklist"]}})
    assert "향수" in pd["title_ko"] and "nike" not in pd["title_ko"] and pd["description_ko"] == "향수"


# ── 4. 네이버 카테고리 고정 매핑표 · 1단계 갈림 AI 고르기 ─────────────────────────────────────────

#: 운영 네이버 트리(app_state naver_categories, 2026-10-15)에서 옮긴 리프 — 매핑표 ID 전부 + 1단계 갈림 후보
NAVER_REAL = dict(json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "y11p_category_trees.json"),
                                 encoding="utf-8"))["naver"])
NAVER_REAL.update({"50001514": "디지털/가전>소프트웨어>사무/회계", "50007327": "여가/생활편의>예체능레슨>댄스/무용"})
#: Y11O-1 뒤: 리클라이너·라운지·안락·오토만이 없는 사무용 의자(고정 매핑표 77989 → 일반의자 계약)
OFFICE = "메쉬 사무용 회전 의자 높이조절 허리 받침"
VR_TITLE = "VRSUK{비즈니스 시리즈} 심플 리클라이너 오일 왁스 가죽 사무용 회전 승강 1인 의자"
VR_CP = "가구/홈데코>가구>학생/사무용가구>학생의자>학생의자/사무용의자"


class _FakeCoupang:
    access_key, secret_key = "ak", "sk"

    def __init__(self, cid="77989", name="학생의자/사무용의자"):
        self.cid, self.name = cid, name

    def predict(self, product_name, description=""):
        return {"id": self.cid, "name": self.name, "type": "SUCCESS", "why": ""}


@pytest.fixture
def naver(monkeypatch):
    from src.uploaders import coupang_categories as CC
    from src.uploaders import naver_categories as NC
    NC.reset()
    CC.reset()
    monkeypatch.setattr(NC, "BACKGROUND", False)
    monkeypatch.setattr(CC, "BACKGROUND", False)
    rows = [{"id": k, "name": v.split(">")[-1], "wholeCategoryName": v, "last": True} for k, v in NAVER_REAL.items()]
    monkeypatch.setattr(NC, "_fetch", lambda account="": rows)
    monkeypatch.setattr(CC, "_fetch", lambda: {"77989": VR_CP})
    fake = _FakeCoupang()
    import src.channel_sync.coupang_uploader as CU
    monkeypatch.setattr(CU, "make_uploader", lambda: (fake, ""))
    yield NC, fake
    NC.reset()
    CC.reset()


def test_map_file_points_only_at_real_naver_leaves():
    from src.uploaders import naver_categories as NC
    m = NC.fixed_map()
    assert {"77989", "77914", "77912", "77904"} <= set(m)
    for cid, row in m.items():
        assert row["naver"] in NAVER_REAL and NAVER_REAL[row["naver"]] == row["naver_name"], cid
        assert all(a in NAVER_REAL for a in row.get("alt") or []), cid


def test_office_chair_without_lounge_words_maps_directly(naver):
    NC, _ = naver
    s = NC.compute_suggestion({"title_ko": OFFICE})
    assert s["mapped"] and s["id"] == "50003264" and s["name"] == "가구/인테리어>서재/사무용가구>의자>일반의자"
    assert [a["id"] for a in s["alts"]] == ["50003293", "50003683"] and s["coupang_path"] == VR_CP
    assert NC.pick({"title_ko": OFFICE}) == ("50003264", "map")
    assert NC.hold({"title_ko": OFFICE}) is None
    assert NC.SOURCE_LABEL["map"] == "자동(고정 매핑표)"


def test_mapped_category_shows_in_ai_fixed_line_and_can_be_reverted(naver):
    NC, _ = naver
    from src.services import ai_fix as AF
    pd, ex = {"title_ko": OFFICE}, {}
    results = [{"market": "smartstore:chezgoga", "ok": True}]
    assert AF.record_fixed_category(pd, ex, results) is True
    assert ex["naver_category_id"] == "50003264" and pd["naver_category_id"] == "50003264"
    sm = AF.summary(ex)
    assert sm["line"] == "AI가 고쳤어요 — 카테고리 1개"
    assert sm["items"][0]["label"].startswith("가구/인테리어>서재/사무용가구>의자>일반의자 (다른 후보: 하이팩의자 · 목받침의자)")
    assert "고정 매핑표" in sm["items"][0]["why"]
    assert AF.record_fixed_category(pd, ex, results) is False                     # 이미 적었다
    assert AF.revert(ex, "naver_category") and ex["naver_category_id"] == ""
    pd2 = AF.overlay({"title_ko": OFFICE}, ex)
    assert pd2.get("naver_category_no_auto") is True and NC.pick(pd2) == ("", "")   # 되돌리면 다시 자동으로 채우지 않는다
    assert AF.record_fixed_category({"title_ko": OFFICE}, ex, results) is False


def test_owner_choice_overrides_map(naver):
    NC, _ = naver
    from src.services import ai_fix as AF
    pd, ex = {"title_ko": OFFICE, "naver_category_id": "50003293"}, {"naver_category_id": "50003293"}
    assert NC.pick(pd) == ("50003293", "manual")
    assert AF.record_fixed_category(pd, ex, [{"market": "smartstore:chezgoga", "ok": True}]) is False


def test_no_record_without_smartstore(naver):
    from src.services import ai_fix as AF
    assert AF.record_fixed_category({"title_ko": OFFICE}, {}, [{"market": "coupang:gogane", "ok": True}]) is False


def test_split_top_level_goes_to_ai_with_photo_and_shows_other_two(naver, monkeypatch):
    NC, fake = naver
    from src.ai import llm
    from src.services import ai_fix as AF
    fake.cid, fake.name = "99999", "알 수 없는 리프"                              # 매핑표에 없는 리프
    monkeypatch.setattr(NC, "rank", lambda cp, title="", limit=3: [
        {"id": "50001341", "name": NAVER_REAL["50001341"], "score": 0.549},
        {"id": "50001514", "name": NAVER_REAL["50001514"], "score": 0.508},
        {"id": "50007327", "name": NAVER_REAL["50007327"], "score": 0.508}])
    pd = {"title_ko": OFFICE, "images": ["https://img.alicdn.com/vrsuk.jpg"]}
    h = NC.hold(pd)
    assert h["code"] == NC.REASON_CANDIDATES and len(h["candidates"]) == 3
    seen = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def fake_call(model, system, prompt, max_tokens, timeout, images=None):
        seen.append({"model": model, "images": images, "prompt": prompt})
        return {"text": json.dumps({"id": "50001341", "why": "의자"}), "tokens_in": 300, "tokens_out": 20}
    monkeypatch.setattr(llm, "_call_anthropic", fake_call)
    results = [{"market": "smartstore:chezgoga", "ok": False, "fixes": ["naver_category"]}]
    ex: dict = {}
    out = AF.run_round(pd, ex, results, calls_left=6)
    assert out["applied"] == ["naver_category"] and ex["naver_category_id"] == "50001341"
    assert seen[0]["images"] == ["https://img.alicdn.com/vrsuk.jpg"] and "haiku" in seen[0]["model"]
    assert "첨부한 대표 사진과 상품명을 보고" in seen[0]["prompt"]
    lab = AF.summary(ex)["items"][0]["label"]
    assert lab.startswith(NAVER_REAL["50001341"]) and NAVER_REAL["50001514"] in lab and NAVER_REAL["50007327"] in lab


# ── 5. 빈 응답 1회 재시도 ─────────────────────────────────────────────────────────────────────

def test_llm_retries_empty_answer_once_on_same_provider(monkeypatch):
    from src.ai import llm
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    answers = iter([{"text": "", "tokens_in": 10, "tokens_out": 0, "stop_reason": "end_turn"},
                    {"text": "{\"ok\": 1}", "tokens_in": 10, "tokens_out": 5}])
    calls = []
    monkeypatch.setattr(llm, "_call_anthropic", lambda *a, **k: calls.append(1) or next(answers))
    r = llm.complete("p", size="small", purpose="t", providers=["anthropic"])
    assert r["text"] == "{\"ok\": 1}" and r["retried_empty"] is True and len(calls) == 2


def test_llm_empty_twice_reports_empty(monkeypatch):
    from src.ai import llm
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    calls = []
    monkeypatch.setattr(llm, "_call_anthropic", lambda *a, **k: calls.append(1) or {"text": "", "tokens_in": 1, "tokens_out": 0})
    r = llm.complete("p", size="small", providers=["anthropic"])
    assert r["text"] == "" and "빈 응답" in r["error"] and len(calls) == 2


def test_polish_reasks_unreadable_batch_once(monkeypatch):
    from src.ai import llm
    from src.services import image_polish as IP
    monkeypatch.setattr(llm, "anthropic_ready", lambda: True)
    replies = iter(["앗 죄송합니다", json.dumps({"boxes": [{"id": "t0", "ko": "편안한 의자"}]})])
    monkeypatch.setattr(llm, "complete", lambda prompt, **k: {"text": next(replies)})
    out = IP.polish_boxes([{"id": "t0", "src": "舒适的椅子", "tgt": "편안한 의자입니다"}], {"rule": None})
    assert out["calls"] == 2 and out["ai_why"] == ""


def test_polish_unreadable_twice_says_so(monkeypatch):
    from src.ai import llm
    from src.services import image_polish as IP
    monkeypatch.setattr(llm, "anthropic_ready", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda prompt, **k: {"text": "", "error": "ValueError: 빈 응답"})
    out = IP.polish_boxes([{"id": "t0", "src": "舒适的椅子", "tgt": "편안한 의자입니다"}], {"rule": None})
    assert out["calls"] == 2 and "다시 물어도 같음" in out["ai_why"] and "빈 응답" in out["ai_why"]


# ── 1. 메모리 — 그리기 워커 하나 · 그리기 끝나고 5초 뒤 · 30초 뒤 1회 자동 재시도 ───────────────────────────

def test_render_runs_on_single_worker_thread_one_at_a_time():
    from src.utils import render_worker as RW
    names, live, peak = [], [0], [0]
    lock = threading.Lock()

    def job(i):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        names.append(threading.current_thread().name)
        time.sleep(0.05)
        with lock:
            live[0] -= 1
        return i * 10

    out = []
    ths = [threading.Thread(target=lambda i=i: out.append(RW.run(job, i, _name=f"t{i}"))) for i in range(4)]
    [t.start() for t in ths]
    [t.join(5) for t in ths]
    assert sorted(out) == [0, 10, 20, 30] and set(names) == {"render-worker"} and peak[0] == 1


def test_render_errors_reach_caller():
    from src.utils import render_worker as RW
    with pytest.raises(ZeroDivisionError):
        RW.run(lambda: 1 / 0, _name="boom")


def test_busy_until_settle_then_idle(monkeypatch):
    from src.utils import render_worker as RW
    monkeypatch.setenv("RENDER_SETTLE_SEC", "0.3")
    RW.run(lambda: None, _name="x")
    assert RW.busy() is True                                                    # 끝난 지 0.3초 안
    waited, timed_out = RW.wait_idle(5)
    assert not timed_out and 0.0 <= waited <= 1.0 and RW.busy() is False


def test_render_records_memory_rows():
    from src.db import image_translate_queue_pg as q
    from src.utils import render_worker as RW
    RW.run(lambda: None, _name="polish:detail21")
    rows = (q.state_get("rss:recent") or {}).get("rows") or []
    assert rows and rows[-1]["kind"] == "render" and rows[-1]["name"] == "polish:detail21" and "inst_after_mb" in rows[-1]


def test_image_edit_apply_renders_on_worker(monkeypatch):
    from src.services import image_edit as IE
    from src.utils import render_worker as RW
    used = []
    monkeypatch.setattr(RW, "run", lambda fn, *a, **kw: used.append((fn.__name__, kw.get("_name"))) or {"ok": False, "why": "테스트"})
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    monkeypatch.setattr(IE, "plan", lambda ex, kind, idx, small=None: {
        "url": "https://x/a.jpg", "size": [10, 10], "boxes": [{"id": "t0", "src": "a", "tgt": "b", "x": 0, "y": 0, "w": 5, "h": 5}]})
    import io as _io
    from PIL import Image
    b = _io.BytesIO()
    Image.new("RGB", (10, 10)).save(b, "JPEG")
    monkeypatch.setattr(IE, "_fetch", lambda url: b.getvalue())
    r = IE.apply({}, "detail", 3, [{"id": "t0", "action": "erase"}], by="user")
    assert used == [("render_local", "user:detail3")] and r["ok"] is False


def test_prevalidate_waits_for_render_then_starts(monkeypatch):
    import src.seller_console.views as V
    from src.utils import render_worker as RW
    from src.utils import rss
    seq = iter([True, True, True] + [False] * 100)
    monkeypatch.setattr(RW, "busy", lambda: next(seq))
    monkeypatch.setattr(RW, "wait_idle", lambda timeout: (6.2, False))
    monkeypatch.setattr(rss, "instance_mb", lambda: 300)
    monkeypatch.setenv("INSTANCE_MEM_START_MAX_MB", "420")
    notes = []
    real_upd = V._pv_update
    monkeypatch.setattr(V, "_pv_update", lambda jid, **kw: notes.append(kw.get("queue_note")) or real_upd(jid, **kw))
    ran = []
    monkeypatch.setattr(V, "_pv_job_body", lambda job_id, data, markets, dispatcher: ran.append(1) or real_upd(job_id, state="done"))
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: object())
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y11o-pv"
    d = c.post("/seller/collect/prevalidate", json={"product": {"title": "x", "price": 1}, "markets": ["elevenst"]}).get_json()
    for _ in range(100):
        if ran:
            break
        time.sleep(0.05)
    assert ran and "사진 그리기가 끝나면 자동으로 시작해요(메모리 보호)" in notes
    mw = V._pv_store().state_get(V._PV_JOB_KEY + d["job_id"])["mem_wait"]
    assert mw["render_wait_sec"] == 6.2 and mw["retry"] is False and mw["first_mb"] == 300
