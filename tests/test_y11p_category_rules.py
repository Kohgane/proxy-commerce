"""Y11O-1·2(오너 2026-10-15) — 상품명 토큰으로 쿠팡 예측 리프 바로잡기 · 매핑표 50 · 품목 주의(항공 운송 제한).

운영 근거: VRSUK 4ebaf1b8 「… 심플 리클라이너 오일 왁스 가죽 사무용 회전 승강 1인 의자」(원문 「…简约躺椅油蜡皮…」) —
쿠팡 예측 77989 「학생의자/사무용의자」. 오너: 라운지체어 → 네이버 「인테리어의자」.
"""
from __future__ import annotations

import copy
import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
TREES = json.load(open(os.path.join(FIX, "y11p_category_trees.json"), encoding="utf-8"))
VRSUK = json.load(open(os.path.join(FIX, "y11o_vrsuk_risk.json"), encoding="utf-8"))
VR = {k: VRSUK[k] for k in ("title_ko", "title", "title_en", "keywords", "tags", "images")}
OFFICE_CP = TREES["coupang"]["77989"]


@pytest.fixture(autouse=True)
def _fresh():
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    yield
    q.reset_for_tests()


class _FakeCoupang:
    access_key, secret_key = "ak", "sk"

    def __init__(self, cid="77989"):
        self.cid = cid

    def predict(self, product_name, description=""):
        return {"id": self.cid, "name": TREES["coupang"][self.cid].split(">")[-1], "type": "SUCCESS", "why": ""}


@pytest.fixture
def cat(monkeypatch):
    from src.uploaders import coupang_categories as CC
    from src.uploaders import naver_categories as NC
    NC.reset()
    CC.reset()
    monkeypatch.setattr(NC, "BACKGROUND", False)
    monkeypatch.setattr(CC, "BACKGROUND", False)
    rows = [{"id": k, "name": v.split(">")[-1], "wholeCategoryName": v, "last": True} for k, v in TREES["naver"].items()]
    monkeypatch.setattr(NC, "_fetch", lambda account="": rows)
    monkeypatch.setattr(CC, "_fetch", lambda: dict(TREES["coupang"]))
    fake = _FakeCoupang()
    import src.channel_sync.coupang_uploader as CU
    monkeypatch.setattr(CU, "make_uploader", lambda: (fake, ""))
    yield NC, fake
    NC.reset()
    CC.reset()


# ── 매핑표 50 ───────────────────────────────────────────────────────────────────────────────

def test_map_has_50_rows_real_ids_and_group_order():
    from src.uploaders import naver_categories as NC
    from src.uploaders import category_rules as CR
    m = NC.fixed_map()
    assert len(m) == 50
    groups = [r["group"] for r in m.values()]
    order = ["가구", "조명", "수납", "주방", "디지털"]
    assert groups == sorted(groups, key=order.index) and set(groups) == set(order)
    for cid, r in m.items():
        assert TREES["coupang"][cid] == r["coupang"], cid
        assert TREES["naver"][r["naver"]] == r["naver_name"], cid
        assert all(a in TREES["naver"] for a in r.get("alt") or []), cid
        assert isinstance(r["freq"], int) and r["freq"] >= 0
    rule = CR.rules()[0]
    assert all(c in TREES["coupang"] for c in rule["coupang_from"] + [rule["coupang"]])
    assert all(n in TREES["naver"] for n in [rule["naver"], rule["naver_lounge"]] + rule["naver_alt"])
    assert m["77916"]["freq"] == 14 and m["62697"]["freq"] == 5 and m["78370"]["freq"] == 5     # 빈백·무선충전기·벽등


# ── 상품명 규칙: VRSUK ─────────────────────────────────────────────────────────────────────────

def test_vrsuk_coupang_leaf_corrected_to_lounge_family(cat):
    NC, _ = cat
    g = NC.coupang_guess(VR)
    assert g["id"] == "77914" and g["name"] == "안락의자" and g["path"] == TREES["coupang"]["77914"]
    assert g["predicted"]["id"] == "77989" and g["rule_why"] == "상품명 「리클라이너」 → 안락의자"


def test_vrsuk_naver_is_interior_chair_by_lounge_signal(cat):
    NC, _ = cat
    s = NC.compute_suggestion(VR)
    assert s["id"] == "50003682" and s["name"] == "가구/인테리어>서재/사무용가구>의자>인테리어의자" and s["mapped"]
    assert [a["id"] for a in s["alts"]] == ["50003291", "50003245"]
    assert "躺椅" in s["map_why"] and "라운지체어" in s["map_why"]
    assert NC.pick(VR) == ("50003682", "map")


def test_recliner_without_lounge_signal_is_armchair(cat):
    NC, _ = cat
    s = NC.compute_suggestion({"title_ko": VR["title_ko"]})
    assert s["id"] == "50003291" and s["alts"][0]["id"] == "50003682" and s["map_why"] == "상품명 「리클라이너」 → 안락의자"


def test_overlay_carries_source_title_signal_from_saved_record(cat):
    """화면은 한국어 상품명만 보낸다 — 저장본 원문(「躺椅」)을 overlay가 얹어 사전검증·등록이 같은 답."""
    NC, _ = cat
    from src.services import ai_fix as AF
    pd = AF.overlay({"title_ko": VR["title_ko"]}, copy.deepcopy(VRSUK))
    assert "躺椅" in pd["category_text"] and NC.compute_suggestion(pd)["id"] == "50003682"


def test_ai_line_shows_both_and_coupang_rule_can_be_reverted(cat):
    NC, _ = cat
    from src.services import ai_fix as AF
    ex = copy.deepcopy(VRSUK)
    pd = AF.overlay({"title_ko": VR["title_ko"]}, ex)
    results = [{"market": "smartstore:chezgoga", "ok": True}, {"market": "coupang:gogane", "ok": True}]
    assert AF.record_coupang_rule(pd, ex, results) is True
    assert AF.record_fixed_category(pd, ex, results) is True
    sm = AF.summary(ex)
    assert sm["line"] == "AI가 고쳤어요 — 카테고리 1개 · 쿠팡 카테고리 1개"
    lab = {i["key"]: i for i in sm["items"]}
    assert lab["coupang_category"]["label"] == "학생의자/사무용의자 → 안락의자"
    assert lab["coupang_category"]["why"] == "상품명 「리클라이너」 → 안락의자"
    assert lab["naver_category"]["label"].startswith("가구/인테리어>서재/사무용가구>의자>인테리어의자 (다른 후보: 안락의자 · 리클라이너소파)")
    assert "라운지체어" in lab["naver_category"]["why"]
    # 오너가 쿠팡 카테고리를 되돌리면 그 상품은 규칙을 끈다 — 쿠팡 예측 그대로(학생의자/사무용의자)
    assert AF.revert(ex, "coupang_category")
    pd2 = AF.overlay({"title_ko": VR["title_ko"]}, ex)
    assert pd2["coupang_category_no_override"] is True
    assert NC.coupang_guess(pd2)["id"] == "77989"
    assert AF.record_coupang_rule(pd2, ex, results) is False


def test_no_coupang_record_without_coupang_market(cat):
    from src.services import ai_fix as AF
    assert AF.record_coupang_rule(dict(VR), {}, [{"market": "smartstore:chezgoga", "ok": True}]) is False


def test_coupang_registration_uses_same_rule(monkeypatch):
    from src.uploaders.coupang_uploader import CoupangUploader, tag_meta_absent
    up = CoupangUploader.__new__(CoupangUploader)
    up._predict_cache = {}
    monkeypatch.setattr(up, "predict_category", lambda name, desc="": "77989", raising=False)
    assert up.category_for({"title": "[해외직구] " + VR["title_ko"]}) == ("77914", "rule", "")
    assert up.category_for({"title": "메쉬 사무용 회전 의자"}) == ("77989", "predict", "")
    assert up.category_for({"title": VR["title_ko"], "coupang_category_no_override": True}) == ("77989", "predict", "")
    assert "상품명 규칙" in tag_meta_absent("옵션 색상가 이 카테고리 메타 속성에 없어", "77914", "rule")


def test_rule_flag_survives_channel_bridge_and_prepare():
    from src.channel_sync._channel_bridge import to_collected
    from src.uploaders.coupang_uploader import CoupangUploader
    col = to_collected({"title": "x", "title_ko": "x", "price": 1, "coupang_category_no_override": True})
    assert col["coupang_category_no_override"] is True
    up = CoupangUploader.__new__(CoupangUploader)
    assert CoupangUploader.prepare_product(up, dict(col, sku="s"))["coupang_category_no_override"] is True


@pytest.mark.parametrize("title,pred,want_cp,want_nv", [
    ("미드 센추리 모던 레트로 리클라이너 (오토만 포함) 라운지 의자", "77912", "77914", "50003682"),   # 라운지·오토만 → 인테리어의자
    ("편안한 안락의자 1인용", "77917", "77914", "50003291"),                                        # 스툴 예측 → 안락의자
    ("1인용 리클라이너 소파 각도조절", "77904", "77904", "50003245"),                                 # 이미 리클라이너 → 매핑표 그대로
    ("리클라이너 의자 커버 방수", "62611", "62611", "50017920"),                                       # 의자류 예측 아님 → 손대지 않음
])
def test_rule_only_touches_chair_predictions(cat, title, pred, want_cp, want_nv):
    NC, fake = cat
    fake.cid = pred
    s = NC.compute_suggestion({"title_ko": title})
    assert NC.coupang_guess({"title_ko": title})["id"] == want_cp and s["id"] == want_nv


# ── Y11O-2 품목 주의 ──────────────────────────────────────────────────────────────────────────

def test_air_restricted_items_are_caution_not_block(monkeypatch):
    monkeypatch.setattr("src.pipeline.coupang_replicate.load_blacklist85", lambda: {"terms": ["향수", "캔들", "상표권", "nike"]})
    from src.services import risk_gate as RG
    sc = RG.scan({"title_ko": "니치 향수 디퓨저 캔들 세트", "keywords": ["토치라이터"]})
    h = next(x for x in sc["hits"] if x["key"] == "item:air")
    assert h["grade"] == "caution" and set(h["found"]) == {"향수", "캔들", "토치라이터"}
    assert h["why"] == "주의: 항공 운송 제한 품목(인화성·배터리) — 배대지 확인"
    assert not any(x["key"] == "blacklist" for x in sc["hits"])                     # 보통명사 — 브랜드 매칭 제외 그대로
    assert RG.holds(sc) == []                                                         # 주의는 등록을 막지 않는다
    row = next(x for x in RG.card(sc)["hits"] if x["key"] == "item:air")
    assert row["grade_label"] == "주의" and row["cat"] == "항공 운송 제한 품목"


def test_trademark_word_and_cosmetics_are_not_air_caution(monkeypatch):
    monkeypatch.setattr("src.pipeline.coupang_replicate.load_blacklist85", lambda: {"terms": ["상표권", "화장품"]})
    from src.services import risk_gate as RG
    sc = RG.scan({"title_ko": "상표권 등록 화장품 파우치"})
    assert not any(x["key"] in ("item:air", "blacklist") for x in sc["hits"])


def test_item_caution_file_matches_owner_decision():
    d = json.load(open(os.path.join(os.path.dirname(__file__), "..", "src", "uploaders", "item_caution.json"), encoding="utf-8"))
    air = d["items"][0]
    assert air["names"] == ["향수", "니치향수", "캔들", "향초", "레이저모듈", "레이저포인터", "토치라이터"]
    assert not {"화장품", "건강기능식품", "건기식", "상표권"} & set(air["names"])


# ── 관리자 표: 실제 쿠팡 예측 리프 빈도 · 매핑표에 있나 ────────────────────────────────────────────────

def test_admin_table_ranks_coupang_leaves_and_flags_unmapped(cat, monkeypatch):
    NC, fake = cat
    from src.dashboard import admin_views as AV
    from src.utils import bg_job
    from src.db import image_translate_queue_pg as ST
    bg_job.reset()
    titles = [("빈백 소파 1인용", 3), ("메쉬 사무용 회전 의자", 2), ("마그네틱 키링 홀더", 1)]
    monkeypatch.setattr(AV, "_ncat_table_titles", lambda limit=1000: titles)
    pred = {"빈백 소파 1인용": "77916", "메쉬 사무용 회전 의자": "77989", "마그네틱 키링 홀더": "64180"}
    fake.predict = lambda name, desc="": {"id": pred[name], "name": TREES["coupang"][pred[name]].split(">")[-1],
                                         "type": "SUCCESS", "why": ""}
    monkeypatch.setattr(NC, "fixed_map", lambda: {k: v for k, v in json.load(open(os.path.join(
        os.path.dirname(__file__), "..", "src", "uploaders", "naver_category_map.json"), encoding="utf-8"))["map"].items()
        if k != "64180"})
    AV._ncat_table_run()
    top = ST.state_get(AV._NCAT_TABLE_KEY)["summary"]["leaves_top"]
    assert [(x["id"], x["count"], x["in_map"]) for x in top] == [("77916", 3, True), ("77989", 2, True), ("64180", 1, False)]
    assert ST.state_get(AV._NCAT_TABLE_KEY)["summary"]["leaves_unmapped"] == 1


# ── #915 그리기 워커 경합(같은 PR에서 발견) ───────────────────────────────────────────────────────

def test_render_worker_first_calls_never_start_two_workers(monkeypatch):
    """`_ensure`가 잠금 밖에서 start하면 그 사이 다른 호출이 워커를 하나 더 만들었다(고치기 전 150라운드 중 48라운드 동시 2장).
    라운드마다 새 큐·상태로 「첫 호출 8건 동시」를 만든다 — 워커는 시작할 때 받은 큐만 먹으니 앞 라운드 워커가 끼어들지 않는다."""
    import contextlib
    import queue
    import threading
    import time
    import types
    from src.utils import render_worker as RW
    from src.utils import rss as _rss
    from src.utils import rss_sampler as _smp
    # Y14-3(오너 2026-10-20): 전체 스위트에서 122초 — 장마다 도는 정리(gc.collect·malloc_trim·PSS 읽기·200ms 샘플러·DB 기록)가
    #   큰 힙에서 느렸다. 이 계약은 「워커가 하나뿐인가」만 본다 — 정리 단계는 가짜로 바꾸고 잠금·큐·스레드는 진짜로 둔다.
    monkeypatch.setattr(RW, "gc", types.SimpleNamespace(collect=lambda: 0))
    monkeypatch.setattr(RW, "trim", lambda: False)
    monkeypatch.setattr(RW, "record", lambda *a, **k: None)
    monkeypatch.setattr(_rss, "instance_mb", lambda: 0)
    monkeypatch.setattr(_smp, "watch", lambda *a, **k: contextlib.nullcontext({}))
    bad = 0
    for _ in range(20):
        monkeypatch.setattr(RW, "_Q", queue.Queue())
        monkeypatch.setattr(RW, "_STATE", {"thread": None, "busy": 0, "last_end": 0.0, "done": 0})
        live, peak, lk, go = [0], [0], threading.Lock(), threading.Event()

        def job():
            with lk:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(0.002)
            with lk:
                live[0] -= 1

        def caller():
            go.wait()
            RW.run(job, _name="race")
        ths = [threading.Thread(target=caller) for _ in range(8)]
        [t.start() for t in ths]
        go.set()
        [t.join(5) for t in ths]
        bad += peak[0] > 1
    assert bad == 0


def test_old_worker_does_not_clear_the_new_workers_slot(monkeypatch):
    """옛 워커가 60초 대기 끝에 나가면서 지금 워커 자리를 비우면 다음 호출이 워커를 하나 더 만든다 — 자기 자리일 때만 비운다."""
    import queue
    import threading
    from src.utils import render_worker as RW
    q_old, st = queue.Queue(), {"thread": "someone-else", "busy": 0, "last_end": 0.0, "done": 0}
    monkeypatch.setattr(RW.queue.Queue, "get", lambda self, timeout=None: (_ for _ in ()).throw(queue.Empty()))
    t = threading.Thread(target=RW._loop, args=(q_old, st))
    t.start()
    t.join(5)
    assert not t.is_alive() and st["thread"] == "someone-else"
