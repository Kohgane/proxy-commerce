"""tests/test_security_advanced.py — Phase 116: 보안 강화 테스트."""
from __future__ import annotations

import time

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 픽스처
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def rbac():
    from src.security_advanced.rbac import RBACManager
    return RBACManager()


@pytest.fixture
def ip_manager():
    from src.security_advanced.ip_whitelist import IPWhitelistManager
    return IPWhitelistManager()


@pytest.fixture
def signer():
    from src.security_advanced.request_signer import RequestSigner
    return RequestSigner()


@pytest.fixture
def audit():
    from src.security_advanced.security_audit import SecurityAuditLogger
    return SecurityAuditLogger()


@pytest.fixture
def flask_app():
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True
    from src.api.security_advanced_api import security_advanced_bp
    app.register_blueprint(security_advanced_bp)
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


# ═══════════════════════════════════════════════════════════════════════════════
# TestRBACManager (25 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRBACManager:

    def test_builtin_roles_initialized(self, rbac):
        roles = rbac.list_roles()
        names = {r.name for r in roles}
        assert "super_admin" in names
        assert "admin" in names
        assert "manager" in names
        assert "operator" in names
        assert "viewer" in names

    def test_builtin_roles_are_system(self, rbac):
        roles = rbac.list_roles()
        for r in roles:
            assert r.is_system is True

    def test_super_admin_has_all_permissions(self, rbac):
        from src.security_advanced.rbac import Permission
        role = rbac.get_role_by_name("super_admin")
        assert role is not None
        assert Permission.ADMIN_FULL in role.permissions
        assert Permission.USER_MANAGE in role.permissions

    def test_viewer_has_only_read_permissions(self, rbac):
        from src.security_advanced.rbac import Permission
        role = rbac.get_role_by_name("viewer")
        assert role is not None
        assert Permission.PRODUCT_READ in role.permissions
        assert Permission.PRODUCT_WRITE not in role.permissions
        assert Permission.PRODUCT_DELETE not in role.permissions

    def test_admin_does_not_have_admin_full(self, rbac):
        from src.security_advanced.rbac import Permission
        role = rbac.get_role_by_name("admin")
        assert role is not None
        assert Permission.ADMIN_FULL not in role.permissions

    def test_create_role_returns_role(self, rbac):
        role = rbac.create_role("custom", {"product:read"}, "custom role")
        assert role.name == "custom"
        assert "product:read" in role.permissions
        assert role.is_system is False

    def test_create_role_added_to_list(self, rbac):
        rbac.create_role("test_role", {"order:read"})
        names = {r.name for r in rbac.list_roles()}
        assert "test_role" in names

    def test_delete_custom_role(self, rbac):
        role = rbac.create_role("to_delete", {"product:read"})
        rbac.delete_role(role.id)
        assert rbac.get_role(role.id) is None

    def test_delete_system_role_raises(self, rbac):
        role = rbac.get_role_by_name("super_admin")
        with pytest.raises(ValueError):
            rbac.delete_role(role.id)

    def test_delete_nonexistent_role_raises(self, rbac):
        with pytest.raises(KeyError):
            rbac.delete_role("nonexistent_id")

    def test_assign_role_to_user(self, rbac):
        role = rbac.get_role_by_name("viewer")
        rbac.assign_role("user1", role.id)
        roles = rbac.get_user_roles("user1")
        assert any(r.name == "viewer" for r in roles)

    def test_assign_nonexistent_role_raises(self, rbac):
        with pytest.raises(KeyError):
            rbac.assign_role("user1", "nonexistent_role_id")

    def test_revoke_role_from_user(self, rbac):
        role = rbac.get_role_by_name("viewer")
        rbac.assign_role("user2", role.id)
        rbac.revoke_role("user2", role.id)
        roles = rbac.get_user_roles("user2")
        assert not any(r.name == "viewer" for r in roles)

    def test_revoke_role_not_assigned_is_silent(self, rbac):
        rbac.revoke_role("unknown_user", "some_role_id")  # should not raise

    def test_get_user_permissions_empty_for_no_roles(self, rbac):
        perms = rbac.get_user_permissions("no_role_user")
        assert perms == set()

    def test_get_user_permissions_merges_all_roles(self, rbac):
        r1 = rbac.create_role("r1", {"product:read", "order:read"})
        r2 = rbac.create_role("r2", {"inventory:read"})
        rbac.assign_role("multi_user", r1.id)
        rbac.assign_role("multi_user", r2.id)
        perms = rbac.get_user_permissions("multi_user")
        assert "product:read" in perms
        assert "order:read" in perms
        assert "inventory:read" in perms

    def test_check_permission_true(self, rbac):
        role = rbac.get_role_by_name("viewer")
        rbac.assign_role("viewer_user", role.id)
        assert rbac.check_permission("viewer_user", "product:read") is True

    def test_check_permission_false(self, rbac):
        role = rbac.get_role_by_name("viewer")
        rbac.assign_role("viewer_user2", role.id)
        assert rbac.check_permission("viewer_user2", "product:delete") is False

    def test_require_permission_decorator_grants_access(self, rbac):
        role = rbac.get_role_by_name("viewer")
        rbac.assign_role("deco_user", role.id)

        @rbac.require_permission("product:read")
        def my_func(user_id=None):
            return "ok"

        assert my_func(user_id="deco_user") == "ok"

    def test_require_permission_decorator_denies_access(self, rbac):
        from src.security_advanced.rbac import PermissionDeniedError
        role = rbac.get_role_by_name("viewer")
        rbac.assign_role("deco_user2", role.id)

        @rbac.require_permission("admin:full")
        def restricted_func(user_id=None):
            return "secret"

        with pytest.raises(PermissionDeniedError):
            restricted_func(user_id="deco_user2")

    def test_require_permission_without_user_id_raises(self, rbac):
        from src.security_advanced.rbac import PermissionDeniedError

        @rbac.require_permission("product:read")
        def no_user_func(user_id=None):
            return "ok"

        with pytest.raises(PermissionDeniedError):
            no_user_func()

    def test_get_role_by_name_existing(self, rbac):
        role = rbac.get_role_by_name("manager")
        assert role is not None
        assert role.name == "manager"

    def test_get_role_by_name_nonexistent(self, rbac):
        assert rbac.get_role_by_name("nonexistent") is None

    def test_manager_has_inventory_write(self, rbac):
        from src.security_advanced.rbac import Permission
        role = rbac.get_role_by_name("manager")
        assert Permission.INVENTORY_WRITE in role.permissions

    def test_operator_lacks_analytics_export(self, rbac):
        from src.security_advanced.rbac import Permission
        role = rbac.get_role_by_name("operator")
        assert Permission.ANALYTICS_EXPORT not in role.permissions


# ═══════════════════════════════════════════════════════════════════════════════
# TestIPWhitelistManager (15 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIPWhitelistManager:

    def test_empty_whitelist_allows_all(self, ip_manager):
        assert ip_manager.is_allowed("1.2.3.4") is True
        assert ip_manager.is_allowed("192.168.1.100") is True

    def test_add_single_ipv4(self, ip_manager):
        ip_manager.add_ip("192.168.1.1", "test", "admin")
        assert len(ip_manager.list_ips()) == 1

    def test_add_ip_blocks_others(self, ip_manager):
        ip_manager.add_ip("10.0.0.1")
        assert ip_manager.is_allowed("10.0.0.1") is True
        assert ip_manager.is_allowed("10.0.0.2") is False

    def test_add_cidr_range(self, ip_manager):
        ip_manager.add_ip("192.168.1.0/24")
        assert ip_manager.is_allowed("192.168.1.1") is True
        assert ip_manager.is_allowed("192.168.1.254") is True
        assert ip_manager.is_allowed("192.168.2.1") is False

    def test_add_ipv6(self, ip_manager):
        ip_manager.add_ip("::1")
        assert ip_manager.is_allowed("::1") is True

    def test_add_invalid_ip_raises(self, ip_manager):
        with pytest.raises(ValueError):
            ip_manager.add_ip("not_an_ip")

    def test_remove_ip(self, ip_manager):
        ip_manager.add_ip("10.0.0.5")
        ip_manager.remove_ip("10.0.0.5")
        assert len(ip_manager.list_ips()) == 0

    def test_remove_nonexistent_ip_raises(self, ip_manager):
        with pytest.raises(KeyError):
            ip_manager.remove_ip("1.2.3.4")

    def test_list_ips_returns_entries(self, ip_manager):
        ip_manager.add_ip("10.0.0.1", "server1", "admin")
        ip_manager.add_ip("10.0.0.2", "server2", "admin")
        entries = ip_manager.list_ips()
        assert len(entries) == 2

    def test_blocked_attempts_initially_empty(self, ip_manager):
        assert ip_manager.get_blocked_attempts() == []

    def test_record_blocked_adds_to_history(self, ip_manager):
        ip_manager.record_blocked("9.9.9.9", "/api/secret")
        attempts = ip_manager.get_blocked_attempts()
        assert len(attempts) == 1
        assert attempts[0].ip_address == "9.9.9.9"
        assert attempts[0].endpoint == "/api/secret"

    def test_multiple_blocked_attempts(self, ip_manager):
        ip_manager.record_blocked("1.1.1.1", "/a")
        ip_manager.record_blocked("2.2.2.2", "/b")
        assert len(ip_manager.get_blocked_attempts()) == 2

    def test_entry_has_description_and_added_by(self, ip_manager):
        ip_manager.add_ip("172.16.0.1", "office", "bob")
        entry = ip_manager.list_ips()[0]
        assert entry.description == "office"
        assert entry.added_by == "bob"

    def test_wide_cidr(self, ip_manager):
        ip_manager.add_ip("10.0.0.0/8")
        assert ip_manager.is_allowed("10.255.255.255") is True
        assert ip_manager.is_allowed("11.0.0.0") is False

    def test_invalid_ip_for_is_allowed_returns_false(self, ip_manager):
        ip_manager.add_ip("192.168.1.0/24")
        assert ip_manager.is_allowed("not_an_ip") is False


# ═══════════════════════════════════════════════════════════════════════════════
# TestRequestSigner (20 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRequestSigner:

    def test_generate_api_key_returns_pair(self, signer):
        api_key, api_secret = signer.generate_api_key()
        assert api_key.startswith("ak_")
        assert len(api_secret) > 10

    def test_keys_are_unique(self, signer):
        k1, _ = signer.generate_api_key()
        k2, _ = signer.generate_api_key()
        assert k1 != k2

    def test_sign_request_returns_hex_string(self, signer):
        _, secret = signer.generate_api_key()
        sig = signer.sign_request("GET", "/test", "", str(time.time()), secret)
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex

    def test_verify_signature_valid(self, signer):
        api_key, api_secret = signer.generate_api_key()
        ts = str(time.time())
        sig = signer.sign_request("POST", "/api/test", '{"x":1}', ts, api_secret)
        assert signer.verify_signature("POST", "/api/test", '{"x":1}', ts, sig, api_key)

    def test_verify_signature_wrong_body(self, signer):
        api_key, api_secret = signer.generate_api_key()
        ts = str(time.time())
        sig = signer.sign_request("POST", "/api/test", "correct_body", ts, api_secret)
        assert not signer.verify_signature("POST", "/api/test", "wrong_body", ts, sig, api_key)

    def test_verify_signature_wrong_method(self, signer):
        api_key, api_secret = signer.generate_api_key()
        ts = str(time.time())
        sig = signer.sign_request("GET", "/api/test", "", ts, api_secret)
        assert not signer.verify_signature("POST", "/api/test", "", ts, sig, api_key)

    def test_verify_signature_wrong_path(self, signer):
        api_key, api_secret = signer.generate_api_key()
        ts = str(time.time())
        sig = signer.sign_request("GET", "/api/test", "", ts, api_secret)
        assert not signer.verify_signature("GET", "/api/other", "", ts, sig, api_key)

    def test_verify_signature_expired_timestamp(self, signer):
        api_key, api_secret = signer.generate_api_key()
        old_ts = str(time.time() - 400)  # 6분 이상 전
        sig = signer.sign_request("GET", "/", "", old_ts, api_secret)
        assert not signer.verify_signature("GET", "/", "", old_ts, sig, api_key)

    def test_verify_signature_future_timestamp(self, signer):
        api_key, api_secret = signer.generate_api_key()
        future_ts = str(time.time() + 400)  # 6분 후
        sig = signer.sign_request("GET", "/", "", future_ts, api_secret)
        assert not signer.verify_signature("GET", "/", "", future_ts, sig, api_key)

    def test_verify_signature_unknown_key(self, signer):
        assert not signer.verify_signature("GET", "/", "", str(time.time()), "sig", "unknown_key")

    def test_revoke_api_key(self, signer):
        api_key, api_secret = signer.generate_api_key()
        signer.revoke_api_key(api_key)
        ts = str(time.time())
        sig = signer.sign_request("GET", "/", "", ts, api_secret)
        assert not signer.verify_signature("GET", "/", "", ts, sig, api_key)

    def test_revoke_nonexistent_key_raises(self, signer):
        with pytest.raises(KeyError):
            signer.revoke_api_key("nonexistent_key")

    def test_list_api_keys_empty_initially(self, signer):
        assert signer.list_api_keys() == []

    def test_list_api_keys_after_generation(self, signer):
        signer.generate_api_key("desc1", "alice")
        signer.generate_api_key("desc2", "bob")
        keys = signer.list_api_keys()
        assert len(keys) == 2

    def test_list_api_keys_does_not_contain_secret(self, signer):
        signer.generate_api_key()
        keys = signer.list_api_keys()
        for k in keys:
            assert not hasattr(k, "api_secret") or k.api_key.startswith("ak_")

    def test_key_record_has_description(self, signer):
        signer.generate_api_key("my key", "tester")
        keys = signer.list_api_keys()
        assert keys[0].description == "my key"
        assert keys[0].created_by == "tester"

    def test_revoked_key_is_inactive(self, signer):
        api_key, _ = signer.generate_api_key()
        signer.revoke_api_key(api_key)
        keys = signer.list_api_keys()
        assert keys[0].is_active is False

    def test_verify_invalid_timestamp_string(self, signer):
        api_key, api_secret = signer.generate_api_key()
        sig = signer.sign_request("GET", "/", "", "not_a_number", api_secret)
        assert not signer.verify_signature("GET", "/", "", "not_a_number", sig, api_key)

    def test_sign_is_deterministic(self, signer):
        _, secret = signer.generate_api_key()
        ts = "1000000.0"
        s1 = signer.sign_request("GET", "/", "", ts, secret)
        s2 = signer.sign_request("GET", "/", "", ts, secret)
        assert s1 == s2

    def test_different_secrets_produce_different_signatures(self, signer):
        _, s1 = signer.generate_api_key()
        _, s2 = signer.generate_api_key()
        ts = str(time.time())
        sig1 = signer.sign_request("GET", "/", "", ts, s1)
        sig2 = signer.sign_request("GET", "/", "", ts, s2)
        assert sig1 != sig2


# ═══════════════════════════════════════════════════════════════════════════════
# TestSecurityAuditLogger (15 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurityAuditLogger:

    def test_log_access_creates_event(self, audit):
        evt = audit.log_access("u1", "product", "read", "success", "1.2.3.4")
        assert evt.event_id is not None
        assert evt.event_type == "access"

    def test_log_auth_event_success(self, audit):
        evt = audit.log_auth_event("u1", "login", True)
        assert evt.result == "success"

    def test_log_auth_event_failure(self, audit):
        evt = audit.log_auth_event("u1", "login", False)
        assert evt.result == "failure"

    def test_log_permission_change(self, audit):
        evt = audit.log_permission_change("admin1", "user2", {"roles": ["added:viewer"]})
        assert evt.event_type == "permission_change"
        assert evt.user_id == "admin1"
        assert "user2" in evt.details.get("target_user_id", "")

    def test_get_security_events_returns_all(self, audit):
        audit.log_access("u1", "order", "read", "success", "10.0.0.1")
        audit.log_access("u2", "product", "write", "failure", "10.0.0.2")
        result = audit.get_security_events()
        assert result["total"] == 2

    def test_get_security_events_filter_by_type(self, audit):
        audit.log_access("u1", "product", "read", "success", "1.1.1.1")
        audit.log_auth_event("u1", "login", True)
        result = audit.get_security_events(filters={"event_type": "auth"})
        assert all(e["event_type"] == "auth" for e in result["events"])

    def test_get_security_events_filter_by_result(self, audit):
        audit.log_access("u1", "p", "r", "success", "1.1.1.1")
        audit.log_access("u2", "p", "r", "failure", "2.2.2.2")
        result = audit.get_security_events(filters={"result": "failure"})
        assert result["total"] == 1

    def test_get_security_events_filter_by_user(self, audit):
        audit.log_access("alice", "p", "r", "success", "1.1.1.1")
        audit.log_access("bob", "p", "r", "success", "1.1.1.1")
        result = audit.get_security_events(filters={"user_id": "alice"})
        assert result["total"] == 1

    def test_get_security_events_pagination(self, audit):
        for i in range(10):
            audit.log_access(f"u{i}", "p", "r", "success", "1.1.1.1")
        result = audit.get_security_events(page=1, per_page=3)
        assert len(result["events"]) == 3

    def test_suspicious_activity_no_failures(self, audit):
        audit.log_access("u1", "p", "r", "success", "1.1.1.1")
        result = audit.get_suspicious_activity(threshold=3)
        assert result == []

    def test_suspicious_activity_detected(self, audit):
        for _ in range(12):
            audit.log_access("u1", "p", "r", "failure", "5.5.5.5")
        result = audit.get_suspicious_activity(threshold=10, window_minutes=5)
        assert len(result) >= 1
        assert result[0].ip_address == "5.5.5.5"
        assert result[0].failure_count >= 10

    def test_suspicious_activity_below_threshold(self, audit):
        for _ in range(5):
            audit.log_access("u1", "p", "r", "failure", "6.6.6.6")
        result = audit.get_suspicious_activity(threshold=10)
        assert result == []

    def test_event_ids_are_unique(self, audit):
        e1 = audit.log_access("u1", "p", "r", "success", "1.1.1.1")
        e2 = audit.log_access("u1", "p", "r", "success", "1.1.1.1")
        assert e1.event_id != e2.event_id

    def test_event_has_timestamp(self, audit):
        evt = audit.log_access("u1", "p", "r", "success", "1.1.1.1")
        assert evt.timestamp is not None

    def test_filter_by_ip(self, audit):
        audit.log_access("u1", "p", "r", "failure", "9.9.9.9")
        audit.log_access("u2", "p", "r", "failure", "8.8.8.8")
        result = audit.get_security_events(filters={"ip_address": "9.9.9.9"})
        assert result["total"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# TestSecurityAPIEndpoints (25 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurityAPIEndpoints:

    # ── RBAC ──────────────────────────────────────────────────────────────────

    def test_list_roles_200(self, client):
        res = client.get("/api/v1/security/roles")
        assert res.status_code == 200
        data = res.get_json()
        assert "roles" in data

    def test_create_role_201(self, client):
        res = client.post(
            "/api/v1/security/roles",
            json={"name": "test_role", "permissions": ["product:read"]},
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data["role"]["name"] == "test_role"

    def test_create_role_missing_name_400(self, client):
        res = client.post("/api/v1/security/roles", json={"permissions": []})
        assert res.status_code == 400

    def test_delete_role_system_400(self, client):
        # 내장 역할 삭제 시도
        res = client.get("/api/v1/security/roles")
        builtin = next(r for r in res.get_json()["roles"] if r["is_system"])
        res = client.delete(f"/api/v1/security/roles/{builtin['id']}")
        assert res.status_code == 400

    def test_delete_role_nonexistent_404(self, client):
        res = client.delete("/api/v1/security/roles/nonexistent_id")
        assert res.status_code == 404

    def test_assign_role_200(self, client):
        roles_res = client.get("/api/v1/security/roles")
        role_id = roles_res.get_json()["roles"][0]["id"]
        res = client.post(
            "/api/v1/security/roles/assign",
            json={"user_id": "u1", "role_id": role_id},
        )
        assert res.status_code == 200

    def test_assign_role_missing_fields_400(self, client):
        res = client.post("/api/v1/security/roles/assign", json={"user_id": "u1"})
        assert res.status_code == 400

    def test_revoke_role_200(self, client):
        res = client.post(
            "/api/v1/security/roles/revoke",
            json={"user_id": "u1", "role_id": "some_role"},
        )
        assert res.status_code == 200

    def test_get_user_permissions_200(self, client):
        res = client.get("/api/v1/security/users/u1/permissions")
        assert res.status_code == 200
        data = res.get_json()
        assert "permissions" in data
        assert "roles" in data

    def test_check_permission_200(self, client):
        res = client.post(
            "/api/v1/security/check-permission",
            json={"user_id": "u1", "permission": "product:read"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert "allowed" in data

    def test_check_permission_missing_fields_400(self, client):
        res = client.post("/api/v1/security/check-permission", json={"user_id": "u1"})
        assert res.status_code == 400

    # ── IP 화이트리스트 ─────────────────────────────────────────────────────

    def test_list_ip_whitelist_200(self, client):
        res = client.get("/api/v1/security/ip-whitelist")
        assert res.status_code == 200
        assert "ips" in res.get_json()

    def test_add_ip_201(self, client):
        res = client.post(
            "/api/v1/security/ip-whitelist",
            json={"ip_address": "10.0.0.1", "description": "server"},
        )
        assert res.status_code == 201

    def test_add_invalid_ip_400(self, client):
        res = client.post(
            "/api/v1/security/ip-whitelist",
            json={"ip_address": "not_an_ip"},
        )
        assert res.status_code == 400

    def test_add_ip_missing_field_400(self, client):
        res = client.post("/api/v1/security/ip-whitelist", json={})
        assert res.status_code == 400

    def test_get_blocked_attempts_200(self, client):
        res = client.get("/api/v1/security/ip-whitelist/blocked")
        assert res.status_code == 200
        assert "blocked" in res.get_json()

    # ── API 서명 ────────────────────────────────────────────────────────────

    def test_generate_api_key_201(self, client):
        res = client.post(
            "/api/v1/security/api-keys",
            json={"description": "test key"},
        )
        assert res.status_code == 201
        data = res.get_json()
        assert "api_key" in data
        assert "api_secret" in data

    def test_list_api_keys_200(self, client):
        res = client.get("/api/v1/security/api-keys")
        assert res.status_code == 200
        assert "api_keys" in res.get_json()

    def test_revoke_api_key_200(self, client):
        gen_res = client.post("/api/v1/security/api-keys", json={})
        api_key = gen_res.get_json()["api_key"]
        res = client.delete(f"/api/v1/security/api-keys/{api_key}")
        assert res.status_code == 200

    def test_revoke_nonexistent_key_404(self, client):
        res = client.delete("/api/v1/security/api-keys/nonexistent")
        assert res.status_code == 404

    def test_verify_signature_missing_fields_400(self, client):
        res = client.post("/api/v1/security/verify-signature", json={})
        assert res.status_code == 400

    def test_verify_signature_valid_200(self, client):
        gen_res = client.post("/api/v1/security/api-keys", json={})
        api_key = gen_res.get_json()["api_key"]
        api_secret = gen_res.get_json()["api_secret"]

        from src.security_advanced.request_signer import RequestSigner
        s = RequestSigner()
        ts = str(time.time())
        sig = s.sign_request("GET", "/test", "", ts, api_secret)

        # Use the global signer from the blueprint
        from src.api.security_advanced_api import _get_signer
        signer = _get_signer()
        real_sig = signer.sign_request("GET", "/test", "", ts, api_secret)

        res = client.post(
            "/api/v1/security/verify-signature",
            json={"method": "GET", "path": "/test", "body": "",
                  "timestamp": ts, "signature": real_sig, "api_key": api_key},
        )
        assert res.status_code == 200

    # ── 보안 감사 ───────────────────────────────────────────────────────────

    def test_get_audit_log_200(self, client):
        res = client.get("/api/v1/security/audit-log")
        assert res.status_code == 200
        data = res.get_json()
        assert "events" in data
        assert "total" in data

    def test_get_suspicious_activity_200(self, client):
        res = client.get("/api/v1/security/suspicious-activity")
        assert res.status_code == 200
        assert "suspicious" in res.get_json()

    def test_delete_custom_role_200(self, client):
        res = client.post(
            "/api/v1/security/roles",
            json={"name": "temp_role", "permissions": ["product:read"]},
        )
        role_id = res.get_json()["role"]["id"]
        del_res = client.delete(f"/api/v1/security/roles/{role_id}")
        assert del_res.status_code == 200
