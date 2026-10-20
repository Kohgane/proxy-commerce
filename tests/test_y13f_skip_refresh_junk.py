"""Y13-F U1·U2(오너 2026-10-19 피샹리).

U1 「넘김」: 토스트만 바뀌고 줄은 「넘기는 중…」, 머리는 「12장」 그대로 — Y12-D 2번(즉시 갱신)이 로컬 브랜치에만 있었다.
   응답에 남은 수(`left`)·넘긴 수(`skipped_total`)를 싣고, 머리 글자는 그 둘로 바로 바뀐다.
U2 지우기 제안 쓰레기: 「- · __ · ____」(기호·밑줄뿐) · 「아스 오그 드 · 블로 피카소」(책등 소품 글자 — 번역 상자엔 확신·기울기가 없어
   10-14 소품 규칙이 못 잡았다)는 제안에서 뺀다. 판촉·로고 상자는 작아도 그대로 제안.
"""
import json

import pytest

from src.seller_console import attention as A
from src.seller_console import collect_history_store as S
from src.services.image_polish import junk_suggestion


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


SIZE = [1000, 1000]


def test_symbol_only_box_is_junk():
    assert junk_suggestion({"src": "-", "tgt": "- · __ · ____"}, {"w": 300, "h": 60}, SIZE)
    assert junk_suggestion({"src": "____", "tgt": ""}, None, None)


def test_tiny_prop_text_box_is_junk_but_promo_and_logo_stay():
    tiny = {"w": 40, "h": 20}                                    # 0.08% — 책등 글자
    assert junk_suggestion({"src": "ASOGDE", "tgt": "아스 오그 드"}, tiny, SIZE) == "작은 소품 글자"
    assert junk_suggestion({"src": "包邮", "tgt": "무료 배송"}, tiny, SIZE) == ""
    assert junk_suggestion({"src": "菲尚丽家", "tgt": "菲尚丽家", "brand_logo": True}, tiny, SIZE) == ""
    assert junk_suggestion({"src": "ASOGDE", "tgt": "아스 오그 드"}, {"w": 300, "h": 200}, SIZE) == ""


def _photo(rows, boxes):
    return {"idx": 1, "kind": "gallery", "use": True, "status": "done", "url": "https://res.cloudinary.com/x/g1-ko.png",
            "boxes": boxes, "box_size": SIZE,
            "polish": {"at": "2026-10-19T04:00:00+00:00", "version": "edit:1", "outbound": True,
                       "suggest_erase": len(rows), "rows": rows}}


def test_photo_with_only_junk_suggestions_is_not_listed():
    rows = [{"id": "t0", "tgt": "- · __ · ____", "suggest_erase": True},
            {"id": "t1", "tgt": "블로 피카소", "suggest_erase": True}]
    ex = {"images": ["https://img.alicdn.com/g0.jpg", "https://img.alicdn.com/g1.jpg"],
          "images_ko": [_photo(rows, [{"x": 0, "y": 0, "w": 300, "h": 40}, {"x": 10, "y": 10, "w": 30, "h": 20}])]}
    assert [p for p in A.erase_photos(ex) if p["state"] != "skipped"] == []


def test_skip_response_carries_left_and_skipped_total():
    uid = "u-y13f-skip"
    rows = lambda t: [{"id": "t0", "tgt": t, "ko": t, "from": "tencent", "suggest_erase": True}]   # noqa: E731
    ex = {"title_ko": "1인용 소파", "images": [f"https://img.alicdn.com/g{i}.jpg" for i in range(3)],
          "images_ko": [dict(_photo(rows(t), [{"x": 0, "y": 0, "w": 400, "h": 100}]), idx=i)
                        for i, t in ((1, "정품 보장"), (2, "무료 배송"))]}
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=913", seller_id=uid, title="소파",
                   price="10", currency="CNY", extra=ex)
    c = _client(uid)
    r = c.post(f"/seller/collect/{iid}/erase-suggest/skip", json={"kind": "gallery", "idx": 1})
    js = r.get_json()
    assert r.status_code == 200 and js["left"] == 1 and js["skipped_total"] == 1
    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    box = html[html.index('data-role="erase-suggest"'):]
    assert 'data-role="erase-left-n">1장 · 넘긴 제안 1' in box
