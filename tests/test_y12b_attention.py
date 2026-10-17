"""Y12-B(오너 2026-10-17) — 대기함 결정 Y12A-3·Y12A-4 계약.

기준(오너): **오너가 눌러야 풀리는 것만 「손댈 것」.**
- Y12A-3 수집 실패: 자동 재수집이 예정된 건(PC 고가수집기 보강 큐 · 온바운드 하루 한도 이월)은 「돌아가는 것 · 재수집 대기」,
  재수집 소진(보강 시도 상한 · 막힘)과 자동 재수집이 없는 실패(보강 축 없는 완전 수집의 가격·갤러리 미확보)만 손댈 것.
  보강 축만 있고 실패 기록이 없는 부분 초안(「보강 대기」)은 실패가 아니다.
- Y12A-4 지우기 제안: 사진별 「넘김」 + 상품별 「전부 넘김」. 지움이든 넘김이든 처리되면 손댈 것에서 빠진다.
  넘긴 제안은 드로어 「넘긴 제안 n」으로 접혀 다시 볼 수 있다. 넘김은 기록만 — 원본·번역본·편집본 픽셀 0.
  반례: 2호·3호가 들어오면 상품마다 제안이 나오니 넘김이 없으면 손댈 것이 영원히 0이 안 된다.
"""
from __future__ import annotations

import copy
import json

import pytest

from src.seller_console import attention as A
from src.seller_console import collect_history_store as S


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    S._in_memory.clear()
    yield
    S._in_memory.clear()


def _client(uid):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=f"{uid}@example.com", user_role="seller")
    return c


def _add(uid, extra, title="수집 상품", price="10", url="https://item.taobao.com/item.htm?id=1"):
    return S.append(source="share", url=url, seller_id=uid, title=title, price=price, currency="CNY", extra=extra)


# ── Y12A-3 수집 실패 ───────────────────────────────────────────────────────────────────────────────────
WAIT_PC = {"mode": "share", "enrich_state": "pending", "gate_ready": True, "price": "10",
           "auto_enrich": {"state": "manual", "kind": "provider_fail", "reason": "공급자 응답 없음"}}
WAIT_CARRY = {"mode": "share", "enrich_state": "pending", "gate_ready": False,
              "auto_enrich": {"state": "manual", "kind": "provider_quota"}}
EXHAUSTED = {"mode": "share", "enrich_state": "blocked", "enrich_attempts": 3, "enrich_blocked_reason": "로그인 벽"}
DRAFT_OK = {"mode": "share", "enrich_state": "pending", "gate_ready": True, "price": "10"}      # 실패 기록 없음 = 보강 대기


def test_waiting_refetch_is_running_not_attention():
    cf = A.collect_fail(WAIT_PC)
    assert cf["phase"] == "waiting" and cf["text"] == "재수집 대기" and "PC 고가수집기" in cf["why"]
    assert A.items(WAIT_PC, fresh=True) == []                    # 오너가 누를 일이 없다 → 손댈 것 아님
    assert A.summarize(WAIT_PC)["refetch"].startswith("재수집 대기")
    carry = A.collect_fail(WAIT_CARRY)
    assert carry["phase"] == "waiting" and "하루 한도" in carry["why"]


def test_exhausted_and_no_auto_refetch_are_attention():
    cf = A.collect_fail(EXHAUSTED)
    assert cf["phase"] == "exhausted" and "로그인 벽" in cf["text"] and "3회" in cf["why"]
    its = A.items(EXHAUSTED, fresh=True)
    assert [i["kind"] for i in its] == ["collect_fail"] and "원본에서 다시 수집" in its[0]["text"]
    # 시도 상한에 닿았는데 상태가 아직 pending으로 남은 옛 행도 소진이다(큐 `/enrich/pending`이 안 집는다)
    assert A.collect_fail(dict(DRAFT_OK, enrich_attempts=3))["phase"] == "exhausted"
    # 보강 축 없는 완전 수집에서 가격·갤러리 둘 다 못 읽음 — 자동 재수집이 없다
    bare = A.collect_fail({"title": "x"}, "x")
    assert bare["phase"] == "exhausted" and "자동 재수집이 없어요" in bare["why"]


def test_not_failures():
    assert A.collect_fail(DRAFT_OK) is None                       # 보강 대기(실패 아님)
    assert A.collect_fail({"mode": "share", "enrich_state": "done", "images": ["a"], "price": "1"}) is None
    assert A.collect_fail({"price": "10", "images": ["a"]}) is None   # 부분 수집은 실패가 아니다
    assert A.items(DRAFT_OK, fresh=True) == []


def test_store_stamp_counts_exhausted_only_and_running_counts_refetch():
    uid = "u-y12b-store"
    ex_id = _add(uid, dict(EXHAUSTED), url="https://item.taobao.com/item.htm?id=11")
    wt_id = _add(uid, dict(WAIT_PC), url="https://item.taobao.com/item.htm?id=12")
    _add(uid, dict(DRAFT_OK), url="https://item.taobao.com/item.htm?id=13")
    attn = [r["id"] for r in S.list_items(days=3650, seller_ids={uid}, attn_only=True)]
    assert attn == [ex_id]
    assert [r["id"] for r in S.list_items(days=3650, seller_ids={uid}, refetch_only=True)] == [wt_id]
    assert S.count_items(days=3650, seller_ids={uid}, refetch_only=True) == 1
    from src.seller_console import home_bundles as H
    a = H._attention({uid})
    assert a["n"] == 1 and any(g["label"] == "수집 실패" for g in a["groups"])


def test_dashboard_refetch_line_in_running_and_fail_in_attention():
    uid = "u-y12b-dash"
    _add(uid, dict(EXHAUSTED), url="https://item.taobao.com/item.htm?id=21")
    _add(uid, dict(WAIT_PC), url="https://item.taobao.com/item.htm?id=22")
    html = _client(uid).get("/seller/").get_data(as_text=True)
    assert 'data-role="hb-attention-n">1<' in html and "수집 실패" in html
    run = html[html.index('data-role="hb-running"'):]
    assert "재수집 대기 1건" in run[:run.index("</details>")]


def test_drawer_flags_say_refetch_waiting():
    uid = "u-y12b-flag"
    iid = _add(uid, dict(WAIT_PC), url="https://item.taobao.com/item.htm?id=31")
    html = _client(uid).get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    flags = html[html.index('data-role="item-flags"'):]
    assert "재수집 대기 · PC 고가수집기가 켜지면 차례로 엽니다" in flags[:flags.index("</p>")]


# ── Y12A-4 지우기 제안 넘김 ─────────────────────────────────────────────────────────────────────────────
def _polish(texts, n=None):
    return {"at": "2026-10-17T05:10:00+00:00", "version": "edit:1", "outbound": True,
            "suggest_erase": len(texts) if n is None else n,
            "rows": [{"id": f"t{i}", "tgt": t, "ko": t, "from": "tencent", "suggest_erase": True} for i, t in enumerate(texts)]
                    + [{"id": "tx", "tgt": "편안함", "ko": "편안함", "from": "polish", "suggest_erase": ""}]}


def _photos():
    return {"title_ko": "VRSUK 리클라이너",
            "images": ["https://img.alicdn.com/g0.jpg", "https://img.alicdn.com/g1.jpg"],
            "detail_images": ["https://img.alicdn.com/d0.jpg"],
            "images_ko": [{"idx": 0, "kind": "gallery", "use": True, "status": "done", "url": "https://res.cloudinary.com/x/g0-ko.png",
                           "polish": _polish(["正品保障"])},
                          {"idx": 1, "kind": "gallery", "use": True, "status": "done", "url": "https://res.cloudinary.com/x/g1-ko.png",
                           "polish": _polish(["20年质保", "包邮"])}],
            "detail_images_ko": [{"idx": 0, "kind": "detail", "use": True, "status": "done", "url": "https://res.cloudinary.com/x/d0-ko.png",
                                  "polish": _polish(["官方旗舰"])}]}


def test_skip_one_photo_leaves_pixels_and_drops_count():
    ex = _photos()
    before = copy.deepcopy(ex)
    assert A.erase_suggestions(ex) == 3
    assert A.skip_erase(ex, "gallery", 1)
    assert A.erase_suggestions(ex) == 2
    ph = {(p["kind"], p["idx"]): p for p in A.erase_photos(ex)}
    assert ph[("gallery", 1)]["state"] == "skipped" and ph[("gallery", 0)]["state"] == "pending"
    # 픽셀 0 — 나가는 주소·원본·다듬기 기록·편집본은 그대로, 넘김 기록만 늘었다
    for k in ("images", "detail_images"):
        assert ex[k] == before[k]
    e = ex["images_ko"][1]
    assert {k: v for k, v in e.items() if k != "erase_skip"} == before["images_ko"][1]
    assert set(e["erase_skip"]["texts"]) == {"20年质保", "包邮"}


def test_erased_in_editor_counts_as_handled():
    ex = _photos()
    ex["detail_images_ko"][0]["edit"] = {"erased": ["官方旗舰"]}           # 사진 편집에서 지운 편집본이 지금 나간다
    assert {(p["kind"], p["idx"]): p["state"] for p in A.erase_photos(ex)}[("detail", 0)] == "erased"
    assert A.erase_suggestions(ex) == 2
    ex["detail_images_ko"][0]["use"] = False                             # 원본으로 되돌리면 그 글자가 다시 나간다 → 다시 제안
    assert A.erase_suggestions(ex) == 3


def test_new_suggestion_after_skip_comes_back():
    ex = _photos()
    A.skip_erase(ex, "gallery", 0)
    ex["images_ko"][0]["polish"] = _polish(["正品保障", "新品"])          # 다시 다듬어 새 제안 글자가 나왔다
    p = next(p for p in A.erase_photos(ex) if p["idx"] == 0 and p["kind"] == "gallery")
    assert p["state"] == "pending" and p["texts"] == ["新品"]


def test_two_three_products_attention_reaches_zero_with_skip_all():
    """반례: 2호·3호가 들어오면 상품마다 제안이 나온다 — 「전부 넘김」으로 손댈 것이 실제로 0이 된다."""
    uid = "u-y12b-zero"
    ids = [_add(uid, _photos(), url=f"https://item.taobao.com/item.htm?id=4{i}") for i in range(3)]
    c = _client(uid)
    assert S.count_items(days=3650, seller_ids={uid}, attn_only=True) == 3
    for iid in ids:
        r = c.post(f"/seller/collect/{iid}/erase-suggest/skip", json={"all": True})
        assert r.status_code == 200 and r.get_json()["skipped"] == 3 and r.get_json()["left"] == 0
    assert S.count_items(days=3650, seller_ids={uid}, attn_only=True) == 0
    html = c.get("/seller/").get_data(as_text=True)
    assert 'data-role="hb-attention-none"' in html
    # 다시 누르면 넘길 게 없다(가짜 성공 금지)
    assert c.post(f"/seller/collect/{ids[0]}/erase-suggest/skip", json={"all": True}).status_code == 409


def test_route_skip_one_and_drawer_folds_skipped():
    uid = "u-y12b-drawer"
    iid = _add(uid, _photos(), url="https://item.taobao.com/item.htm?id=51")
    c = _client(uid)
    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    box = html[html.index('data-role="erase-suggest"'):]
    assert 'data-role="erase-left-n">3장' in box and 'data-role="erase-skip-all"' in box
    assert box.count('data-role="erase-row"') == 3 and box.count('data-role="erase-skip"') == 3
    assert 'data-role="erase-skipped"' not in box[:box.index("</script>")]
    r = c.post(f"/seller/collect/{iid}/erase-suggest/skip", json={"kind": "gallery", "idx": 1})
    assert r.status_code == 200 and r.get_json()["left"] == 2
    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    box = html[html.index('data-role="erase-suggest"'):]
    assert 'data-role="erase-left-n">2장' in box
    sk = box[box.index('data-role="erase-skipped"'):]
    assert "넘긴 제안 1" in sk and "20年质保" in sk and 'data-role="erase-skipped-row"' in sk
    saved = json.loads(S.get(iid, seller_ids={uid})["extra_json"])
    assert saved["attn"]["erase"] == 2 and saved["images_ko"][1]["url"].endswith("g1-ko.png")


def test_route_rejects_bad_kind_and_missing_suggestion():
    uid = "u-y12b-bad"
    iid = _add(uid, _photos(), url="https://item.taobao.com/item.htm?id=61")
    c = _client(uid)
    assert c.post(f"/seller/collect/{iid}/erase-suggest/skip", json={"kind": "logo", "idx": 0}).status_code == 400
    assert c.post(f"/seller/collect/{iid}/erase-suggest/skip", json={"kind": "sku", "idx": 0}).status_code == 409


def test_no_drawer_block_without_suggestions():
    uid = "u-y12b-none"
    iid = _add(uid, {"title_ko": "제안 없음", "images": ["https://img.alicdn.com/a.jpg"]}, url="https://item.taobao.com/item.htm?id=71")
    html = _client(uid).get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert 'data-role="erase-suggest"' not in html


def test_registered_product_is_never_a_collect_failure():
    ex = {"uploaded": [{"market": "coupang:gogane", "product_id": "9", "review": {"state": "approved"}}]}
    assert A.collect_fail(ex) is None                             # 마켓에 올라갔으면 수집은 이미 넘었다


def test_rowless_polish_record_still_counts_and_can_be_skipped():
    """상자 줄 없이 장 수만 남은 다듬기 기록도 셈에서 빠지지 않고, 넘김은 그 다듬기 실행째로 맞춘다."""
    ex = {"detail_images_ko": [{"idx": 3, "polish": {"suggest_erase": 4, "at": "2026-10-17T05:10:00+00:00"}}]}
    assert A.erase_suggestions(ex) == 1
    assert A.skip_erase(ex, "detail", 3) and A.erase_suggestions(ex) == 0
    ex["detail_images_ko"][0]["polish"]["at"] = "2026-10-18T01:00:00+00:00"   # 다시 다듬음 → 다시 제안
    assert A.erase_suggestions(ex) == 1
