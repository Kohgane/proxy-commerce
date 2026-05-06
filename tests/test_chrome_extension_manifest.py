"""tests/test_chrome_extension_manifest.py — manifest.json scripting 권한 테스트 (Phase 135.2)."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_EXT_DIR = os.path.join(os.path.dirname(__file__), "..", "extensions", "chrome-collector")


def _load_manifest():
    with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
        return json.load(f)


class TestManifestScripting:
    def test_scripting_permission_present(self):
        """manifest.json의 permissions에 'scripting'이 포함되어야 함."""
        manifest = _load_manifest()
        permissions = manifest.get("permissions", [])
        assert "scripting" in permissions, "scripting 권한이 permissions에 없습니다."

    def test_all_required_permissions(self):
        """필수 권한 목록 전체 확인."""
        manifest = _load_manifest()
        permissions = manifest.get("permissions", [])
        for perm in ["activeTab", "storage", "contextMenus", "notifications", "scripting"]:
            assert perm in permissions, f"{perm} 권한이 누락됐습니다."

    def test_content_scripts_all_urls(self):
        """content_scripts가 <all_urls>에 주입됨 (폴백 메시지 패싱 가능)."""
        manifest = _load_manifest()
        cs = manifest.get("content_scripts", [])
        assert len(cs) > 0
        matches = cs[0].get("matches", [])
        assert "<all_urls>" in matches


class TestPopupJsScriptingFallback:
    def test_popup_has_scripting_guard(self):
        """popup.js가 chrome.scripting 존재 여부를 확인하는 가드 코드를 가짐."""
        path = os.path.join(_EXT_DIR, "popup.js")
        with open(path, "r") as f:
            content = f.read()
        assert "chrome.scripting" in content
        assert "sendMessage" in content, "tabs.sendMessage 폴백 코드가 없습니다."

    def test_popup_has_fallback_try_catch(self):
        """popup.js가 try/catch로 scripting 실패를 처리함."""
        path = os.path.join(_EXT_DIR, "popup.js")
        with open(path, "r") as f:
            content = f.read()
        assert "try" in content
        assert "catch" in content


class TestContentScriptMessageHandler:
    def test_content_script_handles_extract_meta(self):
        """content_script.js가 extractMeta 메시지를 처리함."""
        path = os.path.join(_EXT_DIR, "content_script.js")
        with open(path, "r") as f:
            content = f.read()
        assert "extractMeta" in content
        assert "onMessage.addListener" in content
