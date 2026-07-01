"""tests/test_v41_step1_dead_features.py — addendum v41 STEP 1 가드."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_my_sources_entry_opens_registry_form(client):
    """사이드바/버튼 진입 URL은 등록 폼으로 이동해야 한다."""
    resp = client.get("/seller/sourcing/my-sources")
    assert resp.status_code in (301, 302)
    location = resp.headers.get("Location", "")
    assert "/seller/sourcing" in location
    assert "#registryDomainInput" in location


def test_my_sources_json_api_kept_with_format_query(client):
    resp = client.get("/seller/sourcing/my-sources?format=json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert isinstance(data["sources"], list)


def test_sourcing_links_point_to_registry_form():
    manual_collect = (REPO / "src/seller_console/templates/manual_collect.html").read_text(encoding="utf-8")
    me = (REPO / "src/seller_console/templates/me.html").read_text(encoding="utf-8")
    base = (REPO / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    assert '/seller/sourcing#registryDomainInput' in manual_collect
    assert '/seller/sourcing#registryDomainInput' in me
    assert '/seller/sourcing#registryDomainInput' in base


def test_extension_token_storage_has_honest_failure_and_local_fallback():
    options_js = (REPO / "extensions/chrome-collector/options.js").read_text(encoding="utf-8")
    background_js = (REPO / "extensions/chrome-collector/background.js").read_text(encoding="utf-8")
    popup_js = (REPO / "extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
    manifest = json.loads((REPO / "extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))

    assert "chrome.runtime.lastError" in options_js
    assert "chrome.storage.local.set(settings" in options_js
    assert "저장 실패" in options_js
    assert "syncData.token || localData.token" in background_js
    assert '"Authorization"' in background_js
    assert 'action: "getSettings"' in popup_js
    parts = [int(x) for x in manifest["version"].split(".")]
    assert parts >= [1, 5, 20]
