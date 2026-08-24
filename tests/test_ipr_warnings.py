"""tests/test_ipr_warnings.py — 카나리 IPR 리스크 경고 계층(오너 지시).

blacklist(등록 차단)와 다른 층위 — 차단 아님·표기만, 판단은 오너. ①애플 호환 ②소명 진행 브랜드.
목록은 env/파일(하드코딩 금지). 오프라인·주입.
"""
from __future__ import annotations

from src.pipeline import register_pipe as RP


def test_apple_compat_warns_but_not_excluded():
    r = RP.build_source_review_row({"title_ko": "MagSafe 아이폰15 케이스 투명", "brand": "Craftly",
                                    "currency": "KRW", "price_original": 30000})
    kinds = [w["kind"] for w in r["warnings"]]
    assert "apple_compat" in kinds and r["excluded"] is False        # 경고만·차단 아님
    assert "사전승인 반려 전례" in [w["reason"] for w in r["warnings"] if w["kind"] == "apple_compat"][0]


def test_samsung_pixel_only_no_apple_warning():
    for t in ("갤럭시 S24 케이스", "Pixel 8 슬림 케이스", "삼성 갤럭시 버즈 케이스"):
        w = RP.assess_warnings(t, "", watch_brands=set())
        assert all(x["kind"] != "apple_compat" for x in w)           # 삼성/픽셀 전용 무경고


def test_apple_tokens_variants():
    for t in ("AirPods Pro 케이스", "에어팟 케이스", "iPad 파우치", "Apple Watch 밴드", "라이트닝 케이블"):
        w = RP.assess_warnings(t, "", watch_brands=set())
        assert any(x["kind"] == "apple_compat" for x in w), t


def test_watch_brand_warns_from_injected_list():
    r = RP.build_source_review_row({"title_ko": "TORRAS 방열 케이스", "brand": "TORRAS",
                                    "currency": "KRW", "price_original": 30000},
                                   watch_brands={"torras"})
    kinds = [w["kind"] for w in r["warnings"]]
    assert "ipr_watch" in kinds and r["excluded"] is False
    # 목록에 없으면 경고 0.
    r2 = RP.build_source_review_row({"title_ko": "무명 케이스", "brand": "무명",
                                     "currency": "KRW", "price_original": 30000}, watch_brands={"torras"})
    assert all(w["kind"] != "ipr_watch" for w in r2["warnings"])


def test_watch_brands_from_env_no_hardcode(monkeypatch):
    monkeypatch.setenv("IPR_WATCH_BRANDS", "TORRAS, ESR | Spigen")
    wb = RP.load_ipr_watch_brands()
    assert {"torras", "esr", "spigen"} <= wb
    # 미설정이면 빈 셋(하드코딩 0).
    monkeypatch.delenv("IPR_WATCH_BRANDS", raising=False)
    monkeypatch.setattr("os.path.isfile", lambda p: False)
    assert RP.load_ipr_watch_brands() == set()


def test_warnings_are_separate_layer_from_blacklist():
    # 취급제외(blacklist)와 경고는 별도 — 애플 호환이어도 excluded는 forbidden 여부로만.
    ok = RP.build_source_review_row({"title_ko": "아이폰 케이스", "currency": "KRW", "price_original": 10000})
    assert ok["excluded"] is False and any(w["kind"] == "apple_compat" for w in ok["warnings"])
    # 실제 금지어면 excluded True(경고와 무관).
    ex = RP.build_source_review_row({"title_ko": "아이폰 향수", "currency": "KRW", "price_original": 10000})
    assert ex["excluded"] is True                                   # 향수=금지 카테고리(차단)
