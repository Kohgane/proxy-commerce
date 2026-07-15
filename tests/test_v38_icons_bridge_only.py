"""tests/test_v38_icons_bridge_only.py — v38 #3: 아이콘 단독화(브릿지 마크·이모지/지구본 0·캐시 갱신)."""
from __future__ import annotations

import json
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
FAVICON_SVG = Path("src/seller_console/static/favicon.svg").read_text(encoding="utf-8")


def test_fab_uses_single_bridge_mark_no_glove():
    assert "KGP_BRIDGE_SVG" in CS               # 단일 브릿지 마크 상수
    assert "KGP_GLOVE_SVG" not in CS            # 옛 글러브 명칭 폐기
    assert "globe" not in CS.lower() and "지구본" not in CS


def test_extension_inpage_has_no_pictographic_emoji():
    # FAB/토스트/축하에 픽토그래픽 이모지 0(브릿지 마크·텍스트만)
    emo = [c for c in CS if ord(c) >= 0x1F000 or ord(c) in (0x2705, 0x274C)]
    assert emo == [], f"확장 인페이지 이모지 잔존: {sorted(set(emo))}"


def test_extension_version_bumped_for_icon_refresh():
    # 캐시된 옛 트레이 아이콘(지구본 오인) 갱신 위해 버전 bump
    assert MANIFEST["version"] == "1.5.87"
    # 아이콘 매핑은 브릿지 PNG(16/32/48/128)
    assert MANIFEST["icons"]["128"] == "icons/128.png"


def test_favicon_cache_bumped():
    assert "v='182'" in BASE                    # 탭 아이콘 캐시 갱신(브릿지)
    assert "v='176'" not in BASE
    assert "bridge gateway mark" in FAVICON_SVG  # favicon = 브릿지 게이트웨이
    assert "globe" not in FAVICON_SVG.lower()
