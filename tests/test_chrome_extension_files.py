"""tests/test_chrome_extension_files.py — 크롬 확장 파일 유효성 검증 (Phase 135)."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_EXT_DIR = os.path.join(os.path.dirname(__file__), "..", "extensions", "chrome-collector")


class TestManifestJson:
    def test_manifest_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "manifest.json"))

    def test_manifest_valid_json(self):
        with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
            manifest = json.load(f)
        assert manifest is not None

    def test_manifest_version_3(self):
        with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
            manifest = json.load(f)
        assert manifest["manifest_version"] == 3

    def test_manifest_has_name(self):
        with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
            manifest = json.load(f)
        assert "name" in manifest
        assert len(manifest["name"]) > 0

    def test_manifest_has_version(self):
        with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
            manifest = json.load(f)
        assert "version" in manifest
        parts = manifest["version"].split(".")
        assert len(parts) == 3

    def test_manifest_has_permissions(self):
        with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
            manifest = json.load(f)
        permissions = manifest.get("permissions", [])
        assert "activeTab" in permissions
        assert "storage" in permissions

    def test_manifest_has_action(self):
        with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
            manifest = json.load(f)
        assert "action" in manifest
        assert "default_popup" in manifest["action"]

    def test_manifest_has_background(self):
        with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
            manifest = json.load(f)
        assert "background" in manifest
        assert "service_worker" in manifest["background"]

    def test_manifest_has_content_scripts(self):
        with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
            manifest = json.load(f)
        cs = manifest.get("content_scripts", [])
        assert len(cs) > 0
        assert "js" in cs[0]

    def test_manifest_no_shein(self):
        """Shein 언급 없음."""
        with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
            content = f.read().lower()
        assert "shein" not in content


class TestExtensionFiles:
    def test_background_js_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "background.js"))

    def test_content_script_js_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "content_script.js"))

    def test_popup_html_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "popup.html"))

    def test_popup_js_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "popup.js"))

    def test_options_html_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "options.html"))

    def test_options_js_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "options.js"))

    def test_readme_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "README.md"))

    def test_build_sh_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "build.sh"))

    def test_popup_html_has_collect_button(self):
        with open(os.path.join(_EXT_DIR, "popup.html"), "r") as f:
            content = f.read()
        assert "btnCollect" in content or "btn-collect" in content or "수집" in content

    def test_options_html_has_token_input(self):
        with open(os.path.join(_EXT_DIR, "options.html"), "r") as f:
            content = f.read()
        assert "token" in content.lower()

    def test_background_js_has_collect_function(self):
        with open(os.path.join(_EXT_DIR, "background.js"), "r") as f:
            content = f.read()
        assert "handleCollect" in content or "collect" in content.lower()

    def test_background_js_uses_bearer_auth(self):
        with open(os.path.join(_EXT_DIR, "background.js"), "r") as f:
            content = f.read()
        assert "Bearer" in content

    def test_content_script_extracts_jsonld(self):
        with open(os.path.join(_EXT_DIR, "content_script.js"), "r") as f:
            content = f.read()
        assert "application/ld+json" in content

    def test_no_shein_in_any_file(self):
        """어떤 확장 파일에도 Shein 언급 없음."""
        js_files = ["background.js", "content_script.js", "popup.js", "options.js"]
        for filename in js_files:
            path = os.path.join(_EXT_DIR, filename)
            if os.path.exists(path):
                with open(path, "r") as f:
                    content = f.read().lower()
                assert "shein" not in content, f"{filename}에 shein 언급 발견"


class TestIcons:
    """크롬 확장 아이콘 파일 존재 확인 (Phase 135.1)."""

    _SIZES = [16, 32, 48, 128]

    def test_icons_directory_exists(self):
        icons_dir = os.path.join(_EXT_DIR, "icons")
        assert os.path.isdir(icons_dir), "icons/ 디렉터리가 없습니다"

    def test_icon_16_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "icons", "16.png"))

    def test_icon_32_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "icons", "32.png"))

    def test_icon_48_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "icons", "48.png"))

    def test_icon_128_exists(self):
        assert os.path.exists(os.path.join(_EXT_DIR, "icons", "128.png"))

    def test_all_four_icon_sizes_exist(self):
        icons_dir = os.path.join(_EXT_DIR, "icons")
        for size in self._SIZES:
            path = os.path.join(icons_dir, f"{size}.png")
            assert os.path.exists(path), f"icons/{size}.png 없음"

    def test_icon_files_are_valid_png(self):
        """각 아이콘이 PNG 시그니처(\x89PNG)를 가지는지 확인."""
        icons_dir = os.path.join(_EXT_DIR, "icons")
        png_sig = b"\x89PNG"
        for size in self._SIZES:
            path = os.path.join(icons_dir, f"{size}.png")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    header = f.read(4)
                assert header == png_sig, f"icons/{size}.png이 유효한 PNG가 아님"

    def test_icon_files_not_empty(self):
        icons_dir = os.path.join(_EXT_DIR, "icons")
        for size in self._SIZES:
            path = os.path.join(icons_dir, f"{size}.png")
            if os.path.exists(path):
                assert os.path.getsize(path) > 0, f"icons/{size}.png이 빈 파일"

    def test_manifest_icon_paths_resolve(self):
        """manifest.json의 아이콘 경로가 실제로 존재하는지 확인."""
        with open(os.path.join(_EXT_DIR, "manifest.json"), "r") as f:
            manifest = json.load(f)
        default_icons = manifest.get("action", {}).get("default_icon", {})
        for size_key, rel_path in default_icons.items():
            full_path = os.path.join(_EXT_DIR, rel_path)
            assert os.path.exists(full_path), f"manifest의 아이콘 경로 미존재: {rel_path}"
