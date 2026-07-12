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


def test_favicon48_answer_is_sole_small_source():
    # v57 오너: 파비콘 소사이즈 정답지=assets/brand-icons/favicon-master-48.png →
    #   favicon-16/32/48·ico·확장 16/32/48이 1024 마스터가 아니라 이 파일 다운스케일(16=48 다운스케일).
    assert "assets/brand-icons/favicon-master-48.png" in BUILD
    assert "def _favicon48_answer" in BUILD
    # 소형 소스가 small48(정답지 우선), 대형은 1024 master로 분리.
    assert "small48 = fav48 if fav48 is not None else build_master(simple=True)" in BUILD
    seg = BUILD.split("def deploy")[1]
    assert "_small(48)" in seg and "_small(16)" in seg               # 48=정답지 그대로, 16=다운스케일
    assert "fav48.copy()" in seg                                     # 48은 리샘플 0(픽셀 동일)
    assert "_rs(master, 512)" in seg or "_rs(master, 1024)" in seg   # 대형은 1024 마스터


def test_favicon48_downscale_pipeline_uses_committed_file(tmp_path):
    # 정답지 파일이 있으면 favicon-16/32/48이 그 파일 다운스케일과 픽셀 동일(파이프라인 계약).
    if not _pillow_ok():
        pytest.skip("Pillow 미설치")
    from PIL import Image
    import hashlib
    mod = _load()
    root = tmp_path
    (root / "assets/brand-icons").mkdir(parents=True)
    (root / "src/seller_console/static").mkdir(parents=True)
    (root / "extensions/chrome-collector/icons").mkdir(parents=True)
    # 임의 48px 정답지(단색 아님 — 대각선)로 파이프라인 검증
    ans = Image.new("RGB", (48, 48), (255, 255, 255))
    for i in range(48):
        ans.putpixel((i, i), (0x11, 0x9A, 0x8E))
    ans.save(root / "assets/brand-icons/favicon-master-48.png")
    mod.deploy(str(root))
    # favicon-48 = 정답지 **픽셀 그대로**(리샘플 0 — 픽셀 동일 보장).
    got48 = Image.open(root / "src/seller_console/static/favicon-48.png").convert("RGBA")
    assert hashlib.md5(got48.tobytes()).hexdigest() == hashlib.md5(ans.convert("RGBA").tobytes()).hexdigest()
    # 16 = 정답지(48) 다운스케일.
    got16 = Image.open(root / "src/seller_console/static/favicon-16.png").convert("RGBA")
    exp16 = ans.convert("RGBA").resize((16, 16), Image.LANCZOS)
    assert hashlib.md5(got16.tobytes()).hexdigest() == hashlib.md5(exp16.tobytes()).hexdigest()


def test_compare_favicon_tool_exists():
    tool = Path("scripts/compare_favicon.py").read_text(encoding="utf-8")
    assert "favicon-master-48.png" in tool
    assert "픽셀 동일" in tool and "--live" in tool


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
        # v57: 소형 favicon은 정답지(favicon-master-48.png) 기준 → tmp에도 복사해야 커밋본과 일치.
        _ans = Path("assets/brand-icons/favicon-master-48.png")
        if _ans.exists():
            shutil.copy(_ans, tmp / "assets/brand-icons/favicon-master-48.png")
        _lm = Path("assets/brand-icons/master-512.png")
        if _lm.exists():
            shutil.copy(_lm, tmp / "assets/brand-icons/master-512.png")
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
