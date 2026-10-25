"""Y15 순찰 95(오너 2026-10-25) — 가족 고정 묶음(`FAMILY_MARKET_BUNDLE`) · 막힌 화면의 계정 번호 안내 · self-host.

A-3: 가족(`FAMILY_EMAILS` 판정) 사용자의 마켓을 묶음 하나로 — 화면엔 그 줄만, 서버는 묶음 밖을 403. 설정이 없으면 지금 그대로.
A-4: 「키를 넣어 주세요」·403에 「가족·관리자인데 이게 보이면 이 계정 번호(앞 8자리)를 오너에게」.
"""
from contextlib import contextmanager


def _fresh(monkeypatch, family="fam@example.com", bundle="woojoo"):
    from src.seller_console import market_credentials as mc
    monkeypatch.setattr(mc, "_shared_cache", {})
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    monkeypatch.setenv("FAMILY_EMAILS", family)
    if bundle is None:
        monkeypatch.delenv("FAMILY_MARKET_BUNDLE", raising=False)
    else:
        monkeypatch.setenv("FAMILY_MARKET_BUNDLE", bundle)


@contextmanager
def _as(uid, email):
    from flask import session
    from src.order_webhook import app
    with app.test_request_context("/seller/collect/upload", method="POST"):
        session["user_id"], session["user_email"], session["user_role"] = uid, email, "seller"
        yield


def test_bundle_is_only_for_family_and_only_when_set(monkeypatch):
    from src.seller_console import market_pick as mp
    _fresh(monkeypatch)
    with _as("fam-1", "fam@example.com"):
        assert mp.family_bundle() == ("coupang:woojoo", "smartstore:gocosmos")
    with _as("someone", "x@example.com"):
        assert mp.family_bundle() == ()                          # 가족 아님
    from src.auth.identity import OWNER_USER_ID
    with _as(OWNER_USER_ID, "owner@example.com"):
        assert mp.family_bundle() == ()                          # 오너는 고정 안 함
    _fresh(monkeypatch, bundle=None)
    with _as("fam-1", "fam@example.com"):
        assert mp.family_bundle() == ()                          # 설정 없음 = 지금 그대로
    _fresh(monkeypatch, bundle="nope")
    with _as("fam-1", "fam@example.com"):
        assert mp.family_bundle() == ()                          # 모르는 묶음 이름은 무시


def test_checks_follow_the_bundle_over_last_and_setting(monkeypatch):
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    from src.seller_console import market_pick as mp
    _fresh(monkeypatch)
    rows = [{"code": c, "connected": True} for c in ("coupang:gogane", "coupang:woojoo", "smartstore:chezgoga",
                                                    "smartstore:gocosmos")]
    mp.save_last("shared", ["coupang:gogane", "smartstore:chezgoga"])
    with _as("fam-1", "fam@example.com"):
        pick = mp.apply_checks(rows, "shared", shared=True)
    assert pick == {"source": "family_bundle", "codes": ["coupang:woojoo", "smartstore:gocosmos"]}
    assert mp.source_label("family_bundle").startswith("가족 계정")


def test_server_refuses_markets_outside_the_bundle_with_the_hint(monkeypatch):
    from src.seller_console import views as V
    _fresh(monkeypatch)
    with _as("fam-12345678-x", "fam@example.com"):
        assert V._account_codes_forbidden(["coupang:woojoo", "smartstore:gocosmos"]) is None
        resp, code = V._account_codes_forbidden(["coupang:gogane", "coupang:woojoo"])
        js = resp.get_json()
    assert code == 403 and js["markets"] == ["coupang:gogane"]
    assert "쿠팡 우주대행 · 스마트스토어 고코스모스" in js["error"] and "coupang:" not in js["error"]
    assert "앞 8자리 fam-1234" in js["hint"]
    _fresh(monkeypatch, bundle=None)
    with _as("fam-12345678-x", "fam@example.com"):
        assert V._account_codes_forbidden(["coupang:gogane"]) is None     # 설정 없음 = 예전 그대로


def test_no_key_wall_carries_the_account_number(monkeypatch):
    from src.seller_console.upload_dispatcher import PrevalidationResult, UploadDispatcher
    _fresh(monkeypatch, family="", bundle=None)
    monkeypatch.setattr(UploadDispatcher, "_prevalidate_market",
                        lambda self, pd, base: PrevalidationResult(market=base, ok=False, error_code="token_missing",
                                                                   message="마켓 연동에서 내 키를 넣어 주세요",
                                                                   hint="키를 넣으면 이 사전검증을 다시 눌러 주세요."))
    with _as("a07afb1b-72f9", "kgp-cn-test@example.com"):
        r = UploadDispatcher().prevalidate({"title": "x"}, ["coupang"])[0]
        shop = UploadDispatcher().prevalidate({"title": "x"}, ["shopify"])[0]
    assert r.hint.startswith("키를 넣으면 이 사전검증을 다시 눌러 주세요 · ") and "앞 8자리 a07afb1b" in r.hint
    assert "가족·관리자인데" in r.hint
    assert "앞 8자리" not in (shop.hint or "")                   # 오너와 함께 쓰는 마켓(쿠팡·스스) 줄에만


def test_cn_test_account_is_out_of_aggregates():
    from src.utils.test_accounts import NOT_TEST_SQL, is_test_account
    assert is_test_account("a07afb1b-72f9-4127-a0e9-682ed13aab39") and not is_test_account("a07ee471-2095")
    assert "'a07afb1b-72f9-4127-a0e9-682ed13aab39'" in NOT_TEST_SQL and "'dev'" in NOT_TEST_SQL


def test_no_cdn_or_google_font_left_in_pages_and_csp_is_self():
    import pathlib
    import re
    bad = re.compile(r"cdn\.jsdelivr\.net|fonts\.googleapis\.com|fonts\.gstatic\.com|google\.com/s2/favicons")
    hits = [str(p) for p in pathlib.Path("src").rglob("*")
            if p.suffix in (".html", ".css", ".js") and "vendor" not in p.parts and bad.search(p.read_text(encoding="utf-8"))]
    assert hits == []
    from src.middleware import security as S
    assert "jsdelivr" not in S._CSP_HTML_PAGES and "googleapis" not in S._CSP_HTML_PAGES
    for f in ("bootstrap-5.3.3/bootstrap.min.css", "bootstrap-5.3.3/bootstrap.bundle.min.js",
              "bootstrap-icons-1.11.3/fonts/bootstrap-icons.woff2", "noto-serif-kr/noto-serif-kr.css",
              "pretendard-1.3.9/pretendardvariable-dynamic-subset.css", "chartjs-4.4.0/chart.umd.min.js"):
        assert pathlib.Path("src/static/vendor", f).is_file(), f


def test_favicon_passthrough_validates_domain_and_caches(monkeypatch):
    from src.order_webhook import app
    from src.seller_console import views as V
    calls = []

    class _R:
        status_code, content = 200, b"\x89PNG-fake"

    import requests
    monkeypatch.setattr(requests, "get", lambda url, params=None, timeout=None: calls.append(params) or _R())
    monkeypatch.setattr(V, "_FAV_CACHE", {})
    c = app.test_client()
    assert c.get("/seller/fav/taobao.com.png").data == b"\x89PNG-fake"
    assert c.get("/seller/fav/taobao.com.png").status_code == 200 and len(calls) == 1      # 두 번째는 캐시
    assert c.get("/seller/fav/not a domain.png").status_code == 404 and len(calls) == 1
