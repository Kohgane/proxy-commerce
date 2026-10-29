"""V42-3(오너 2026-10-28 「저 과정이 너무 오래 걸려」) — 사진 글자 읽기 워커 2줄 병렬 + 장별 저장은 merge_extra(같은 상품의 다른 장이 나란히 돌아도 앞 장을 안 지운다)."""
from __future__ import annotations

import json
import threading
import time

import pytest


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    monkeypatch.delenv("IMGKO_PARALLEL", raising=False)
    monkeypatch.delenv("WORKERS_ENABLED", raising=False)


def _item(seller="v423"):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "t", "images": ["https://img.test/a.jpg", "https://img.test/b.jpg", "https://img.test/c.jpg"], "detail_images": []}
    return S.append(source="share_text", url="https://item.taobao.com/item.htm?id=423", seller_id=seller, title="t", price="1", currency="CNY", extra=ex)


def test_parallel_lanes_env(monkeypatch):
    from src.services import image_translate_auto as A
    assert A.parallel_lanes() == 2
    monkeypatch.setenv("IMGKO_PARALLEL", "9"); assert A.parallel_lanes() == 4
    monkeypatch.setenv("IMGKO_PARALLEL", "0"); assert A.parallel_lanes() == 1
    monkeypatch.setenv("IMGKO_PARALLEL", "x"); assert A.parallel_lanes() == 2


def test_two_pages_of_one_item_translated_concurrently_both_persist(monkeypatch):
    """핵심 회귀: 예전 전체-덮어쓰기면 둘 중 하나가 사라졌다. 번역을 느리게(겹치게) 흉내 낸다."""
    from src.services import image_translate_auto as A
    from src.db import image_translate_queue_pg as q
    from src.seller_console import collect_history_store as S
    iid = _item()
    gate = threading.Barrier(2, timeout=5)

    def fake_translate(url, *, idx, kind, item_id, seller_id, title, prop_exempt):
        gate.wait()                                                      # 두 줄이 같은 시각에 「저장 직전」에 선다
        time.sleep(0.05)
        return {"idx": idx, "kind": kind, "status": "done", "url": url.replace(".jpg", "-ko.jpg"), "at": "2026-10-29T00:00:00Z"}
    monkeypatch.setattr(A, "translate_page", fake_translate)
    monkeypatch.setattr(A, "parallel_lanes", lambda: 2)
    monkeypatch.setattr(A, "daily_cap", lambda: 1000)
    monkeypatch.setattr("src.utils.rss.start_ok", lambda: (True, -1, 0))
    q.enqueue("v423", iid, [("gallery", 0), ("gallery", 1)])
    n = A.run_until_idle()                                               # 2줄
    assert n == 2
    ex = json.loads(S.get(iid, seller_ids={"v423"})["extra_json"])
    got = sorted(int(e["idx"]) for e in ex.get("images_ko") or [])
    assert got == [0, 1], ex.get("images_ko")                           # 둘 다 남았다(전체 덮어쓰기면 하나만)
    assert q.counts(iid)["done"] == 2 and q.counts(iid)["queued"] == 0


def test_protected_entry_not_overwritten(monkeypatch):
    from src.services import image_translate_auto as A
    from src.db import image_translate_queue_pg as q
    from src.seller_console import collect_history_store as S
    from src.services import image_translate_store as istore
    iid = _item(seller="v423b")
    S.update(iid, seller_ids={"v423b"}, extra_json=json.dumps({"title_ko": "t", "images": ["https://img.test/a.jpg"],
             "images_ko": [{"idx": 0, "kind": "gallery", "status": "done", "boxes": [{"x": 1}], "url": "https://img.test/a-edit.jpg"}]}))
    monkeypatch.setattr(A, "translate_page", lambda *a, **k: {"idx": 0, "kind": "gallery", "status": "done", "url": "x"})
    monkeypatch.setattr(A, "daily_cap", lambda: 1000)
    monkeypatch.setattr("src.utils.rss.start_ok", lambda: (True, -1, 0))
    q.enqueue("v423b", iid, [("gallery", 0)])
    A.run_until_idle()
    ex = json.loads(S.get(iid, seller_ids={"v423b"})["extra_json"])
    assert ex["images_ko"][0]["url"] == "https://img.test/a-edit.jpg"      # 상자 있는 편집본은 그대로
    assert istore.has_boxes(ex["images_ko"][0])


def test_single_lane_path_unchanged(monkeypatch):
    from src.services import image_translate_auto as A
    from src.db import image_translate_queue_pg as q
    monkeypatch.setenv("IMGKO_PARALLEL", "1")
    calls = []
    monkeypatch.setattr(A, "_drain", lambda max_pages=10_000: calls.append(threading.current_thread().name) or 0)
    A.run_until_idle()
    assert calls and "imgko-auto-" not in calls[0]                      # 1줄이면 현재 스레드에서 그대로
