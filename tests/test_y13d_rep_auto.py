"""Y13-D 1(오너 2026-10-18 「피샹리 쿠팡 대표사진 텍스트 있음 보류가 왜 사라졌나」).

실측(운영 6f9c7ddf 18:40 UTC): 대표 교체 — 사람이 고른 게 아니라 **자동**. 07:40 번역으로 1번째 사진에 판촉 어휘(立减·할인·증정)가
잡혀 T3 「판촉 의심 기본 제외」로 갤러리에서 빠졌고, 쿠팡 대표가 2번째(책 소품 「PABLO PICASSO」뿐 → 소품 글자 규칙으로 줄 없음)로
넘어갔다. 로고 菲尚丽家는 1번째 사진에 그대로다(지우지 않았다 · 판정 규칙도 안 바뀌었다).
수리: 원래 대표가 자동으로 빠지면 오너가 「사진 편집」(지우면 대표로 돌아옴)·「넘김」(빠진 채)으로 정할 때까지 「지우기 제안」 —
그 전엔 「등록 준비 완료」 대신 「등록 전 확인 1건」. 같은 유형: 나가지 않는 장의 판촉 글자로 「나가기 전 경고」가 뜨던 것.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.seller_console import collect_history_store as S

_FISH = json.loads(Path("tests/fixtures/y13d_fishangli_gallery.json").read_text(encoding="utf-8"))
MK = ["coupang:gogane", "coupang:woojoo", "smartstore:chezgoga", "smartstore:gocosmos"]


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    S._in_memory.clear()
    yield
    S._in_memory.clear()


def _ex():
    ex = copy.deepcopy(_FISH)
    ex.pop("_doc", None)
    return ex


def test_fishangli_rep_switched_by_promo_exclusion_not_by_owner():
    """왜 사라졌나 = 대표 교체(자동): 나가는 첫 장이 2번째 사진 — 1번째(로고·판촉)는 등록 목록에 없다."""
    from src.services import image_translate_store as its
    ex = _ex()
    eff = its.effective_images(ex, originals=ex["images"])
    assert eff[0] == ex["images_ko"][1]["url"] and ex["images_ko"][0]["url"] not in eff
    assert its.promo_excluded(ex["images_ko"][0]) and not ex.get("rep_image")       # 오너가 고른 대표 아님


def test_auto_dropped_rep_is_a_pending_erase_suggestion_with_logo():
    from src.seller_console.attention import erase_photos, rep_auto_dropped
    ex = _ex()
    r = rep_auto_dropped(ex)
    assert r and r["state"] == "pending" and r["rep_auto"] and (r["kind"], r["idx"]) == ("gallery", 0)
    assert r["texts"][0] == "菲尚丽家"                                               # 로고 = 제목 맨 앞 한자가 사진에 그대로
    assert {"下单享好礼", "超级立减", "买贵退差价", "享3期免息"} <= set(r["texts"])
    assert "PICASSO" not in r["texts"] and "W" not in r["texts"]                      # 일반 글자는 제안 아님
    rows = erase_photos(ex)
    assert rows[0]["rep_auto"] and rows[0]["state"] == "pending"


def test_skip_records_choice_and_clears_pending():
    from src.seller_console.attention import rep_auto_dropped, rep_auto_line, skip_erase
    ex = _ex()
    assert rep_auto_line(ex).startswith("대표 사진이 자동으로 바뀌었어요")
    assert skip_erase(ex, "gallery", 0, by="owner") is True
    assert rep_auto_dropped(ex)["state"] == "skipped" and rep_auto_line(ex) == ""
    from src.services import image_translate_store as its
    assert its.promo_excluded(ex["images_ko"][0])                                     # 넘김 = 빠진 채로 두기(사진 그대로)


def test_erasing_the_texts_brings_rep_back_and_ends_the_question():
    """「사진 편집」으로 판촉·로고 상자를 지운 편집본을 쓰면 판촉 의심이 아니다 → 원래 대표로 돌아오고 질문은 끝난다."""
    from src.seller_console.attention import rep_auto_dropped
    from src.services import image_translate_store as its
    ex = _ex()
    e = ex["images_ko"][0]
    gone = [b["src"] for b in e["boxes"] if b["src"] not in ("W", "Excelle nt Quality, Exquisite Technology", "PICASSO")] + \
           [b["tgt"] for b in e["boxes"] if b["src"] not in ("W", "Excelle nt Quality, Exquisite Technology", "PICASSO")]
    e["edit"] = {"url": "https://res.cloudinary.com/x/edit/e1.jpg", "erased": gone}
    e["url"] = e["edit"]["url"]
    assert not its.promo_excluded(e) and rep_auto_dropped(ex) is None
    assert its.effective_images(ex, originals=ex["images"])[0] == "https://res.cloudinary.com/x/edit/e1.jpg"


def test_owner_picked_rep_or_promo_include_is_a_decision():
    from src.seller_console.attention import rep_auto_dropped
    ex = _ex()
    ex["rep_image"] = ex["images"][1]
    assert rep_auto_dropped(ex) is None
    ex = _ex()
    ex["images_ko"][0]["promo_include"] = True                                      # 「그래도 넣기」
    assert rep_auto_dropped(ex) is None
    ex = _ex()
    ex["images"] = ex["images"][:1]
    ex["images_ko"] = ex["images_ko"][:1]
    assert rep_auto_dropped(ex) is None                                             # 한 장뿐이면 안 뺀다(대표 그대로)


def _drawer(iid, uid):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=f"{uid}@example.com", user_role="seller")
    return c, c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)


def _mark(iid, uid):
    from src.order_webhook import app
    from src.seller_console import views as V
    with app.test_request_context():
        from flask import session
        session["user_id"] = uid
        V._pv_mark_ready({"item_id": iid}, MK, {"results": {m: {"ok": True} for m in MK}}, "job-fish")


def test_all_markets_pass_but_ready_waits_for_owner_then_ready_after_skip():
    iid = S.append(source="share", url="https://detail.tmall.com/item.htm?id=851803804374", seller_id="u-fish",
                   title=_FISH["title_ko"], price="1999", currency="CNY", extra=_ex())
    _mark(iid, "u-fish")
    rec = json.loads(S.get(iid, seller_ids={"u-fish"})["extra_json"])["pv_ready"]
    assert rec["ok"] and rec["pending"] and rec["pending"][0].startswith("대표 사진이 자동으로 바뀌었어요")
    c, html = _drawer(iid, "u-fish")
    assert 'data-role="pv-ready-pending"' in html and "등록 전 확인 1건" in html and "菲尚丽家" in html
    assert 'data-role="pv-ready"' not in html and 'data-role="pv-ready-register"' not in html
    assert 'data-role="erase-row" data-kind="gallery" data-idx="0"' in html          # 위 「지우기 제안」에 그 장(사진 편집·넘김)
    r = c.post(f"/seller/collect/{iid}/erase-suggest/skip", json={"kind": "gallery", "idx": 0})
    assert r.status_code == 200 and r.get_json()["ok"]
    html2 = _drawer(iid, "u-fish")[1]
    assert 'data-role="pv-ready"' in html2 and "등록 준비 완료" in html2 and 'data-role="pv-ready-pending"' not in html2


def test_precheck_cautions_carry_the_rep_line(monkeypatch):
    """사전검증 카드에도 같은 줄(주의 칩 · 보류 아님 — 마켓 통과는 그대로)."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"title": "의자", "price": "100", "currency": "KRW", "images": ["https://x/a.jpg"],
          "rep_auto_caution": "대표 사진이 자동으로 바뀌었어요 — 테스트"}
    res = UploadDispatcher().prevalidate(pd, ["woocommerce"])
    assert any("대표 사진이 자동으로 바뀌었어요" in c for c in (res[0].cautions or []))


def test_promo_caution_ignores_photos_that_do_not_go_out():
    """같은 유형: 나가지 않는 1번째 사진(판촉 자동 제외)의 판촉 글자로 「나가기 전 경고」가 떴다(18:40 피샹리 4마켓 전부)."""
    from src.services.image_polish import promo_left_caution
    ex = _ex()
    assert promo_left_caution(ex) == ""
    ex["images_ko"][0]["promo_include"] = True                                      # 「그래도 넣기」면 나간다 → 경고
    assert "번역본 1장에 판촉 글자" in promo_left_caution(ex)
