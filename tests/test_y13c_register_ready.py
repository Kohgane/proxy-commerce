"""Y13-C(오너 2026-10-18 「2호 등록 직전」) — 다시 번역 일회성 · 옵션 축약 검사 · 실측 치수·가구 추정 금지 · 등록 준비 완료 · 문지기 기록."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.seller_console import collect_history_store as S


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    S._in_memory.clear()
    from src.db import image_translate_queue_pg as st
    st._MEM_STATE.pop("rss:gate", None)
    yield
    S._in_memory.clear()


# ── 1. 「다시 번역」 일회성 — 적힌 장만 · 계획이 빼는 장은 사유 ───────────────────────────────────────────────
def test_retranslate_op_queues_only_listed_pages(monkeypatch):
    from src.services import image_translate_auto as A
    from src.services import oneshot_ops as OO
    ex = {"images": [f"https://img.alicdn.com/g{i}.jpg" for i in range(5)],
          "images_ko": [{"idx": i, "kind": "gallery", "status": "failed", "error_class": "ConvertFailed"} for i in range(5)],
          "detail_images": ["https://img.alicdn.com/d0.jpg", "https://g.alicdn.com/s.gif"]}
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id="u-y13c", title="t",
                   price="1", currency="CNY", extra=ex)
    got = {}

    class Q:
        def is_no_text(self, s):
            return "PictureWithoutText" in s

        def enqueue(self, uid, item_id, pages):
            got.update(uid=uid, pages=list(pages))
            return len(pages)

        def requeue_pages(self, item_id, pages):
            return 0
    monkeypatch.setattr(A, "_q", lambda: Q())
    monkeypatch.setattr(A, "kick", lambda: None)
    out = OO._run({"op": "retranslate", "item_id": iid, "pages": [["gallery", 0], ["gallery", 4], ["detail", 1]]})
    assert got["uid"] == "u-y13c" and got["pages"] == [("gallery", 0), ("gallery", 4)]
    assert out["accepted"] == 2
    d1 = next(r for r in out["rows"] if r["kind"] == "detail")
    assert not d1["sent"] and d1["why"] == "스페이서"
    assert OO._run({"op": "retranslate", "item_id": "nope"})["ok"] is False


# ── 2. 옵션 축약 검사 — 색 꼬리·가죽 꼬리는 낱말 절단이 아니다(운영 피샹리 3건) ───────────────────────────────
@pytest.mark.parametrize("ko,short", [
    ("부조 직조 면마 + 고양이 발톱 가죽 검정색 프레임", "부조 면마+검정"),
    ("리치 벨벳 그린 방석 + 고양이 스크래처 가죽 베이지색 프레임", "리치 벨벳 그린+베이지"),
    ("실리콘가죽 아이보리 시트+스크래치방지가죽 베이지 프레임", "실리콘 아이보리+베이지"),
])
def test_short_guard_accepts_suffix_stems(ko, short):
    from src.services.ai_fix import short_guard
    assert short_guard(ko, short) == ""


def test_short_guard_still_rejects_mid_word_cut():
    from src.services.ai_fix import short_guard
    ko15 = "블랙 풀가죽 아닐린 가죽 / 발받침 포함 천연 소가죽"
    assert short_guard(ko15, "블랙 풀가죽 아닐린 천연소").startswith("단어 중간 절단")   # Y11-Q 운영 답 — 그대로 버림
    assert short_guard("레드 소가죽 시트", "레드 소").startswith("단어 중간 절단")          # 꼬리를 떼고 1자만 남으면 버림


def test_old_guard_rejects_are_asked_again_new_ones_wait():
    from src.services import ai_fix as F
    old = (F.SHORT_GUARD_SINCE - timedelta(hours=3)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    ex = {"ai_fix_tried": {"option_short:a": old, "option_short:b": new, "option_short:c": old},
          "ai_fix_rejects": {"option_short:a": "단어 중간 절단(검정)", "option_short:b": "단어 중간 절단(x)",
                             "option_short:c": "다른 옵션 값과 같아짐"}}
    assert not F._skip(ex, "option_short:a")          # 옛 검사가 버린 답 → 하루 기다리지 않고 다시
    assert F._skip(ex, "option_short:b")              # 새 검사가 버린 답 → 하루 기다림(같은 돈 안 씀)
    assert F._skip(ex, "option_short:c") is (datetime.now(timezone.utc) - datetime.fromisoformat(old) < F.RETRY_AFTER)


def test_option_short_hold_does_not_say_wait():
    from src.seller_console.upload_dispatcher import readiness_message
    msg = readiness_message([{"short": "옵션값 25자 초과", "fix": "option_short", "line": "x"}])
    assert "기다리" not in msg and "AI 축약이 검사에서 떨어진 값을 옵션 탭에서 25자 안으로 줄인" in msg


# ── 3. 배송 치수 — 사진 규격에서 실측 · 가구는 기본 크기 추정 금지 ───────────────────────────────────────────
FISH_D6 = ("Parameter information 参数信息 名称/:利川转椅 填充/:3A级公仔棉 手工测量会有1-3cm的误差,请以实物为准! 菲尚 靠背宽80cm "
           "靠背高70cm 总高74cm 菲尚丽家 回朋 扶手高56cm 坐深55cm 菲尚丽家 坐高40cm 左右宽100cm 前后长114cm")
SOFA = {"title_src": "菲尚丽家单人沙发椅设计师客厅阳台休闲懒人沙发可睡可躺舒适单椅", "title": "피샹리 1인용 소파 의자",
        "url": "https://detail.tmall.com/item.htm?id=851803804374", "price": "1999", "currency": "CNY"}


def test_labeled_dims_from_detail_photo_7():
    from src.seller_console import shipping_ratio as R
    assert R.labeled_dims(FISH_D6)["dims_cm"] == [100.0, 114.0, 74.0]       # 축마다 가장 큰 값(좌석 깊이 55·등받이 80 아님)
    assert R.labeled_dims("가로 120cm 세로 60cm 높이 75cm")["dims_cm"] == [120.0, 60.0, 75.0]
    assert R.labeled_dims("靠背宽80cm 坐深55cm") is None                  # 셋이 안 모이면 치수로 안 쓴다
    sz = R.read_size(dict(SOFA, photo_text=FISH_D6))
    assert sz["dims_cm"] == [100.0, 114.0, 74.0] and "규격에서 읽은 치수" in sz["basis"]
    assert R.read_size(dict(SOFA, photo_text="尺寸 100x114x74"))["dims_cm"] == [100.0, 114.0, 74.0]


def test_furniture_without_dims_holds_need_dims_not_default_size():
    from src.seller_console import shipping_ratio as R
    sz = R.read_size(dict(SOFA, photo_text=""))
    assert sz["dims_cm"] is None and sz["need_dims"] == "소파"
    h = R.hold(dict(SOFA, photo_text=""))
    assert h["fix"] == "ship_dims" and h["short"] == "치수 확인 필요" and "기본 크기로 추정하지 않아요" in h["line"]
    # 직접 넣으면 실측으로
    assert R.read_size(dict(SOFA, photo_text=""))["need_dims"]
    assert R._size_for(dict(SOFA, photo_text="", ship_input={"l": 100, "w": 114, "h": 74}))["dims_cm"] == [100.0, 114.0, 74.0]
    # 가구 아닌 표 줄(캐리어)은 예전처럼 추정
    assert R.read_size({"title": "기내용 캐리어 20인치"})["basis"].startswith("크기 표 추정(캐리어")


def test_photo_keyword_does_not_decide_product_kind():
    """사진 속 광고 글자 「椅」로 상품 종류를 정하지 않는다 — 크기 표 키워드는 상품 글에서만."""
    from src.seller_console import shipping_ratio as R
    assert R.read_size({"title": "무드등", "photo_text": "办公椅 推荐"})["basis"] == ""


def test_build_product_and_precheck_share_photo_text():
    """등록(`build_product`)과 사전검증(`_pv_prepare`)이 같은 사진 글자 함수 — 배송 치수가 두 길에서 같다."""
    from src.seller_console.product_builder import build_product
    from src.services.detail_image_plan import photo_text
    from src.seller_console import views as V
    ex = dict(title=SOFA["title_src"], title_ko=SOFA["title"], price="1999", currency="CNY",
              detail_images=[f"https://img.alicdn.com/imgextra/i2/x/d{i}.jpg" for i in range(8)],
              detail_images_ko=[{"idx": 6, "kind": "detail", "status": "done", "url": "https://res.cloudinary.com/x/d6.jpg",
                                 "source_text": FISH_D6, "target_text": ""}])
    iid = S.append(source="share", url=SOFA["url"], seller_id="u-fish", title=SOFA["title"], price="1999", currency="CNY",
                   extra=ex)
    pd = build_product(S.get(iid, seller_ids={"u-fish"}), seller_id="u-fish")
    assert "左右宽100cm" in pd["photo_text"] and pd["photo_text"] == photo_text(ex) == V._ocr_text_of(ex)
    from src.seller_console import shipping_ratio as R
    assert R.read_size(pd)["dims_cm"] == [100.0, 114.0, 74.0]


# ── 4. 등록 준비 완료 ───────────────────────────────────────────────────────────────────────────────────
def _drawer(iid, uid):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=f"{uid}@example.com", user_role="seller")
    return c, c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)


def test_ready_badge_after_all_markets_pass_and_cleared_on_save():
    from src.order_webhook import app
    from src.seller_console import views as V
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id="u-bh",
                   title="블랙홀 벽등", price="69.9", currency="CNY", extra={"title_ko": "블랙홀 벽등"})
    mk = ["coupang:gogane", "coupang:woojoo", "smartstore:chezgoga", "smartstore:gocosmos"]
    with app.test_request_context():
        from flask import session
        session["user_id"] = "u-bh"
        V._pv_mark_ready({"item_id": iid}, mk, {"results": {m: {"ok": True} for m in mk}}, "job-1")
    ex = json.loads(S.get(iid, seller_ids={"u-bh"})["extra_json"])
    assert ex["pv_ready"]["ok"] and ex["pv_ready"]["held"] == []
    c, html = _drawer(iid, "u-bh")
    assert 'data-role="pv-ready"' in html and "등록 준비 완료" in html and "쿠팡 2 · 스마트스토어 2 통과" in html
    assert 'data-role="pv-ready-register"' in html
    r = c.post(f"/seller/collect/preview/{iid}/save", json={"title": "블랙홀 벽등"})
    assert r.status_code == 200
    assert "pv_ready" not in json.loads(S.get(iid, seller_ids={"u-bh"})["extra_json"])
    assert 'data-role="pv-ready"' not in _drawer(iid, "u-bh")[1]


def test_ready_not_shown_when_any_market_held():
    from src.order_webhook import app
    from src.seller_console import views as V
    iid = S.append(source="share", url="https://detail.tmall.com/item.htm?id=851803804374", seller_id="u-f2",
                   title="소파", price="1999", currency="CNY", extra={"title_ko": "소파", "pv_ready": {"ok": True, "markets": ["coupang"]}})
    with app.test_request_context():
        from flask import session
        session["user_id"] = "u-f2"
        V._pv_mark_ready({"item_id": iid}, ["coupang", "smartstore"], {"results": {"coupang": {"ok": True},
                                                                                   "smartstore": {"ok": False}}}, "j")
    ex = json.loads(S.get(iid, seller_ids={"u-f2"})["extra_json"])
    assert ex["pv_ready"]["ok"] is False and ex["pv_ready"]["held"] == ["smartstore"]
    assert 'data-role="pv-ready"' not in _drawer(iid, "u-f2")[1]


# ── 5. 문지기 기록 ───────────────────────────────────────────────────────────────────────────────────
def test_gate_decisions_are_recorded(monkeypatch):
    from src.db import image_translate_queue_pg as st
    from src.utils import bg_job as B
    from src.utils import rss as R
    monkeypatch.setattr(R, "start_ok", lambda: (False, 425, 420))
    ok, info = B.start("y13c-test", lambda: {})
    assert not ok and info["state"] == "refused"
    monkeypatch.setattr(R, "start_ok", lambda: (True, 300, 420))
    ok, _ = B.start("y13c-test2", lambda: {})
    rows = st.state_get(B.GATE_KEY)["rows"]
    assert [(r["job"], r["ok"], r["mb"], r["limit"]) for r in rows[-2:]] == [("y13c-test", False, 425, 420), ("y13c-test2", True, 300, 420)]


# ── c. 배송비 비율 분모 = 판매가(오너 결정 2026-10-18) — 피샹리 실측 수치 그대로 ─────────────────────────────────
def test_fishangli_ship_ratio_is_against_sell_price_and_passes(monkeypatch):
    """피샹리(운영 6f9c7ddf): 원가 215,766원 · 운임 94,500원(LCL 1cbm — 실측 100×114×74 = 0.85cbm) · 판매가 589,400원
    → 16% < 35% 통과. 예전 분모(원가)로는 44% 보류였다. 분모는 등록이 매기는 판매가(`UploadDispatcher._landed_krw`) 한 함수."""
    from src.seller_console import shipping_ratio as R
    from src.seller_console.upload_dispatcher import UploadDispatcher
    seen = []
    monkeypatch.setattr(UploadDispatcher, "_landed_krw",
                        staticmethod(lambda pd, market="": seen.append(market) or (589400.0, "")))
    monkeypatch.setattr(R, "_fx", lambda c: 107.94)
    monkeypatch.delenv("SHIPPING_RATIO_MAX", raising=False)
    pd = dict(SOFA, photo_text=FISH_D6)
    est = R.estimate(pd, market="smartstore:chezgoga")
    assert (est["ship_krw"], est["sell_krw"], est["ratio_pct"], est["cost_krw"]) == (94500, 589400, 16, 215772)
    assert est["line"].startswith("운임 94,500원 · 판매가 589,400원 대비 16% (기준 35%)")
    assert R.hold(pd, market="smartstore:chezgoga") is None and seen[-1] == "smartstore:chezgoga"
    # 숫자만 바꾼다 — SHIPPING_RATIO_MAX=15면 같은 상품이 보류(문구 「운임 n원 · 판매가 대비 n%」)
    monkeypatch.setenv("SHIPPING_RATIO_MAX", "15")
    h = R.hold(pd, market="coupang:gogane")
    assert h["short"] == "운임 94,500원 · 판매가 대비 16% (LCL 추정)" and "(기준 15%)" in h["line"]


def test_dispatcher_precheck_passes_market_to_ship_hold(monkeypatch):
    """사전검증 보류 판정이 그 마켓 판매가로 비율을 잰다 — 호출부가 마켓을 넘긴다(같은 함수 · 마켓별 수수료). 행동으로 잰다."""
    from src.seller_console import shipping_ratio as R
    from src.seller_console.upload_dispatcher import UploadDispatcher
    seen = []
    monkeypatch.setattr(R, "hold", lambda pd, seller_id="", market="": seen.append(market) or None)
    UploadDispatcher.readiness_holds(dict(SOFA, photo_text=FISH_D6), "smartstore")
    UploadDispatcher.readiness_holds(dict(SOFA, photo_text=FISH_D6), "coupang")
    assert seen == ["smartstore", "coupang"]


def test_furniture_gate_only_where_freight_is_measurable():
    """출발국 요율이 없는 상품(주소 없음)은 운임을 못 잰다 — 가구 치수 게이트도 걸지 않는다(예전처럼 통과)."""
    from src.seller_console import shipping_ratio as R
    assert R.hold({"title": "라운지 의자", "price": "6995"}) is None
    assert R.hold(dict(SOFA, photo_text=""))["fix"] == "ship_dims"
