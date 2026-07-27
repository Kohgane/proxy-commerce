"""tests/test_v87_dashboard_auth_gate.py — /dashboard/* 관리자 인증 게이트 계약.

v87 S1.5 (P0): /dashboard/* 는 주문 화면에서 고객 실명·개인통관고유부호(PCC)를 렌더하는데
인증 검사가 없어 URL만 알면 비인증으로 열람 가능했다. 블루프린트 단일 게이트로 차단한다.

핵심 계약 — **라우트 목록을 하드코딩하지 않는다.** 앱 url_map에서 /dashboard 이하를 동적으로
수집하므로, 나중에 라우트가 추가돼도 이 테스트가 자동으로 커버한다(누락 방지).
"""

import pytest


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def app_with_dashboard(monkeypatch):
    """web_ui_bp만 올린 **격리 Flask 앱**.

    공용 `order_webhook.app`에 `session_transaction()`을 쓰면 세션 저장 경로가 시트 기반
    SECRET_KEY/자격증명 초기화를 건드려 **뒤에 도는 다른 테스트(test_billing 등)를 오염**시킨다.
    게이트는 블루프린트 before_request라 격리 앱에서 그대로 검증된다.
    """
    monkeypatch.setenv("DASHBOARD_WEB_UI_ENABLED", "1")
    from flask import Flask
    from src.dashboard.web_ui import web_ui_bp
    app = Flask(__name__)
    app.secret_key = "test-secret-v87"
    app.config["TESTING"] = True
    app.register_blueprint(web_ui_bp)
    return app


def _client_with_session(app, **session_values):
    client = app.test_client()
    if session_values:
        with client.session_transaction() as sess:
            sess.update(session_values)
    return client


@pytest.fixture
def anon_client(app_with_dashboard):
    """비인증(세션 없음) 클라이언트."""
    return _client_with_session(app_with_dashboard)


@pytest.fixture
def admin_client(app_with_dashboard):
    return _client_with_session(
        app_with_dashboard,
        user_id="admin-test", user_role="admin", user_email="admin@example.com",
    )


@pytest.fixture
def seller_client(app_with_dashboard):
    """로그인했지만 관리자가 아닌 세션."""
    return _client_with_session(
        app_with_dashboard,
        user_id="seller-test", user_role="seller", user_email="seller@example.com",
    )


def _dashboard_routes(app):
    """앱 라우트맵에서 /dashboard 이하 GET 경로를 동적 수집(하드코딩 금지)."""
    paths = []
    for rule in app.url_map.iter_rules():
        if not str(rule.rule).startswith("/dashboard"):
            continue
        if "GET" not in (rule.methods or set()):
            continue
        if "<" in str(rule.rule):  # 파라미터 라우트는 현재 없음 — 생기면 별도 처리
            continue
        paths.append(str(rule.rule))
    return sorted(set(paths))


# ---------------------------------------------------------------------------
# 게이트 계약
# ---------------------------------------------------------------------------

class TestDashboardAuthGate:
    def test_route_map_is_not_empty(self, app_with_dashboard):
        """수집 자체가 실패하면 아래 계약이 공허하게 통과하므로 먼저 못박는다."""
        routes = _dashboard_routes(app_with_dashboard)
        assert len(routes) >= 5, f"/dashboard 라우트 수집 실패: {routes}"

    def test_anonymous_gets_no_200_on_any_dashboard_route(self, anon_client, app_with_dashboard):
        """비인증으로 /dashboard 전 라우트 순회 — 어느 하나도 200이면 안 된다."""
        leaked = []
        for path in _dashboard_routes(app_with_dashboard):
            resp = anon_client.get(path)
            if resp.status_code == 200:
                leaked.append((path, resp.status_code))
        assert not leaked, f"비인증 접근이 200으로 새는 라우트: {leaked}"

    def test_anonymous_html_redirects_to_login_with_next(self, anon_client):
        resp = anon_client.get("/dashboard/orders")
        assert resp.status_code in (301, 302)
        loc = resp.headers.get("Location", "")
        assert "/auth/login" in loc
        assert "next=" in loc and "/dashboard/orders" in loc

    def test_next_param_is_encoded_so_query_survives(self, anon_client):
        """원래 쿼리가 있으면 next 값이 인코딩돼야 로그인 URL 파싱이 안 깨진다."""
        from urllib.parse import parse_qs, urlparse
        resp = anon_client.get("/dashboard/orders?status=paid")
        loc = resp.headers.get("Location", "")
        nxt = parse_qs(urlparse(loc).query).get("next", [""])[0]
        assert nxt == "/dashboard/orders?status=paid", f"next 훼손: {nxt!r} (from {loc!r})"

    def test_anonymous_json_gets_401_not_redirect(self, anon_client):
        resp = anon_client.get("/dashboard/orders?format=json")
        assert resp.status_code == 401
        assert resp.get_json().get("error") == "authentication_required"

    def test_anonymous_summary_json_gets_401(self, anon_client):
        resp = anon_client.get("/dashboard/summary")
        assert resp.status_code == 401

    def test_logged_in_non_admin_gets_403(self, seller_client):
        assert seller_client.get("/dashboard/orders").status_code == 403
        assert seller_client.get("/dashboard/orders?format=json").status_code == 403

    def test_admin_still_reaches_screens(self, admin_client, app_with_dashboard):
        """게이트가 관리자까지 막아버리면 화면이 죽는다 — 반대 방향도 못박는다."""
        from unittest.mock import patch
        # 외부 환율 API를 타지 않도록 고정(네트워크 의존 제거).
        with patch("src.dashboard.web_ui._get_fx_rates", return_value={"USDKRW": 1350.0}):
            for path in _dashboard_routes(app_with_dashboard):
                resp = admin_client.get(path)
                assert resp.status_code == 200, f"{path} → {resp.status_code} (관리자는 통과해야 함)"

    def test_fx_screens_survive_non_numeric_provider_fields(self, admin_client):
        """공급자가 timestamp 등 비수치 항목을 섞어 줘도 화면이 500으로 죽지 않는다."""
        from unittest.mock import patch
        fx = {"USDKRW": 1461.0, "timestamp": "2026-07-27T06:22:18+00:00"}
        with patch("src.dashboard.web_ui._get_fx_rates", return_value=fx):
            for path in ("/dashboard/", "/dashboard/fx", "/dashboard/summary"):
                assert admin_client.get(path).status_code == 200, path

    def test_pcc_not_reachable_anonymously(self, anon_client):
        """개인통관고유부호가 비인증 응답 본문에 실리지 않는다(회귀 방지 핵심)."""
        from unittest.mock import patch
        orders = [{
            "order_id": "10001", "customer_name": "홍길동",
            "pcc": "P123456789012", "status": "paid",
        }]
        with patch("src.dashboard.web_ui._load_orders", return_value=orders):
            for path in ("/dashboard/orders", "/dashboard/orders?format=json"):
                body = anon_client.get(path).data.decode("utf-8", "ignore")
                assert "P123456789012" not in body
                assert "홍길동" not in body


class TestDashboardNoStore:
    def test_admin_response_is_no_store(self, admin_client):
        """PCC가 실리는 화면 — 중간 캐시에 남기지 않는다."""
        resp = admin_client.get("/dashboard/orders")
        assert "no-store" in resp.headers.get("Cache-Control", "")

    def test_redirect_is_also_no_store(self, anon_client):
        resp = anon_client.get("/dashboard/orders")
        assert "no-store" in resp.headers.get("Cache-Control", "")
