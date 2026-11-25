"""오너 11-25 15:56 ③ — 쿠팡이 **실제로** 반려한 경우(전송 후 · 승인 반려)에도 폰에 길이 있다. 계약.

· 카드: 반려 사유 원문 그대로 + 사람 말 한 줄 + 「고쳐서 다시 올리기」(그 마켓만 사전검증 → Y8 자동 수정이 지난 반려 사유로 고침 →
  고친 것 → 바뀐 값 → 오너가 누를 때만 등록)
· 목록: 「반려」 필터 · 반려 배지 · 반쪽 등록 「쿠팡 남음」 칩/필터(「등록 끝」으로 닫지 않는다)
· 푸시: 쿠팡 등록이 성공하면 승인 결과 지켜보기 줄에 서고(읽기만), 반려가 보이면 한 번 「쿠팡 반려 1건 — 고쳐서 다시 올리기」
마켓 전송은 오너 탭으로만 — 지켜보기는 상태 조회뿐이다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

M5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
LIST = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
ROWS = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


_MADE: list = []


@pytest.fixture(autouse=True)
def _cleanup():
    """만든 상품을 지운다 — 반려 기록이 남으면 다른 계약의 대시보드 「손댈 것」에 섞인다(같은 인메모리 저장소)."""
    yield
    from src.seller_console import collect_history_store as S
    for sid, iid in _MADE:
        try:
            S.delete([iid], seller_id=sid)
        except Exception:
            pass
    _MADE.clear()


def _item(**extra):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "OKNIFE 오타클 D1 접이식 나이프", "images": ["https://img.example/a.jpg"], "price": "39.99", "currency": "USD"}
    ex.update(extra)
    iid = S.append(source="share", url="https://www.amazon.com/dp/B0CQ1X8Y2Z", title="OKNIFE Otacle D1", price="39.99",
                   currency="USD", image="", seller_id="default", extra=ex)
    _MADE.append(("default", iid))
    return iid


_REJ = {"market": "coupang:gogane", "market_label": "쿠팡 — 고가네", "product_id": "13892554342", "at": "2026-11-25T07:00:00+00:00",
        "review": {"state": "rejected", "comment": "노출상품명에 금지어(최고급)가 포함되어 있습니다. 수정 후 재요청 바랍니다."}}


# ── 요약 ────────────────────────────────────────────────────────────────────

def test_reject_summary_is_one_human_line_and_never_invents():
    from src.seller_console.listing_status import reject_summary
    assert reject_summary(_REJ["review"]["comment"]).startswith("상품명 때문에 반려됐어요")
    assert reject_summary("대표이미지에 텍스트가 포함").startswith("사진 때문에")
    assert reject_summary("") .startswith("쿠팡이 사유를 보내지 않았어요")
    assert reject_summary("기타 사유 XYZ") == "반려 사유(원문)를 보고 고쳐 다시 올려요."


# ── 카드 ────────────────────────────────────────────────────────────────────

def test_card_shows_raw_reason_summary_and_fix_button(client):
    iid = _item(uploaded=[_REJ])
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-rejected"' in h and 'data-role="m5-reject-fix" data-market="coupang:gogane"' in h
    assert "노출상품명에 금지어(최고급)가 포함되어 있습니다." in h                     # 원문 그대로
    assert "상품명 때문에 반려됐어요" in h                                          # 한 줄
    assert "13892554342" in h


def test_fix_button_runs_prevalidate_for_that_market_only():
    assert "var ms = b.getAttribute('data-role') === 'm5-reject-fix' ? [b.getAttribute('data-market')]" in M5
    assert "pickOnly(ms);" in M5 and "resetGo(); runCheck(ms, false);" in M5
    # 이미 등록된(반려된) 마켓 칸 — 중복 확인 칸이 다시 끄지 않게(실제 전송 땐 서버가 중복 확인을 받는다)
    assert "i.setAttribute('data-dup-ok', '1')" in M5
    assert "if (box.getAttribute('data-dup-ok') === '1') return;" in Path("src/seller_console/templates/_market_status.html").read_text(encoding="utf-8")
    # 등록은 오너가 누를 때만 — 이 버튼은 사전검증까지만(등록 함수를 부르지 않는다)
    i = M5.index("var b = e.target && e.target.closest ? e.target.closest('[data-role=m5-reject-fix],[data-role=m5-left-resume]')")
    j = M5.index("});", i)
    assert "register(" not in M5[i:j] and "/collect/upload" not in M5[i:j]


def test_y8_autofix_reads_the_stored_rejection():
    """「고쳐서 다시 올리기」가 고칠 재료 = 등록 기록의 반려 사유(지켜보기·팝업이 적은 `review.comment`)."""
    from src.services import reject_autofix as R
    ex = {"uploaded": [_REJ]}
    pd = {"title": "OKNIFE 최고급 접이식 나이프", "title_ko": "OKNIFE 최고급 접이식 나이프"}

    class _Res:
        market, ok, hold, fixes, message = "coupang:gogane", True, False, [], ""
    reasons = R.collect(pd, [_Res()], ex)
    assert any(r.get("kind") == "past_rejection" for r in reasons), reasons


# ── 반쪽 등록 ───────────────────────────────────────────────────────────────

def test_left_markets_saved_and_cleared_on_success(client):
    from src.seller_console import collect_history_store as S
    from src.seller_console.listing_status import left_markets, left_label
    iid = _item(uploaded=[{"market": "smartstore:shegoga", "product_id": "1", "channel_product_no": "13894618263"}])
    d = client.post(f"/seller/collect/{iid}/left-markets", json={"markets": ["coupang:gogane", "coupang:woojoo"]}).get_json()
    assert d["ok"] and d["label"] == "쿠팡 남음"
    ex = json.loads(S.get(iid, seller_id="default")["extra_json"])
    assert left_markets(ex) == ["coupang:gogane", "coupang:woojoo"]
    from src.seller_console import views as V
    with client.application.test_request_context():
        V._persist_upload_status(iid, {"results": [{"market": "coupang:gogane", "success": True, "external_product_id": "555"}]})
    ex = json.loads(S.get(iid, seller_id="default")["extra_json"])
    assert left_markets(ex) == ["coupang:woojoo"] and left_label(left_markets(ex)) == "쿠팡 남음"


def test_finish_records_left_markets_instead_of_closing():
    assert "'/left-markets', {markets: _left}" in M5
    assert "!pvOff[m] && !sendCancel[m] && _okM.indexOf(m) < 0" in M5        # 직접 뺀 마켓·취소한 마켓은 「남음」이 아니다
    assert 'data-role="m5-left-resume"' in M5 and "이어서 올리기" in M5


# ── 목록 ────────────────────────────────────────────────────────────────────

def test_list_filters_rejected_and_left(client):
    a = _item(uploaded=[_REJ])
    b = _item(left_markets=["coupang:woojoo"], uploaded=[{"market": "smartstore:shegoga", "product_id": "1"}])
    c = _item()
    h = client.get("/seller/collect/history?rej=1").get_data(as_text=True)
    assert a in h and b not in h and c not in h
    h2 = client.get("/seller/collect/history?left=1").get_data(as_text=True)
    assert b in h2 and a not in h2 and 'data-role="mk-left"' in h2 and "쿠팡 남음" in h2
    assert 'data-role="rej-filter"' in LIST and 'data-role="left-filter"' in LIST
    assert 'href="/seller/m/item/{{ it.id }}?resume=1"' in ROWS


# ── 지켜보기 · 푸시 ─────────────────────────────────────────────────────────

def test_review_watch_pushes_once_on_rejection(monkeypatch):
    from src.seller_console import collect_history_store as S
    from src.services import coupang_review_watch as W
    store = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: store.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: store.__setitem__(k, v))
    sent = []
    import src.notifications.apns as A
    monkeypatch.setattr(A, "notify", lambda uid, t, b, p="": sent.append((uid, t, p)))
    iid = S.append(source="share", url="https://www.amazon.com/dp/B0CQ1X8Y2Z", title="OKNIFE", price="1", currency="USD", image="",
                   seller_id="u-own", extra={"title_ko": "OKNIFE", "uploaded": [{"market": "coupang:gogane", "product_id": "777"}]})
    _MADE.append(("u-own", iid))
    assert W.add(iid, "coupang:gogane", "777", seller_id="u-own")

    class _Up:
        def review_status(self, sid):
            return {"state": "rejected", "label": "승인반려", "comment": "대표이미지에 텍스트 포함"}
    out = W.tick(make_up=lambda acct: _Up())
    assert out["rejected"] == 1 and out["left"] == 0
    assert sent == [("u-own", "쿠팡 반려 1건 — 고쳐서 다시 올리기", f"/seller/m/item/{iid}?rej=1")]
    ex = json.loads(S.get(iid, seller_ids={"u-own"})["extra_json"])
    rv = ex["uploaded"][0]["review"]
    assert rv["state"] == "rejected" and rv["comment"] == "대표이미지에 텍스트 포함"
    # 같은 반려를 다시 봐도 두 번 보내지 않는다
    from src.services import coupang_detail_refresh as cdr
    cdr.notify_rejected({"item_id": iid, "market": "coupang:gogane", "sid": "777", "seller_id": "u-own"}, {"state": "rejected", "comment": "x"})
    assert len(sent) == 1


def test_review_watch_is_read_only_and_keeps_pending(monkeypatch):
    from src.services import coupang_review_watch as W
    store = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: store.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: store.__setitem__(k, v))
    W.add("i1", "coupang:woojoo", "888")

    class _Up:
        calls = []

        def review_status(self, sid):
            self.calls.append(sid)
            return {"state": "reviewing"}
    up = _Up()
    out = W.tick(make_up=lambda acct: up)
    assert out["checked"] == 1 and out["left"] == 1 and up.calls == ["888"]
    assert [m for m in dir(up) if not m.startswith("_")] == ["calls", "review_status"]   # 조회만 쓴다(판매중지·수정 메서드 없음)
