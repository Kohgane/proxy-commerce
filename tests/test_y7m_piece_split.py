"""Y7-M(오너 2026-10-10) — 세트 상품명 vs 조각별 옵션 불일치 가드.

증거 21:11 KST 고코스모스 채널 13803531537(플리츠 세트 `ae9cee70`): 옵션 값 「블랙 상의 / 블랙 스커트 / …」 8개
= 색상 4 × 조각 2(조각별 개별 판매)인데 상품명·본문은 「투피스 세트」, 노출 가격은 가장 싼 조각 값.

1. 판별기(`src/uploaders/piece_split.py` · 토큰 `src/uploaders/piece_tokens.json`): 조각 2종 이상 → piecewise.
2. 본문 「옵션·상세」 맨 앞 한 줄 — 네이버(자동 초안·셀러 글)·쿠팡 모두 같은 조립(`_payload_for_market`).
3. 사전검증 「주의」 칩 — 상품명에 세트 낱말이 있을 때만, 보류 아님.
4. 상품명은 고치지 않는다.
6. 네이버 「본문 다시 보내기」도 같은 조립 → 기존 등록 상품에 반영.
"""
from __future__ import annotations

import pytest

from src.uploaders import piece_split as PS
from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS

from tests.test_y7j_naver_body import COLORS, COLORS_KO, GALLERY, TITLE, _extra

LINE = "상의와 스커트는 각각 따로 판매돼요. 세트로 받으시려면 두 가지를 각각 담아 주세요."
CHIP = "옵션이 상의/스커트 개별 판매 — 상품명에 '세트' 포함. 가격은 조각 하나 기준"
OPTS = [{"name": "颜色分类", "values": COLORS, "name_ko": "색상", "values_ko": COLORS_KO},
        {"name": "尺码", "values": ["均码"], "name_ko": "사이즈", "values_ko": ["프리사이즈"]}]
KEYRING = [{"name": "颜色", "name_ko": "색상", "values_ko": ["블랙", "화이트", "핑크", "스카이 블루"]}]

#: 운영 `ae9cee70` detail_auto.text(Y7-J 뒤 기본 문장) 모양
AUTO = (TITLE + "\n\n■ 옵션·상세\n· 색상은 " + ", ".join(COLORS_KO) + " 8가지 중에서 고를 수 있어요.\n"
        "· 사이즈는 프리사이즈 한 가지예요.\n\n■ 사이즈·세탁 안내\n· 세탁은 제품에 붙은 라벨 안내를 따라 주세요.\n\n"
        "■ 배송·구매대행 안내\n· 해외 구매대행 상품으로, 주문 후 현지 배송·통관을 거쳐 발송됩니다.")


# ── 1. 판별기 ─────────────────────────────────────────────────────────────────────────────────

def test_1_pleats_set_is_piecewise():
    j = PS.judge(OPTS)
    assert j == {"piecewise": True, "pieces": ["상의", "스커트"]}


def test_1_keyring_colors_only_is_not_piecewise():
    assert PS.judge(KEYRING) == {"piecewise": False, "pieces": []}


def test_1_one_piece_in_many_colors_is_not_piecewise():
    assert PS.judge([{"name_ko": "색상", "values_ko": ["블랙 상의", "화이트 상의", "네이비 상의"]}])["piecewise"] is False


def test_1_synonyms_are_one_piece_and_case_is_ignored():
    # 스커트=치마=skirt 는 한 조각 · 영문 대소문자 무시 · 영문은 단어 경계(laptop ≠ top)
    assert PS.judge([{"values_ko": ["블랙 스커트", "블랙 치마", "Black SKIRT"]}])["piecewise"] is False
    assert PS.judge([{"values_ko": ["Black TOP", "Black Skirt"]}])["pieces"] == ["상의", "스커트"]
    assert PS.judge([{"values_ko": ["laptop stand", "stop sign"]}])["pieces"] == []
    assert PS.judge([{"values_ko": ["블랙 자켓", "블랙 팬츠"]}])["pieces"] == ["재킷", "바지"]


def test_1_tokens_live_in_a_file():
    import json
    from pathlib import Path
    d = json.loads(Path("src/uploaders/piece_tokens.json").read_text(encoding="utf-8"))
    labels = {p["label"] for p in d["pieces"]}
    assert {"상의", "하의", "스커트", "바지", "재킷", "아우터", "이너", "셔츠", "블라우스", "원피스"} <= labels
    toks = {t for p in d["pieces"] for t in p["tokens"]}
    assert {"팬츠", "치마", "자켓", "top", "bottom", "skirt", "pants", "jacket"} <= toks
    assert d["set_words"] == ["세트", "투피스", "2종", "쓰리피스", "3종"]


def test_1_line_uses_detected_names_and_particles():
    assert PS.notice_line(["상의", "스커트"]) == LINE
    assert PS.notice_line(["재킷", "바지"]) == "재킷과 바지는 각각 따로 판매돼요. 세트로 받으시려면 두 가지를 각각 담아 주세요."
    assert PS.notice_line(["상의"]) == ""


# ── 2. 본문 한 줄 ────────────────────────────────────────────────────────────────────────────

def _pd(**over):
    pd = {**_extra(detail_auto={"text": AUTO, "images": list(GALLERY), "provider": "stub", "v": 2}),
          "description": "", "description_ko": "", "title": TITLE, "item_id": "ae9cee70", "sku": "P"}
    pd.update(over)
    return pd


def test_2_naver_body_from_draft_has_the_line_first_in_options_block():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    payload, _ = UploadDispatcher._payload_for_market(_pd(), "smartstore:gocosmos")
    h = payload["description_html"]
    assert h.count(LINE) == 1
    i = h.index("■ 옵션·상세")
    assert i < h.index(LINE) < h.index("색상은")                 # 제목 바로 아래 · 옵션 문장보다 먼저
    assert h.index("<img") < h.index(LINE)                         # 사진 위 · 글 아래(Y7-J 순서 유지)


def test_2_naver_body_from_seller_text_template_too():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = _pd(detail_auto={}, description="주름이 살아 있는 플리츠 원단이에요.\n가볍게 입기 좋아요.")
    payload, _ = UploadDispatcher._payload_for_market(pd, "smartstore")
    h = payload["description_html"]
    assert h.count(LINE) == 1 and h.index(LINE) < h.index("주름이")        # 옵션·상세 제목이 없으면 글 맨 앞


def test_2_coupang_body_has_the_same_line():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    payload, _ = UploadDispatcher._payload_for_market(_pd(description=AUTO), "coupang")
    d = payload.get("description_html") or payload["description"]
    lines = d.split("\n")
    assert lines[lines.index("■ 옵션·상세") + 1] == LINE
    from src.channel_sync._channel_bridge import to_collected
    assert LINE in to_collected(payload)["description_html"]          # 쿠팡 contents 재료(bridge)


def test_2_not_injected_twice_and_not_for_keyring():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    once, _ = UploadDispatcher._payload_for_market(_pd(), "smartstore")
    again = PS.apply(once)
    assert again["description_html"].count(LINE) == 1
    pd = _pd(options=KEYRING, skus=[], title="키링 세트", title_ko="키링 세트")
    payload, _ = UploadDispatcher._payload_for_market(pd, "smartstore")
    assert "따로 판매돼요" not in payload["description_html"]


def test_2_title_is_not_rewritten():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    payload, _ = UploadDispatcher._payload_for_market(_pd(), "smartstore")
    assert payload["title_ko"] == TITLE and "세트" in payload["title_ko"]


# ── 3. 사전검증 「주의」 칩 ───────────────────────────────────────────────────────────────────

def test_3_caution_only_when_title_says_set():
    assert PS.caution({"title_ko": TITLE, "options": OPTS}) == CHIP
    assert PS.caution({"title_ko": "플리츠 상의 스커트", "options": OPTS}) == ""        # 세트 낱말 없음
    assert PS.caution({"title_ko": "키링 세트", "options": KEYRING}) == ""            # 조각 판매 아님
    assert "'투피스'" in PS.caution({"title_ko": "플리츠 투피스", "options": OPTS})


def test_3_prevalidate_card_has_caution_and_does_not_hold(monkeypatch):
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import smartstore_routing as SR
    import src.uploaders.naver_categories as NC
    monkeypatch.setattr(UD, "smartstore_approved", lambda store="": True)
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    monkeypatch.setattr(NC, "hold", lambda *a, **k: None)
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    monkeypatch.setattr(SS, "image_upload_enabled", False, raising=False)
    # 상품명은 50자 이내(긴 운영 제목은 네이버 품명 칸 보류가 따로 걸린다 — 이 테스트는 칩만 본다)
    pd = {"title_ko": "플리츠 상의 스커트 투피스 세트", "price": 168, "images": GALLERY, "options": OPTS, "category_code": "CLO",
          "description": "주름이 살아 있는 플리츠 원단이에요.", "item_id": "it-7m"}
    r = UD.UploadDispatcher().prevalidate(pd, ["smartstore"])[0]
    assert r.cautions == [CHIP]
    # 칩은 사유가 아니다 — 판정(통과·보류·막힘)은 다른 줄들이 정한다(이 샌드박스는 이미지 서버에 못 닿아 이미지로 막힘)
    assert "조각" not in (r.message or "") and not any("따로 판매" in d for d in r.details or [])
    assert (r.error_code or "") in ("", "image_inaccessible"), (r.error_code, r.message)
    import src.seller_console.views as V
    assert V._pv_dict(r)["cautions"] == [CHIP]


def test_3_both_cards_render_the_chip():
    from pathlib import Path
    cp = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert "renderCautions(r.cautions)" in cp and 'data-role="pv-caution"' in cp
    assert 'data-role="m5-caution"' in m5 and "pc-badge-caution" in m5
    css = Path("src/static/app.css").read_text(encoding="utf-8")
    assert ".pc-badge-caution" in css


# ── 6. 「본문 다시 보내기」 — 기존 등록 상품 ──────────────────────────────────────────────────────

def test_6_resend_route_carries_the_line(monkeypatch):
    monkeypatch.setenv("FAMILY_EMAILS", "fam-y7m@example.com")
    monkeypatch.setenv("NAVER_GOCOSMOS_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_GOCOSMOS_CLIENT_SECRET", "sec")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from src.services import image_reachability as R
    monkeypatch.setattr(R, "check_all", lambda *a, **k: None)
    monkeypatch.setattr(SS, "_fetch_image", lambda self, url, on_skip=None: url)
    monkeypatch.setattr(SS, "_upload_parts", lambda self, ps: {"ok": True, "reason": "",
                                                                "urls": ["https://shop-phinf.pstatic.net/" + p.rsplit("/", 1)[-1] for p in ps]})
    sent = {}

    def upd(self, no, html):
        sent.update(no=no, html=html, account=self.account)
        return {"success": True, "status_type": "SALE"}
    monkeypatch.setattr(SS, "update_detail_content", upd)
    from src.seller_console import collect_history_store as CH
    ex = _extra(uploaded=[{"market": "smartstore:gocosmos", "account": "gocosmos", "product_id": "13742400001",
                           "channel_product_no": "13803531537",
                           "external_url": "https://smartstore.naver.com/main/products/13803531537",
                           "market_label": "스마트스토어 — 고코스모스", "at": "2026-10-10T12:11:00+00:00"}])
    iid = CH.append(source="test", url="https://detail.tmall.com/item.htm?id=1557", title=TITLE, price="168",
                    currency="CNY", extra=ex, seller_id="y7m")
    iid = iid[0] if isinstance(iid, tuple) else iid
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="y7m", user_email="fam-y7m@example.com", user_role="seller")
    d = c.post(f"/seller/collect/{iid}/naver-resend-detail", json={"market": "smartstore:gocosmos"}).get_json()
    assert d["ok"] is True, d
    assert sent["account"] == "gocosmos" and sent["html"].count(LINE) == 1
    assert sent["html"].index(LINE) < sent["html"].index("색상은")
