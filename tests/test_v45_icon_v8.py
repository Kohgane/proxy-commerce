"""tests/test_v45_icon_v8.py — 아이콘 v8: scripts/build_icons.py 코드 생성 + 전 위치 교체.

흰 배경 + 먹 라운드 보더 + 골드 게이트 아치 + 주황 키스톤 + 틸 데크. 소형(16/32)은 고대비 변형.
PIL은 함수 내 지연 import(CI collect-only 안전).
"""
from __future__ import annotations

from pathlib import Path

STATIC = Path("src/seller_console/static")
EXT = Path("extensions/chrome-collector")
SCRIPT = Path("scripts/build_icons.py").read_text(encoding="utf-8")


def test_build_script_exists_with_api():
    assert "def build_master(" in SCRIPT
    assert "def deploy(" in SCRIPT
    # 스펙 상수(지오메트리) 코드로 명시
    for tok in ("ARCH_R = 165", "ARCH_CY = 430", "TOWER_X = (252, 772)", "DECK_Y = (612, 664)",
                "0x1A, 0x17, 0x14", "0xC9, 0xA2, 0x4B", "0xF5, 0x82, 0x1F", "0x11, 0x9A, 0x8E"):
        assert tok in SCRIPT, tok


def _near(px, rgb, tol=44):
    return all(abs(int(px[i]) - rgb[i]) <= tol for i in range(3))


def _has(path, rgb, tol=44, size=64):
    from PIL import Image
    im = Image.open(path).convert("RGB").resize((size, size))
    return any(_near(p, rgb, tol) for p in im.getdata())


def test_master_is_white_bg_with_brand_colors():
    from PIL import Image
    im = Image.open(STATIC / "icon-1024.png").convert("RGB")
    # 모서리(보더 바깥)는 흰 배경
    assert _near(im.getpixel((8, 8)), (255, 255, 255), tol=6), "마스터 배경이 흰색 아님"
    # 브랜드 색 존재: 골드·틸·주황·먹
    for rgb, name in [((201, 162, 75), "gold"), ((17, 154, 142), "teal"),
                      ((245, 130, 31), "orange"), ((26, 23, 20), "ink")]:
        assert _has(STATIC / "icon-1024.png", rgb), f"마스터에 {name} 없음"


def test_small_favicons_high_contrast():
    # 16/32 소형에 틸·주황·골드 생존(뭉개짐 0)
    for s in (16, 32):
        p = STATIC / f"favicon-{s}.png"
        assert p.exists()
        assert _has(p, (17, 154, 142)), f"favicon-{s} 청록 없음"
        assert _has(p, (245, 130, 31)), f"favicon-{s} 주황 없음"


def test_all_icon_files_present():
    for f in ("favicon.ico", "favicon.svg", "favicon-16.png", "favicon-32.png",
              "favicon-48.png", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-1024.png"):
        assert (STATIC / f).exists(), f
    for s in ("16", "32", "48", "128"):
        assert (EXT / "icons" / f"{s}.png").exists(), s


def test_no_globe_dark_splash_residue():
    svg = (STATIC / "favicon.svg").read_text(encoding="utf-8")
    assert "globe" not in svg.lower()
    assert "#020010" not in svg          # 옛 순흑 스플래시 잔재 0
    assert "gateway" in svg              # 브릿지/게이트 정체성 aria


def test_cache_version_and_manifest_bumped():
    import json
    base = (Path("src/seller_console/templates/_base.html")).read_text(encoding="utf-8")
    assert "v='181'" in base and "v='179'" not in base
    mf = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    assert mf["version"] == "1.5.55"
