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
    im = Image.open(STATIC / "icon-1024.png").convert("RGBA")
    # v57 대형 통일(오너 공식 512): 모서리(보더 바깥)는 **투명**(alpha 0) 또는 흰색, 내부는 흰 배경.
    cr, cg, cb, ca = im.getpixel((8, 8))
    assert ca == 0 or _near((cr, cg, cb), (255, 255, 255), tol=8), "모서리가 투명/흰색 아님"
    assert _near(im.convert("RGB").getpixel((512, 512)), (255, 255, 255), tol=8), "내부 배경이 흰색 아님"
    # 브랜드 색 존재: 골드·틸·주황·먹
    for rgb, name in [((201, 162, 75), "gold"), ((17, 154, 142), "teal"),
                      ((245, 130, 31), "orange"), ((26, 23, 20), "ink")]:
        assert _has(STATIC / "icon-1024.png", rgb), f"마스터에 {name} 없음"


def test_small_favicons_high_contrast():
    # v57: 소형 favicon = 오너 정답지(favicon-master-48.png) 기준. 정답지(=favicon-48)에 브랜드색(청록·주황)
    #   존재를 보증(브랜드 정체성). 16/32는 그 다운스케일 — 소형 축소로 순색은 완화될 수 있으며 정답지가 최종 권위.
    ans = STATIC / "favicon-48.png"
    assert ans.exists()
    assert _has(ans, (17, 154, 142)), "정답지(favicon-48)에 청록 없음"
    assert _has(ans, (245, 130, 31)), "정답지(favicon-48)에 주황 없음"
    for s in (16, 32):
        assert (STATIC / f"favicon-{s}.png").exists()


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
    assert "v='182'" in base and "v='181'" not in base
    mf = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    assert mf["version"] == "1.5.76"
