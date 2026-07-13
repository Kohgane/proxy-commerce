"""tests/test_v50_icon_v8_rollout.py — v50: 브랜드 아이콘 v8 전면 배포(해시 일치 + 캐시버스트).

오너가 라이브 파비콘과 v8 마스터 해시 불일치를 확인 → 배포/캐시 문제. 진단 결과 커밋된 static
파비콘은 이미 build_icons.py 코드 v8과 해시 일치(Docker도 포함)했고, og-card만 pre-v8(구 아이콘)이라
재생성했다. 캐시버스트 ?v=181(파비콘)·?v=5(og)로 강제 갱신. 확장 1.5.56.

Pillow는 빌드타임 전용(CI collect-only 미설치) → 해시 테스트는 함수 내 지연 import + 미설치 시 skip.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

STATIC = Path("src/seller_console/static")
BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
BASE_APP = Path("src/templates/_base_app.html").read_text(encoding="utf-8")
MANIFEST = Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8")


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _pillow_ok() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _pillow_ok(), reason="Pillow 미설치(빌드타임 전용)")
def test_committed_favicons_match_code_v8_master():
    # 커밋된 static 파비콘 = build_icons.py deploy() 코드 v8 출력(해시 일치) → 드리프트 0.
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
            assert _md5(STATIC / f) == _md5(tmp / "src/seller_console/static" / f), f"{f} 커밋≠코드v8(재생성 필요)"
        for f in ("16.png", "32.png", "48.png", "128.png"):
            a = _md5(Path("extensions/chrome-collector/icons") / f)
            b = _md5(tmp / "extensions/chrome-collector/icons" / f)
            assert a == b, f"확장 {f} 커밋≠코드v8"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.skipif(not _pillow_ok(), reason="Pillow 미설치")
def test_og_card_uses_v8_master():
    # og-card.png = 현재 v8 마스터(assets/brand-icons/icon-master-1024.png)로 재생성된 최신본.
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen_og_card", "scripts/gen_og_card.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    before = _md5(STATIC / "og-card.png")
    mod.main() if hasattr(mod, "main") else None
    after = _md5(STATIC / "og-card.png")
    # 재실행해도 동일(=이미 v8 마스터 기준) — 재생성이 멱등.
    assert before == after, "og-card가 v8 마스터와 불일치(재생성 필요)"


def test_cache_bust_bumped():
    # 파비콘 ?v=182(v57 아이콘 정정), og ?v=6(v57 대형 통일 — OG도 오너 공식 마크로) 캐시버스트.
    assert "v='182'" in BASE and "v='181'" not in BASE
    assert "og-card.png?v=6" in BASE_APP and "og-card.png?v=5" not in BASE_APP


def test_extension_version_bumped():
    import json
    assert json.loads(MANIFEST)["version"] == "1.5.66"


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
