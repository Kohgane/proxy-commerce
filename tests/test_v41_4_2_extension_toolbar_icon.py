"""tests/test_v41_4_2_extension_toolbar_icon.py — v41 4-2: 확장 툴바 아이콘 = 브릿지 마크(지구본 0).

오너 증상: 크롬 확장 툴바 아이콘이 지구본. 실제 원인=캐시된 옛 확장(현재 아이콘은 v39-A2에서 이미 브릿지).
이 가드: ①manifest.json의 icons + action.default_icon 4사이즈 전부 브릿지 PNG 지정 ②버전 bump로 재로딩 유도
③툴바 아이콘 PNG가 실제 브릿지 색(금 게이트+주황 키스톤)인지 픽셀 검증 ④manifest에 globe 0.
CI(collect-only, Pillow 미설치) 안전 위해 PIL은 함수 내 지연 import.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
_SIZES = ("16", "32", "48", "128")


def test_manifest_icons_and_action_all_bridge_png():
    """icons + action.default_icon 4사이즈 전부 icons/*.png(브릿지) 지정 — 툴바 아이콘 확정."""
    for s in _SIZES:
        assert MANIFEST["icons"][s] == f"icons/{s}.png"
        assert MANIFEST["action"]["default_icon"][s] == f"icons/{s}.png"
        assert (EXT / "icons" / f"{s}.png").exists()


def test_version_bumped_for_reload():
    """캐시된 옛 확장(지구본) 재로딩 유도 — 버전 상향."""
    assert MANIFEST["version"] == "1.5.83"


def test_manifest_has_no_globe():
    raw = (EXT / "manifest.json").read_text(encoding="utf-8").lower()
    assert "globe" not in raw and "🌐" not in raw


def _near(px, rgb, tol=42):
    return all(abs(int(px[i]) - rgb[i]) <= tol for i in range(3))


def _colors_present(path, must):
    from PIL import Image  # 지연 import(CI collect-only 안전)
    im = Image.open(path).convert("RGB").resize((64, 64))
    pixels = list(im.getdata())
    found = {k: False for k in must}
    for p in pixels:
        for k, rgb in must.items():
            if _near(p, rgb):
                found[k] = True
    return found


def test_toolbar_128_48_are_full_bridge_marks():
    """대표 툴바 아이콘(128/48)에 금 게이트 + 주황 키스톤 존재(지구본 파랑 아님)."""
    GOLD, ORANGE = (201, 162, 75), (245, 130, 31)
    for name in ("128.png", "48.png"):
        f = _colors_present(EXT / "icons" / name, {"gold": GOLD, "orange": ORANGE})
        assert all(f.values()), f"ext {name}: {f}"
