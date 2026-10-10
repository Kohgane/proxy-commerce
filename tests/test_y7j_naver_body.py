"""Y7-J(오너 2026-10-10 07:3x KST) — 셰고가 smartstore.naver.com/chezgoga/products/13802276439(앱 저장 ID 13741121333).

증거(운영 DB `ae9cee70…` · 판매자센터 상세 HTML): 본문 = 「■ 특징 · 미야케 · 아키라의 · 미니멀리즘 …」(제목 낱말 나열),
「■ 옵션·상세」 같은 두 줄이 두 번, 「■ 원문 상세」 아래는 가게 통계 → 이미지 0장.
원인(코드·운영 DB)
- `detail_auto.provider = stub` · `draft_status = openai_error` — OpenAI는 불렸고(키 있음) 실패, 오류 원문은 저장하지 않았다.
  폴백 초안이 **키워드**(= 옛 번역 제목 「미야케 아키라의 …」을 낱말로 자른 값)를 「■ 특징」으로 나열했다.
- 초안 재료에 옵션을 스펙으로도 붙이고 옵션으로도 넘겨 「■ 옵션·상세」가 두 번(축 이름은 쿠팡 메타 이름).
- 이미지 0장: 편집 화면이 초안 글을 상세 칸에 미리 채워 등록이 「셀러 글」로 읽음 → 초안 사진(갤러리 3장 — 네이버 CDN에
  10-09 19:45 KST 이미 올라가 있었다)을 버림 → 남은 상세 1장(`…_1200x1200q30.jpg_.webp`)은 캐시에 없음(업로드 실패, 사유는
  Render 로그에만) + 가게 아이콘은 필터 → 0장.

계약
1. 상표 게이트(제목과 같은 표 + 미야케/Miyake/三宅一生) — 상세 본문·AI 초안은 그 줄째, 옵션 값·고시 칸은 이름만. 카드 한 줄.
2. 초안은 문장형(키워드 나열 0·「해외 정품」 같은 확인 안 된 주장 0) · AI 호출 기록(모델·프롬프트·응답·오류) 저장.
3. 「■ 옵션·상세」 한 번 · 내용 없는 섹션 제목 생략.
4. 본문 = 사진(대표·갤러리 → 상세) 위 · 글 아래. 셀러 글이 초안 그대로 돌아와도 사진은 안 버린다. 못 올린 장 사유는 DB에도.
5. 등록 기록에 원상품번호·채널 상품번호 둘 다 · 딥링크·M6·M7은 채널 번호 · 예전 기록은 주소에서 소급.
6. M6 「본문 다시 보내기」 — GET → detailContent만 갈아 끼움 → PUT origin-products/{원상품번호}.
7. 판매가 구성 한 줄(등록과 같은 식).
"""
from __future__ import annotations

import json

import pytest

from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS

GALLERY = ["https://img.alicdn.com/imgextra/i4/1116632222/O1CN01aIAj6j1SHjCvoXWD5_!!1116632222.jpg",
           "https://img.alicdn.com/imgextra/i2/1116632222/O1CN01zIZgzm1SHjCr4nGTO_!!1116632222.jpg",
           "https://img.alicdn.com/imgextra/i2/1116632222/O1CN01ASMLxw1SHjCvYEYAf_!!1116632222.jpg"]
DETAIL_WEBP = ("//img.alicdn.com/imgextra/i1/1116632222/O1CN01SGQy8H1SHiuTtVrP9_!!1116632222-0-shopmanager.jpg"
               "_1200x1200q30.jpg_.webp")
SHOP_ICON = "https://gtms04.alicdn.com/tps/i4/TB1lLP.HpXXXXb5XpXXaYjxHXXX-51-24.png_.webp"
SHOP_STATS = "츠츠지 할인점\n4.8\n88VIP 긍정 평가율 98%\n평균 12시간 내 발송\n고객센터 평균 답변 시간 10초입니다."
TITLE = "플리츠 미니멀 여성 여름 세트, 디자인 감각이 돋보이는 언밸런스 컷팅 주름 상의와 스커트 투피스 세트"
COLORS = ["黑色上衣", "黑色半裙", "蓝色上衣", "蓝色半裙", "苔藓绿上衣", "苔藓绿半裙", "宝蓝上衣", "宝蓝半裙"]
COLORS_KO = ["블랙 상의", "블랙 스커트", "블루 상의", "블루 스커트", "모스 그린 상의", "모스 그린 스커트", "로열 블루 상의", "로열 블루 스커트"]
#: 운영 DB `detail_auto.text`(10-09 10:45 UTC, provider stub · draft_status openai_error) — 13802276439 본문 그대로
OLD_AUTO = (TITLE + "\n해외 정품 · 국내 배송으로 편하게 만나보세요.\n의류\n\n■ 특징\n· 미야케\n· 아키라의\n· 미니멀리즘\n· 스타일\n"
            "· 여성\n· 여름\n· 디자인\n· 감각이\n\n■ 옵션·상세\n· 색상: " + ", ".join(COLORS_KO) + "\n· 패션의류/잡화 사이즈: 프리사이즈\n"
            "· 색상: " + ", ".join(COLORS_KO) + "\n· 패션의류/잡화 사이즈: 프리사이즈\n\n■ 원문 상세\n" + SHOP_STATS +
            "\n\n■ 배송·구매대행 안내\n· 해외 구매대행 상품으로, 주문 후 현지 배송·통관을 거쳐 발송됩니다.")


def _extra(**over):
    """운영 `ae9cee70…` 저장값 모양(Y7-I 정리 뒤)."""
    ex = {"title_ko": TITLE, "title_en": "三宅艺创极简风套装女夏设计感不规则剪裁褶皱上衣半身裙两件套",
          "keywords": ["미야케", "아키라의", "미니멀리즘", "스타일", "여성", "여름"], "tags": ["미야케", "아키라의"],
          "brand": "", "category_code": "CLO", "description": SHOP_STATS, "description_ko": SHOP_STATS,
          "images": list(GALLERY), "gallery_images": list(GALLERY), "detail_images": [DETAIL_WEBP, SHOP_ICON],
          "options": [{"name": "颜色分类", "values": COLORS, "name_ko": "색상", "values_ko": COLORS_KO},
                      {"name": "尺码", "values": ["均码"], "name_ko": "사이즈", "values_ko": ["프리사이즈"]}],
          "skus": [{"spec": [c, "均码"], "price": "168.00", "currency": "CNY", "stock": 200, "sku_id": str(i)}
                   for i, c in enumerate(COLORS)],
          "option_name_overrides": {}, "coupang_option_names": {"尺码": "패션의류/잡화 사이즈"},
          "detail_auto": {"text": OLD_AUTO, "images": list(GALLERY), "provider": "stub", "draft_status": "openai_error",
                          "at": "2026-10-09T10:45:36+00:00"},
          "uploaded": [{"market": "smartstore:chezgoga", "account": "chezgoga", "product_id": "13741121333",
                        "external_url": "https://smartstore.naver.com/main/products/13802276439",
                        "market_label": "스마트스토어 — 셰고가", "at": "2026-10-09T22:31:22+00:00"}]}
    ex.update(over)
    return ex


# ── 1. 상표 게이트 ──────────────────────────────────────────────────────────────────────────────

def test_1_gate_removes_miyake_lines_from_the_registered_body():
    from src.seller_console.upload_dispatcher import market_description, mark_note
    out = market_description(OLD_AUTO)
    assert "미야케" not in out and "아키라" in out                     # 그 줄만 빠진다(옛 초안 자체는 아래 2번이 새로 만든다)
    assert mark_note({"detail_auto": {"text": OLD_AUTO}}) == "상표 표현 제거: 미야케"
    from src.collectors import ko_polish as KP
    assert KP.mark_hits("ISSEY MIYAKE 플리츠") == ["미야케"] and KP.mark_hits("三宅一生 褶皱") == ["미야케"]
    assert KP.strip_marks("이세이 미야케 블루")[0] == "블루"


def test_1_this_item_original_gives_zero_miyake_in_the_body(monkeypatch):
    """이 상품 원문(저장값 그대로 — 옛 초안·키워드 「미야케」 포함) → 네이버 본문에 「미야케」 0회."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {**_extra(), "title": TITLE, "item_id": "ae9cee70", "sku": "P"}
    payload, _ = UploadDispatcher._payload_for_market(pd, "smartstore")
    assert payload["description_html"].count("미야케") == 0
    assert "Miyake" not in payload["description_html"] and "三宅" not in payload["description_html"]


def test_1_option_values_and_notice_fields_drop_the_name():
    from src.uploaders.coupang_options import resolve_option_value
    r = resolve_option_value("宝蓝上衣", override="미야케 로열 블루 상의")
    assert r["value"] == "로열 블루 상의" and r["marks"] == ["미야케"]
    assert resolve_option_value("宝蓝上衣", override="ISSEY MIYAKE")["value"] == ""
    from src.uploaders import naver_notice as NN
    st = dict(NN.DEFAULTS)
    n = NN.build({"brand": "Issey Miyake", "url": "https://detail.tmall.com/item.htm?id=1", "category_id": ""}, settings=st)
    assert n["etc"]["manufacturer"] == "상세페이지 참조 (제조국: 중국)"                   # 브랜드가 상표뿐이면 기본값


def test_1_card_line_on_prevalidate(monkeypatch):
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import smartstore_routing as SR
    import src.uploaders.naver_categories as NC
    monkeypatch.setattr(UD, "smartstore_approved", lambda store="": True)
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    monkeypatch.setattr(NC, "hold", lambda *a, **k: None)
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    monkeypatch.setattr(SS, "image_upload_enabled", False, raising=False)
    pd = {"title_ko": "플리츠", "price": 168, "images": GALLERY, "description": "이세이 미야케 감성의 플리츠\n가볍게 입어요",
          "item_id": "it-7j", "category_code": "CLO"}
    r = UD.UploadDispatcher().prevalidate(pd, ["smartstore"])[0]
    assert "상표 표현 제거: 미야케" in (r.details or []) + [r.action_label or ""], (r.details, r.action_label)


# ── 2. 초안 — 문장형 · 호출 기록 ─────────────────────────────────────────────────────────────────

def test_2_fallback_draft_is_sentences_not_title_words(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import src.seller_console.views as V
    res = V._ai_detail_draft(TITLE, _extra())
    t = res["text"]
    assert res["provider"] == "stub" and res["ai_call"]["called"] is False
    assert "미야케" not in t and "아키라" not in t and "■ 특징" not in t and "해외 정품" not in t
    assert t.count("■ 옵션·상세") == 1 and "■ 원문 상세" not in t and "88VIP" not in t and "4.8" not in t
    assert "색상은 블랙 상의, 블랙 스커트" in t and "8가지 중에서 고를 수 있어요." in t
    assert "사이즈는 프리사이즈 한 가지예요." in t and "패션의류/잡화" not in t     # 축 이름 = 사람 이름(쿠팡 메타 이름 아님)
    assert "■ 사이즈·세탁 안내" in t                                              # 의류만


def test_2_openai_prompt_model_and_response_are_recorded(monkeypatch):
    import requests
    seen = {}

    class R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "가볍게 걸치기 좋은 플리츠 투피스예요.\n이세이 미야케 느낌의 주름이에요.\n"
                                                         "상의와 스커트를 따로 입어도 좋아요."}}]}

    def post(url, headers=None, json=None, timeout=None):
        seen["prompt"] = json["messages"][0]["content"]
        seen["model"] = json["model"]
        return R()
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import src.seller_console.views as V
    res = V._ai_detail_draft(TITLE, _extra())
    p = seen["prompt"]
    assert res["provider"] == "openai" and res["ai_call"]["called"] and res["ai_call"]["model"] == "gpt-4o-mini"
    assert res["ai_call"]["prompt"] == p and res["ai_call"]["response_head"].startswith("가볍게")
    assert "미야케" not in p and "키워드" not in p and "아키라" not in p                 # 키워드(옛 제목 낱말) 안 넣음
    assert "특징 3~5개" in p and "상표·브랜드명" in p and "낱말로 쪼개 나열" in p
    assert "색상: 블랙 상의" in p and "88VIP" not in p                                # 옵션 한국어 · 가게 통계 빠짐
    assert "미야케" not in res["text"] and "따로 입어도" in res["text"]               # 모델이 상표를 써도 그 줄은 빠진다


def test_2_openai_failure_is_recorded_with_reason(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("insufficient_quota")))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import src.seller_console.views as V
    res = V._ai_detail_draft(TITLE, _extra())
    assert res["draft_status"] == "openai_error" and res["ai_call"]["called"] is True
    assert "insufficient_quota" in res["ai_call"]["error"] and res["provider"] == "stub"
    from src.seller_console.upload_dispatcher import detail_auto_note
    note = detail_auto_note({"detail_auto": {"text": "x", "provider": "stub", "draft_status": "openai_error"}, "item_id": "i"})
    # Y7-K(오너 2026-10-10): 「AI 초안 대신 기본 문장을 썼어요 — 사유」(사유 코드 없으면 「AI 호출 실패」)
    assert note["line"] == "AI 초안 대신 기본 문장을 썼어요 — AI 호출 실패 — 확인(바꾸기)"


def test_2_old_draft_is_regenerated():
    import src.seller_console.views as V
    pd = {**_extra(), "description": ""}
    assert V._pv_needs_auto_text(pd, ["smartstore:chezgoga"]) is True                   # 옛 형식(v 없음)
    from src.seller_console.ai.translator import DRAFT_VERSION
    pd2 = {**pd, "detail_auto": {**pd["detail_auto"], "v": DRAFT_VERSION}}
    assert V._pv_needs_auto_text(pd2, ["smartstore:chezgoga"]) is False
    assert V._pv_needs_auto_text({**pd, "description": "셀러가 쓴 상세예요."}, ["smartstore"]) is False
    assert V._pv_needs_auto_text(pd, ["coupang"]) is False


# ── 3. 섹션 정리 ────────────────────────────────────────────────────────────────────────────────

def test_3_duplicate_bullets_and_empty_headings_are_dropped():
    from src.seller_console.upload_dispatcher import market_description
    out = market_description(OLD_AUTO)
    assert out.count("■ 옵션·상세") == 1 and out.count("· 색상:") == 1
    assert "■ 원문 상세" not in out                                                   # 아래가 가게 통계뿐 → 제목도 뺀다


# ── 4. 사진 위 · 글 아래 ────────────────────────────────────────────────────────────────────────

def test_4_body_has_gallery_on_top_then_text():
    from src.uploaders import naver_detail as ND
    pd = {**_extra(), "detail_auto": {"text": "가볍게 걸치기 좋은 플리츠 세트예요.", "images": GALLERY, "v": 2}}
    html = ND.build({**pd, "description": ""})
    imgs = [html.index(u) for u in GALLERY]
    assert imgs == sorted(imgs) and max(imgs) < html.index("가볍게")                    # 대표·갤러리 순서 그대로, 글보다 위
    assert "shopmanager" in html and SHOP_ICON not in html                           # 상세 이미지는 갤러리 뒤, 가게 아이콘 제외


def test_4_echoed_draft_does_not_throw_away_the_photos():
    """13802276439 — 편집 화면이 초안 글을 상세 칸에 채워 보냄 → 예전엔 셀러 글로 읽고 초안 사진을 버렸다(0장)."""
    from src.uploaders import naver_detail as ND
    da = {"text": "가볍게 걸치기 좋은 플리츠 세트예요.", "images": GALLERY, "v": 2}
    pd = {**_extra(detail_images=[]), "detail_auto": da, "description": da["text"]}
    assert ND._text_of(pd) == ""                                                      # 초안이 돌아온 것 — 셀러 글 아님
    html = ND.build(pd)
    assert html.count("<img") == 3 and "가볍게" in html


def test_4_cdn_failure_reason_is_kept_in_db(monkeypatch):
    from src.uploaders import naver_cdn_cache as CC

    def fetch(self, url, on_skip=None):
        if "shopmanager" in url:
            on_skip and on_skip(url, "미허용 형식 webp → jpg 변환 실패")
            return None
        return url
    monkeypatch.setattr(SS, "_fetch_image", fetch)
    monkeypatch.setattr(SS, "_upload_parts", lambda self, ps: {"ok": True, "reason": "",
                                                                "urls": ["https://shop-phinf.pstatic.net/" + str(i) for i in range(len(ps))]})
    up = SS(account="chezgoga")
    up.cdn_map([DETAIL_WEBP, GALLERY[0]], "S")
    assert CC.get_fail("chezgoga", "https:" + DETAIL_WEBP)["reason"] == "미허용 형식 webp → jpg 변환 실패"


# ── 5. 번호 두 개 ───────────────────────────────────────────────────────────────────────────────

def test_5_upload_returns_both_numbers_and_store_url(monkeypatch):
    up = SS(account="chezgoga")
    assert up.product_url("13802276439") == "https://smartstore.naver.com/chezgoga/products/13802276439"
    assert SS(account="gocosmos").product_url("1") == "https://smartstore.naver.com/main/products/1"   # 확인 못 한 주소 — 지어내지 않음
    monkeypatch.setenv("NAVER_GOCOSMOS_STORE_SLUG", "gocosmos-shop")
    assert SS(account="gocosmos").product_url("1") == "https://smartstore.naver.com/gocosmos-shop/products/1"
    from src.seller_console.upload_dispatcher import UploadResult, DispatchResult
    d = DispatchResult(product_url="", results=[UploadResult(market="smartstore:chezgoga", success=True, message="",
                                                             external_product_id="13741121333",
                                                             channel_product_no="13802276439")]).to_dict()
    assert d["results"][0]["channel_product_no"] == "13802276439"


def test_5_old_record_backfills_channel_number_and_store_url():
    from src.seller_console import listing_status as MS
    rec = MS.records(_extra())[0]
    assert rec["product_id"] == "13741121333" and rec["channel_product_no"] == "13802276439"
    assert rec["external_url"] == "https://smartstore.naver.com/chezgoga/products/13802276439"
    assert rec["shown_no"] == "13802276439"                                            # M7 칩·「이미 등록됨」 번호


def test_5_status_lookup_uses_channel_number(monkeypatch):
    from src.seller_console import listing_status as MS
    MS.reset_cache()
    paths = []

    def api(self, method, path, data=None, **kw):
        paths.append(path)
        return {"originProduct": {"statusType": "SALE"}, "smartstoreChannelProduct": {"channelProductNo": 13802276439}}
    monkeypatch.setattr(SS, "_api_request", api)
    row = MS.query(MS.records(_extra())[0])
    assert paths == ["/v2/products/channel-products/13802276439"]
    assert row["state"] == "approved" and row["link"] == "https://smartstore.naver.com/chezgoga/products/13802276439"


# ── 6. 본문 다시 보내기 ──────────────────────────────────────────────────────────────────────────

def test_6_update_detail_content_replaces_only_detail(monkeypatch):
    calls = []
    cur = {"originProduct": {"statusType": "SALE", "name": "플리츠", "salePrice": 96650, "detailContent": "<p>옛</p>",
                             "images": {"representativeImage": {"url": "https://shop-phinf.pstatic.net/a.jpg"}}},
           "smartstoreChannelProduct": {"channelProductName": "플리츠", "naverShoppingRegistration": True}}

    def api(self, method, path, data=None, **kw):
        calls.append((method, path, data))
        return json.loads(json.dumps(cur)) if method == "GET" else {}
    monkeypatch.setattr(SS, "_api_request", api)
    res = SS(account="chezgoga").update_detail_content("13741121333", "<p>새 본문</p>")
    assert res["success"] is True
    assert [(m, p) for m, p, _d in calls] == [("GET", "/v2/products/origin-products/13741121333"),
                                             ("PUT", "/v2/products/origin-products/13741121333")]
    body = calls[1][2]
    assert body["originProduct"]["detailContent"] == "<p>새 본문</p>"
    assert body["originProduct"]["salePrice"] == 96650 and body["smartstoreChannelProduct"] == cur["smartstoreChannelProduct"]


def test_6_not_editable_status_sends_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(SS, "_api_request", lambda self, m, p, data=None, **k: calls.append(m) or
                        {"originProduct": {"statusType": "REJECTION"}})
    res = SS(account="chezgoga").update_detail_content("1", "<p>x</p>")
    assert res["success"] is False and "REJECTION" in res["error"] and calls == ["GET"]


def test_6_resend_route_sends_gallery_on_top_and_records(monkeypatch):
    """M6 팝업 버튼 — 이 상품(옛 초안·상세 webp 실패)에 1~4를 적용해 다시 보낸다: 사진 위·글 아래·미야케 0."""
    monkeypatch.setenv("FAMILY_EMAILS", "fam-y7j@example.com")
    monkeypatch.setenv("NAVER_CHEZGOGA_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CHEZGOGA_CLIENT_SECRET", "sec")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import src.seller_console.views as V
    from src.services import image_reachability as R
    monkeypatch.setattr(R, "check_all", lambda *a, **k: None)

    def fetch(self, url, on_skip=None):
        if "shopmanager" in url:
            on_skip and on_skip(url, "미허용 형식 webp → jpg 변환 실패")
            return None
        return url
    monkeypatch.setattr(SS, "_fetch_image", fetch)
    monkeypatch.setattr(SS, "_upload_parts", lambda self, ps: {"ok": True, "reason": "",
                                                                "urls": ["https://shop-phinf.pstatic.net/" + p.rsplit("/", 1)[-1] for p in ps]})
    sent = {}

    def upd(self, no, html):
        sent.update(no=no, html=html, account=self.account)
        return {"success": True, "status_type": "SALE"}
    monkeypatch.setattr(SS, "update_detail_content", upd)
    from src.seller_console import collect_history_store as CH
    iid = CH.append(source="test", url="https://detail.tmall.com/item.htm?id=1556", title=TITLE, price="168",
                    currency="CNY", extra=_extra(), seller_id="y7j")
    iid = iid[0] if isinstance(iid, tuple) else iid
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="y7j", user_email="fam-y7j@example.com", user_role="seller")
    d = c.post(f"/seller/collect/{iid}/naver-resend-detail", json={"market": "smartstore:chezgoga"}).get_json()
    assert d["ok"] is True, d
    html = sent["html"]
    assert sent["no"] == "13741121333" and sent["account"] == "chezgoga"
    assert html.count("미야케") == 0 and "88VIP" not in html and "■ 특징" not in html
    assert html.count("<img") == 3 and html.index("<img") < html.index("색상은")      # 갤러리 3장 위 · 글 아래
    assert d["images"] == 3 and d["dropped"][0]["reason"].startswith("미허용 형식")
    ex = json.loads(CH.get(iid, seller_ids={"y7j"})["extra_json"])
    assert ex["detail_auto"]["v"] == 2 and ex["detail_auto"]["ai_call"]["called"] is False   # 옛 초안을 새로 만들었다
    up = next(u for u in ex["uploaded"] if u["market"] == "smartstore:chezgoga")
    assert up["detail_resent"]["images"] == 3 and up["channel_product_no"] == "13802276439"


def test_6_popup_has_the_button():
    from pathlib import Path
    t = Path("src/seller_console/templates/_market_status.html").read_text(encoding="utf-8")
    assert 'data-role="mst-resend"' in t and "본문 다시 보내기" in t and "naver-resend-detail" in t
    assert "채널 상품번호" in t and "mst-price-line" in t


# ── 7. 판매가 구성 ──────────────────────────────────────────────────────────────────────────────

def test_7_price_parts_line_matches_calc_sell_price(monkeypatch):
    monkeypatch.setenv("MARKET_COMMISSION_PCT_SMARTSTORE", "5.5")
    monkeypatch.setenv("FORWARDER_FEE_JPY", "300")
    monkeypatch.setenv("SHIPPING_FEE_DEFAULT", "12000")
    monkeypatch.setenv("DOMESTIC_SHIPPING_FEE_KRW", "3000")
    from src.price import sell_price_parts, calc_sell_price
    from decimal import Decimal
    fx = {"CNYKRW": Decimal("200.45"), "JPYKRW": Decimal("9.0")}
    parts = sell_price_parts(168, "CNY", "smartstore", 35, fx_rates=fx)
    assert parts["sell_krw"] == float(calc_sell_price(168, "CNY", "smartstore", 35, fx_rates=fx))
    line = parts["line"]
    assert line.startswith("원가 168 CNY×200.45 = 33,676원") and "수수료 5.5%" in line and "마진 35%" in line
    assert "기본값 — 무게·크기를 몰라서" in line and "10원 올림" in line and "SHIPPING_FEE" not in line   # 화면에 env 이름 0
