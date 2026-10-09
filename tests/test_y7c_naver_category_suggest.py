"""Y7-C(오너 2026-10-08) — 네이버 카테고리 자동 추천(「그분 3클릭」 복원).

#862 이후 네이버 카테고리 = 오너 지정 → 상품명 사전 → 보류(category_unset). 사전에 없는 상품은 매번 손으로 골라야 했다.
네이버 커머스API엔 상품명 → 카테고리 추천 엔드포인트를 찾지 못해, **쿠팡 카테고리 예측**이 돌려준 리프 이름을
네이버 리프 이름과 맞춘다:
- 확신(점수·2등과 차)이 되면 자동 지정 + 카드 「카테고리 자동: 패션의류>여성의류>투피스 (바꾸기)」
- 모자라면 후보 3개 칩 — 1탭으로 저장하고 그 마켓만 다시 검증
- 오너가 고른 결과는 상품명 낱말 → 리프로 기억 — 같은 류 다음 상품은 자동
"""
from __future__ import annotations

import json
import os

import pytest

from src.db import image_translate_queue_pg as ST
from src.uploaders import naver_categories as NC
from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS

LEAF = "50000805"
ROWS = [
    {"id": "50000000", "name": "패션의류", "wholeCategoryName": "패션의류", "last": False},
    {"id": "50000167", "name": "여성의류", "wholeCategoryName": "패션의류>여성의류", "last": False},
    {"id": LEAF, "name": "투피스", "wholeCategoryName": "패션의류>여성의류>투피스", "last": True},
    {"id": "50000806", "name": "스커트", "wholeCategoryName": "패션의류>여성의류>스커트", "last": True},
    {"id": "50000810", "name": "정장세트", "wholeCategoryName": "패션의류>여성의류>정장세트", "last": True},
    {"id": "50000830", "name": "정장세트", "wholeCategoryName": "패션의류>남성의류>정장세트", "last": True},
    {"id": "50001500", "name": "정장세트", "wholeCategoryName": "출산/육아>유아동의류>정장세트", "last": True},
    {"id": "50001501", "name": "투피스", "wholeCategoryName": "출산/육아>유아동의류>투피스", "last": True},
    {"id": "50004737", "name": "주전자", "wholeCategoryName": "생활/건강>주방용품>주전자", "last": True},
]
FAM = "fam-y7c@example.com"


class FakeCoupang:
    """쿠팡 예측만 흉내 — 받은 (상품명, 설명)을 적어 둔다."""
    access_key, secret_key = "ak", "sk"

    def __init__(self, name):
        self.name, self.calls = name, []

    def predict(self, product_name, description=""):
        self.calls.append((product_name, description))
        return {"id": "63955", "name": self.name, "type": "SUCCESS", "why": ""}


_SCOPES = ("shared", "s:default", "s:y7c-own", "s:y7c-other", "s:y7c-card", "s:y7c-auto", "s:fam-y7c")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    def wipe():
        NC.reset()
        for k in [NC.STATE_KEY, NC.SUGGEST_KEY] + [NC.LEARN_KEY + sc for sc in _SCOPES]:
            ST.state_set(k, {})
    wipe()
    monkeypatch.setattr(NC, "BACKGROUND", False)     # Z8 이후 트리는 백그라운드 — 여기선 그 자리 받기로 재현
    monkeypatch.setattr(NC, "_fetch", lambda account="": ROWS)
    monkeypatch.setenv("NAVER_IMAGE_UPLOAD", "0")
    monkeypatch.setenv("FAMILY_EMAILS", FAM)
    yield
    wipe()                      # 끝날 때도 — 추천 기억·학습이 다음 파일(Y7-B 보류 계약)로 번지지 않게


def _coupang(monkeypatch, name):
    fake = FakeCoupang(name)
    import src.channel_sync.coupang_uploader as CU
    monkeypatch.setattr(CU, "make_uploader", lambda: (fake, ""))
    return fake


def _pleats(**over):
    src = ["黑色上衣", "黑色半裙"]
    pd = {"sku": "PLEATS-1", "title_ko": "플리츠 미니멀 여성 여름 세트", "sell_price_krw": 52000, "price": 168,
          "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"], "category_code": "CLO", "item_id": "it-1",
          "description_ko": "가볍고 시원한 플리츠 상의와 스커트 세트입니다.",
          "description": "가볍고 시원한 플리츠 상의와 스커트 세트입니다.",       # Y7-F: 업로더 직행 대역 — 네이버 상세 본문 필수
          "options": [{"name": "颜色分类", "values": src}, {"name": "尺码", "values": ["均码"]}],
          "skus": [{"sku_id": str(i), "spec": [v, "均码"], "stock": 5, "sell_price_krw": 52000} for i, v in enumerate(src)]}
    pd.update(over)
    return pd


def _upload(pd, monkeypatch):
    from src.channel_sync._channel_bridge import to_collected
    up = SS(account="chezgoga")
    sent = {}

    def fake(m, p, data=None):
        sent["d"] = data
        return {"originProductNo": "77"}
    monkeypatch.setattr(up, "_api_request", fake)
    return up.upload_product(up.prepare_product(to_collected(pd))), sent.get("d")


def _prevalidate(monkeypatch, pd):
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import smartstore_routing as SR
    monkeypatch.setattr(UD, "smartstore_approved", lambda store="": True)
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    import contextlib
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: contextlib.nullcontext())   # 대표 이미지 HEAD(네트워크) 대역
    return UD.UploadDispatcher().prevalidate(pd, ["smartstore"])[0]


# ── 1. 플리츠 세트 → 네이버 리프 자동 지정 ───────────────────────────────────────────────────────────

def test_pleats_auto_leaf_from_coupang_prediction(monkeypatch):
    """사전에 없는 플리츠 세트 — 쿠팡 예측 「여성 투피스」 → 네이버 「패션의류>여성의류>투피스」 자동.
    사전검증이 통과하고 카드 재료가 「카테고리 자동」을 싣고, 등록이 **같은 리프**를 보낸다(쿠팡엔 한 번만 묻는다)."""
    assert SS.match_category("플리츠 미니멀 여성 여름 세트") == ""                 # 사전 미적중(#862 이후 보류였던 상품)
    fake = _coupang(monkeypatch, "여성 투피스")
    pv = _prevalidate(monkeypatch, _pleats())
    assert pv.ok, pv
    assert pv.category["id"] == LEAF and pv.category["source"] == "coupang"
    assert pv.category["name"] == "패션의류>여성의류>투피스"
    assert pv.category["change_url"] == "/seller/collect/it-1/naver-category"
    from src.seller_console.views import _pv_dict
    assert _pv_dict(pv)["category"]["name"] == "패션의류>여성의류>투피스"        # 카드가 받는 모양
    res, sent = _upload(_pleats(), monkeypatch)
    assert res["success"] is True and sent["originProduct"]["leafCategoryId"] == LEAF
    assert len(sent["originProduct"]["detailAttribute"]["optionInfo"]["optionCombinations"]) == 2
    assert len(fake.calls) == 1                                                  # 사전검증·등록이 같은 답(저장해 둔 추천)
    assert fake.calls[0] == ("플리츠 미니멀 여성 여름 세트", "가볍고 시원한 플리츠 상의와 스커트 세트입니다.")


def test_foreign_description_not_sent_to_prediction(monkeypatch):
    fake = _coupang(monkeypatch, "여성 투피스")
    NC.suggest(_pleats(description_ko="黑色百褶半身裙套装"))
    assert fake.calls == [("플리츠 미니멀 여성 여름 세트", "")]                   # 번역 전 원문은 잡음 — 상품명만


# ── 2. 유사도 미달 → 후보 3개 → 1탭 ───────────────────────────────────────────────────────────────

def test_ambiguous_prediction_offers_three_candidates_and_holds(monkeypatch):
    """쿠팡 「정장세트」 — 같은 이름 리프가 여성·남성·유아동 세 갈래, 상품명에 갈래 말이 없다 → 자동 지정 안 함·후보 3·전송 0."""
    _coupang(monkeypatch, "정장세트")
    pd = _pleats(title_ko="플리츠 상하의 세트")
    pv = _prevalidate(monkeypatch, pd)
    assert pv.hold and pv.error_code == NC.REASON_CANDIDATES and pv.fixes == ["naver_category"]
    names = [c["name"] for c in pv.category["candidates"]]
    assert len(names) == 3 and set(names) == {"패션의류>여성의류>정장세트", "패션의류>남성의류>정장세트",
                                              "출산/육아>유아동의류>정장세트"}
    assert "후보 카테고리를 누르거나" in pv.message
    res, sent = _upload(pd, monkeypatch)
    assert sent is None and res["held"] is True and res["reason_code"] == NC.REASON_CANDIDATES


def test_unrelated_prediction_is_unset_with_reason(monkeypatch):
    """닮은 리프가 없으면 지금처럼 category_unset — 사유에 쿠팡 예측 이름."""
    _coupang(monkeypatch, "리빙박스")
    h = NC.hold(_pleats(title_ko="원목 리빙박스 대형"))
    assert h["code"] == NC.REASON_UNSET and "「리빙박스」" in h["line"]


def test_no_coupang_key_is_unset_not_guess(monkeypatch):
    import src.channel_sync.coupang_uploader as CU

    class NoKey(FakeCoupang):
        access_key = ""
    monkeypatch.setattr(CU, "make_uploader", lambda: (NoKey("x"), ""))
    h = NC.hold(_pleats())
    assert h["code"] == NC.REASON_UNSET and "쿠팡 키가 없어" in h["line"]


def test_tree_missing_skips_coupang_call(monkeypatch):
    fake = _coupang(monkeypatch, "여성 투피스")
    monkeypatch.setattr(NC, "_fetch", lambda account="": None)
    NC.reset()
    assert NC.pick(_pleats()) == ("", "") and fake.calls == []


def test_scores_respect_gender_and_kids_branches():
    t = "플리츠 미니멀 여성 여름 세트"
    assert NC.score_leaf("여성 투피스", "패션의류>여성의류>투피스", t) > 0.8
    assert NC.score_leaf("여성 투피스", "출산/육아>유아동의류>투피스", t) < 0.6     # 아이 말이 없으면 유아동 갈래 깎음
    assert NC.score_leaf("여성정장세트", "패션의류>남성의류>정장세트") < 0.5        # 여성 ↔ 남성 엇갈림
    assert NC.score_leaf("수납함", "패션의류>여성의류>투피스") == 0.0


# ── 3. 학습 — 오너가 고른 결과 → 같은 류 다음 상품은 자동 ──────────────────────────────────────────

@pytest.fixture
def item():
    from src.seller_console import collect_history_store as S
    return S.append(source="share", url="https://item.taobao.com/item.htm?id=73", seller_id="y7c-own",
                    title="플리츠 상하의 세트 미니멀", price="168", currency="CNY",
                    extra={"title_ko": "플리츠 상하의 세트 미니멀", "category_code": "CLO"})


def _client(uid="y7c-own", email=None):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=email or f"{uid}@example.com", user_role="seller")
    return c


def test_candidate_tap_saves_learns_and_next_similar_product_is_auto(monkeypatch, item):
    """후보 칩 1탭(JSON 저장) → 그 상품은 지정 · 낱말 기억 → 비슷한 다음 상품은 쿠팡에 묻지 않고 자동(학습 재적중)."""
    fake = _coupang(monkeypatch, "정장세트")
    c = _client()
    r = c.post(f"/seller/collect/{item}/naver-category", json={"category_id": "50000810"})
    assert r.status_code == 200 and r.get_json() == {"ok": True, "error": "", "id": "50000810",
                                                     "name": "패션의류>여성의류>정장세트"}
    from src.seller_console import collect_history_store as S
    assert json.loads(S.get(item, seller_ids={"y7c-own"})["extra_json"])["naver_category_id"] == "50000810"
    nxt = _pleats(title_ko="플리츠 상하의 롱 세트", item_id="it-2")
    assert NC.pick({**nxt, "cat_scope": "s:y7c-own"}) == ("50000810", "learned")
    assert fake.calls == []                                                     # 기억으로 정했다 — 쿠팡에 안 물었다
    # 다른 셀러에겐 안 번진다(공개 가입자는 셀러별)
    assert NC.learned("s:y7c-other", "플리츠 상하의 롱 세트") == ""
    # 상위 카테고리는 JSON으로도 거절
    bad = c.post(f"/seller/collect/{item}/naver-category", json={"category_id": "50000167"})
    assert bad.status_code == 400 and "상위 카테고리" in bad.get_json()["error"]


def test_learning_needs_two_agreeing_words():
    NC.learn("s:y7c-own", "플리츠 미니멀 투피스", LEAF)
    assert NC.learned("s:y7c-own", "플리츠 미니멀 투피스") == LEAF                 # 같은 상품명
    assert NC.learned("s:y7c-own", "미니멀 플리츠 스커트") == LEAF                 # 낱말 둘이 같은 리프
    assert NC.learned("s:y7c-own", "미니멀 머그컵") == ""                          # 낱말 하나로는 안 정한다
    assert NC.tokens("[해외직구] 여성 플리츠 세트 2025 봄") == ["플리츠"]          # 머리표·흔한 말·숫자 제외


def test_family_learning_is_shared(monkeypatch, item):
    """오너 서버 공유 마켓 사용자(가족)가 고른 결과는 한 벌(`shared`) — 같은 공유 사용자의 다음 상품에 적용."""
    _coupang(monkeypatch, "정장세트")
    from src.seller_console import collect_history_store as S
    fam_item = S.append(source="share", url="https://item.taobao.com/item.htm?id=74", seller_id="fam-y7c",
                        title="플리츠 상하의 세트 미니멀", price="168", currency="CNY",
                        extra={"title_ko": "플리츠 상하의 세트 미니멀"})
    c = _client("fam-y7c", email=FAM)
    assert c.post(f"/seller/collect/{fam_item}/naver-category", json={"category_id": "50000810"}).status_code == 200
    assert NC.learned("shared", "플리츠 상하의 롱 세트") == "50000810"
    assert NC.learned("s:fam-y7c", "플리츠 상하의 롱 세트") == ""


def test_picker_page_shows_auto_and_candidates(monkeypatch, item):
    _coupang(monkeypatch, "정장세트")
    h = _client().get(f"/seller/collect/{item}/naver-category").get_data(as_text=True)
    assert 'data-role="ncp-candidates"' in h and h.count('name="category_id"') == 3
    assert "쿠팡 예측 「정장세트」" in h


# ── 4. 쿠팡 예측 — 이름까지 받고, 설명이 거부되면 상품명만으로 ────────────────────────────────────

def test_coupang_predict_returns_name_and_falls_back_to_name_only(monkeypatch):
    from src.uploaders.coupang_uploader import CoupangUploader
    up = CoupangUploader(access_key="ak", secret_key="sk", vendor_id="A0")
    bodies = []

    def api(m, p, data=None):
        bodies.append(data)
        if "productDescription" in data:
            return {"error": "HTTP 400 — unknown field"}
        return {"code": "SUCCESS", "data": {"autoCategorizationPredictionResultType": "SUCCESS",
                                            "predictedCategoryId": "63955", "predictedCategoryName": "투피스"}}
    monkeypatch.setattr(up, "_api_request", api)
    r = up.predict("플리츠 세트", "가벼운 세트")
    assert r == {"id": "63955", "name": "투피스", "type": "SUCCESS", "why": ""}
    assert bodies == [{"productName": "플리츠 세트", "productDescription": "가벼운 세트"}, {"productName": "플리츠 세트"}]
    assert up.predict("플리츠 세트", "가벼운 세트")["id"] == "63955" and len(bodies) == 2   # 같은 입력은 다시 안 묻는다
    # 쿠팡 등록 경로(predict_category)는 예전 그대로 — 상품명만
    up2 = CoupangUploader(access_key="ak", secret_key="sk", vendor_id="A0")
    sent = []
    monkeypatch.setattr(up2, "_api_request", lambda m, p, data=None: sent.append(data) or {"data": {"predictedCategoryId": "1001"}})
    assert up2.predict_category("머그컵") == "1001" and sent == [{"productName": "머그컵"}]


# ── 5. 화면 — 폰 카드 390px: 자동 한 줄 · 후보 칩 1탭 ────────────────────────────────────────────────

BROWSER = pytest.mark.skipif(not os.path.exists("/opt/pw-browsers/chromium") and not os.environ.get("KGP_REQUIRE_BROWSER"),
                             reason="브라우저 없음")


def _card_run(client, path, rows_seq, act):
    """폰 카드를 실브라우저로 — 사전검증 응답만 준비한 결과(서버가 만든 실제 행)로 돌려준다. 나머지 요청은 앱 그대로."""
    pytest.importorskip("playwright.sync_api")
    from urllib.parse import urlparse
    from playwright.sync_api import sync_playwright
    page_html = client.get(path).get_data(as_text=True)
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    seq = list(rows_seq)
    asked = {"markets": []}
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = b.new_page(viewport={"width": 390, "height": 900})

        def handle(route):
            u = route.request.url
            if (urlparse(u).hostname or "") != "kgp.test":
                return route.fulfill(status=200, body=b"")
            pth = u.split("kgp.test", 1)[-1]
            if pth == path:
                return route.fulfill(status=200, content_type="text/html", body=page_html)
            if pth == "/seller/collect/prevalidate":
                asked["markets"] = (json.loads(route.request.post_data or "{}") or {}).get("markets") or []
                return route.fulfill(status=202, content_type="application/json",
                                     body=json.dumps({"ok": True, "job_id": "j", "poll": "/seller/collect/prevalidate/job/j"}))
            if pth.startswith("/seller/collect/prevalidate/job/"):
                rows = [dict(r, market=asked["markets"][0]) for r in (seq.pop(0) if len(seq) > 1 else seq[0])]   # 화면이 고른 마켓 줄에
                return route.fulfill(status=200, content_type="application/json",
                                     body=json.dumps({"ok": True, "state": "done", "results": rows, "pending": []}, ensure_ascii=False))
            r = client.open(pth, method=route.request.method, data=route.request.post_data,
                            content_type=route.request.headers.get("content-type"))
            return route.fulfill(status=r.status_code, content_type=r.content_type or "text/plain", body=r.get_data())
        pg.route("**/*", handle)
        pg.goto("http://kgp.test" + path)
        try:
            return act(pg)
        finally:
            b.close()


def _card_item(seller):
    from src.seller_console import collect_history_store as S
    return S.append(source="share", url="https://item.taobao.com/item.htm?id=75", seller_id=seller,
                    title="플리츠 상하의 세트 미니멀", price="168", currency="CNY",
                    extra={"title_ko": "플리츠 상하의 세트 미니멀", "images": ["https://img.alicdn.com/a.jpg"]})


def _row(pv, market):
    from src.seller_console.views import _pv_dict
    d = _pv_dict(pv)
    d["market"] = market
    return d


@BROWSER
def test_phone_card_auto_line_and_candidate_tap(monkeypatch):
    """390px 폰 카드: 후보 칩 3개(가로 넘침 0·칩마다 한 줄 이상 높이 44) → 1탭 → 저장 → 다시 검증 → 「카테고리 지정: …」.
    대조: 자동으로 정해진 상품은 「카테고리 자동: 패션의류>여성의류>투피스 (바꾸기)」 한 줄."""
    _coupang(monkeypatch, "정장세트")
    iid = _card_item("y7c-card")
    c = _client("y7c-card")
    mk = "smartstore"
    cands = _row(_prevalidate(monkeypatch, _pleats(title_ko="플리츠 상하의 세트 미니멀", item_id=iid)), mk)
    assert cands["category"]["candidates"]
    picked = _row(_prevalidate(monkeypatch, _pleats(title_ko="플리츠 상하의 세트 미니멀", item_id=iid,
                                                     naver_category_id="50000810")), mk)
    path = f"/seller/m/item/{iid}"

    def act(pg):
        # 화면에 있는 마켓 하나만 체크(검증 결과는 그 줄에 그린다 — 사전검증 응답은 위에서 준비한 스마트스토어 행)
        pg.evaluate("""() => { const bs = [...document.querySelectorAll('input[name=m5-market]')];
                               bs.forEach((b, i) => { b.checked = i === 0; }); }""")
        pg.click("#m5Check")
        pg.wait_for_selector("[data-role=m5-cat-pick]")
        chips = pg.eval_on_selector_all("[data-role=m5-cat-pick]",
                                        "els => els.map(e => [Math.round(e.getBoundingClientRect().height), Math.round(e.getBoundingClientRect().right), e.textContent])")
        doc = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        pg.click("[data-role=m5-cat-pick][data-cat='50000810']")
        pg.wait_for_selector("[data-role=m5-cat-auto]")
        line = pg.inner_text("[data-role=m5-cat-auto]")
        return chips, doc, line
    chips, (sw, cw), line = _card_run(c, path, [[cands], [picked]], act)
    assert len(chips) == 3 and all(h >= 44 and right <= 390 for h, right, _t in chips), chips
    assert sw <= cw
    assert line.startswith("카테고리 지정: 패션의류>여성의류>정장세트")
    from src.seller_console import collect_history_store as S
    assert json.loads(S.get(iid, seller_ids={"y7c-card"})["extra_json"])["naver_category_id"] == "50000810"
    assert NC.learned("s:y7c-card", "플리츠 상하의 롱 세트") == "50000810"           # 1탭이 학습까지


@BROWSER
def test_phone_card_shows_auto_line_with_change_link(monkeypatch):
    """사전에 없는 플리츠 세트가 쿠팡 예측으로 정해지면 카드는 탭 없이 「카테고리 자동: 패션의류>여성의류>투피스 (바꾸기)」.

    Z9: 쿠팡 전체 경로 표가 있을 때의 줄 — 표가 아직 없으면 「(추정 — 쿠팡 카테고리 경로를 받는 중)」이 붙는다(별도 계약)."""
    _coupang(monkeypatch, "여성 투피스")
    monkeypatch.setattr("src.uploaders.coupang_categories.path_of", lambda code: "패션의류잡화>여성패션>여성의류>여성 투피스")
    iid = _card_item("y7c-auto")
    c = _client("y7c-auto")
    auto = _row(_prevalidate(monkeypatch, _pleats(item_id=iid)), "smartstore")
    assert auto["ok"] and auto["category"]["source"] == "coupang"

    def act(pg):
        pg.evaluate("() => [...document.querySelectorAll('input[name=m5-market]')].forEach((b, i) => { b.checked = i === 0; })")
        pg.click("#m5Check")
        pg.wait_for_selector("[data-role=m5-cat-auto]")
        return (pg.inner_text("[data-role=m5-cat-auto]"), pg.get_attribute("[data-role=m5-cat-change]", "href"),
                pg.locator("[data-role=m5-cat-pick]").count(),
                round(pg.eval_on_selector("[data-role=m5-cat-auto]", "e => e.getBoundingClientRect().right")))
    text, href, n_chips, right = _card_run(c, f"/seller/m/item/{iid}", [[auto]], act)
    assert text.replace("\n", " ") == "카테고리 자동: 패션의류>여성의류>투피스 (바꾸기)"
    assert href == f"/seller/collect/{iid}/naver-category" and n_chips == 0 and right <= 390
