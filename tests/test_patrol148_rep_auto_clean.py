"""순찰 148 H-rep — 쿠팡 대표 후보가 전부 글자 장일 때 최소 상자 장의 글자를 지워 다시 재고, 0상자면 그 장을 쿠팡 대표로.

계약: 0상자 장 있으면 안 돎(pick_rep 우선) · 지우기 뒤 0상자 → 대표 바뀜 · 0 아님 → 보류 유지 + 「자동 정리 시도: N상자 → M상자」 ·
수집 원본 images 불변 · 나가는 버전(번역본)은 그대로 — 정리본은 쿠팡 대표 자리에만 · 하루 상한 · 상품마다 한 번.
"""
import json

import pytest

ORIG = [f"https://img.example/o{i}.jpg" for i in range(5)]
CLEAN = "https://res.cloudinary.com/x/image/upload/proxy-commerce/edit/clean3.png"


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    monkeypatch.delenv("REP_AUTO_CLEAN_DAILY_CAP", raising=False)
    yield


def _extra():
    # 3번 장(idx 3)은 번역본이 나가는 중 — 정리 뒤에도 그대로여야 한다
    return {"images": list(ORIG), "rep_need_change": "후보 4장 모두 글자가 있어요(상자 1번 9개, 2번 9개, 4번 4개, 5번 9개)",
            "images_ko": [{"idx": 3, "kind": "gallery", "status": "done", "use": True, "url": "https://cdn/t3.jpg",
                           "translated_url": "https://cdn/t3.jpg"}]}


@pytest.fixture
def fake_edit(monkeypatch):
    # External render/upload boundary double; selection/storage logic stays real.
    from src.services import image_edit as IE
    from src.services import rep_clean_edit as E
    calls = {"apply": []}

    def prepare(extra, idx):
        return {"ok": True, "identity": E.identity(extra, idx), "idx": idx}

    def render(prepared):
        return {"ok": True, "boxes_after": 0, "method": "edge_crop"}

    def publish(extra, idx, prepared, result):
        calls["apply"].append(("gallery", idx))
        e = IE._entry(extra, "gallery", idx, create=True)
        n = len(IE.edits(e)) + 1
        e["edits"] = IE.edits(e) + [{"n": n, "url": CLEAN, "ready": True, "by": "rep_auto"}]
        e.setdefault("vboxes", {})[f"edit:{n}"] = {"img": CLEAN, "boxes": [], "size": [750, 750]}
        return {"ok": True, "url": CLEAN, "version": f"edit:{n}"}
    monkeypatch.setattr(E, "prepare", prepare)
    monkeypatch.setattr(E, "render", render)
    monkeypatch.setattr(E, "publish", publish)
    return calls


def test_pick_min_rules():
    from src.services import rep_auto_clean as R
    assert R.pick_min({0: 9, 1: 9, 3: 4, 4: 9}) == 3
    assert R.pick_min({0: 5, 2: 4, 3: 4}) == 2                                  # 동률 = 앞 번호
    assert R.pick_min({0: 3, 1: 0}) == -1                                        # 0상자 장이 있으면 안 돎(pick_rep 우선)
    assert R.pick_min({0: None, 1: None}) == -1
    assert R.pick_min({0: None, 1: 7}) == 1


def test_clean_success_sets_coupang_rep_and_keeps_outbound_version(fake_edit):
    from src.services import image_edit as IE
    from src.services import rep_auto_clean as R
    ex = _extra()
    out = R.clean(ex, {0: 9, 1: 9, 3: 4, 4: 9}, by="auto", ocr=lambda u: (0, "") if u == CLEAN else (9, ""))
    assert out["ok"] and out["idx"] == 3 and out["boxes_before"] == 4 and out["boxes_after"] == 0
    assert fake_edit["apply"] == [("gallery", 3)]
    assert ex["rep_image"] == ORIG[3] and "rep_need_change" not in ex
    assert ex["images"] == ORIG                                                   # 수집 원본 불변
    e = IE._entry(ex, "gallery", 3)
    assert IE.current_key(e) == "translated" and e["url"] == "https://cdn/t3.jpg"  # 나가는 버전 = 번역본 그대로
    rc = ex["rep_auto_clean"]
    assert rc["ok"] and rc["url"] == CLEAN and rc["orig"] == ORIG[3] and rc["version"] == "edit:1" and rc["boxes_before"] == 4
    assert R.valid(ex) == rc


def test_clean_not_zero_keeps_hold_with_reason(fake_edit):
    from src.services import rep_auto_clean as R
    ex = _extra()
    out = R.clean(ex, {0: 9, 1: 9, 3: 4, 4: 9}, ocr=lambda u: (2, ""))
    assert not out["ok"] and out["boxes_after"] == 2
    assert "글자가 남아 있어요" in ex["rep_need_change"] and ex["rep_need_change"].startswith("후보 4장")
    assert [i for _, i in fake_edit["apply"]] == [3, 0, 1, 4]
    assert "rep_image" not in ex and R.valid(ex) is None
    assert all(not e.get("edits") for e in ex["images_ko"])
    # 같은 장은 다시 하지 않는다(한 번만) — 사유도 두 번 붙지 않는다
    again = R.clean(ex, {0: 9, 1: 9, 3: 4, 4: 9}, ocr=lambda u: pytest.fail("다시 재면 안 된다"))
    assert "이미 시도" in again["why"] and ex["rep_need_change"].count("자동 정리 시도") == 1


def test_clean_skips_when_a_zero_box_candidate_exists(fake_edit):
    from src.services import rep_auto_clean as R
    ex = _extra()
    out = R.clean(ex, {0: 9, 2: 0}, ocr=lambda u: pytest.fail("안 돈다"))
    assert not out["tried"] and fake_edit["apply"] == [] and "rep_auto_clean" not in ex


def test_daily_cap(fake_edit, monkeypatch):
    from src.services import rep_auto_clean as R
    monkeypatch.setenv("REP_AUTO_CLEAN_DAILY_CAP", "1")
    assert R.clean(_extra(), {0: 9, 3: 4}, ocr=lambda u: (0, ""))["ok"]
    out = R.clean(_extra(), {0: 9, 3: 4}, ocr=lambda u: (0, ""))
    assert not out["tried"] and "한도(1회)" in out["why"]


def test_valid_only_while_rep_and_version_hold(fake_edit):
    from src.services import rep_auto_clean as R
    ex = _extra()
    R.clean(ex, {0: 9, 3: 4}, ocr=lambda u: (0, ""))
    assert R.valid(ex)
    ex2 = json.loads(json.dumps(ex))
    ex2["rep_image"] = ORIG[1]                                                    # 사람이 다른 장을 대표로 → 정리본 안 씀
    assert R.valid(ex2) is None
    ex3 = json.loads(json.dumps(ex))
    ex3["images_ko"][0]["edits"] = []                                             # 편집 버전을 지웠다(되돌리기) → 안 씀
    assert R.valid(ex3) is None


def test_only_coupang_payload_gets_the_cleaned_rep():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.services import coupang_image_check as C
    rc = {"ok": True, "url": CLEAN, "orig": ORIG[3], "idx": 3, "version": "edit:1"}
    pd = {"title": "x", "images": ["https://cdn/t3.jpg", ORIG[0]], "images_effective": ["https://cdn/t3.jpg", ORIG[0]],
          "rep_auto_clean": rc, "rep_auto_clean_valid": True}
    cp, _ = UploadDispatcher._payload_for_market_core(pd, "coupang")
    assert cp["images"] == [CLEAN, ORIG[0]] and cp["thumbnail"] == CLEAN
    for m in ("smartstore", "elevenst", "woocommerce"):
        assert UploadDispatcher._payload_for_market_core(pd, m)[0]["images"][0] == "https://cdn/t3.jpg"
    assert C._coupang_imgs(pd)[0] == CLEAN                                        # 사전검증 대표 판정도 같은 장
    assert C._coupang_imgs(dict(pd, rep_auto_clean_valid=False))[0] == "https://cdn/t3.jpg"


def test_rep_clean_op_saves_and_prevalidates(fake_edit, monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    from src.seller_console import collect_history_store as store
    item = {"id": "i-1", "extra_json": json.dumps(_extra(), ensure_ascii=False)}
    monkeypatch.setattr(D, "_item", lambda iid: (item, "u-1"))
    saved = {}
    monkeypatch.setattr(store, "update", lambda iid, seller_ids=None, extra_json="": saved.update(iid=iid, ex=json.loads(extra_json)) or True)
    pv = []
    boxes = {ORIG[0]: 9, ORIG[1]: 9, ORIG[2]: 5, ORIG[3]: 4, ORIG[4]: 9, CLEAN: 0}
    out = O.rep_clean("i-1", ocr=lambda u: (boxes[u], ""), prevalidate=lambda iid, mk: pv.append(iid) or {"ok": True})
    assert out["ok"] and out["how"] == "대표 사진 정리" and out["picked"] == 3 and pv == ["i-1"]
    assert saved["ex"]["rep_image"] == ORIG[3] and "rep_need_change" not in saved["ex"]
    # 0상자 장이 생겼으면(재수집 등) 지우지 않고 그 장
    boxes[ORIG[2]] = 0
    item["extra_json"] = json.dumps(_extra(), ensure_ascii=False)
    out = O.rep_clean("i-1", ocr=lambda u: (boxes[u], ""), prevalidate=lambda iid, mk: {"ok": True})
    assert out["how"] == "0상자 장" and out["picked"] == 2 and saved["ex"]["rep_image"] == ORIG[2]


def test_rep_clean_is_a_known_heavy_op():
    from src.services import oneshot_ops as O
    assert "rep_clean" in O.OPS and "rep_clean" in O.HEAVY_OPS and "rep_clean" not in O.REQUEUE_SAFE_OPS


def test_prevalidate_enqueues_rep_clean():
    """사전검증 준비가 「대표 사진 바꾸기 필요」를 보면 `rep_clean` 일회성 줄을 넣는다(구조 — AST)."""
    from src.seller_console import views as V
    from tests._ast_probe import calls_in, string_constants_in
    assert "enqueue" in {c.split(".")[-1] for c in calls_in(V._pv_prepare)}
    assert {"rep_clean", "rep_need_change", "rep_auto_clean"} <= string_constants_in(V._pv_prepare)
