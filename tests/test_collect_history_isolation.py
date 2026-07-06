"""셀러별 수집 이력 격리 + 셀러 콘솔 인증 enforce 테스트.

멀티유저: 각 셀러는 자기 수집 항목만 보이고, 타 셀러 항목엔 접근 불가.
"""
import pytest

from src.seller_console import collect_history_store as chs


@pytest.fixture
def in_memory_store(monkeypatch):
    """인메모리(PG 미설정) 모드 + 저장소 초기화. (PG-only 전환으로 Sheets 경로 제거됨.)"""
    chs._in_memory.clear()
    yield chs
    chs._in_memory.clear()


class TestSellerIsolation:
    def test_list_items_filters_by_seller(self, in_memory_store):
        chs.append(source="manual", url="http://a.com/1", title="A", seller_id="alice")
        chs.append(source="manual", url="http://b.com/2", title="B", seller_id="bob")

        alice_items = chs.list_items(seller_id="alice")
        assert len(alice_items) == 1
        assert alice_items[0]["title"] == "A"

        bob_items = chs.list_items(seller_id="bob")
        assert len(bob_items) == 1
        assert bob_items[0]["title"] == "B"

    def test_list_items_none_returns_all(self, in_memory_store):
        """seller_id=None → 전체(레거시/단일 테넌트 하위호환)."""
        chs.append(source="manual", url="http://a.com/1", title="A", seller_id="alice")
        chs.append(source="manual", url="http://b.com/2", title="B", seller_id="bob")
        assert len(chs.list_items(seller_id=None)) == 2

    def test_get_enforces_ownership(self, in_memory_store):
        item_id = chs.append(source="manual", url="http://a.com/1", title="A", seller_id="alice")
        # 소유자는 조회 가능
        assert chs.get(item_id, seller_id="alice") is not None
        # 타 셀러는 차단
        assert chs.get(item_id, seller_id="bob") is None
        # seller_id 미지정 → 검사 안 함(하위호환)
        assert chs.get(item_id) is not None

    def test_summary_and_domains_respect_seller(self, in_memory_store):
        chs.append(source="manual", url="http://a.com/1", title="A", seller_id="alice")
        chs.append(source="bulk", url="http://b.com/2", title="B", seller_id="bob")
        assert chs.summary(seller_id="alice")["total"] == 1
        assert chs.distinct_domains(seller_id="bob") == ["b.com"]


class TestAuthEnforcement:
    def test_auth_off_allows_anonymous(self, monkeypatch):
        from src.seller_console import views
        monkeypatch.setattr(views, "_AUTH_ENABLED", False)
        app = __import__("src.order_webhook", fromlist=["app"]).app
        with app.test_request_context("/seller/"):
            assert views._check_auth() is True

    def test_auth_on_blocks_anonymous(self, monkeypatch):
        from src.seller_console import views
        monkeypatch.setattr(views, "_AUTH_ENABLED", True)
        app = __import__("src.order_webhook", fromlist=["app"]).app
        with app.test_request_context("/seller/"):
            assert views._check_auth() is False

    def test_auth_on_allows_logged_in(self, monkeypatch):
        from flask import session
        from src.seller_console import views
        monkeypatch.setattr(views, "_AUTH_ENABLED", True)
        app = __import__("src.order_webhook", fromlist=["app"]).app
        with app.test_request_context("/seller/"):
            session["user_id"] = "alice"
            assert views._check_auth() is True
            assert views._seller_id() == "alice"
