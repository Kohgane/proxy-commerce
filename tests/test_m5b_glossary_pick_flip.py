"""M5 후속(오너 2026-10-07, 실사용 1호) — 5) 용어집·음역 의심 6) 마켓 체크 글과 상태 일치 7) 좌우반전 확인 도구."""
from __future__ import annotations

import io
import re

import pytest

SRC = "老钱风吊带连衣裙女夏100%桑蚕丝法式新中式通勤长裙"


@pytest.mark.parametrize("ko,src,want", [
    ("라오첸 스타일 원피스", "老钱风连衣裙", "올드머니 룩 원피스"),
    ("뽕나무 누에고치 실크 블라우스", "桑蚕丝衬衫", "실크 블라우스"),
    ("100% 뽕나무 누에고치 실크 원피스", "100%桑蚕丝连衣裙", "100% 실크 원피스"),
    ("리얼 실크 셔츠", "真丝衬衫", "실크 셔츠"),
    ("멜빵 드레스 여름", "吊带连衣裙夏", "슬립 원피스 여름"),
    ("여름 스커트", "连衣裙夏", "여름 원피스"),                    # 连衣裙을 「스커트」로 옮긴 오역
    ("하프 스커트", "半身裙", "스커트"),
    ("프랑스식 블라우스", "法式衬衫", "프렌치 블라우스"),
    ("신중식 원피스", "新中式连衣裙", "뉴차이니즈 원피스"),
    ("통근 셔츠", "通勤衬衫", "오피스룩 셔츠"),
])
def test_glossary(ko, src, want):
    from src.collectors import ko_polish as K
    assert K.title_fix(ko, src) == want


def test_glossary_is_code_constant_and_skirt_kept_when_real_skirt():
    from src.collectors import ko_polish as K
    cns = [r[0] for r in K.TITLE_GLOSSARY]
    for cn in ("老钱风", "桑蚕丝", "真丝", "100%桑蚕丝", "吊带连衣裙", "连衣裙", "半身裙", "法式", "新中式", "通勤"):
        assert cn in cns
    assert K.title_fix("니트 상의 + 스커트", "针织上衣半身裙连衣裙套装") == "니트 상의 + 스커트"   # 진짜 스커트는 그대로
    assert K.title_fix("라오첸 스타일", "") == "라오첸 스타일"                                # 원문 없으면 손대지 않음


def test_translit_suspects_marks_but_never_rewrites():
    from src.collectors import ko_polish as K
    assert K.translit_suspects("라오첸 미니 원피스", "老钱风连衣裙") == ["라오첸"]
    assert K.translit_suspects("쉬폰 웨딩 원피스", "雪纺连衣裙") == []
    assert K.translit_suspects("라오첸 원피스", "") == []                            # 중국 소싱이 아니면 안 봄
    assert K.translit_suspects("올드머니 룩 실크 원피스", SRC) == []


def _item(seller, extra=None):
    from src.seller_console import collect_history_store as S
    ex = {"title": SRC, "title_ko": "라오첸 미니 원피스", "images": ["https://img.alicdn.com/a.jpg"] * 2,
          "price": "328", "currency": "CNY"}
    ex.update(extra or {})
    return S.append(source="share_text", url="https://item.taobao.com/item.htm?id=1", seller_id=seller,
                    title="라오첸 미니 원피스", price="328", currency="CNY", extra=ex)


def _client(**sess):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(sess)
    return c


def test_card_shows_translit_check():
    """카드 제목은 용어집을 지난 뒤라 「라오첸」은 이미 「올드머니 룩」 — 용어집에 없는 음역(「샤오펑」)만 남아 표시된다."""
    iid = _item("m5b-g", {"title": "小凤连衣裙", "title_ko": "샤오펑 미니 원피스"})
    h = _client(user_id="m5b-g").get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-translit"' in h and "<strong>샤오펑</strong>" in h and "확인 필요" in h
    iid2 = _item("m5b-g")
    h2 = _client(user_id="m5b-g").get(f"/seller/m/item/{iid2}").get_data(as_text=True)
    assert "올드머니 룩" in h2 and "라오첸" not in h2.split('data-role="m5-title"')[1][:200]


def test_pick_line_counts_current_state(monkeypatch):
    from src.db import image_translate_queue_pg as st
    from src.seller_console import market_cred_view as MCV, smartstore_routing as SR, market_credentials as mc
    st.reset_for_tests()
    monkeypatch.setenv("FAMILY_EMAILS", "mom@example.com")
    monkeypatch.setattr(MCV, "coupang_account_choices", lambda: [
        {"code": "coupang:gogane", "account": "gogane", "label": "쿠팡 — 고가네", "ready": True, "missing": []},
        {"code": "coupang:woojoo", "account": "woojoo", "label": "쿠팡 — 우주대행", "ready": False, "missing": ["키"]}])
    monkeypatch.setattr(SR, "store_choices", lambda p=None: [])
    monkeypatch.setattr(mc, "connected_markets", lambda sid, ms: {m: m in ("shopify",) for m in ms})
    iid = _item("mom-g")
    h = _client(user_id="mom-g", user_email="mom@example.com").get(f"/seller/m/item/{iid}").get_data(as_text=True)
    checked = len(re.findall(r'name="m5-market"[^>]* checked', h))
    assert checked == 0                                                       # 우주대행 쿠팡 키 없음 → 묶음이 아무것도 안 켬
    assert f'data-role="m5-pick-count">{checked}<' in h and "우주대행 묶음 줄이 아직 준비 안 돼 비워 뒀어요" in h
    assert 'autocomplete="off"' in h and "pageshow" in h and "recount()" in h


def _png(flip=False, color=(200, 30, 30)):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (120, 120), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([5, 10, 50, 110], fill=color)                                # 왼쪽에 치우친 막대(좌우 비대칭)
    d.ellipse([70, 70, 100, 100], fill=(20, 20, 20))
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_flip_compare_verdicts():
    from src.services import flip_check as F
    assert F.compare(_png(), _png())["verdict"] == "같음"
    r = F.compare(_png(), _png(flip=True))
    assert r["verdict"] == "좌우반전" and r["mirror"] < r["same"]
    assert F.compare(_png(), _png(color=(0, 0, 255)))["verdict"] in ("다름", "같음")
    assert F.compare(b"not-an-image", _png())["verdict"] == "판정 못 함"


def test_flip_check_pair_and_original_urls():
    from src.services import flip_check as F
    store = {"o": _png(), "s": _png(flip=True)}
    r = F.check_pair("o", "s", fetch=lambda u: (store.get(u, b""), "없음"))
    assert r["verdict"] == "좌우반전"
    assert F.check_pair("x", "s", fetch=lambda u: (store.get(u, b""), "HTTP 403"))["why"] == "원본: HTTP 403"
    raw = {"item": {"item_imgs": [{"url": "//img.alicdn.com/1.jpg"}, {"url": "https://img.alicdn.com/2.jpg"}]}}
    assert F.original_urls({"images": ["z"]}, raw) == ["https://img.alicdn.com/1.jpg", "https://img.alicdn.com/2.jpg"]
    assert F.original_urls({"images": ["z"]}, None) == ["z"]


def test_flip_admin_page(monkeypatch):
    from src.services import flip_check as F
    store = {"https://img.alicdn.com/a.jpg": _png()}
    monkeypatch.setattr(F, "check_pair", lambda o, s, fetch=None: dict(F.compare(store[o], _png(flip=True))))
    iid = _item("m5b-flip")
    h = _client(user_id="owner-flip", user_role="admin").get(f"/admin/diagnostics/flip-check?item={iid}").get_data(as_text=True)
    assert 'data-role="flip-summary"' in h and "좌우반전 2장" in h and "원본 출처 수집 images" in h
