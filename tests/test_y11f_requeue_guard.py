"""Y11-F(오너 2026-10-14) — 「done + 글자 상자 있음」인 장은 어떤 경로로도 다시 보내지(덮지) 않는다.

실측 18:20 KST(09:20 UTC) VRSUK 4ebaf1b8 갤러리 3 — 운영 큐 행·`workers:runs` 값 그대로 재현:
  17:26:02 「다시 번역」(`retry_item`) → 갤러리 1·2·3(그때 OCR 「한자 0」으로 건너뛴 장, 상자 없음)을 줄에 넣음 · 일일 상한이라 대기
  17:26:48 · 17:28:42 편집기 「번역하고 글자 상자 받기」(직접 작업 경로)가 갤러리 1·3을 따로 번역 → done + 상자
  18:20 #900 배포 뒤 크론이 큐를 깨움 → 낡은 줄을 꺼내 **지금 상태를 다시 보지 않고** OCR 사전검사(「한자 0」) → 장을 통째 덮음
반례(오너): 「done이면 무조건 금지」로 막으면 「다시 번역」의 「상자 없는 옛 번역본 재전송」이 같이 죽는다 — 조건은 done AND 상자 있음.
"""
from __future__ import annotations

import json

import pytest

IMGS = [f"https://img.alicdn.com/imgextra/g{i}.jpg" for i in range(5)]
BOXES = [{"x": 1143, "y": 1676, "w": 145, "h": 28, "src": "Zaha Hadid", "tgt": "자하 하디드"}]
OCR_SKIP = {"status": "skipped", "vendor": "tencent-ocr", "use": True,
            "reason": "중국어 글자 없음(OCR 판정 — 한자 0) — 원본 그대로 · 읽은 글자 「OUY TAHT」"}


def _extra():
    return {"title": "VRSUK", "images": list(IMGS), "images_ko": [
        {"idx": 0, "kind": "gallery", "status": "done", "use": True, "vendor": "tencent",
         "url": "https://res.cloudinary.com/x/p0_TENCENT.jpg"},                       # 9/30 번역본 — 상자 없음(옛)
        dict(OCR_SKIP, idx=1, kind="gallery"), dict(OCR_SKIP, idx=2, kind="gallery"), dict(OCR_SKIP, idx=3, kind="gallery"),
        {"idx": 4, "kind": "gallery", "status": "skipped", "vendor": "tencent", "reason": "글자 없는 사진 — 원본 그대로"}]}


@pytest.fixture
def mem(monkeypatch):
    from src.db import image_translate_queue_pg as q
    from src.services import image_translate_auto as A
    q.reset_for_tests()
    monkeypatch.setattr(A, "kick", lambda: None)
    yield q
    q.reset_for_tests()


def _store(seller, ex):
    from src.seller_console import collect_history_store as S
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=748639898871", seller_id=seller,
                   title="VRSUK", price="7183", currency="CNY", extra=ex)
    return iid[0] if isinstance(iid, tuple) else iid


def _load(iid, seller):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_ids={seller})["extra_json"])


def _save(iid, seller, ex):
    from src.seller_console import collect_history_store as S
    assert S.update(iid, seller_ids={seller}, extra_json=json.dumps(ex, ensure_ascii=False))


def _editor_translated(iid, seller, idx):
    """편집기 「번역하고 글자 상자 받기」(직접 작업 경로)가 그 장을 번역해 상자를 얻은 결과 — 운영 17:28:42 갤러리 3 모양."""
    ex = _load(iid, seller)
    ex["images_ko"] = [e for e in ex["images_ko"] if e["idx"] != idx] + [
        {"idx": idx, "kind": "gallery", "status": "done", "use": True, "vendor": "tencent",
         "url": f"https://res.cloudinary.com/x/sel-20261014-082841_p{idx}_TENCENT.jpg",
         "boxes": list(BOXES), "box_size": [1440, 1920], "box_frame": "rot180"}]
    _save(iid, seller, ex)


def _drain_with(monkeypatch, sent, on_send=None):
    """줄을 비운다 — 공급사 대신 OCR 「한자 0」 결과를 돌려주는 가짜(운영 18:20의 결과 그대로)."""
    from src.services import image_translate_auto as A
    monkeypatch.setattr(A, "daily_cap", lambda: 320)

    def fake(url, *, idx, kind, item_id, seller_id, title="", **_kw):
        sent.append((kind, idx))
        if on_send:
            on_send(kind, idx)
        return dict(OCR_SKIP, idx=idx, kind=kind, ms=0)
    monkeypatch.setattr(A, "translate_page", fake)
    return A._drain(50)


def test_1820_stale_queue_row_does_not_overwrite_photo_translated_meanwhile(mem, monkeypatch):
    from src.services import image_translate_auto as A
    from src.services import image_translate_store as S
    seller = "y11f"
    iid = _store(seller, _extra())
    r = A.retry_item(seller, iid, "https://item.taobao.com/item.htm?id=748639898871", _load(iid, seller), may_resume=False)
    assert {(p["kind"], p["idx"]) for p in r["pages"]} == {("gallery", 0), ("gallery", 1), ("gallery", 2), ("gallery", 3)}
    _editor_translated(iid, seller, 1)                      # 17:26:48
    _editor_translated(iid, seller, 3)                      # 17:28:42
    sent = []
    _drain_with(monkeypatch, sent)                          # 18:20 배포 뒤 크론이 큐를 깨움
    assert sorted(sent) == [("gallery", 0), ("gallery", 2)]  # 상자 있는 1·3은 보내지 않는다(OCR 사전검사도 안 함)
    ex = _load(iid, seller)
    by = {e["idx"]: e for e in ex["images_ko"]}
    for i in (1, 3):
        assert by[i]["status"] == "done" and by[i]["boxes"] == BOXES and by[i]["url"].endswith(f"p{i}_TENCENT.jpg")
    rows = {(r["kind"], int(r["idx"])): r for r in mem._MEM_Q if r["item_id"] == iid}
    assert rows[("gallery", 3)]["status"] == "skipped" and rows[("gallery", 3)]["reason"] == S.PROTECTED_REASON


def test_photo_that_gets_boxes_while_being_translated_is_not_overwritten(mem, monkeypatch):
    """꺼낼 땐 상자가 없었는데 번역하는 몇 초 사이 다른 길이 상자를 얻었다 — 쓰기 직전에 다시 보고 덮지 않는다."""
    from src.services import image_translate_auto as A
    seller = "y11f-race"
    iid = _store(seller, _extra())
    A.retry_item(seller, iid, "https://item.taobao.com/item.htm?id=1", _load(iid, seller), may_resume=False)
    sent = []
    _drain_with(monkeypatch, sent, on_send=lambda k, i: i == 2 and _editor_translated(iid, seller, 2))
    assert ("gallery", 2) in sent
    e2 = next(e for e in _load(iid, seller)["images_ko"] if e["idx"] == 2)
    assert e2["status"] == "done" and e2["boxes"] == BOXES


def test_counterexample_done_without_boxes_is_still_resent_by_retry(mem):
    """반례: 상자 없는 옛 번역본(대표사진 9/30)은 「다시 번역」이 다시 보낸다 · 빈 상자 목록도 「없음」이다."""
    from src.services import image_translate_auto as A
    ex = _extra()
    plan = A.translate_plan(ex, retry=True)
    assert ("gallery", 0, "no_boxes") in plan["send"]
    ex["images_ko"][0].update(boxes=[], box_size=[800, 800])          # 상자 목록은 있는데 비었다(예전엔 「상자 있음」으로 건너뜀)
    assert ("gallery", 0, "no_boxes") in A.translate_plan(ex, retry=True)["send"]
    ex["images_ko"][0].update(boxes=list(BOXES))
    plan = A.translate_plan(ex, retry=True)
    assert ("gallery", 0) in plan["skip"]["done"] and all(i != 0 for _k, i, _w in plan["send"])


def test_direct_job_path_refuses_protected_photo(monkeypatch):
    """편집기 「번역하고 글자 상자 받기」·갤러리 「번역」(직접 작업)도 같은 판정 — 상자 있는 장은 접수하지 않는다(과금 0)."""
    from src.services import image_translate_job as job
    from src.services import image_translate_store as S
    from src.services import image_translate_tencent as tc
    seller = "y11f-job"
    ex = _extra()
    ex["images_ko"][3].update(status="done", boxes=list(BOXES), box_size=[1440, 1920], url="https://res.cloudinary.com/x/p3.jpg")
    iid = _store(seller, ex)
    monkeypatch.setattr(tc, "_cap_full", lambda: None)
    started = []
    monkeypatch.setattr(job, "_start", lambda *a: started.append(a))
    r = job.accept(iid, seller, [3], seller_ids={seller})
    assert not r["ok"] and r["protected"] and S.PROTECTED_REASON in r["error"] and started == []
    r = job.accept(iid, seller, [1, 3], seller_ids={seller})
    assert r["ok"] and r["queued"] == [1] and r["skipped"] == [{"idx": 3, "reason": S.PROTECTED_REASON}]
    e3 = next(e for e in _load(iid, seller)["images_ko"] if e["idx"] == 3)
    assert e3["status"] == "done" and e3["boxes"] == BOXES                       # 「queued」 자리표시로도 덮지 않는다
