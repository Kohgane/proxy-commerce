"""tests/test_market_credentials.py — 셀프서비스 마켓 연결(셀러별 자격증명) 검증.

저장/조회/암호화/마스킹/주입/라우트를 고정한다. SaaS 다중 셀러 대비 기능.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_CRED_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret")
    monkeypatch.delenv("MARKET_CRED_ENC_KEY", raising=False)
    from src.seller_console import market_credentials as module
    importlib.reload(module)
    return module


class TestStoreRoundtrip:
    def test_save_and_get(self, mc):
        mc.save("seller1", "coupang", {
            "COUPANG_ACCESS_KEY": "ak123456",
            "COUPANG_SECRET_KEY": "sk123456",
            "COUPANG_VENDOR_ID": "A001",
        })
        got = mc.get("seller1", "coupang")
        assert got["COUPANG_ACCESS_KEY"] == "ak123456"
        assert got["COUPANG_VENDOR_ID"] == "A001"

    def test_save_filters_unknown_and_empty(self, mc):
        saved = mc.save("seller1", "elevenst", {
            "ELEVENST_API_KEY": "key1",
            "UNKNOWN_FIELD": "x",
            "ELEVENST_DISP_CTGR_NO": "  ",
        })
        assert saved == {"ELEVENST_API_KEY": "key1"}

    def test_delete(self, mc):
        mc.save("seller1", "coupang", {"COUPANG_ACCESS_KEY": "a", "COUPANG_SECRET_KEY": "b", "COUPANG_VENDOR_ID": "c"})
        assert mc.delete("seller1", "coupang") is True
        assert mc.get("seller1", "coupang") == {}
        assert mc.delete("seller1", "coupang") is False

    def test_per_seller_isolation(self, mc):
        mc.save("sellerA", "elevenst", {"ELEVENST_API_KEY": "AAA"})
        mc.save("sellerB", "elevenst", {"ELEVENST_API_KEY": "BBB"})
        assert mc.get("sellerA", "elevenst")["ELEVENST_API_KEY"] == "AAA"
        assert mc.get("sellerB", "elevenst")["ELEVENST_API_KEY"] == "BBB"

    def test_unknown_market_raises(self, mc):
        with pytest.raises(KeyError):
            mc.save("seller1", "gmarket", {"X": "y"})


class TestEncryption:
    def test_secret_not_plaintext_on_disk(self, mc, tmp_path):
        mc.save("seller1", "shopify", {
            "SHOPIFY_SHOP": "x.myshopify.com",
            "SHOPIFY_AUTO_TOKEN": "atk_supersecret_value",
        })
        # 디스크 파일에 비밀값이 평문으로 남지 않아야 한다
        path = os.path.join(str(tmp_path), "seller1.json")
        with open(path, "r", encoding="utf-8") as fp:
            raw = fp.read()
        assert "atk_supersecret_value" not in raw
        assert '"_enc": true' in raw.replace(" ", "").replace("\n", "") or '"_enc":true' in raw.replace(" ", "")

    def test_plaintext_fallback_without_keys(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARKET_CRED_DIR", str(tmp_path))
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.delenv("MARKET_CRED_ENC_KEY", raising=False)
        from src.seller_console import market_credentials as module
        importlib.reload(module)
        module.save("s", "elevenst", {"ELEVENST_API_KEY": "k"})
        # 키 없으면 평문이라도 조회는 정상 (개발용)
        assert module.get("s", "elevenst")["ELEVENST_API_KEY"] == "k"


class TestConnectionStatus:
    def test_is_connected_with_stored(self, mc):
        assert mc.is_connected("s", "elevenst") is False
        mc.save("s", "elevenst", {"ELEVENST_API_KEY": "k"})
        assert mc.is_connected("s", "elevenst") is True

    def test_is_connected_falls_back_to_global_env(self, mc, monkeypatch):
        monkeypatch.setenv("ELEVENST_API_KEY", "global-key")
        assert mc.is_connected("s", "elevenst") is True

    def test_status_masks_secrets(self, mc):
        mc.save("s", "coupang", {"COUPANG_ACCESS_KEY": "ak12345678", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A001"})
        st = mc.status("s", "coupang")
        fields = {f["env"]: f for f in st["fields"]}
        # 비밀값은 마스킹, 일반값은 그대로
        assert "12345678" not in fields["COUPANG_ACCESS_KEY"]["display"]
        assert "••••" in fields["COUPANG_ACCESS_KEY"]["display"]
        assert fields["COUPANG_VENDOR_ID"]["display"] == "A001"
        assert st["connected"] is True


class TestEnvInjection:
    def test_seller_market_env_injects_and_restores(self, mc, monkeypatch):
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)
        mc.save("s", "elevenst", {"ELEVENST_API_KEY": "seller-key"})
        assert os.getenv("ELEVENST_API_KEY") is None
        with mc.seller_market_env("s", "elevenst"):
            assert os.getenv("ELEVENST_API_KEY") == "seller-key"
        assert os.getenv("ELEVENST_API_KEY") is None

    def test_extra_overrides_pending_values(self, mc, monkeypatch):
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)
        with mc.seller_market_env("s", "elevenst", extra={"ELEVENST_API_KEY": "typed-now"}):
            assert os.getenv("ELEVENST_API_KEY") == "typed-now"
        assert os.getenv("ELEVENST_API_KEY") is None


class TestAllCredentialEnv:
    def test_merges_all_markets(self, mc):
        mc.save("s", "coupang", {"COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A1"})
        mc.save("s", "elevenst", {"ELEVENST_API_KEY": "ek"})
        merged = mc.all_credential_env("s")
        assert merged["COUPANG_ACCESS_KEY"] == "ak"
        assert merged["ELEVENST_API_KEY"] == "ek"


class TestSellerCredsReflectedInMarketsPage:
    """인앱 저장 키가 마켓 현황 '연결됨' 판정에 반영된다 (Render env 없이도)."""

    def test_market_configured_for_seller_uses_store(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARKET_CRED_DIR", str(tmp_path))
        monkeypatch.setenv("SECRET_KEY", "x")
        # 전역 환경변수는 비움
        for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID"):
            monkeypatch.delenv(k, raising=False)
        from src.seller_console import market_credentials as module
        importlib.reload(module)
        module.save("default", "coupang", {
            "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A1"})

        from src.seller_console import views
        # 전역 env 기준으로는 미설정
        assert views._market_is_configured("coupang") is False
        # 셀러 인앱 저장 기준으로는 설정됨
        assert views._market_configured_for_seller("coupang") is True


class TestConnectRoutes:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARKET_CRED_DIR", str(tmp_path))
        monkeypatch.setenv("SECRET_KEY", "route-test-secret")
        from src.seller_console import market_credentials as module
        importlib.reload(module)
        import src.order_webhook as wh
        wh.app.config["TESTING"] = True
        with wh.app.test_client() as c:
            yield c

    def test_connect_page_200(self, client):
        resp = client.get("/seller/markets/connect")
        assert resp.status_code == 200
        assert "마켓 연결" in resp.get_data(as_text=True)

    def test_save_and_status(self, client):
        resp = client.post("/seller/markets/connect/coupang", json={"values": {
            "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A1"}})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["status"]["connected"] is True

    def test_save_unsupported_market_404(self, client):
        resp = client.post("/seller/markets/connect/gmarket", json={"values": {"X": "y"}})
        assert resp.status_code == 404

    def test_save_bad_values_400(self, client):
        resp = client.post("/seller/markets/connect/coupang", json={"values": "not-a-dict"})
        assert resp.status_code == 400

    def test_test_route_returns_status(self, client):
        resp = client.post("/seller/markets/connect/elevenst/test", json={"values": {}})
        assert resp.status_code == 200
        assert "result" in resp.get_json()

    def test_per_market_page_renders(self, client):
        resp = client.get("/seller/markets/connect/coupang")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "쿠팡 연결" in html
        assert "키 발급 방법" in html  # 인라인 가이드
        assert "전체 마켓 보기" in html

    def test_per_market_11st_maps_to_elevenst(self, client):
        resp = client.get("/seller/markets/connect/11st")
        assert resp.status_code == 200
        assert "11번가 연결" in resp.get_data(as_text=True)

    def test_per_market_invalid_redirects(self, client):
        resp = client.get("/seller/markets/connect/foobar")
        assert resp.status_code in (301, 302)

    def test_disconnect(self, client):
        client.post("/seller/markets/connect/coupang", json={"values": {
            "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A1"}})
        resp = client.post("/seller/markets/connect/coupang/disconnect", json={})
        assert resp.status_code == 200
        assert resp.get_json()["removed"] is True
