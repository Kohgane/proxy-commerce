"""tests/test_v50_icon_v8_rollout.py — v50: 브랜드 아이콘 v8 전면 배포(해시 일치 + 캐시버스트).

오너가 라이브 파비콘과 v8 마스터 해시 불일치를 확인 → 배포/캐시 문제. 진단 결과 커밋된 static
파비콘은 이미 build_icons.py 코드 v8과 해시 일치(Docker도 포함)했고, og-card만 pre-v8(구 아이콘)이라
재생성했다. 캐시버스트 ?v=181(파비콘)·?v=5(og)로 강제 갱신. 확장 1.5.56.

Pillow는 빌드타임 전용(CI collect-only 미설치) → 해시 테스트는 함수 내 지연 import + 미설치 시 skip.
"""
from __future__ import annotations

from pathlib import Path

import pytest

STATIC = Path("src/seller_console/static")
BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
BASE_APP = Path("src/templates/_base_app.html").read_text(encoding="utf-8")
MANIFEST = Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8")


def _pillow_ok() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def _same_pixels(a: Path, b: Path) -> bool:
    """두 이미지가 **보이는 그림으로** 같은가.

    v87-S4: 종전엔 md5(PNG 바이트)로 비교했는데, 같은 픽셀도 Pillow 버전이 다르면 인코딩 바이트가
    달라진다. 그래서 이 단언은 '아이콘 드리프트'가 아니라 **Pillow 버전 차이**를 잡고 있었고,
    로컬에서만 상시 실패(사전 존재 실패 목록의 favicon-16)로 남아 있었다. 실측 확인 결과 커밋본 15개는
    코드 마스터 출력과 **픽셀 100% 동일**이었다 — 재생성 커밋은 아무것도 고치지 못하고 다음 Pillow
    업그레이드에 또 깨진다. 판정을 픽셀로 바꿔 '그림이 달라졌을 때만' 빨개지게 한다.
    """
    from PIL import Image, ImageChops
    with Image.open(a) as ia, Image.open(b) as ib:
        ia, ib = ia.convert("RGBA"), ib.convert("RGBA")
        if ia.size != ib.size:
            return False
        return ImageChops.difference(ia, ib).getbbox() is None


@pytest.mark.skipif(not _pillow_ok(), reason="Pillow 미설치(빌드타임 전용)")
def test_committed_favicons_match_code_v8_master():
    # 커밋된 static 파비콘 = build_icons.py deploy() 코드 v8 출력(픽셀 일치) → 드리프트 0.
    import importlib.util
    import tempfile
    import shutil
    spec = importlib.util.spec_from_file_location("build_icons", "scripts/build_icons.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "src/seller_console/static").mkdir(parents=True)
        (tmp / "extensions/chrome-collector/icons").mkdir(parents=True)
        (tmp / "assets/brand-icons").mkdir(parents=True)
        # v57: 소형 favicon은 정답지(favicon-master-48.png) 기준 → tmp에도 복사(커밋본 일치).
        _ans = Path("assets/brand-icons/favicon-master-48.png")
        if _ans.exists():
            shutil.copy(_ans, tmp / "assets/brand-icons/favicon-master-48.png")
        _lm = Path("assets/brand-icons/master-512.png")
        if _lm.exists():
            shutil.copy(_lm, tmp / "assets/brand-icons/master-512.png")
        mod.deploy(str(tmp))
        for f in ("favicon-16.png", "favicon-32.png", "favicon-48.png", "favicon.ico",
                  "apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-1024.png"):
            assert _same_pixels(STATIC / f, tmp / "src/seller_console/static" / f), \
                f"{f} 커밋≠코드v8(그림이 다름 — 재생성 필요)"
        for f in ("16.png", "32.png", "48.png", "128.png"):
            assert _same_pixels(Path("extensions/chrome-collector/icons") / f,
                                tmp / "extensions/chrome-collector/icons" / f), f"확장 {f} 커밋≠코드v8"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.skipif(not _pillow_ok(), reason="Pillow 미설치")
def test_og_card_uses_v8_master():
    """og-card.png = v8 마스터(흰 배경 브릿지 마크) 기반 최신본 — 구 글러브/다크 카드 아님.

    v86-K: 종전엔 gen_og_card.py로 재생성해 md5(before)==md5(after) 멱등을 봤는데, og-card 텍스트가
    시스템 폰트(_SERIF_CANDIDATES 폴백)로 렌더되므로 **커밋 환경과 CI의 폰트가 다르면** 재생성 바이트가
    달라져 상시 red였다(그림 드리프트가 아니라 폰트/Pillow 차이). 계약의 본질은 'og-card가 v8 마스터를
    쓰는 최신본이냐(구 글러브/다크 카드로 스테일하지 않냐)'이므로, 재생성 대신 **커밋본 내용**으로 판정한다:
    ①규격 1200×630 ②먹(#1A1714) 배경 ③좌측 마크 영역에 v8 마스터의 흰 배경이 실존(구 다크 글러브 카드면
    흰 블록이 없다). 폰트 비의존 → 포터블.
    """
    from PIL import Image

    with Image.open(STATIC / "og-card.png") as im:
        im = im.convert("RGBA")
        assert im.size == (1200, 630), f"og-card 규격 아님: {im.size}"
        px = im.load()
        W, H = im.size

        def _near(p, c, tol=12):
            return all(abs(p[i] - c[i]) <= tol for i in range(3))

        # ② 먹 배경(상단 중앙, 텍스트/보더 밖)
        assert _near(px[600, 40], (26, 23, 20)), f"og-card 먹 배경 아님: {px[600, 40]}"
        # ③ 좌측 마크 영역(96..526)에 v8 마스터 흰 배경 실존 — 구 다크 카드면 흰색 없음.
        top = (H - 430) // 2
        white = total = 0
        for y in range(top, top + 430, 8):
            for x in range(96, 526, 8):
                total += 1
                if _near(px[x, y], (255, 255, 255), 12):
                    white += 1
        assert white / total > 0.3, \
            f"og-card 좌측 마크에 v8 마스터 흰 배경 없음(구 글러브/다크 카드 의심): {white}/{total}"


def test_cache_bust_bumped():
    # 파비콘 ?v=183(v57 아이콘 정정), og ?v=6(v57 대형 통일 — OG도 오너 공식 마크로) 캐시버스트.
    assert "v='183'" in BASE and "v='182'" not in BASE
    assert "og-card.png?v=6" in BASE_APP and "og-card.png?v=5" not in BASE_APP


def test_extension_version_bumped():
    import json
    assert json.loads(MANIFEST)["version"] == "1.5.147"


def test_no_stale_old_icon_files():
    # static에 v8 세트만(글러브/오빗/지구본 등 구 아이콘 PNG 파일 0).
    names = [p.name for p in STATIC.glob("*.png")] + [p.name for p in STATIC.glob("*.ico")]
    for bad in ("glove", "orbit", "globe", "splash"):
        assert not any(bad in n for n in names), f"구 아이콘 파일 잔존: {bad}"
    # 참조된 아이콘 파일은 전부 실존
    import re
    refs = set(re.findall(r"filename='([a-zA-Z0-9._-]+\.(?:png|svg|ico))'", BASE))
    for r in refs:
        assert (STATIC / r).exists(), f"참조된 아이콘 파일 없음: {r}"
