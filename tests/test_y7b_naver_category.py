"""Y7-B(오너 2026-10-08) — 네이버 `leafCategoryId` NotValid.

실측(오너 폰 16:26 KST, 플리츠 세트 셰고가): `POST /v2/products` 400 `invalidInputs[originProduct.leafCategoryId]
NotValid 「리프 카테고리ID 항목이 유효하지 않습니다」` · 화면은 「잠시 뒤 다시 시도」(400엔 틀린 안내) · 코드 api_error.
원인: 상품 `category_code=CLO` → 업로더 `CATEGORY_MAP['CLO']='50000000'`(최상위). 그 표는 전부 최상위 ID였다 —
운영 등록 기록에 스마트스토어 성공 0건. 수리: 표 삭제 · 오너 지정 → 정본 사전 매칭 순 · 리프 캐시(하루 1회)로 가드 ·
400 invalidInputs는 필드별 조치(재시도 안내 0) · 「카테고리 지정 →」 화면.
"""
from __future__ import annotations

import json

import pytest

from src.uploaders import naver_categories as NC
from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS

LEAF, PARENT = "50000805", "50000000"
ROWS = [
    {"id": PARENT, "name": "패션의류", "wholeCategoryName": "패션의류", "last": False},
    {"id": "50000167", "name": "여성의류", "wholeCategoryName": "패션의류>여성의류", "last": False},
    {"id": LEAF, "name": "투피스", "wholeCategoryName": "패션의류>여성의류>투피스", "last": True},
    {"id": "50000806", "name": "스커트", "wholeCategoryName": "패션의류>여성의류>스커트", "last": True},
    {"id": "50004737", "name": "주전자", "wholeCategoryName": "생활/건강>주방용품>주전자", "last": True},
]
BODY_400 = json.dumps({"code": "BAD_REQUEST", "message": "요청 파라미터가 올바르지 않습니다.", "invalidInputs": [
    {"name": "originProduct.leafCategoryId", "type": "NotValid", "message": "리프 카테고리ID 항목이 유효하지 않습니다."}]},
    ensure_ascii=False)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    NC.reset()
    from src.db import image_translate_queue_pg as st
    st.state_set(NC.STATE_KEY, {})
    monkeypatch.setenv("NAVER_IMAGE_UPLOAD", "0")
    yield
    NC.reset()
    st.state_set(NC.STATE_KEY, {})


@pytest.fixture
def tree(monkeypatch):
    calls = []
    monkeypatch.setattr(NC, "_fetch", lambda account="": calls.append(account) or ROWS)
    return calls


def _pleats(**over):
    src = ["黑色上衣", "黑色半裙"]
    pd = {"sku": "PLEATS-1", "title_ko": "플리츠 미니멀 여성 여름 세트", "sell_price_krw": 52000, "price": 168,
          "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"], "category_code": "CLO", "item_id": "it-1",
          "options": [{"name": "颜色分类", "values": src}, {"name": "尺码", "values": ["均码"]}],
          "skus": [{"sku_id": str(i), "spec": [v, "均码"], "stock": 5, "sell_price_krw": 52000} for i, v in enumerate(src)]}
    pd.update(over)
    return pd


def _upload(pd, monkeypatch, api=None):
    from src.channel_sync._channel_bridge import to_collected
    up = SS(account="chezgoga")
    sent = {}

    def fake(m, p, data=None):
        sent["d"] = data
        return api(m, p, data) if api else {"originProductNo": "77"}
    monkeypatch.setattr(up, "_api_request", fake)
    return up.upload_product(up.prepare_product(to_collected(pd))), sent.get("d")


def test_root_cause_category_map_was_top_level_and_is_gone():
    """옛 표(CLO→50000000)는 최상위 — 지웠다. prepare는 오너 지정만 싣고, 없으면 비운다(정본 매칭은 compose가)."""
    assert not hasattr(SS, "CATEGORY_MAP")
    from src.channel_sync._channel_bridge import to_collected
    prepared = SS(account="chezgoga").prepare_product(to_collected(_pleats()))
    assert prepared["category_id"] == "" and prepared["item_id"] == "it-1"


def test_unmatched_title_holds_category_unset_without_calling_naver(monkeypatch):
    """상품명으로 못 정하면 기본 리프로 보내지 않는다(등록 뒤 못 바꾼다) — 보류 + 「카테고리 지정 →」."""
    res, sent = _upload(_pleats(), monkeypatch)
    assert sent is None
    assert res["held"] is True and res["reason_code"] == "category_unset"
    assert "카테고리를 다시 지정하세요(카테고리 지정 →)" in res["error"]
    assert res["action_url"] == "/seller/collect/it-1/naver-category"


def test_parent_id_holds_category_not_leaf(monkeypatch, tree):
    res, sent = _upload(_pleats(naver_category_id=PARENT), monkeypatch)
    assert sent is None and res["reason_code"] == "category_not_leaf" and PARENT in res["error"]


def test_leaf_goes_out_with_8_combo_options(monkeypatch, tree):
    """오너가 리프를 고르면 그 ID 그대로 · 옵션 조합도 같이(Y7 캐너리 경로)."""
    res, sent = _upload(_pleats(naver_category_id=LEAF), monkeypatch)
    assert res["success"] is True
    op = sent["originProduct"]
    assert op["leafCategoryId"] == LEAF
    assert len(op["detailAttribute"]["optionInfo"]["optionCombinations"]) == 2


def test_tree_unavailable_does_not_block(monkeypatch):
    """트리를 못 받으면(키·네트워크) 판정 못 함 = 막지 않는다 — 네이버가 답한다."""
    monkeypatch.setattr(NC, "_fetch", lambda account="": None)
    res, sent = _upload(_pleats(naver_category_id=LEAF), monkeypatch)
    assert res["success"] is True and sent["originProduct"]["leafCategoryId"] == LEAF
    assert NC.leaf_state(PARENT) == "unknown"


def test_tree_cached_once_a_day(monkeypatch, tree):
    assert NC.leaf_state(LEAF) == "leaf" and NC.leaf_state(PARENT) == "not_leaf"
    assert NC.leaf_state("999") == "unknown_id"
    assert len(tree) == 1                                                     # 같은 날 다시 안 부른다
    NC.reset()
    assert NC.leaf_state(LEAF) == "leaf" and len(tree) == 1                   # 메모리 비워도 저장본(app_state)
    d = NC.tree()
    d["fetched_at"] -= NC.TTL_SEC + 1
    from src.db import image_translate_queue_pg as st
    st.state_set(NC.STATE_KEY, d)
    NC.reset()
    NC.tree()
    assert len(tree) == 2                                                     # 하루 지나면 다시 받는다


def test_400_invalid_inputs_is_action_not_retry(monkeypatch):
    """400 invalidInputs → naver_invalid_input · 필드별 조치 · 재시도 안내 없음."""
    def api(m, p, data):
        return {"error": "네이버 거부 — stage=POST /v2/products http_status=400 body=" + BODY_400,
                "http_status": 400, "body": BODY_400}
    res, _ = _upload(_pleats(naver_category_id=LEAF), monkeypatch, api=api)
    assert res["success"] is False and res["reason_code"] == "naver_invalid_input"
    assert res["error_lines"] == ["카테고리를 다시 지정하세요(카테고리 지정 →)"]
    assert res["action_url"] == "/seller/collect/it-1/naver-category"
    other = SS.invalid_input_lines(json.dumps({"invalidInputs": [{"name": "originProduct.salePrice", "message": "최소 10원"}]}))
    assert other == [("originProduct.salePrice", "originProduct.salePrice — 값 확인(최소 10원)")]
    assert SS.invalid_input_lines("not json") == [] and SS.invalid_input_lines('{"code":"X"}') == []


def test_dispatcher_shows_naver_invalid_input_without_retry_hint(monkeypatch):
    from src.seller_console.upload_dispatcher import UploadDispatcher, _RETRY_HINT
    from src.channel_sync import smartstore_uploader as SU
    from src.channel_sync._channel_bridge import ChannelUploadError

    def boom(pd):
        e = ChannelUploadError("스마트스토어 업로드 실패: 네이버가 입력값을 거부했어요",
                               lines=["카테고리를 다시 지정하세요(카테고리 지정 →)"], held=False)
        e.reason_code, e.action_url = "naver_invalid_input", "/seller/collect/it-1/naver-category"
        raise e
    monkeypatch.setattr(SU, "upload", boom)
    r = UploadDispatcher()._upload_smartstore({})
    assert r.error_code == "naver_invalid_input" and r.action_url.endswith("/naver-category")
    assert "다시 시도" not in (r.message + (r.hint or "")) and r.hint != _RETRY_HINT


def test_prevalidate_holds_before_naver(monkeypatch, tree):
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import smartstore_routing as SR
    monkeypatch.setattr(UD, "smartstore_approved", lambda store="": True)
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    pv = UD.UploadDispatcher()._prevalidate_market(_pleats(), "smartstore")
    assert pv.hold and pv.error_code == "category_unset" and pv.fixes == ["naver_category"]
    assert pv.action_url == "/seller/collect/it-1/naver-category"
    pv2 = UD.UploadDispatcher()._prevalidate_market(_pleats(naver_category_id=PARENT), "smartstore")
    assert pv2.error_code == "category_not_leaf"
    r = UD.UploadDispatcher()._dispatch_one(_pleats(), "smartstore")
    assert r.success is False and r.error_code == "category_unset" and r.action_url.endswith("/naver-category")
    ok = UD.UploadDispatcher()._prevalidate_market(_pleats(naver_category_id=LEAF), "smartstore")
    assert ok.error_code not in ("category_unset", "category_not_leaf")


@pytest.fixture
def item():
    from src.seller_console import collect_history_store as S
    return S.append(source="share", url="https://item.taobao.com/item.htm?id=7", seller_id="y7b-own",
                    title="플리츠 미니멀 여성 여름 세트", price="168", currency="CNY",
                    extra={"title_ko": "플리츠 미니멀 여성 여름 세트", "category_code": "CLO"})


def _client(uid="y7b-own"):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=f"{uid}@example.com", user_role="seller")
    return c


def test_picker_searches_leaves_and_saves_only_a_leaf(item, tree):
    c = _client()
    h = c.get(f"/seller/collect/{item}/naver-category?q=여성의류").get_data(as_text=True)
    assert "패션의류&gt;여성의류&gt;투피스" in h and f'value="{LEAF}"' in h
    assert 'value="50000167"' not in h                                         # 상위 카테고리는 고를 수 없다
    bad = c.post(f"/seller/collect/{item}/naver-category", data={"category_id": PARENT}).get_data(as_text=True)
    assert "상위 카테고리예요" in bad
    good = c.post(f"/seller/collect/{item}/naver-category", data={"category_id": LEAF}).get_data(as_text=True)
    assert "저장했어요 — 패션의류&gt;여성의류&gt;투피스" in good
    from src.seller_console import collect_history_store as S
    ex = json.loads(S.get(item, seller_ids={"y7b-own"})["extra_json"])
    assert ex["naver_category_id"] == LEAF
    from src.seller_console.product_builder import build_product
    assert build_product(S.get(item, seller_ids={"y7b-own"}))["naver_category_id"] == LEAF   # 등록·사전검증 몸통에 실린다


def test_picker_is_owner_scoped(item, tree):
    assert _client("stranger").get(f"/seller/collect/{item}/naver-category").status_code == 404
