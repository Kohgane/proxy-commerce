from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import bcrypt


MODULE_PATH = Path(__file__).resolve().parents[1] / "automation" / "api_sync" / "naver_commerce_sync.py"


def _load_module(monkeypatch, **env_overrides):
    required = {
        "NAVER_COMMERCE_CLIENT_ID": "cid",
        "NAVER_COMMERCE_CLIENT_SECRET": bcrypt.gensalt().decode("utf-8"),
        "WC_URL": "https://wc.example.com",
        "WC_KEY": "key",
        "WC_SECRET": "secret",
        "DRY_RUN": "true",
    }
    for key in ("NAVER_HTTPS_PROXY", "QUOTAGUARD_URL", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(key, raising=False)
    for k, v in {**required, **env_overrides}.items():
        monkeypatch.setenv(k, v)

    module_name = f"naver_commerce_sync_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_get_naver_token_uses_explicit_proxy(monkeypatch):
    proxy_url = "******xxxx.quotaguard.com:9293"
    mod = _load_module(monkeypatch, NAVER_HTTPS_PROXY=proxy_url)
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"access_token": "token-123"}

    def fake_post(url, data=None, timeout=None, proxies=None):
        captured["proxies"] = proxies
        return FakeResponse()

    monkeypatch.setattr(mod.requests, "post", fake_post)
    assert mod.get_naver_token() == "token-123"
    assert captured["proxies"] == {
        "https": proxy_url,
        "http": proxy_url,
    }


def test_get_naver_products_uses_quotaguard_proxy(monkeypatch):
    proxy_url = "******proxy.example.com:9293"
    mod = _load_module(monkeypatch, QUOTAGUARD_URL=proxy_url)
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"contents": []}

    def fake_post(url, headers=None, json=None, timeout=None, proxies=None):
        captured["proxies"] = proxies
        return FakeResponse()

    monkeypatch.setattr(mod.requests, "post", fake_post)
    mod.get_naver_products("token")
    assert captured["proxies"] == {
        "https": proxy_url,
        "http": proxy_url,
    }


def test_naver_proxy_unset_passes_none(monkeypatch):
    mod = _load_module(monkeypatch)
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    def fake_get(url, headers=None, timeout=None, proxies=None):
        captured["proxies"] = proxies
        return FakeResponse()

    monkeypatch.setattr(mod.requests, "get", fake_get)
    mod.get_naver_product_detail("token", "123")
    assert captured["proxies"] is None


def test_woocommerce_calls_do_not_use_proxy(monkeypatch):
    mod = _load_module(monkeypatch, NAVER_HTTPS_PROXY="******proxy.example.com:9293")
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return []

    def fake_session_get(url, params=None, timeout=None):
        captured["called"] = True
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(mod.session, "get", fake_session_get)
    mod.preload_wc_categories()
    assert captured["called"] is True
    assert captured["params"]["per_page"] == 100


def test_get_naver_token_ip_not_allowed_diagnostic(monkeypatch, capsys):
    mod = _load_module(monkeypatch)

    class FakeResponse:
        status_code = 403
        text = '{"code":"GW.IP_NOT_ALLOWED","message":"호출이 허용되지 않은 IP입니다."}'

        @staticmethod
        def json():
            return {"code": "GW.IP_NOT_ALLOWED", "message": "호출이 허용되지 않은 IP입니다."}

    monkeypatch.setattr(mod.requests, "post", lambda *args, **kwargs: FakeResponse())

    assert mod.get_naver_token() is None
    out = capsys.readouterr().out
    assert "GW.IP_NOT_ALLOWED" in out
    assert "허용되지 않은 IP" in out
    assert mod.LAST_TOKEN_ERROR_CODE == "GW.IP_NOT_ALLOWED"
