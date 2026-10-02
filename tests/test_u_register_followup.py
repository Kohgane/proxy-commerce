"""U(오너 2026-10-02 18:54~18:59) — 폰 등록 성공(쿠팡 16401838524 「쿠팡 업로드 성공 (미현지화: 원문 사용)」) 후속.

## 실측(운영 읽기 전용 · 몸통 재구성)
- 「미현지화: 원문 사용」 = `upload_dispatcher._upload_to_market`이 **옛 AI 현지화 묶음(`localized[ko-KR]`)이 없을 때** 붙이던 꼬리.
  보낸 칸의 언어와 무관했다 — 저장된 상품(ae9cee70)으로 쿠팡 몸통을 그대로 다시 만들면 **한자 칸 0**.
- 진짜 문제는 다른 데 있었다: 검색어에 「미야케·아키라의」(옛 번역 제목을 낱말로 자른 것 — T3이 제목만 고쳤다),
  옵션 값 「코코넛 블루·디올 블루」(번역기가 宝蓝을 브랜드로), 상세는 가게 줄뿐이라 비어 상품명만 나감.

## 계약
  U1 전송 칸 한국어 검사(보낼 몸통 그대로 — 남으면 보류, 원문 폴백 금지) · 꼬리 문구 삭제 · 검색어 정리 · 지어낸 브랜드 이름 폐기
  U2 검토 상태 조회(statusName → 승인/검토중/반려+사유) · 화면 버튼·폴링 · 목록 배지 · 승인 전 링크 대신 WING
  U1b 등록본 점검·교정(쿠팡 원본 vs 지금 규칙 → 바뀌는 칸만 PUT, 관리자·확인 뒤)
  U0 쿠팡 두 계정 — 마켓 코드 `coupang:<계정>` → 그 계정 키·출고지로(판정 회피용 차등 규칙은 **만들지 않음**)
  U3 옵션 값 30자(문서) · 축약표 · 오너 값 몰래 자르지 않음
  U4 옵션 아닌 SKU — 제외·번역기 안 보냄·점검표 따로 셈·가격이 그 SKU에만 있으면 보류
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.collectors import ko_polish as kp

AE9 = {  # 운영 ae9cee70 저장값(읽기 전용 실측 — 이미지 주소만 줄임)
    "title": "三宅艺创极简风套装女夏设计感不规则剪裁褶皱上衣半身裙两件套",
    "title_ko": "플리츠 미니멀 여성 여름 세트, 디자인 감각이 돋보이는 언밸런스 컷팅 주름 상의와 스커트 투피스 세트",
    "price": "168.00", "currency": "CNY", "brand": "",
    "tags": ["미야케", "아키라의", "미니멀리즘", "스타일", "여성", "여름", "디자인", "감각이", "돋보이는", "언밸런스",
             "컷팅", "주름", "상의와", "스커트", "투피스"],
    "options": [{"name": "颜色分类", "name_ko": "색상",
                 "values": ["黑色上衣", "黑色半裙", "蓝色上衣", "蓝色半裙", "苔藓绿上衣", "苔藓绿半裙", "宝蓝上衣", "宝蓝半裙"],
                 "values_ko": ["검은색 상의", "검은색 미디 스커트", "파란색 상의", "파란색 미디 스커트", "이끼색 상의",
                               "이끼빛 그린 미디 스커트", "코코넛 블루 상의", "디올 블루 미디 스커트"]},
                {"name": "尺码", "name_ko": "사이즈", "values": ["均码"], "values_ko": ["프리사이즈"]}],
    "option_name_overrides": {"尺码": "패션의류/잡화 사이즈"},
    "description": "褶衣折扣店\n4.8\n88VIP好评率98%\n平均12小时发货\n客服平均10秒回复",
    "description_ko": "츠츠지 할인점\n4.8\n88VIP 긍정 평가율 98%\n평균 12시간 내 발송\n고객센터 평균 답변 시간 10초입니다.",
    "images": ["https://img.alicdn.com/g1.jpg", "https://img.alicdn.com/g2.jpg"],
}
_SPEC = ["黑色上衣", "黑色半裙", "蓝色上衣", "蓝色半裙", "苔藓绿上衣", "苔藓绿半裙", "宝蓝上衣", "宝蓝半裙"]
AE9["keywords"] = list(AE9["tags"])
AE9["skus"] = [{"spec": [v, "均码"], "image": f"https://gw.alicdn.com/s{i}.jpg", "price": "168.00", "stock": 200,
                "sku_id": str(5982774941492 + i), "currency": "CNY"} for i, v in enumerate(_SPEC)]
META_FASHION = {"attributes": [{"attributeTypeName": "패션의류/잡화 색상", "required": "MANDATORY"},
                               {"attributeTypeName": "패션의류/잡화 사이즈", "required": "MANDATORY"},
                               {"attributeTypeName": "수량", "required": "OPTIONAL", "basicUnit": "개", "usableUnits": ["개"]}],
                "noticeCategories": [], "requiredDocumentNames": []}


@pytest.fixture(autouse=True)
def _fresh():
    kp.reset_cache()
    yield
    kp.reset_cache()


@pytest.fixture
def wired(monkeypatch):
    """쿠팡 네트워크 0 — 메타·택배사·출고지만 가짜, 등록 POST·조회·수정은 잡아 둔다."""
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    import src.price as P
    sent = {"calls": [], "inits": []}
    for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID"):
        monkeypatch.setenv(k, "x")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    monkeypatch.setattr(CU, "_missing_shipping_config", lambda self: [])
    monkeypatch.setattr(CU, "resolve_delivery_company_code", lambda self: "CJGLS")
    monkeypatch.setattr(CU, "outbound_for_delivery", lambda self: ("1", None))
    monkeypatch.setattr(CU, "is_agent_buy", lambda self: False)
    monkeypatch.setattr(CU, "predict_category", lambda self, t: "69182")
    monkeypatch.setattr(CU, "get_category_meta", lambda self, c: META_FASHION)
    monkeypatch.setattr(CU, "get_category_notice_schema", lambda self, c: [])
    monkeypatch.setattr(CU, "required_documents_plan", lambda self, m: ([], None))
    monkeypatch.setattr(CU, "request_approval", lambda self, sid: {"success": True})
    monkeypatch.setattr(CU, "image_screen_enabled", False, raising=False)

    def api(self, method, path, data=None):
        sent["calls"].append((method, path, data, self.access_key, self.account))
        return {"code": "SUCCESS", "data": 16401838524}
    monkeypatch.setattr(CU, "_api_request", api)
    monkeypatch.setattr(P, "commission_pct", lambda m: (10.8, ""))
    return sent


def _dispatch(extra, markets=("coupang",), url="https://item.taobao.com/item.htm?id=999609404643"):
    from src.seller_console import collect_history_store as S
    from src.seller_console.product_builder import build_product
    from src.seller_console.upload_dispatcher import build_dispatch_payload, UploadDispatcher
    iid = S.append(source="extension", url=url, seller_id="u-u", title=extra.get("title_ko") or extra["title"],
                   price=extra.get("price"), currency=extra.get("currency"), extra=extra)
    row = S.get(iid, seller_ids={"u-u"})
    pd = build_dispatch_payload(build_product(row, edits={}, seller_id="u-u"), row)
    return UploadDispatcher().dispatch(pd, list(markets)).to_dict()


def _posted(sent):
    return next(d for m, p, d, *_ in sent["calls"] if m == "POST")


# ── U1 ────────────────────────────────────────────────────────────────────────

def test_u1_owner_product_payload_is_korean_without_the_invented_name(wired):
    r = _dispatch(json.loads(json.dumps(AE9)))["results"][0]
    assert r["success"] is True and "미현지화" not in r["message"]            # 꼬리 문구 삭제(언어와 무관했다)
    p = _posted(wired)
    from src.uploaders.coupang_uploader import CoupangUploader
    assert CoupangUploader.foreign_fields(p) == []                            # 보낸 칸 한자 0
    tags = p["items"][0]["searchTags"]
    assert not {"미야케", "아키라의", "상의와", "돋보이는"} & set(tags) and "투피스" not in tags[:2]
    vals = [a["attributeValueName"] for it in p["items"] for a in it["attributes"]]
    assert "로열 블루 스커트" in vals and "모스 그린 상의" in vals
    assert not any("디올" in v or "코코넛" in v for v in vals)


def test_u1_chinese_only_title_is_held_not_sent(wired):
    ex = json.loads(json.dumps(AE9))
    ex.pop("title_ko")
    r = _dispatch(ex)["results"][0]
    assert r["success"] is False and "원문(외국어)이 남은 칸: 상품명" in r["message"]
    assert not any(m == "POST" for m, *_ in wired["calls"])                   # 원문을 대신 보내지 않는다


def test_u1_other_korean_markets_hold_on_foreign_fields():
    from src.seller_console.upload_dispatcher import UploadDispatcher, readiness_message
    base = {"title": "三宅艺创", "price": "100", "images": ["/seller/static/icon-512.png"]}
    h = UploadDispatcher.readiness_holds(base, "smartstore")
    assert any(x["short"].startswith("원문(외국어) 남음 — 상품명") for x in h)
    assert "번역" in readiness_message(h)
    assert not any("원문(외국어)" in x["short"] for x in UploadDispatcher.readiness_holds(base, "shopify"))


def test_u1_search_tags_and_invented_brands():
    assert kp.clean_tags(AE9["tags"], AE9["title_ko"]) == ["여성", "여름", "디자인", "감각이", "언밸런스", "컷팅", "주름",
                                                           "스커트", "투피스"]
    canary_tags = ["수행", "방패", "SPORTLINK", "애플", "워치", "충전", "거치대", "applewatch7", "iwatch", "Airpods"]
    assert kp.clean_tags(canary_tags, "SPORTLINK(SPORTLINK)는 애플워치 호환 충전 거치대") == ["SPORTLINK", "충전", "거치대"]
    from src.uploaders.coupang_options import resolve_option_value
    assert resolve_option_value("宝蓝半裙", values_ko="디올 블루 미디 스커트")["value"] == "로열 블루 스커트"   # 규칙이 먼저
    bad = resolve_option_value("宝石蓝款式超长特别版", values_ko="디올 블루 특별판")
    assert bad["value"] == "" and "원문에 없는 이름(디올)" in bad["why"]
    assert kp.drop_detail_lines("스포츠링크 플래그십 스토어\n4.9\n고객 만족도 90%\n충전 거치대")[0] == "충전 거치대"


# ── U2 ────────────────────────────────────────────────────────────────────────

def _up_with(monkeypatch, product=None, histories=None, error=None):
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    calls = []

    def api(self, method, path, data=None):
        calls.append((method, path, data))
        if error:
            return {"error": error}
        if path.endswith("/histories"):
            return histories or {"data": []}
        if method == "PUT":
            return {"code": "SUCCESS", "data": None}
        return {"code": "SUCCESS", "data": product}
    monkeypatch.setattr(CU, "_api_request", api)
    return CU(access_key="a", secret_key="b", vendor_id="A01381223"), calls


def test_u2_status_mapping_and_rejection_reason(monkeypatch):
    up, calls = _up_with(monkeypatch, product={"statusName": "승인반려", "sellerProductName": "x", "items": []},
                         histories={"data": [{"statusName": "승인반려", "comment": "상표권 확인 필요", "createdAt": "2026-10-02T10:00:00"}]})
    st = up.review_status("16401838524")
    assert (st["state"], st["label"], st["comment"]) == ("rejected", "반려", "상표권 확인 필요")
    assert calls[0][1].endswith("/seller-products/16401838524") and calls[0][0] == "GET"
    up2, _ = _up_with(monkeypatch, product={"statusName": "승인완료", "productId": 8123, "items": [{"searchTags": ["수입"]}]})
    st2 = up2.review_status("16397045086")
    assert st2["state"] == "approved" and st2["link"] == "https://www.coupang.com/vp/products/8123"
    up3, _ = _up_with(monkeypatch, product={"statusName": "심사중", "items": []})
    st3 = up3.review_status("1")
    assert st3["state"] == "pending" and st3["link"] == "" and "wing.coupang.com" in st3["wing_url"]
    up4, _ = _up_with(monkeypatch, error="401 Unauthorized")
    assert up4.review_status("1")["state"] == "unknown"                       # 못 물으면 「확인 못 함」(지어내지 않음)


def _uploaded_item(seller="u-u2", market="coupang", account=""):
    from src.seller_console import collect_history_store as S
    ex = json.loads(json.dumps(AE9))
    ex["uploaded"] = [{"market": market, "market_label": "쿠팡", "external_url": "https://www.coupang.com/vp/products/16401838524",
                       "at": "2026-10-02T09:54:59+00:00", "account": account}]
    return S.append(source="extension", url="https://item.taobao.com/item.htm?id=999609404643", seller_id=seller,
                    title=ex["title_ko"], price="168", currency="CNY", extra=ex)


def test_u2_route_persists_review_and_list_badge(monkeypatch):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    _up_with(monkeypatch, product={"statusName": "심사중", "items": []})
    iid = _uploaded_item()
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-u2"
    d = c.get(f"/seller/collect/{iid}/review-status").get_json()
    assert d["ok"] and d["rows"][0]["sid"] == "16401838524" and d["rows"][0]["label"] == "검토중"
    ex = json.loads(S.get(iid, seller_ids={"u-u2"})["extra_json"])
    assert ex["uploaded"][0]["review"]["state"] == "pending" and ex["uploaded"][0]["product_id"] == "16401838524"
    h = c.get("/seller/collect/history").get_data(as_text=True)
    assert 'data-role="list-review-badge"' in h and 'data-state="pending"' in h


def test_u2_screens_ask_for_review_instead_of_opening_the_seller_number_url():
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert 'data-role="m5-review-btn"' in m5 and "/review-status" in m5 and "60000" in m5 and "WING에서 찾기" in m5
    assert 'data-role="cp-review-btn"' in pv and 'data-role="cp-result-review"' in pv and "cpReviewStatus" in pv


# ── U1b 등록본 점검·교정 ──────────────────────────────────────────────────────

LIVE = {"sellerProductId": 16397045086, "statusName": "승인완료",
        "sellerProductName": "[해외직구] 수행 방패(SPORTLINK)는 애플 워치 충전 거치대 applewatch7 9용, S8 무선 i",
        "displayProductName": "[해외직구] 수행 방패(SPORTLINK)는 애플 워치 충전 거치대 applewatch7 9용, S8 무선 i",
        "items": [{"sellerProductItemId": 1, "vendorItemId": 2, "searchTags": ["수입", "해외직구", "수행", "방패", "애플"],
                   "salePrice": 9900}]}


def test_u1b_plan_changes_only_name_and_tags(monkeypatch):
    up, calls = _up_with(monkeypatch, product=LIVE)
    plan = up.live_fix_plan(up.get_product("16397045086"), name="SPORTLINK 3in1 애플워치 호환 충전 거치대 (에어팟 겸용)",
                            search_tags=["수입", "해외직구", "SPORTLINK", "충전", "거치대"])
    assert [c["field"] for c in plan["changes"]] == ["상품명", "검색어"]
    b = plan["body"]
    assert b["sellerProductName"] == b["displayProductName"] == "SPORTLINK 3in1 애플워치 호환 충전 거치대 (에어팟 겸용)"
    assert b["items"][0]["searchTags"] == ["수입", "해외직구", "SPORTLINK", "충전", "거치대"]
    assert b["items"][0]["salePrice"] == 9900 and b["items"][0]["sellerProductItemId"] == 1    # 다른 칸은 그대로
    assert b["sellerProductId"] == 16397045086 and b["requested"] is True
    assert up.modify_product(b)["success"] is True
    assert calls[-1][0] == "PUT" and calls[-1][1].endswith("/marketplace/seller-products")      # 문서: 경로에 번호 없음
    assert up.modify_product({"sellerProductName": "x"})["success"] is False                     # 원문 아닌 몸통은 거절


def test_u1b_route_is_admin_only_and_previews_before_sending(monkeypatch):
    from src.order_webhook import app
    import src.seller_console.views as V
    _, calls = _up_with(monkeypatch, product=json.loads(json.dumps(LIVE)))
    iid = _uploaded_item(seller="u-u1b")
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-u1b"
    assert c.get(f"/seller/collect/{iid}/live-fix").status_code == 403
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    d = c.get(f"/seller/collect/{iid}/live-fix").get_json()
    assert d["ok"] and {x["field"] for x in d["changes"]} >= {"상품명", "검색어"} and "다시 심사" in d["note"]
    assert not any(m == "PUT" for m, *_ in calls)                              # 미리보기는 보내지 않는다
    d2 = c.post(f"/seller/collect/{iid}/live-fix", json={}).get_json()
    assert d2["sent"] is True and any(m == "PUT" for m, *_ in calls)
    put = next(data for m, p, data in calls if m == "PUT")
    assert "미야케" not in json.dumps(put, ensure_ascii=False) and put["sellerProductName"].startswith("플리츠")
    pv = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert 'data-role="cp-live-check"' in pv and "pcConfirm('고친 칸을 쿠팡에 보낼까요?" in pv


# ── U0 두 계정 ────────────────────────────────────────────────────────────────

def test_u0_account_code_routes_to_that_accounts_keys(wired, monkeypatch):
    monkeypatch.setenv("COUPANG_WOOJOO_ACCESS_KEY", "woo-a")
    monkeypatch.setenv("COUPANG_WOOJOO_SECRET_KEY", "woo-s")
    monkeypatch.setenv("COUPANG_WOOJOO_VENDOR_ID", "A01504840")
    for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID"):
        monkeypatch.delenv(k, raising=False)
    from src.seller_console.market_cred_view import coupang_account_choices
    ch = {c["code"]: c for c in coupang_account_choices()}
    assert ch["coupang:woojoo"]["ready"] and ch["coupang:woojoo"]["label"] == "쿠팡 — 우주대행"
    assert not ch["coupang:gogane"]["ready"] and "액세스 키" in ch["coupang:gogane"]["missing"]
    r = _dispatch(json.loads(json.dumps(AE9)), markets=["coupang:woojoo"])["results"][0]
    assert r["success"] and r["market"] == "coupang:woojoo" and r["market_label"] == "쿠팡 — 우주대행"
    post = next(c for c in wired["calls"] if c[0] == "POST")
    assert post[3] == "woo-a" and post[4] == "woojoo"                         # 우주대행 키로 · 우주대행 출고지 읽기
    from src.seller_console.market_cred_view import _ACCOUNT_OVERRIDE
    assert _ACCOUNT_OVERRIDE.get() == ""                                      # 그 한 건이 끝나면 고른 계정은 풀린다


def test_u0_missing_account_keys_say_so_and_non_admin_sees_one_coupang(monkeypatch):
    for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID",
              "COUPANG_GOGANE_ACCESS_KEY", "COUPANG_GOGANE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("COUPANG_WOOJOO_ACCESS_KEY", "woo-a")
    monkeypatch.setenv("COUPANG_WOOJOO_SECRET_KEY", "woo-s")
    monkeypatch.setenv("COUPANG_WOOJOO_VENDOR_ID", "A01504840")
    from src.seller_console.upload_dispatcher import UploadDispatcher
    r = UploadDispatcher().prevalidate({"title": "의자", "price": "10", "images": ["/x.png"]}, ["coupang:gogane"])[0]
    assert r.market == "coupang:gogane" and r.ok is False
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: False)
    assert [m["code"] for m in V._with_coupang_accounts([{"code": "coupang", "checked": True}])] == ["coupang"]
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    rows = V._with_coupang_accounts([{"code": "coupang", "checked": True}])
    assert [m["code"] for m in rows] == ["coupang:gogane", "coupang:woojoo"]
    assert [m["checked"] for m in rows] == [False, True]                      # 키 있는 계정 하나만 기본 체크


def test_u0_no_evasion_variants_are_built():
    """오너 U0의 「계정별 차등(이름·이미지 순서·가격)으로 중복 판정 회피」는 **만들지 않았다**(쿠팡 정책 우회).
    두 계정은 같은 빌더·같은 규칙으로 나간다 — 규칙표에 그런 키가 없다."""
    r = kp.rules()
    assert not any(k for k in r if "variant" in k or "account_diff" in k or "evasion" in k)


# ── U3 ────────────────────────────────────────────────────────────────────────

def test_u3_thirty_chars_and_abbreviations():
    from src.uploaders.coupang_options import resolve_option_value
    assert kp.MAX_OPTION_VALUE == 30
    pairs = json.loads(Path("tests/fixtures/ko_polish/u_long_values_2026-10-02.json").read_text(encoding="utf-8"))["pairs"]
    out = [resolve_option_value(v, values_ko=k) for v, k in pairs]
    ok = [r["value"] for r in out if r["value"]]
    assert len(pairs) == 155 and len(ok) >= 140                              # 전: 번역기 값 155개 전부 28자 넘음
    assert all(len(v) <= 30 for v in ok)
    over = [r for r in out if "넘습니다" in r["why"]]
    assert all("자르" not in r["value"] for r in over) and len(over) <= 3     # 넘는 건 자르지 않고 미해석
    assert kp.shorten("연회색(의자발 캡 포함) 좌고 41cm + 커버 쿠션 받침 블랙 테두리") != ""
    assert kp.polish_ko("연회색(의자 코너 포함) 앉는 높이 41cm + 먼지 커버") == "연회색(의자발 캡 포함) 좌고 41cm + 커버"
    # U5 실측 결함: 소재 줄임이 색을 버려 「분리 세탁 테크 패브릭 / 쿠션」(모든 색 SKU가 같은 값)이 됐다 → 색은 남는다
    v1 = resolve_option_value("【可拆洗】【原色】X型脚托+【科技布-咖啡色】软包",
                              values_ko="분리 세탁 / 원목색 / X형 발받침 / 테크 패브릭 - 커피 브라운 / 쿠션")["value"]
    v2 = resolve_option_value("【可拆洗】【咖啡色】X型脚托+【科技布-咖啡色】软包",
                              values_ko="분리 세탁 / 커피 브라운 / X형 발받침 / 테크 패브릭 - 커피 브라운 / 쿠션")["value"]
    assert "원목색" in v1 and "커피 브라운" in v1 and v1 != v2 and len(v1) <= 30


def test_u3_owner_value_is_not_silently_cut():
    from src.order_webhook import app
    iid = _uploaded_item(seller="u-u3")
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-u3"
    r = c.post(f"/seller/collect/preview/{iid}/option-value", json={"orig": "黑色上衣", "value": "가" * 31})
    assert r.status_code == 400 and "30자" in r.get_json()["error"]


# ── U4 ────────────────────────────────────────────────────────────────────────

NON_OPT = {"title": "휴지걸이", "title_ko": "휴지걸이", "price": "175.5", "currency": "CNY",
           "options": [{"name": "商品规格", "values": ["双位纸巾架【卷纸丨湿厕纸丨抽纸】", "售后品质保障丨购买无忧"],
                        "values_ko": ["2단 휴지걸이(롤·물티슈·각티슈)", "售后品质保障丨购买无忧"]}],
           "skus": [{"spec": ["双位纸巾架【卷纸丨湿厕纸丨抽纸】"], "sku_id": "1", "price": "175.5", "stock": 5},
                    {"spec": ["售后品质保障丨购买无忧"], "sku_id": "2", "price": "9.9", "stock": 99}]}


def test_u4_non_option_values_are_dropped_and_counted_apart():
    from src.seller_console.upload_dispatcher import drop_non_option_values
    from src.services import option_translate_auto as optauto
    pd = drop_non_option_values(json.loads(json.dumps(NON_OPT)))
    assert pd["options"][0]["values"] == ["双位纸巾架【卷纸丨湿厕纸丨抽纸】"] and [k["sku_id"] for k in pd["skus"]] == ["1"]
    ex = json.loads(json.dumps(NON_OPT))
    st = optauto.rule_pass(ex)
    assert "售后品质保障丨购买无忧" not in st["pending"]                         # 번역기에 보내지 않는다
    a = optauto.audit([{"id": "x", "extra_json": json.dumps(NON_OPT)}])
    assert a["counts"]["non_option"] == 1 and "售后品质保障丨购买无忧" in a["non_option_samples"]
    assert a["counts"]["left"] == 0 or "售后" not in str(a["left_samples"])
    tpl = Path("src/seller_console/templates/translate_audit.html").read_text(encoding="utf-8")
    assert 'data-role="ta-non-option"' in tpl and 'data-role="ta-awkward-over"' in tpl


def test_u4_price_only_on_the_non_option_sku_is_held():
    from src.seller_console.upload_dispatcher import UploadDispatcher, readiness_message
    p = json.loads(json.dumps(NON_OPT))
    p["skus"][0]["price"] = ""                                                 # 진짜 옵션엔 가격 없음, 보증 SKU에만
    p["images"] = ["/x.png"]
    h = UploadDispatcher.readiness_holds(p, "coupang")
    assert any(x["fix"] == "price" for x in h) and "판매가 직접 입력" in readiness_message(h)
    ok = json.loads(json.dumps(NON_OPT))
    ok["images"] = ["/x.png"]
    assert not any(x["fix"] == "price" for x in UploadDispatcher.readiness_holds(ok, "coupang"))
