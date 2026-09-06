"""tests/test_static_assets_exist.py — 참조한 정적 자산이 실제로 있는가.

**깨진 이미지는 화면에서만 보이고 테스트에서는 안 보인다.** 그래서 계약으로 본다.

부검(2026-09-06, 6-f-2): 수집 화면 확장 안내의 브랜드 마크가 라이브에서 깨져 있었다.
나는 그걸 **캡처 아티팩트로 판정했는데 오너의 라이브 스크린샷이 반증**했다
([[캡처 아티팩트 판정의 역용]]).

실측 결과 그 건은 파일 실존·경로 200·CSP 허용이 전부 통과해 **로컬 재현이 안 됐다.**
근본 원인을 단정하지 못한 채로도 옳은 수리는 있다 — **외부 파일 의존을 없애는 것.**
아이콘 하나에 404·CSP·배포 아티팩트 리스크를 지불할 이유가 없다.

이 계약은 그 결함 **유형**을 막는다: 템플릿이 가리키는 정적 파일이 레포에 없으면 잡는다.
(배포 이미지에 들어가는지는 Dockerfile COPY 계약이 따로 본다.)
"""
from __future__ import annotations

import re
from pathlib import Path

TPL_DIRS = [Path("src/seller_console/templates"), Path("src/templates")]
STATIC_DIRS = {
    "seller_console.static": Path("src/seller_console/static"),
    "static": Path("src/static"),
}

# `url_for('<endpoint>', filename='<path>')` — 템플릿이 정적 자산을 가리키는 정본 방식.
_URL_FOR = re.compile(
    r"url_for\(\s*['\"]([\w.]*static)['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]")


def _templates():
    for d in TPL_DIRS:
        if d.exists():
            yield from sorted(d.rglob("*.html"))


def test_every_referenced_static_file_exists():
    """★ 템플릿이 가리키는 정적 파일은 **레포에 실제로 있어야 한다.**

    없으면 사용자는 깨진 아이콘을 보고, 우리는 스위트가 초록이라 모른다.
    """
    missing = []
    for tpl in _templates():
        for endpoint, filename in _URL_FOR.findall(tpl.read_text(encoding="utf-8")):
            root = STATIC_DIRS.get(endpoint)
            if root is None:                       # 우리가 모르는 엔드포인트는 판단하지 않는다
                continue
            if not (root / filename).exists():
                missing.append(f"{tpl.name} → {endpoint}:{filename}")
    assert not missing, "참조한 정적 파일이 없다:\n  " + "\n  ".join(missing)


def test_static_dirs_ship_in_the_image():
    """배포 아티팩트 — `COPY src/`가 static을 통째로 실어야 한다.

    이 프로젝트는 같은 지뢰를 두 번 밟았다(extensions/ 누락 #227 · scripts/ 누락 #423):
    **컨테이너에 있다 ≠ 프로덕션에 있다.**
    """
    docker = Path("Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^COPY\s+src/\s+\./src/", docker, re.M), "src/ COPY가 사라졌다"
    ignored = Path(".dockerignore").read_text(encoding="utf-8") if Path(".dockerignore").exists() else ""
    for line in ignored.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            assert "static" not in line, f".dockerignore가 static을 배제한다: {line}"


def test_brand_mark_in_collect_note_is_inline():
    """★ 확장 안내 마크는 **인라인 SVG**다 — 외부 파일이면 404·CSP·배포 누락이 깰 수 있다.

    라이브 파손의 근본 원인을 단정하진 못했지만, 의존을 없애면 원인과 무관하게 안 깨진다.
    """
    tpl = Path("src/seller_console/templates/manual_collect.html").read_text(encoding="utf-8")
    # 경계는 `</svg>`로 잡는다 — `</div>`로 자르면 svg 속성 중간에서 끊긴다(첫 판의 오탐).
    note = tpl.split('class="mc-note mt-3"')[1].split("</svg>")[0] + "</svg>"
    assert '<svg class="mc-note-mark"' in note
    assert "favicon.svg" not in tpl, "외부 파일 참조가 되살아났다"
    # 색은 클래스로 — SVG 프레젠테이션 속성은 var()를 못 받는다.
    assert not re.findall(r'(?:fill|stroke)="#', note), "인라인 SVG에 하드코딩 색"
    css = Path("src/static/app.css").read_text(encoding="utf-8")
    for cls in (".bm-arch", ".bm-deck", ".bm-tie", ".bm-key"):
        assert cls in css, f"{cls} 선언 없음"


def test_remaining_remote_images_degrade_quietly():
    """외부 호스트 이미지(소싱처 파비콘)는 **실패해도 깨진 아이콘을 남기지 않는다.**

    우리가 통제 못 하는 자산이라 실존 검사를 걸 수 없다 — 대신 조용히 사라지게 한다.
    """
    tpl = Path("src/seller_console/templates/manual_collect.html").read_text(encoding="utf-8")
    for m in re.finditer(r"<img[^>]*src=\"https?://[^\"]+\"[^>]*>", tpl):
        assert "onerror" in m.group(0), f"외부 이미지에 폴백이 없다: {m.group(0)[:80]}"
