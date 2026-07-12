"""tests/test_v57_icon_truth.py — v57 STEP1: 아이콘 전면 정정(오답 마크 회수).

오너 판정: 라이브 v181 파비콘 = 오답(타워 없는 단일 아치+점). 정답 = 두 타워 현수교
(두 타워 + 현수 케이블 + 중앙 원형 키스톤 + 수면 라인, 흰 배경 + 먹 라운드 보더).

build_icons.build_simple()(=소형 favicon 16/32/48·확장 16/32/48 소스)이 두 타워 현수교를
렌더하는지, 커밋 원본(brand_icons_v2/master-48.png)이 있으면 그걸 우선하는지, 캐시버스트/확장
버전이 범프됐는지 가드. Pillow 빌드타임 전용 → 렌더 검증은 지연 import + 미설치 시 skip.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
BASE_APP = Path("src/templates/_base_app.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
BUILD = Path("scripts/build_icons.py").read_text(encoding="utf-8")


def _pillow_ok() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_icons", "scripts/build_icons.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cache_bust_v182():
    # 오답 회수를 라이브에 강제 반영 — ?v=182 일괄, 구 v181 잔존 0.
    assert "v='182'" in BASE and "v='181'" not in BASE
    assert "favicon.svg?v=182" in BASE_APP and "v=181" not in BASE_APP


def test_extension_version_bumped():
    # 확장 재로딩 유도(툴바 아이콘 오답 회수).
    assert MANIFEST["version"] == "1.5.57"


def test_build_simple_is_two_tower_not_arch_dot():
    # 소형 렌더가 '두 타워 현수교' 계열임을 소스로 못박음(구 타워없는 아치+점 회귀 방지).
    assert "두 타워" in BUILD or "two-tower" in BUILD.lower()
    # build_simple이 타워 2개(TX 튜플)와 원형 키스톤(dot)·수면 라인(WATER)을 그린다.
    seg = BUILD.split("def build_simple")[1].split("def build_master")[0]
    assert "TX" in seg and "dot(" in seg and "WATER" in seg
    assert "leg(" in seg, "타워(leg) 스트로크가 있어야 두 타워"


def test_committed_master_preferred_when_present():
    # 오너가 정답 원본을 커밋하면(brand_icons_v2/master-48.png) 그걸 유일 정답지로 우선.
    assert "_committed_master" in BUILD
    assert "brand_icons_v2" in BUILD and "master-48.png" in BUILD


@pytest.mark.skipif(not _pillow_ok(), reason="Pillow 미설치(빌드타임 전용)")
def test_small_icon_renders_two_towers_pixels():
    # 실제 렌더: 소형 아이콘에 골드(타워)·틸(데크)·주황(키스톤) 픽셀이 모두 존재(단색 아치 아님).
    mod = _load()
    img = mod.build_master(simple=True).convert("RGB")
    px = list(img.getdata())

    def near(c, t, tol=40):
        return all(abs(c[i] - t[i]) <= tol for i in range(3))

    gold = sum(1 for c in px if near(c, mod.GOLD))
    teal = sum(1 for c in px if near(c, mod.TEAL, 55))
    orange = sum(1 for c in px if near(c, mod.ORANGE))
    assert gold > 200, f"타워/케이블 골드 픽셀 부족: {gold}"
    assert teal > 200, f"데크 틸 픽셀 부족: {teal}"
    assert orange > 100, f"키스톤 주황 픽셀 부족: {orange}"


@pytest.mark.skipif(not _pillow_ok(), reason="Pillow 미설치")
def test_committed_favicons_match_code():
    # 커밋된 static/확장 파비콘 = deploy() 코드 출력(해시 일치) → 배포 드리프트 0.
    import hashlib
    import shutil
    import tempfile
    mod = _load()
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "src/seller_console/static").mkdir(parents=True)
        (tmp / "extensions/chrome-collector/icons").mkdir(parents=True)
        (tmp / "assets/brand-icons").mkdir(parents=True)
        mod.deploy(str(tmp))

        def md5(p):
            return hashlib.md5(Path(p).read_bytes()).hexdigest()

        for f in ("favicon-16.png", "favicon-32.png", "favicon-48.png", "favicon.ico",
                  "apple-touch-icon.png", "icon-192.png", "icon-512.png"):
            assert md5(f"src/seller_console/static/{f}") == md5(tmp / "src/seller_console/static" / f), \
                f"{f} 커밋≠코드(재생성 필요)"
        for f in ("16.png", "32.png", "48.png", "128.png"):
            assert md5(f"extensions/chrome-collector/icons/{f}") == md5(tmp / "extensions/chrome-collector/icons" / f), \
                f"확장 {f} 커밋≠코드"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
