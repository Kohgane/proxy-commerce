"""tests/test_mobile_store_packaging_v15.py — v15 모바일 양대 스토어 패키징 경로 가드."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_assetlinks_empty_when_unset(client, monkeypatch):
    monkeypatch.delenv("TWA_PACKAGE_NAME", raising=False)
    monkeypatch.delenv("TWA_SHA256_FINGERPRINTS", raising=False)
    r = client.get("/.well-known/assetlinks.json")
    assert r.status_code == 200
    assert r.content_type.startswith("application/json")
    assert json.loads(r.get_data(as_text=True)) == []     # 가짜 연동 금지(빈 배열)


def test_assetlinks_populated_when_env_set(client, monkeypatch):
    monkeypatch.setenv("TWA_PACKAGE_NAME", "com.kohgane.collector")
    monkeypatch.setenv("TWA_SHA256_FINGERPRINTS", "AA:BB:CC, DD:EE:FF")
    data = json.loads(client.get("/.well-known/assetlinks.json").get_data(as_text=True))
    assert len(data) == 1
    tgt = data[0]["target"]
    assert tgt["package_name"] == "com.kohgane.collector"
    assert tgt["sha256_cert_fingerprints"] == ["AA:BB:CC", "DD:EE:FF"]


def test_aasa_route(client, monkeypatch):
    monkeypatch.delenv("IOS_APP_ID", raising=False)
    r = client.get("/.well-known/apple-app-site-association")
    assert r.status_code == 200
    assert r.content_type.startswith("application/json")
    body = json.loads(r.get_data(as_text=True))
    assert body["applinks"]["details"] == []
    monkeypatch.setenv("IOS_APP_ID", "ABCDE12345.com.kohgane.app")
    body2 = json.loads(client.get("/.well-known/apple-app-site-association").get_data(as_text=True))
    assert body2["applinks"]["details"][0]["appID"] == "ABCDE12345.com.kohgane.app"


def test_packaging_configs_exist():
    base = Path("mobile")
    assert (base / "README.md").exists()
    twa = json.loads((base / "twa-manifest.json").read_text(encoding="utf-8"))
    assert twa["webManifestUrl"].endswith("manifest.webmanifest")
    cap = json.loads((base / "capacitor.config.json").read_text(encoding="utf-8"))
    assert cap["server"]["url"].startswith("https://")
