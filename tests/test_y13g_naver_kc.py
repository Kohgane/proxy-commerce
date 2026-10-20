"""Y13-G 1(오너 2026-10-20) — 네이버 KC 인증 대상 카테고리는 KC 특례(해외구매대행)로 보내고, 칸이 비면 사전검증이 보류.

실측: BLACKHOLES 벽등(50003332) 셰고가·고코스모스 400 「KC 인증대상 인증 종류를 선택하셔야 합니다」 — 우리는
`certificationTargetExcludeContent: {}`(기본 FALSE = KC 대상)를 보냈다. 값 출처는 `src/uploaders/naver_kc.py` 머리말.
"""
import pytest

from src.uploaders import naver_kc as K


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_translate_queue_pg as st
    st.reset_for_tests()
    K._MEM.clear()
    yield
    st.reset_for_tests()
    K._MEM.clear()


class _Up:
    def __init__(self, resp):
        self.resp, self.calls = resp, 0

    def _api_request(self, method, path, data=None):
        self.calls += 1
        assert method == "GET" and path == "/v1/categories/50003332"
        return self.resp


KC_CAT = {"id": "50003332", "exceptionalCategories": ["KC_CERTIFICATION"],
          "certificationInfos": [{"id": 58, "name": "[생활용품]안전확인_국가인증", "kindTypes": ["KC_CERTIFICATION", "OVERSEAS"]}]}


def _payload(cid="50003332"):
    return {"originProduct": {"leafCategoryId": cid, "detailAttribute": {"certificationTargetExcludeContent": {}}}}


def test_kc_category_gets_overseas_exemption_and_is_cached():
    up = _Up(KC_CAT)
    p = _payload()
    assert K.apply(p, {"title": "벽등"}, up) is True
    assert p["originProduct"]["detailAttribute"]["certificationTargetExcludeContent"] == {
        "kcCertifiedProductExclusionYn": "KC_EXEMPTION_OBJECT", "kcExemptionType": "OVERSEAS"}
    assert "productCertificationInfos" not in p["originProduct"]["detailAttribute"]   # 인증 정보는 지어 넣지 않는다
    assert K.hold(p, True) is None
    K.apply(_payload(), {}, up)
    assert up.calls == 1                                         # 7일 캐시


def test_non_kc_category_is_left_as_template():
    p = _payload()
    assert K.apply(p, {}, _Up({"exceptionalCategories": []})) is False
    assert p["originProduct"]["detailAttribute"]["certificationTargetExcludeContent"] == {}
    assert K.hold(p, False) is None


def test_kc_category_with_exemption_switched_off_is_held():
    p = _payload()
    K.apply(p, {"kc_exemption": ""}, _Up(KC_CAT))
    h = K.hold(p, True)
    assert h and h["code"] == K.CODE and "KC" in h["line"]


def test_lookup_failure_does_not_block():
    p = _payload()
    assert K.apply(p, {}, _Up({"error": "토큰 실패"})) is None
    assert K.hold(p, None) is None


def test_uploader_build_payload_carries_the_exemption(monkeypatch):
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as U
    monkeypatch.setattr(K, "kc_required", lambda cid, up=None: True)
    up = U(account=None)
    body = up._build_product_payload({"title": "블랙홀 벽등", "price": 30000, "images": ["https://a/b.jpg"],
                                      "category_id": "50003332", "description_html": "<p>x</p>"})
    assert body["originProduct"]["detailAttribute"]["certificationTargetExcludeContent"]["kcExemptionType"] == "OVERSEAS"
    assert up.last_kc_required is True
