"""Y7-G(오너 2026-10-09 15:56 KST, 플리츠 세트 · 셰고가) — 상세 본문: 사전검증·등록 판정 일치 + 빈 상세 자동 생성.

증거: `[PV] job=32d81b8b code=ok`(통과) → 등록 「전송 전에 보류 — 상세 본문 비어 있음」(naver_required_detailContent).

원인(코드·운영 DB로 확인)
- 그 상품의 상세 설명 63자는 가게 통계 줄(S2가 지움) · 상세 이미지 = `…_1200x1200q30.jpg_.webp` 1장 + 51×24 가게 아이콘.
- 사전검증 `naver_required_holds`는 **상세 이미지 URL이 있나**(`has_content`)로 통과시켰다.
- 등록은 그 장을 **받아 → webp→jpg 변환 → 네이버 CDN 업로드** 한 뒤 못 올린 장을 빼고 잰다 → 그 장이 빠져 빈 본문.
  (어느 단계에서 빠졌는지는 Render 로그 줄 — 이 환경에선 못 읽는다. 아래 계약은 어느 단계든 같은 답을 내게 한다.)

계약
1. 판정은 `naver_detail.judge` 하나 — 사전검증과 등록이 같은 본문·같은 업로더로 **실제로 올린 뒤** 잰다.
   사전검증이 올린 장은 캐시(`naver_cdn_cache`) — 등록은 다시 올리지 않는다.
2. 못 올린 장만 빼고 사유를 남긴다. 텍스트가 있으면 텍스트만으로 보낸다.
3. 설명·이미지가 없으면(또는 이미지를 하나도 못 올리면) 보류 전에 AI 상세 초안(편집 화면 기능과 같은 함수) +
   대표·갤러리 사진으로 자동 생성 → 카드에 「상세 자동 생성 — 확인(바꾸기)」. 생성 실패일 때만 보류. KC·플러그 고지는 그대로.
"""
from __future__ import annotations

import contextlib
import json

import pytest

from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS

DETAIL_WEBP = ("//img.alicdn.com/imgextra/i1/1116632222/O1CN01SGQy8H1SHiuTtVrP9_!!1116632222-0-shopmanager.jpg"
               "_1200x1200q30.jpg_.webp")
SHOP_ICON = "https://gtms04.alicdn.com/tps/i4/TB1lLP.HpXXXXb5XpXXaYjxHXXX-51-24.png_.webp"
GALLERY = ["https://img.alicdn.com/imgextra/i4/1116632222/O1CN01aIAj6j1SHjCvoXWD5_!!1116632222.jpg",
           "https://img.alicdn.com/imgextra/i2/1116632222/O1CN01zIZgzm1SHjCr4nGTO_!!1116632222.jpg"]
SHOP_STATS = "츠츠지 할인점\n4.8\n88VIP 긍정 평가율 98%\n평균 12시간 내 발송\n고객센터 평균 답변 시간 10초입니다."


def _pleats(**over):
    """운영 DB `ae9cee70…` 저장값 모양(15:56 그 상품)."""
    pd = {"sku": "PLEATS-1", "title_ko": "플리츠 미니멀 여성 여름 세트", "title": "플리츠 미니멀 여성 여름 세트",
          "sell_price_krw": 52000, "price": 168, "currency": "CNY", "images": list(GALLERY),
          "description": SHOP_STATS, "detail_images": [DETAIL_WEBP, SHOP_ICON], "detail_blocks": {"common": []},
          "category_code": "CLO", "item_id": "it-7g", "naver_category_id": "50000816"}
    pd.update(over)
    return pd


@pytest.fixture
def cdn(monkeypatch):
    """네이버 CDN 대역 — 받기(`_fetch_image`)·올리기(`_upload_parts`)를 세고, `fail`에 든 주소는 받기 실패."""
    from src.db import image_translate_queue_pg as st
    for k in [k for k in list(getattr(st, "_MEM_STATE", {})) if k.startswith("naver_cdn:")]:
        st._MEM_STATE.pop(k, None)
    box = {"fetched": [], "uploaded": [], "fail": {}}

    def fetch(self, url, on_skip=None):
        box["fetched"].append(url)
        for frag, why in box["fail"].items():
            if frag in url:
                if on_skip:
                    on_skip(url, why)
                return None
        return url

    def parts(self, ps):
        box["uploaded"] += list(ps)
        return {"ok": True, "reason": "", "urls": ["https://shop-phinf.pstatic.net/" + p.rsplit("/", 1)[-1] for p in ps]}
    monkeypatch.setattr(SS, "_fetch_image", fetch)
    monkeypatch.setattr(SS, "_upload_parts", parts)
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    monkeypatch.setenv("NAVER_CHEZGOGA_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CHEZGOGA_CLIENT_SECRET", "sec")
    import src.uploaders.naver_categories as NC
    monkeypatch.setattr(NC, "hold", lambda *a, **k: None)
    monkeypatch.setattr(NC, "describe", lambda *a, **k: {})
    return box


def _register(monkeypatch, pd):
    """등록 경로 그대로 — 디스패처 페이로드 → 채널 브리지 → prepare_product → upload_product. 네이버 상품 생성 호출을 잡는다."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.channel_sync._channel_bridge import to_collected
    payload, _ = UploadDispatcher._payload_for_market(dict(pd), "smartstore")
    from src.channel_sync.smartstore_uploader import make_uploader
    up = make_uploader()                         # 등록(`smartstore_uploader.upload`)과 같은 업로더 — 같은 스토어 키·캐시 키
    sent = []

    def api(method, path, data=None, **kw):
        sent.append(data)
        return {"originProductNo": 1, "smartstoreChannelProductNo": 2}
    monkeypatch.setattr(up, "_api_request", api)
    res = up.upload_product(up.prepare_product(to_collected(payload)))
    return res, sent


def _detail_of(sent):
    return next(d for d in sent if isinstance(d, dict) and "originProduct" in d)["originProduct"]["detailContent"]


# ── 1. 같은 함수·같은 입력 — 15:56 그 상품 ─────────────────────────────────────────────────────────

def test_1556_item_prevalidate_and_registration_agree_and_upload_once(monkeypatch, cdn):
    """CDN이 받아 주면 둘 다 통과 — 상세 이미지는 사전검증이 **한 번** 올리고 등록은 캐시를 쓴다."""
    from src.seller_console.upload_dispatcher import naver_detail_verdict, naver_required_holds
    v = naver_detail_verdict(_pleats())
    assert v["ok"] is True and v["kept"] == 1 and not v["dropped"]
    assert [h for h in naver_required_holds(_pleats()) if h["code"] == "naver_required_detailContent"] == []
    detail_ups = [u for u in cdn["uploaded"] if "shopmanager" in u]
    assert len(detail_ups) == 1                                                      # 사전검증이 올림
    res, sent = _register(monkeypatch, _pleats())
    assert res.get("success") is not False, res
    assert len([u for u in cdn["uploaded"] if "shopmanager" in u]) == 1              # 등록은 다시 안 올림(캐시)
    body = _detail_of(sent)
    assert "shop-phinf.pstatic.net" in body and "alicdn" not in body and "88VIP" not in body


def test_1556_item_cdn_failure_both_hold_with_the_reason(monkeypatch, cdn):
    """그 장을 못 올리면 — 사전검증도 등록도 보류, 같은 사유코드. 사전검증 줄에 왜 못 올렸는지."""
    cdn["fail"]["shopmanager"] = "미허용 형식 webp → jpg 변환 실패"
    from src.seller_console.upload_dispatcher import naver_detail_verdict, naver_required_holds
    v = naver_detail_verdict(_pleats())
    assert v["ok"] is False and v["dropped"][0]["reason"] == "미허용 형식 webp → jpg 변환 실패"
    hold = next(h for h in naver_required_holds(_pleats()) if h["code"] == "naver_required_detailContent")
    assert "네이버에 못 올렸고" in hold["line"] and "변환 실패" in hold["line"]
    res, sent = _register(monkeypatch, _pleats())
    assert res["held"] is True and res["reason_code"] == "naver_required_detailContent"
    assert not [d for d in sent if isinstance(d, dict) and "originProduct" in d]     # 네이버에 안 보냄


def test_cdn_failure_with_text_sends_text_only(monkeypatch, cdn, caplog):
    """2번 — 이미지를 전부 못 올려도 텍스트가 있으면 보낸다. 못 올린 장만 빠지고 사유는 로그에."""
    cdn["fail"]["shopmanager"] = "다운로드 실패(ConnectTimeout)"
    pd = _pleats(description="가볍고 시원한 플리츠 세트예요.\n\n손빨래를 권해요.")
    from src.seller_console.upload_dispatcher import naver_detail_verdict
    assert naver_detail_verdict(pd)["ok"] is True
    import logging
    caplog.set_level(logging.WARNING)
    res, sent = _register(monkeypatch, pd)
    assert res.get("success") is not False, res
    body = _detail_of(sent)
    assert "가볍고 시원한 플리츠 세트예요." in body and "<img" not in body
    assert any("상세 이미지 뺌" in r.getMessage() and "ConnectTimeout" in r.getMessage() for r in caplog.records)


def test_one_bad_image_does_not_drop_the_others(monkeypatch, cdn):
    """예전엔 묶음 업로드 결과 장 수가 안 맞으면 그 묶음 전체를 뺐다 — 이제 장마다."""
    cdn["fail"]["d2"] = "1000바이트 — 1024바이트 미만"
    up = SS(account="chezgoga")
    html = ('<p>본문</p><img src="https://res.cloudinary.com/x/d1.jpg"><img src="https://res.cloudinary.com/x/d2.jpg">'
            '<img src="https://res.cloudinary.com/x/d3.jpg">')
    rep = {}
    out = up._detail_to_cdn(html, "S", report=rep)
    assert out.count("shop-phinf.pstatic.net") == 2 and "d2.jpg" not in out
    assert rep["kept"] == 2 and rep["dropped"][0]["reason"].startswith("1000바이트")


def test_cache_is_per_store(monkeypatch, cdn):
    from src.uploaders import naver_cdn_cache as CC
    CC.put("chezgoga", "https://a/x.jpg", "https://shop-phinf.pstatic.net/x.jpg")
    assert CC.get("chezgoga", "https://a/x.jpg") == "https://shop-phinf.pstatic.net/x.jpg"
    assert CC.get("gocosmos", "https://a/x.jpg") == ""


# ── 3. 빈 상세 — 사전검증이 초안을 만든다 ──────────────────────────────────────────────────────────

FAM = "fam-y7g@example.com"


def _job_env(monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setenv("FAMILY_EMAILS", FAM)                 # 공유 사용자 — 서버 env 키를 쓴다(일반 가입자는 자기 저장 키만)
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import smartstore_routing as SR
    from src.services import image_reachability as R
    monkeypatch.setattr(UD, "smartstore_approved", lambda store="": True)
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    monkeypatch.setattr(V, "_account_codes_forbidden", lambda m: None)
    monkeypatch.setattr(R, "check_all", lambda *a, **k: None)
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: contextlib.nullcontext())
    return V


def _item(uid, **extra):
    from src.seller_console import collect_history_store as CH
    ex = {"title_ko": "플리츠 미니멀 여성 여름 세트", "description": "", "detail_images": [], "images": list(GALLERY),
          "options": [{"name": "색상", "values": ["블랙", "화이트"]}]}
    ex.update(extra)
    return CH.append(source="test", url="https://detail.tmall.com/item.htm?id=7", title="플리츠 미니멀 여성 여름 세트",
                     price="168", currency="CNY", extra=ex, seller_id=uid)


def _prevalidate(V, uid, iid):
    from tests._pv_helper import prevalidate as _pv
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=FAM, user_role="seller")
    body = {"item_id": iid, "markets": ["smartstore"],
            "product": {"title_ko": "플리츠 미니멀 여성 여름 세트", "title": "플리츠 미니멀 여성 여름 세트", "price": 168,
                        "currency": "CNY", "sell_price_krw": 52000, "images": list(GALLERY), "description": "",
                        "detail_images": [], "naver_category_id": "50000816", "category_code": "CLO"}}
    with app.app_context():
        return _pv(c, body)


def test_blank_detail_auto_generates_and_passes(monkeypatch, cdn):
    V = _job_env(monkeypatch)
    from src.seller_console.ai import translator as T
    calls = []

    def gen(self, product):
        calls.append(product)
        return {"text": "가볍게 걸치기 좋은 플리츠 세트예요.\n\n색상은 블랙·화이트 두 가지예요.", "provider": "openai",
                "draft_status": "openai", "draft_error": ""}
    monkeypatch.setattr(T.AITranslator, "generate_description", gen)
    # 다시 재는 마켓 검증도 셀러 키 범위(`seller_market_env`) 안에서 — 밖이면 스토어 키 없이 잰다
    from src.seller_console import market_credentials as MC
    depth, runs = {"n": 0}, []
    _env0, _run0 = MC.seller_market_env, V._pv_run_markets

    @contextlib.contextmanager
    def env(*a, **k):
        depth["n"] += 1
        try:
            with _env0(*a, **k):
                yield
        finally:
            depth["n"] -= 1

    def run(*a, **k):
        runs.append(depth["n"])
        return _run0(*a, **k)
    monkeypatch.setattr(MC, "seller_market_env", env)
    monkeypatch.setattr(V, "_pv_run_markets", run)
    iid = _item("y7g-auto")
    d = _prevalidate(V, "y7g-auto", iid)
    row = d["results"][0]
    assert row["ok"] is True, row
    assert len(runs) == 2 and all(n > 0 for n in runs), runs                          # 첫 검증 + 초안 뒤 다시 검증
    # 카드 한 줄 = 그 줄이 곧 링크(편집 화면 상세 탭)
    assert row["action_url"] == f"/seller/collect/preview/{iid}?tab=detail"
    assert row["action_label"] == "상세 자동 생성(AI) — 확인(바꾸기)"
    assert calls and calls[0]["title"] == "플리츠 미니멀 여성 여름 세트"                  # 편집 화면과 같은 재료(상품명·옵션)
    assert any(o.get("name") == "색상" for o in calls[0]["options"])
    st = V._pv_store().state_get(V._PV_JOB_KEY + d["job_id"])
    assert st["auto_detail"]["status"] == "done" and d["auto_detail"]["status"] == "done"      # 폴링 응답에도(카드 진행 줄)
    from src.seller_console import collect_history_store as CH
    ex = json.loads(CH.get(iid, seller_ids={"y7g-auto"})["extra_json"])
    assert ex["detail_auto"]["text"].startswith("가볍게") and ex["detail_auto"]["images"] == GALLERY


def test_auto_draft_reaches_registration_with_notices(monkeypatch, cdn):
    """등록도 같은 초안 — 수집 기록에서 싣는 자리(`_outbound_images`)가 사전검증과 같다. KC·플러그 고지는 그대로."""
    V = _job_env(monkeypatch)
    from src.seller_console import upload_dispatcher as UD
    import src.collectors.voltage_plug as VP
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE
    da = {"text": "가볍게 걸치기 좋은 플리츠 세트예요.", "images": GALLERY[:1], "provider": "openai", "at": "2026-10-09T07:00:00+00:00"}
    iid = _item("y7g-reg", detail_auto=da)
    from src.order_webhook import app
    with app.test_request_context():
        from flask import session
        session["user_id"] = "y7g-reg"
        pd, _w, _r = V._outbound_images({"title_ko": "플리츠", "images": list(GALLERY), "description": "",
                                         "detail_images": [], "item_id": iid}, iid)
    assert pd["detail_auto"]["text"] == da["text"]
    monkeypatch.setattr(VP, "plug_notice_needed", lambda skus: True)
    payload, _ = UD.UploadDispatcher._payload_for_market(pd, "smartstore")
    html = payload["description_html"]
    assert "가볍게 걸치기 좋은 플리츠 세트예요." in html and html.count("<img") == 1
    assert html.count(PURCHASE_AGENT_NOTICE) == 1
    from src.seller_console.notice_texts import PLUG_CN_TITLE
    assert html.index(PLUG_CN_TITLE) < html.index("가볍게")                            # 플러그 고지는 맨 위
    assert UD.naver_detail_verdict(pd)["ok"] is True


def test_auto_draft_failure_keeps_the_hold(monkeypatch, cdn):
    V = _job_env(monkeypatch)
    from src.seller_console.ai import translator as T

    def boom(self, product):
        raise RuntimeError("openai 503")
    monkeypatch.setattr(T.AITranslator, "generate_description", boom)
    iid = _item("y7g-fail")
    d = _prevalidate(V, "y7g-fail", iid)
    row = d["results"][0]
    assert row["ok"] is False and row["error_code"] == "naver_required_detailContent"
    st = V._pv_store().state_get(V._PV_JOB_KEY + d["job_id"])
    assert st["auto_detail"]["status"] == "failed" and "openai 503" in st["auto_detail"]["error"]
    from src.seller_console import collect_history_store as CH
    assert "detail_auto" not in json.loads(CH.get(iid, seller_ids={"y7g-fail"})["extra_json"])


def test_seller_text_wins_over_the_auto_draft():
    from src.uploaders import naver_detail as ND
    da = {"text": "자동 초안", "images": [], "provider": "openai"}
    assert "자동 초안" in ND.build({"description": "", "detail_auto": da})
    html = ND.build({"description": "셀러가 쓴 상세", "detail_auto": da})
    assert "셀러가 쓴 상세" in html and "자동 초안" not in html
    from src.seller_console.upload_dispatcher import detail_auto_note
    assert detail_auto_note({"description": "셀러가 쓴 상세", "detail_auto": da, "item_id": "x"}) == {}
    assert detail_auto_note({"description": SHOP_STATS, "detail_auto": da, "item_id": "x"})["label"] == "확인(바꾸기)"


def test_edit_page_shows_the_auto_draft_to_change(monkeypatch):
    """「확인(바꾸기)」 → 편집 화면 상세 탭에 그 초안이 들어 있고 AI 초안 딱지 — 저장하면 셀러 상세가 된다."""
    da = {"text": "가볍게 걸치기 좋은 플리츠 세트예요.", "images": [], "provider": "openai", "at": "2026-10-09T07:00:00+00:00"}
    iid = _item("y7g-edit", detail_auto=da, description=SHOP_STATS)
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="y7g-edit")
    html = c.get(f"/seller/collect/preview/{iid}?tab=detail").get_data(as_text=True)
    assert "const _DETAIL_AUTO_ACTIVE = true;" in html
    iid2 = _item("y7g-edit", description="셀러가 쓴 상세 설명이에요.", detail_auto=da)
    html2 = c.get(f"/seller/collect/preview/{iid2}").get_data(as_text=True)
    assert "const _DETAIL_AUTO_ACTIVE = false;" in html2


def test_job_uploads_detail_images_once_before_the_market_window(monkeypatch, cdn):
    """상세 이미지는 마켓별 12초 창 밖(잡 준비 단계)에서 한 번 올리고, 마켓 검증은 캐시를 읽는다 — 잡 전체에서 1회."""
    V = _job_env(monkeypatch)
    iid = _item("y7g-warm", detail_images=[DETAIL_WEBP])
    from tests._pv_helper import prevalidate as _pv
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="y7g-warm", user_email=FAM, user_role="seller")
    body = {"item_id": iid, "markets": ["smartstore"],
            "product": {"title_ko": "플리츠 미니멀 여성 여름 세트", "price": 168, "currency": "CNY", "sell_price_krw": 52000,
                        "images": list(GALLERY), "description": "", "detail_images": [DETAIL_WEBP],
                        "naver_category_id": "50000816", "category_code": "CLO"}}
    with app.app_context():
        d = _pv(c, body)
    assert d["results"][0]["ok"] is True, d["results"][0]
    assert len([u for u in cdn["uploaded"] if "shopmanager" in u]) == 1
    st = V._pv_store().state_get(V._PV_JOB_KEY + d["job_id"])
    assert "naver_detail_cdn" in (st.get("stages") or {})
