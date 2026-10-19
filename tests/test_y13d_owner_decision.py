"""Y13-D 2(오너 2026-10-18 BLACKHOLES 「권고안 채택」) — 대표 사진(0번 빼고 OCR 0상자 장) · 상표 「빼고 등록」(음차 상자만 원본 복원,
영문 Interstellar가 사진에 남으면 그 장은 뺀다) · 적용 뒤 사전검증. 운영 301c02cd 기록 모양(18:40 UTC) 그대로 줄여 심는다.

같은 유형(지목 안 함): 위험 검사가 **옵션(SKU) 사진**을 안 봤다 — 옵션 사진 0번(영화 포스터: INTERSTELLAR ×2 · A CHRISTOPHER
NOLAN FILM)이 다듬은 「인터스텔라」 글자를 얹고 쿠팡 옵션 대표로 나갈 뻔했다.
"""
from __future__ import annotations

import copy
import json

import pytest

from src.seller_console import collect_history_store as S

IMGS = ["https://img.alicdn.com/imgextra/i2/3596090318/O1CN01yqZT4K3oxSKAOX2W_!!3596090318.png",
        "https://img.alicdn.com/imgextra/i3/3596090318/O1CN01yaWvo3SdZoFCfVya~crop,1076,0,4160,4160~_!!3596090318.jpg",
        "https://img.alicdn.com/imgextra/i1/3596090318/O1CN01f9Vrp5CshwF8RgLQ_!!3596090318.jpg",
        "https://img.alicdn.com/imgextra/i3/3596090318/O1CN01mSzsbHs19FB8RgLQ_!!3596090318.jpg",
        "https://img.alicdn.com/imgextra/i2/3596090318/O1CN01sf6y0qmpYhB8RgLQ_!!3596090318.jpg"]
SKU_IMGS = ["https://gw.alicdn.com/bao/uploaded/i1/3596090318/O1CN01ivdH4hXr5QB5CGWG_!!3596090318.png",
            "https://gw.alicdn.com/bao/uploaded/i2/3596090318/O1CN01DacjHLsN9EL5CGWG_!!3596090318.jpg"]
G0 = "https://res.cloudinary.com/dzxkl9put/image/upload/v1792347624/proxy-commerce/seller/auto-20261018-182023_p0_TENCENT.jpg"
K0 = "https://res.cloudinary.com/dzxkl9put/image/upload/v1792348272/proxy-commerce/edit/yzuyih0c1fmjuxsj1hkw.jpg"
K1 = "https://res.cloudinary.com/dzxkl9put/image/upload/v1792348285/proxy-commerce/edit/atdszvarijj4m54xcy3n.jpg"


def _bh():
    g0_boxes = [{"h": 155, "w": 1057, "x": 44, "y": 70, "src": "BLACK HOLES", "tgt": "블랙홀"},
                {"h": 51, "w": 496, "x": 573, "y": 241, "src": "INTERSTELLAR", "tgt": "인터스텔라럴"},
                {"h": 187, "w": 517, "x": 54, "y": 285, "src": "THE KEY TO UNDERSTANDING THE UNIVERSE", "tgt": "우주를 이해하는 열쇠"},
                {"h": 112, "w": 1032, "x": 461, "y": 993, "src": "INTERSTELLAR", "tgt": "인터스텔라럴"},
                {"h": 155, "w": 400, "x": 1531, "y": 1815, "src": "BRIAN COX JEFF FORSHAW", "tgt": "브라이언 코크 제프 포시아우"}]
    k0_boxes = [{"h": 162, "w": 1098, "x": 60, "y": 76, "src": "BLACK HOLES", "tgt": "블랙 호일"},
                {"h": 117, "w": 1197, "x": 661, "y": 493, "src": "INTERSTELLAR", "tgt": "인터스텔러"},
                {"h": 53, "w": 1228, "x": 640, "y": 1960, "src": "A CHRISTOPHER NOLAN FILM", "tgt": "크리스토퍼 노란 영화"},
                {"h": 153, "w": 1621, "x": 444, "y": 2031, "src": "INTERSTELLAR", "tgt": "인터스텔라럴"}]
    k1_boxes = [{"h": 208, "w": 1418, "x": 96, "y": 113, "src": "BLACK HOLES", "tgt": "블랙홀"},
                {"h": 299, "w": 760, "x": 1748, "y": 2225, "src": "BRIAN COX JEFF FORSHAW", "tgt": "브라이언 코크 제프 포시아우"}]
    skipped = [{"idx": i, "kind": "gallery", "use": True, "status": "skipped", "vendor": "tencent-ocr", "ocr_text": "",
                "reason": "중국어 글자 없음(OCR 판정 — 한자 0) — 원본 그대로"} for i in (1, 2, 3, 4)]
    return {
        "title": "BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주",
        "title_ko": "BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주",
        "title_en": "【BLACKHOLES】黑洞小夜灯星际穿越电影周边摆件装饰模型手办宇宙",
        "images": list(IMGS), "detail_images": [],
        "options": [{"name": "颜色分类", "values": ["Yellow light", "White light"]}],
        "skus": [{"spec": ["【BLACKHOLES】", "Yellow light"], "image": SKU_IMGS[0], "price": "69.90", "sku_id": "6129730953948"},
                 {"spec": ["【BLACKHOLES】", "White light"], "image": SKU_IMGS[1], "price": "69.90", "sku_id": "6129730953949"}],
        "images_ko": [{"idx": 0, "kind": "gallery", "status": "done", "use": True, "url": G0, "translated_url": G0, "boxes_img": G0,
                       "box_size": [2000, 2000], "box_frame": "identity", "boxes": g0_boxes,
                       "source_text": " ".join(b["src"] for b in g0_boxes), "target_text": " ".join(b["tgt"] for b in g0_boxes)}] + skipped,
        "sku_images_ko": [
            {"idx": 0, "kind": "sku", "status": "done", "use": True, "url": K0, "translated_url": K0, "box_size": [2560, 2560],
             "box_frame": "identity", "boxes": k0_boxes, "source_text": " ".join(b["src"] for b in k0_boxes),
             "target_text": " ".join(b["tgt"] for b in k0_boxes)},
            {"idx": 1, "kind": "sku", "status": "done", "use": True, "url": K1, "translated_url": K1, "box_size": [2560, 2560],
             "box_frame": "identity", "boxes": k1_boxes, "source_text": " ".join(b["src"] for b in k1_boxes),
             "target_text": " ".join(b["tgt"] for b in k1_boxes)}],
    }


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    S._in_memory.clear()
    from src.services import image_edit as IE
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    monkeypatch.setattr(IE, "apply", lambda *a, **k: pytest.fail("원문에 상표가 남는 장을 그리러 갔다(렌더 0이어야)"))
    yield
    S._in_memory.clear()


def _hit(ex):
    from src.services import risk_gate as R
    return next(h for h in R.scan(ex)["hits"] if h["label"] == "인터스텔라")


def test_scan_now_sees_the_option_photo():
    """같은 유형: 옵션 사진 0번(포스터)도 위험 검사 대상 — 예전엔 갤러리 1장만 셌다."""
    h = _hit(_bh())
    where = {(i["kind"], int(i["idx"])) for i in h["images"]}
    assert ("gallery", 0) in where and ("sku", 0) in where and ("sku", 1) not in where
    assert "옵션 사진 1" in " · ".join(i["name"] for i in h["images"])


def test_restore_mode_drops_photos_whose_original_letters_are_the_mark():
    """영문 INTERSTELLAR가 원문 상자에 있다 → 음차 상자를 되살려도 상표가 남는다 → 사진째 뺀다(그리지 않는다)."""
    from src.services import risk_gate as R
    ex = _bh()
    res = R.decide(ex, _hit(ex)["key"], "strip", by="owner", pixels="restore")
    assert res["ok"]
    g0, k0, k1 = ex["images_ko"][0], ex["sku_images_ko"][0], ex["sku_images_ko"][1]
    assert "원문 글자에 상표가 그대로: 「INTERSTELLAR」" in g0["risk_exclude"] and "되살려도 남음" in g0["risk_exclude"]
    assert "사진째 뺌" in k0["risk_exclude"] and not k1.get("risk_exclude")
    assert not any(h["label"] == "인터스텔라" for h in R.scan(ex)["hits"])              # 보류가 풀린다
    assert R.strip_image_line(ex, res["hit"]).startswith("사진 2장: 사진째 뺌 2")


def test_dropped_photos_do_not_go_out_option_photo_falls_back_to_product_photos():
    from src.services import image_translate_store as its
    from src.services import risk_gate as R
    from src.seller_console.views import apply_sku_images
    ex = _bh()
    R.decide(ex, _hit(ex)["key"], "strip", by="owner", pixels="restore")
    eff = its.effective_images(ex, originals=ex["images"])
    assert G0 not in eff and IMGS[0] not in eff and eff == IMGS[1:]
    m = its.sku_image_map(ex)
    assert m[SKU_IMGS[0]] == "" and m[SKU_IMGS[1]] == K1                          # 포스터 옵션 사진 = 사진 없음 → 상품 사진
    skus = apply_sku_images(ex["skus"], m)
    assert skus[0]["image"] == "" and skus[1]["image"] == K1
    assert ex["skus"][0]["image"] == SKU_IMGS[0]                                  # 수집 원본 불변


def test_restore_mode_restores_transliteration_only_boxes():
    """원문이 상표가 아닌데 번역문에만 음차가 든 상자 → 그 상자만 원본 픽셀 복원(지우기 아님)."""
    from src.services import image_edit as IE
    from src.services import risk_gate as R
    calls = []
    IE_apply = lambda ex, kind, idx, ops, by="user", small=None: calls.append((kind, idx, ops, by)) or \
        {"ok": True, "version": "edit:1", "erased": [], "pending": False}
    ex = _bh()
    ex["images_ko"][0]["boxes"] = [{"h": 50, "w": 400, "x": 10, "y": 10, "src": "星际", "tgt": "인터스텔라"},
                                   {"h": 50, "w": 400, "x": 10, "y": 90, "src": "黑洞", "tgt": "블랙홀"}]
    ex["images_ko"][0]["source_text"], ex["images_ko"][0]["target_text"] = "星际 黑洞", "인터스텔라 블랙홀"
    ex["sku_images_ko"] = []
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(IE, "apply", IE_apply)
    try:
        R.decide(ex, _hit(ex)["key"], "strip", by="owner", pixels="restore")
    finally:
        mp.undo()
    assert calls == [("gallery", 0, [{"id": "t0", "action": "restore"}], "risk")]
    e = ex["images_ko"][0]
    assert not e.get("risk_exclude") and e["risk_erase"]["how"] == "restore" and e["risk_erase"]["erased"] == ["인터스텔라"]


def test_default_button_now_restores_like_the_owner_decision(monkeypatch):
    """Y13-F(Y13-E 이월 1, 오너 2026-10-19): 화면 「빼고 등록」 기본값도 복원(음차 상자 원본 픽셀 · 상표가 남으면 그 장 뺌).
    예전 기본(Y11-J6 상자 지우기)은 `pixels="erase"`로만."""
    from src.services import risk_gate as R
    erased, restored = [], []
    monkeypatch.setattr(R, "_erase_hit", lambda ex, kind, idx, names, case: erased.append((kind, idx)) or {"ok": False, "why": "x"})
    monkeypatch.setattr(R, "_restore_or_exclude", lambda ex, kind, e, names, case, label: restored.append((kind, int(e["idx"]))))
    ex = _bh()
    R.decide(ex, _hit(ex)["key"], "strip", by="owner")
    assert erased == [] and ("gallery", 0) in restored and ("sku", 0) in restored
    ex = _bh()
    R.decide(ex, _hit(ex)["key"], "strip", by="owner", pixels="erase")
    assert ("gallery", 0) in erased


def test_pick_rep_rule():
    from src.services.oneshot_ops import pick_rep
    assert pick_rep({1: 0, 2: 0, 3: 0, 4: 0}, prefer=1) == 1                        # 넷 다 0상자 — 지정 장
    assert pick_rep({1: 2, 2: 0, 3: 0, 4: 1}, prefer=1) == 2                        # 지정 장에 글자 — 0상자 첫 장
    assert pick_rep({1: 3, 2: None, 3: 1, 4: 2}, prefer=1) == -1                    # 0상자 없음 — 대표를 안 바꾼다


def test_owner_decision_op_applies_both_and_starts_precheck(monkeypatch):
    from src.services import oneshot_ops as OO
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=1", seller_id="u-bh", title="블랙홀 벽등",
                   price="69.9", currency="CNY", extra=_bh())
    asked = []

    def ocr(url):
        asked.append(url)
        return 0, ""
    monkeypatch.setattr(OO, "_ocr_box_count", ocr)
    monkeypatch.setattr(OO, "_prevalidate", lambda item_id, markets: {"ok": True, "job_id": "j1", "markets": markets})
    out = OO._run({"op": "owner_decision", "item_id": iid, "rep": {"candidates": [1, 2, 3, 4], "prefer": 1},
                   "strip": ["인터스텔라"], "pixels": "restore"})
    assert out["ok"] and out["saved"] and out["prevalidate"]["job_id"] == "j1"
    assert asked == IMGS[1:] and out["rep"]["picked"] == 1 and out["rep"]["counts"] == {"1": 0, "2": 0, "3": 0, "4": 0}
    assert out["strip"][0]["ok"] and out["strip"][0]["images"].startswith("사진 2장: 사진째 뺌 2")
    ex = json.loads(S.get(iid, seller_ids={"u-bh"})["extra_json"])
    assert ex["rep_image"] == IMGS[1] and ex["images"] == IMGS                       # 원본 배열 불변 · 대표만
    assert ex["risk_decisions"]["tm:인터스텔라"]["action"] == "strip"
    from src.services import image_translate_store as its
    assert its.effective_images(ex, originals=ex["images"])[0] == IMGS[1]


def _polished_sku0(ex):
    """운영 10-19 01:20 그대로: 옵션 사진 0번의 지금 버전 = 다듬은 편집본(edit:1). 덮은 상자 목록(erased)에 INTERSTELLAR·인터스텔러가
    있고, 그 자리에 다듬기가 「인터스텔라」를 다시 그렸다(ops text) — 예전 검사는 erased만 빼고 그린 글자는 안 봐서 놓쳤다."""
    k0 = ex["sku_images_ko"][0]
    ed = {"n": 1, "by": "polish", "url": "https://res.cloudinary.com/x/edit/k0e1.jpg", "base_key": "translated",
          "ops": [{"id": "t1", "text": "인터스텔라", "action": "text"}, {"id": "t2", "text": "크리스토퍼 놀란 영화", "action": "text"},
                  {"id": "t3", "text": "인터스텔라", "action": "text"}],
          "erased": ["INTERSTELLAR", "인터스텔러", "A CHRISTOPHER NOLAN FILM", "크리스토퍼 노란 영화", "INTERSTELLAR", "인터스텔라럴"]}
    k0.update(edit=ed, edits=[ed], url=ed["url"], current="edit:1",
              vboxes={"edit:1": {"img": ed["url"], "size": [2560, 2560], "source": "polish",
                                 "boxes": [dict(b, tgt=("인터스텔라" if b["src"] == "INTERSTELLAR" else b["tgt"])) for b in k0["boxes"]]}})
    return ex


def test_polished_option_photo_with_redrawn_mark_is_caught_and_dropped():
    from src.services import risk_gate as R
    from src.services.detail_image_plan import entry_text
    ex = _polished_sku0(_bh())
    assert "인터스텔라" in entry_text(ex["sku_images_ko"][0])                       # 그려 넣은 글자도 사진 글자
    h = _hit(ex)
    assert ("sku", 0) in {(i["kind"], int(i["idx"])) for i in h["images"]}
    R.decide(ex, h["key"], "strip", by="owner", pixels="restore")
    assert "원문 글자에 상표가 그대로" in ex["sku_images_ko"][0]["risk_exclude"]
    assert not any(x["label"] == "인터스텔라" for x in R.scan(ex)["hits"])


def test_owner_decision_rerun_after_earlier_strip_catches_the_option_photo(monkeypatch):
    """운영처럼 앞 실행이 갤러리 0번만 뺐고 결정(strip)이 이미 있다 — 다시 돌리면 옵션 사진도 뺀다(대표는 건드리지 않음)."""
    from src.services import oneshot_ops as OO
    from src.services import risk_gate as R
    ex = _polished_sku0(_bh())
    ex["rep_image"] = IMGS[2]
    h0 = _hit(ex)
    R.strip_extra(ex, dict(h0, images=[i for i in h0["images"] if i["kind"] == "gallery"]), pixels="restore")
    ex["risk_decisions"] = {h0["key"]: {"action": "strip", "label": h0["label"], "names": h0["names"], "cat": h0["cat"]}}
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=1", seller_id="u-bh", title="블랙홀 벽등",
                   price="69.9", currency="CNY", extra=ex)
    monkeypatch.setattr(OO, "_prevalidate", lambda item_id, markets: {"ok": True, "job_id": "j2", "markets": markets})
    out = OO._run({"op": "owner_decision", "item_id": iid, "strip": ["인터스텔라"], "pixels": "restore"})
    assert out["ok"] and "rep" not in out and out["strip"][0]["ok"]
    got = json.loads(S.get(iid, seller_ids={"u-bh"})["extra_json"])
    assert got["rep_image"] == IMGS[2] and got["sku_images_ko"][0]["risk_exclude"] and got["images_ko"][0]["risk_exclude"]
