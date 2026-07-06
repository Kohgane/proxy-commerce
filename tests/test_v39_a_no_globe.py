"""tests/test_v39_a_no_globe.py — v39 A: 북마클릿·확장·파비콘 지구본 잔존 0 → 브릿지 마크 단독."""
from __future__ import annotations

import glob
import json
from pathlib import Path

EXT = "extensions/chrome-collector"
POPUP = Path(f"{EXT}/popup.html").read_text(encoding="utf-8")
OPTIONS = Path(f"{EXT}/options.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path(f"{EXT}/manifest.json").read_text(encoding="utf-8"))


def _emoji(s):
    return sorted(set(c for c in s if ord(c) >= 0x1F300 or ord(c) in (0x2705, 0x274C, 0x2699, 0x2B50, 0x1F441, 0x231B)))


def test_no_globe_in_extension_and_bot():
    for f in glob.glob(f"{EXT}/*.html") + glob.glob(f"{EXT}/*.js"):
        s = Path(f).read_text(encoding="utf-8")
        assert "🌐" not in s, f"{f}에 지구본 이모지 잔존"
        assert "globe" not in s.lower(), f"{f}에 globe 잔존"
    bot = Path("src/bot/formatters.py").read_text(encoding="utf-8")
    assert "🌐" not in bot


def test_extension_chrome_emoji_free_with_bridge_mark():
    # 확장 popup/options = 이모지 0 + 브릿지 마크 SVG(옛 글러브 🧤 폐기)
    assert _emoji(POPUP) == [], f"popup 이모지: {_emoji(POPUP)}"
    assert _emoji(OPTIONS) == [], f"options 이모지: {_emoji(OPTIONS)}"
    assert "🧤" not in POPUP
    assert "viewBox=\"0 0 512 512\"" in POPUP and "#f5821f" in POPUP   # 브릿지 마크(주황 키스톤)


def test_all_extension_js_emoji_free():
    for f in glob.glob(f"{EXT}/*.js"):
        s = Path(f).read_text(encoding="utf-8")
        assert _emoji(s) == [], f"{f} 이모지: {_emoji(s)}"


def test_favicon_is_bridge_and_version_bumped():
    fav = Path("src/seller_console/static/favicon.svg").read_text(encoding="utf-8")
    assert "bridge gateway mark" in fav and "globe" not in fav.lower()
    assert MANIFEST["version"] == "1.5.39"
