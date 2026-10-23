"""Y15 순찰 41(오너 2026-10-23) P0 — 마켓 자격 fail-closed · 실측 캐시 범위 · 접미 없는 스마트스토어 이름 · 가입 알림 권한 줄 · 토스 키 이름.

핀(오너): 오너 user_id 잡은 서버 자격이 보이고, 일반 셀러 잡은 안 보이고, 세션 role=admin이라도 user_id가 목록에 없으면 안 보인다.
"""
import os
import threading
import contextvars

import pytest

OWNER_KEY = "owner-coupang-access-key"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("COUPANG_ACCESS_KEY", OWNER_KEY)
    for k in ("ADMIN_EMAILS", "ADMIN_USER_IDS", "FAMILY_EMAILS"):
        monkeypatch.delenv(k, raising=False)
    from src.seller_console import market_credentials as mc
    mc._shared_cache.clear()
    yield
    mc._shared_cache.clear()


def _app():
    from src.order_webhook import app
    return app


def _seen_in(seller_id, session=None):
    """그 잡 주인으로 `seller_market_env`에 들어갔을 때 오너 키가 보이나(세션 있으면 그 요청 안에서)."""
    from src.seller_console import market_credentials as mc
    if session is None:
        with mc.seller_market_env(seller_id, ["coupang"]):
            return os.getenv("COUPANG_ACCESS_KEY") == OWNER_KEY
    with _app().test_request_context("/x", method="POST"):
        from flask import session as s
        s.update(session)
        with mc.seller_market_env(seller_id, ["coupang"]):
            return os.getenv("COUPANG_ACCESS_KEY") == OWNER_KEY


def test_owner_job_sees_server_creds_plain_seller_does_not():
    from src.auth.identity import OWNER_USER_ID
    assert _seen_in(OWNER_USER_ID) is True                       # 오너 잡(요청 밖 = 틱)
    assert _seen_in("") is True                                  # 주인 없는 서버 잡(오너 풀)
    assert _seen_in("plain-seller-1") is False                   # 일반 셀러 잡 — 요청 밖이어도 닫힌다
    assert os.getenv("COUPANG_ACCESS_KEY") == OWNER_KEY          # 격리는 그 컨텍스트 안에서만(전역 값은 그대로)


def test_session_admin_role_is_not_enough():
    s = {"user_id": "a07ee471-new", "user_email": "new@example.com", "user_role": "admin"}
    assert _seen_in("a07ee471-new", s) is False                  # 세션 role=admin이라도 user_id가 목록 밖이면 닫힘


def test_admin_user_ids_and_family_identity_open(monkeypatch):
    from src.db import user_identities_pg
    monkeypatch.setenv("ADMIN_USER_IDS", "admin-uid-9")
    assert _seen_in("admin-uid-9") is True
    monkeypatch.setenv("FAMILY_EMAILS", "fam@example.com")
    monkeypatch.setattr(user_identities_pg, "emails_for", lambda uid: ["fam@example.com"] if uid == "fam-uid" else [])
    assert _seen_in("fam-uid") is True                           # 가족 = 정체성 표의 로그인 이메일로
    assert _seen_in("someone-else") is False


def test_request_level_isolation_for_plain_seller_session():
    """그 사람이 `seller_market_env`를 안 거치는 화면·잡 스레드(copy_context)에서 os.environ을 직접 읽어도 오너 키가 없다."""
    from src.seller_console import market_credentials as mc
    app = _app()
    seen = {}
    with app.test_request_context("/seller/collect/history"):
        from flask import session
        session.update({"user_id": "plain-seller-2", "user_email": "p2@example.com", "user_role": "seller"})
        tok = mc.request_isolation_begin()
        seen["view"] = os.getenv("COUPANG_ACCESS_KEY")
        t = threading.Thread(target=contextvars.copy_context().run,
                             args=(lambda: seen.__setitem__("job", os.getenv("COUPANG_ACCESS_KEY")),))
        t.start()
        t.join()
        mc.request_isolation_end(tok)
        seen["after"] = os.getenv("COUPANG_ACCESS_KEY")
    assert seen == {"view": None, "job": None, "after": OWNER_KEY}
    from src.auth.identity import OWNER_USER_ID
    with app.test_request_context("/seller/collect/history"):
        from flask import session
        session.update({"user_id": OWNER_USER_ID, "user_email": "o@example.com"})
        assert mc.request_isolation_begin() is None              # 오너 요청은 영향 0
        assert os.getenv("COUPANG_ACCESS_KEY") == OWNER_KEY


def test_background_job_runs_under_item_owner(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    monkeypatch.setattr(D, "_item", lambda iid: ({"id": iid}, "plain-seller-3" if iid == "x-other" else ""))
    got = {}
    monkeypatch.setattr(O, "_run", lambda row: got.__setitem__(row["item_id"], os.getenv("COUPANG_ACCESS_KEY")) or {"ok": True})
    for iid in ("x-other", "x-owner"):
        with O._job_env({"op": "review_status", "item_id": iid}):
            O._run({"item_id": iid})
    assert got == {"x-other": None, "x-owner": OWNER_KEY}


def test_probe_cache_is_scoped_by_whose_keys(monkeypatch):
    """운영 10-22 07:58: 부팅 실측(오너 키)의 「전자서명 생성 실패(bcrypt)」가 10분 캐시로 새 가입자의 사전검증에 그대로 나갔다."""
    from src.seller_console import smartstore_routing as R
    from src.seller_console import market_credentials as mc
    monkeypatch.setattr(R, "_live_on", lambda: True)
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "srv-id")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "not-a-bcrypt-salt")
    R._probes.clear()
    srv = R.probe("", force=True)                                # 서버(오너) 키로 잰 결과
    assert srv["state"] == "fail" and "bcrypt" in srv["raw"]
    with mc.isolated_market_env({}):                             # 키 없는 일반 셀러
        mine = R.probe("")
    assert mine["state"] == "no_creds" and "bcrypt" not in mine["raw"]
    assert R.probe("")["raw"] == srv["raw"]                      # 오너 캐시는 셀러 결과로 덮이지 않았다
    R._probes.clear()


def test_plain_seller_prevalidate_says_add_your_key(monkeypatch):
    from src.seller_console import market_credentials as mc
    from src.seller_console import smartstore_routing as R
    from src.seller_console.upload_dispatcher import UploadDispatcher
    monkeypatch.setattr(R, "_live_on", lambda: True)
    R._probes.clear()
    with mc.isolated_market_env({}):
        r = UploadDispatcher().prevalidate({"title": "수납 바구니", "price": 10000, "images": ["https://e.x/a.jpg"]},
                                           ["smartstore"])[0]
    assert r.ok is False and r.message.startswith("마켓 연동에서 내 키를 넣어 주세요")
    assert "NAVER_" not in (r.message + r.hint)                  # 서버 env 이름을 일반 셀러에게 보이지 않는다
    R._probes.clear()


def test_unsuffixed_smartstore_never_reads_login_oauth_names(monkeypatch):
    """`NAVER_CLIENT_*`는 서버에서 네이버 로그인 OAuth 값 — 접미 없는 커머스 계정은 커머스 이름만 읽는다."""
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    from src.seller_console import market_credentials as mc
    monkeypatch.setenv("NAVER_CLIENT_ID", "login-oauth-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "login-oauth-secret")
    monkeypatch.delenv("NAVER_COMMERCE_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_COMMERCE_CLIENT_SECRET", raising=False)
    up = NaverSmartStoreUploader()
    assert (up.client_id, up.client_secret) == ("", "")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "commerce-id")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "$2a$04$commercesecret")
    assert NaverSmartStoreUploader().client_id == "commerce-id"
    # 셀러가 연동 화면 칸(NAVER_CLIENT_*)에 넣은 자기 키는 커머스 이름으로도 실려 그대로 쓰인다
    monkeypatch.setattr(mc, "credential_env", lambda sid, m: {"NAVER_CLIENT_ID": "seller-id",
                                                              "NAVER_CLIENT_SECRET": "$2a$04$sellersecret"})
    with mc.seller_market_env("plain-seller-4", ["smartstore"]):
        assert NaverSmartStoreUploader().client_id == "seller-id"


def test_signup_notice_line_shows_role_and_shared_verdict(monkeypatch):
    from src.auth import views as AV
    from src.auth.identity import OWNER_USER_ID
    assert AV._signup_access_line("new-uid", "seller", "n@example.com") == "권한: seller · 공유 판정: 아니오"
    assert AV._signup_access_line("new-uid", "admin", "n@example.com") == "권한: admin · 공유 판정: 아니오"
    assert AV._signup_access_line(OWNER_USER_ID, "admin", "o@example.com") == "권한: admin · 공유 판정: 예(owner)"
    monkeypatch.setenv("FAMILY_EMAILS", "fam@example.com")
    from src.db import user_identities_pg
    monkeypatch.setattr(user_identities_pg, "emails_for", lambda uid: ["fam@example.com"])
    assert AV._signup_access_line("fam-uid", "seller", "fam@example.com") == "권한: family · 공유 판정: 예(FAMILY_EMAILS)"


def test_pv_job_records_shared_reason_names_only():
    from src.seller_console import market_credentials as mc
    with _app().test_request_context("/x", method="POST"):
        from flask import session
        session.update({"user_id": "plain-seller-5", "user_role": "admin"})
        assert mc.fallback_reason() == "not_shared"
        with mc.isolated_market_env({}):
            assert mc.fallback_reason() == "overlay"
    assert mc.fallback_reason() == "no_request"


# ── G. 토스 비밀키 이름 한 벌 ────────────────────────────────────────────────────

def test_toss_secret_env_is_one_name_with_old_fallback(monkeypatch):
    from src.payments.toss_client import TossPaymentsClient
    monkeypatch.delenv("TOSS_PAYMENTS_SECRET_KEY", raising=False)
    monkeypatch.setenv("TOSS_SECRET_KEY", "test_sk_new")
    assert TossPaymentsClient()._secret_key == "test_sk_new"
    monkeypatch.delenv("TOSS_SECRET_KEY")
    monkeypatch.setenv("TOSS_PAYMENTS_SECRET_KEY", "test_sk_old")
    assert TossPaymentsClient()._secret_key == "test_sk_old"     # 옛 이름은 폴백만


def test_billing_test_mode_badge_and_no_fake_activation(monkeypatch):
    from src.seller_console import billing_store as bs
    monkeypatch.setenv("TOSS_CLIENT_KEY", "test_ck_x")
    monkeypatch.setenv("TOSS_SECRET_KEY", "test_sk_x")
    c = _app().test_client()
    html = c.get("/seller/billing").get_data(as_text=True)
    assert "data-pay-test-mode" in html and "테스트 결제 모드" in html
    bs.create_pending_payment(seller_id="default", plan="plus", order_id="o-test-1", amount=19000)
    import src.payments.toss as T
    monkeypatch.setattr(T, "confirm_payment", lambda **kw: {"ok": True, "status": "DONE"})
    r = c.get("/seller/billing/success?paymentKey=pk&orderId=o-test-1&amount=19000")
    assert r.status_code == 302 and "%ED%85%8C%EC%8A%A4%ED%8A%B8" in r.headers["Location"]   # 「테스트」 안내
    assert bs.get_account("default")["plan"] != "plus"           # 테스트 결제로 요금제가 바뀌지 않는다
    monkeypatch.setenv("TOSS_CLIENT_KEY", "live_ck_x")
    monkeypatch.setenv("TOSS_SECRET_KEY", "live_sk_x")
    assert "data-pay-test-mode" not in c.get("/seller/billing").get_data(as_text=True)
