"""Y13-H 1(오너 2026-10-20) — KC 특례로 보낸 상품(KC 대상 카테고리)은 본문 맨 위에 구매대행 고지.

문구: 전기용품 및 생활용품 안전관리법 제36조(구매대행업자 고지) — 국가기술표준원 안내의 KC마크 없는 안전관리대상 제품 게시 문구
「이 제품은 구매대행을 통하여 유통되는 제품임」 · 「이 제품은 전기용품 및 생활용품 안전관리법에 따른 안전관리대상 제품임」.
"""
import pytest

from src.seller_console.notice_texts import KC_AGENT_LINES, PURCHASE_AGENT_NOTICE
from src.uploaders import naver_kc as K


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_translate_queue_pg as st
    st.reset_for_tests()
    K._MEM.clear()
    yield
    st.reset_for_tests()
    K._MEM.clear()


def test_notice_is_the_law_text_and_added_once():
    assert KC_AGENT_LINES == ("이 제품은 구매대행을 통하여 유통되는 제품임",
                              "이 제품은 전기용품 및 생활용품 안전관리법에 따른 안전관리대상 제품임")
    once = K.with_notice("<p>본문</p>")
    assert once.startswith('<div class="kgp-agent-notice">') and once.endswith("<p>본문</p>")
    assert K.with_notice(once) == once
    assert K.with_notice("<p>" + PURCHASE_AGENT_NOTICE + "</p>x").count("구매대행을 통하여") == 1   # Y10-B 고지가 이미 있으면 그대로


def test_register_body_gets_notice_only_for_kc_exempt(monkeypatch):
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as U
    pd = {"title": "블랙홀 벽등", "price": 30000, "images": ["https://a/b.jpg"], "category_id": "50003332",
          "description_html": "<p>상세</p>"}
    monkeypatch.setattr(K, "kc_required", lambda cid, up=None: True)
    body = U(account=None)._build_product_payload(dict(pd))
    assert "구매대행을 통하여 유통되는 제품임" in body["originProduct"]["detailContent"]
    monkeypatch.setattr(K, "kc_required", lambda cid, up=None: False)
    body = U(account=None)._build_product_payload(dict(pd))
    assert "구매대행을 통하여" not in body["originProduct"]["detailContent"]


def test_detail_resend_adds_notice_for_kc_category(monkeypatch):
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as U
    sent = {}

    class Up(U):
        def __init__(self):
            pass

        def _api_request(self, method, path, data=None):
            if method == "GET" and "origin-products" in path:
                return {"originProduct": {"statusType": "SALE", "leafCategoryId": "50003332", "detailContent": "옛 본문"},
                        "smartstoreChannelProduct": {}}
            if method == "PUT":
                sent.update(data)
                return {"originProductNo": 1}
            raise AssertionError(path)
    monkeypatch.setattr(K, "kc_required", lambda cid, up=None: cid == "50003332")
    out = Up().update_detail_content("13762366733", "<p>새 본문</p>")
    assert out["success"] and sent["originProduct"]["detailContent"].startswith('<div class="kgp-agent-notice">')
