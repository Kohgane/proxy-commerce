"""Y7-E(오너 폰 2026-10-08 23:37 KST, 플리츠 세트 셰고가 사전검증) — 카테고리 매핑을 리프 이름이 아니라 **전체 경로**로.

증거(운영 app_state `naver_cat_suggest` 원문): 쿠팡 예측 「여성 캐주얼 세트」 → 후보
「식품>통조림/캔>세트 · 출산/육아>신생아의류>세트 · 스포츠/레저>등산>등산의류>세트」 전부 0.6225 — 끝 낱말 「세트」만 적중.
아래 네이버 리프는 운영 저장본(GET /v1/categories, 23:37 KST)에서 그대로 옮긴 것.
"""
from __future__ import annotations

import pytest

from src.db import image_translate_queue_pg as ST
from src.uploaders import coupang_categories as CC
from src.uploaders import naver_categories as NC

REAL = {
    "50000816": "패션의류>여성의류>정장세트", "50000778": "패션의류>여성의류>코디세트", "50000808": "패션의류>여성의류>스커트",
    "50000807": "패션의류>여성의류>원피스", "50000803": "패션의류>여성의류>티셔츠", "50000810": "패션의류>여성의류>바지",
    "50000818": "패션의류>여성의류>트레이닝복", "50021360": "패션의류>여성의류>아우터>재킷",
    "50012020": "식품>통조림/캔>세트", "50005307": "출산/육아>신생아의류>세트", "50002633": "스포츠/레저>등산>등산의류>세트",
}
ROWS = [{"id": k, "name": v.split(">")[-1], "wholeCategoryName": v, "last": True} for k, v in REAL.items()]
PLEATS = "플리츠 미니멀 여성 여름 세트, 디자인 감각이 돋보이는 언밸런스 컷팅 주름 상의와 스커트 투피스 세트"
CP_PATH = "패션의류잡화>여성패션>여성의류>정장/세트>여성 캐주얼 세트"


class FakeCoupang:
    access_key, secret_key = "ak", "sk"

    def __init__(self, name="여성 캐주얼 세트", cid="80001"):
        self.name, self.cid = name, cid

    def predict(self, product_name, description=""):
        return {"id": self.cid, "name": self.name, "type": "SUCCESS", "why": ""}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    NC.reset()
    CC.reset()
    for k in (NC.STATE_KEY, NC.SUGGEST_KEY, CC.STATE_KEY):
        ST.state_set(k, {})
    monkeypatch.setattr(NC, "BACKGROUND", False)
    monkeypatch.setattr(CC, "BACKGROUND", False)
    monkeypatch.setattr(NC, "_fetch", lambda account="": ROWS)
    import src.channel_sync.coupang_uploader as CU
    monkeypatch.setattr(CU, "make_uploader", lambda: (FakeCoupang(), ""))
    yield
    NC.reset()
    CC.reset()
    for k in (NC.STATE_KEY, NC.SUGGEST_KEY, CC.STATE_KEY):
        ST.state_set(k, {})


def _with_coupang_paths(monkeypatch, paths):
    monkeypatch.setattr(CC, "_fetch", lambda: paths)


def test_pleats_auto_to_women_set_with_full_path(monkeypatch):
    """쿠팡 경로가 있으면 플리츠 세트는 「패션의류>여성의류>…세트」로 자동 — 식품·출산육아·스포츠는 1단계에서 탈락."""
    _with_coupang_paths(monkeypatch, {"80001": CP_PATH})
    s = NC.compute_suggestion({"title_ko": PLEATS})
    assert s["coupang_path"] == CP_PATH
    assert s["id"] in ("50000816", "50000778") and s["name"].startswith("패션의류>여성의류>"), s
    assert s["name"].endswith("세트")
    assert NC.pick({"title_ko": PLEATS}) == (s["id"], "coupang")


def test_top_level_gate_drops_other_branches(monkeypatch):
    _with_coupang_paths(monkeypatch, {"80001": CP_PATH})
    names = [c["name"] for c in NC.rank(CP_PATH, PLEATS, limit=10)]
    assert names and all(n.startswith("패션의류>") for n in names)
    assert NC.allowed_tops(CP_PATH) == ["패션의류", "패션잡화"]
    assert NC.allowed_tops("여성 캐주얼 세트") is None                  # 경로가 없으면 게이트 없음(리프 이름만)


def test_generic_leaf_word_has_zero_weight():
    """「세트」「기타」「용품」은 가중치 0 — 끝 낱말 「세트」만 같은 리프는 0점."""
    for whole in ("식품>통조림/캔>세트", "출산/육아>신생아의류>세트", "스포츠/레저>등산>등산의류>세트"):
        assert NC.score_path("여성 캐주얼 세트", whole, PLEATS) == 0.0, whole
    assert [t for t, _w in NC.path_tokens("생활용품>욕실용품>기타")] == ["생활용품", "욕실용품"]
    assert NC._core("정장세트") == "정장" and NC._core("주방용품") == "주방"


def test_the_2337_failure_no_longer_offers_food_babies_sports(monkeypatch):
    """23:37 그대로(쿠팡 경로 표 없이 리프 이름만) — 예전 후보 3개는 0점이라 안 나오고, 근거 없으면 category_unset."""
    _with_coupang_paths(monkeypatch, {})
    s = NC.compute_suggestion({"title_ko": PLEATS})
    assert not any("식품" in c["name"] or "출산" in c["name"] or "스포츠" in c["name"] for c in s.get("candidates") or [])
    assert NC.hold({"title_ko": PLEATS})["code"] == NC.REASON_UNSET


def test_candidates_all_different_tops_are_not_offered(monkeypatch):
    """후보 3개가 전부 다른 1단계면 후보 자체를 내지 않는다 → category_unset."""
    _with_coupang_paths(monkeypatch, {})
    monkeypatch.setattr(NC, "rank", lambda cp, title="", limit=3: [
        {"id": "1", "name": "식품>통조림/캔>세트", "score": 0.4}, {"id": "2", "name": "출산/육아>신생아의류>세트", "score": 0.4},
        {"id": "3", "name": "스포츠/레저>등산>등산의류>세트", "score": 0.4}])
    s = NC.compute_suggestion({"title_ko": PLEATS})
    assert s["candidates"] == [] and s["id"] == "" and "1단계부터 갈려요" in s["why"]
    h = NC.hold({"title_ko": PLEATS})
    assert h["code"] == NC.REASON_UNSET


def test_same_top_candidates_still_offered(monkeypatch):
    _with_coupang_paths(monkeypatch, {})
    monkeypatch.setattr(NC, "rank", lambda cp, title="", limit=3: [
        {"id": "1", "name": "패션의류>여성의류>정장세트", "score": 0.4}, {"id": "2", "name": "패션의류>여성의류>코디세트", "score": 0.38}])
    s = NC.compute_suggestion({"title_ko": PLEATS})
    assert [c["id"] for c in s["candidates"]] == ["1", "2"]


def test_flatten_coupang_tree_shapes():
    tree = {"displayItemCategoryCode": 0, "name": "ROOT", "child": [
        {"displayItemCategoryCode": 1001, "name": "패션의류잡화", "child": [
            {"displayItemCategoryCode": 1002, "name": "여성패션", "child": [
                {"displayItemCategoryCode": 80001, "name": "여성 캐주얼 세트", "child": []}]}]}]}
    assert CC.flatten(tree)["80001"] == "패션의류잡화>여성패션>여성 캐주얼 세트"
    alt = [{"code": "7", "name": "가전디지털", "children": [{"id": "8", "name": "모니터"}]}]
    assert CC.flatten(alt) == {"7": "가전디지털", "8": "가전디지털>모니터"}


def test_old_suggestion_cache_is_not_reused():
    """예전 규칙으로 기억한 「식품… 후보」(v1 키)는 읽지 않는다."""
    ST.state_set("naver_cat_suggest", {PLEATS: {"id": "", "candidates": [{"id": "50012020", "name": "식품>통조림/캔>세트"}]}})
    try:
        assert NC.SUGGEST_KEY != "naver_cat_suggest"
        assert NC._suggest_cache_get(PLEATS) is None
    finally:
        ST.state_set("naver_cat_suggest", {})


def test_admin_table_runs_in_background_and_exports_csv(monkeypatch):
    """724건 표 — 오너가 관리자 화면에서 누르면 백그라운드로 계산, 표·CSV로 본다(쿠팡 키는 서버에만)."""
    _with_coupang_paths(monkeypatch, {"80001": CP_PATH})
    from src.dashboard import admin_views as AV
    from src.utils import bg_job
    bg_job.reset()
    monkeypatch.setattr(AV, "_ncat_table_titles", lambda limit=1000: [(PLEATS, 3), ("원목 리빙박스 대형", 1)])
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="admin-1", user_email="admin@example.com", user_role="admin")
    r = c.post("/admin/diagnostics/naver-category-table")
    assert r.status_code == 200
    st = bg_job.join("naver-category-table")
    assert st["state"] == "done", st
    h = c.get("/admin/diagnostics/naver-category-table").get_data(as_text=True)
    summary = h.split('data-role="ncat-summary">')[1].split("</div>")[0]
    assert "상품명 2" in summary and "자동 2" in summary, summary          # 가짜 예측은 두 상품명 모두 같은 경로
    assert "패션의류&gt;여성의류&gt;" in h
    csv = c.get("/admin/diagnostics/naver-category-table?format=csv").get_data(as_text=True)
    assert CP_PATH in csv and "auto" in csv
    ST.state_set(AV._NCAT_TABLE_KEY, {})
