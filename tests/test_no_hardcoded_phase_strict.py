"""tests/test_no_hardcoded_phase_strict.py — Phase 151.1: 엄격한 Phase 하드코딩 봉쇄 테스트.

HTML 템플릿과 Python 코드의 문자열 리터럴에 'Phase NNN' 하드코딩이 없어야 한다.

허용:
  - Python docstring/주석 (# 또는 \"\"\" 블록)
  - HTML 주석 <!-- ... -->
  - src/version.py, ROADMAP.md, CHANGELOG.md, docs/

금지:
  - HTML 태그 안 직접 렌더되는 Phase NNN
  - Python quoted string literals (API 응답, 하드코딩 메시지)
  - JS 코드 내 Phase NNN 문자열
"""
from __future__ import annotations

import pathlib
import re
import os


PHASE_PATTERN = re.compile(r'Phase\s+\d+', re.IGNORECASE)

WHITELIST_FILES = {"ROADMAP.md", "CHANGELOG.md", "src/version.py"}
WHITELIST_DIRS = {"docs/"}
ROOT = pathlib.Path(os.path.dirname(os.path.dirname(__file__)))


def _html_has_hardcoded_phase(text: str) -> list[tuple[int, str]]:
    """HTML 파일에서 하드코딩 Phase 발견. HTML 주석은 제외."""
    offending_lines = []
    in_comment = False
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if "<!--" in stripped:
            in_comment = True
        if "-->" in stripped:
            in_comment = False
            continue
        if in_comment:
            continue
        # 동적 템플릿 변수는 허용
        if "{{ current_phase" in line or "{%%" in line:
            continue
        if PHASE_PATTERN.search(line):
            offending_lines.append((lineno, stripped))
    return offending_lines


def _py_has_hardcoded_phase_literal(text: str) -> list[tuple[int, str]]:
    # Python 파일에서 따옴표 안의 Phase NNN 리터럴 발견.
    # 주석(#), docstring 블록, 모듈 docstring은 제외.
    offending_lines = []
    in_docstring = False
    docstring_delim = None

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()

        # docstring 토글
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                delim = stripped[:3]
                # 같은 줄에서 닫힘 여부
                if stripped.count(delim) >= 2 and len(stripped) > 3:
                    # 단일 줄 docstring - 건너뜀
                    continue
                in_docstring = True
                docstring_delim = delim
                continue
        else:
            if docstring_delim and docstring_delim in stripped:
                in_docstring = False
            continue

        # 주석 라인
        if stripped.startswith("#"):
            continue

        # 따옴표 안의 Phase NNN 리터럴만 체크
        if re.search(r'["\'].*Phase\s+\d+.*["\']', line):
            # {{ current_phase }} 형태 허용
            if "current_phase" in line:
                continue
            offending_lines.append((lineno, stripped))

    return offending_lines


def test_no_hardcoded_phase_in_html_templates():
    """templates/ 하위 HTML 파일에 Phase NNN 하드코딩 없어야 함."""
    offenders = []
    base = ROOT / "templates"
    if not base.exists():
        return
    for path in base.rglob("*.html"):
        rel = str(path.relative_to(ROOT))
        if path.name in WHITELIST_FILES or any(rel.startswith(d) for d in WHITELIST_DIRS):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for lineno, line in _html_has_hardcoded_phase(text):
            offenders.append(f"{rel}:{lineno}: {line}")

    assert not offenders, (
        "❌ HTML 템플릿에 하드코딩된 Phase 발견:\n"
        + "\n".join(offenders)
        + "\n\n{{ current_phase }} 템플릿 변수를 사용하세요."
    )


def test_no_hardcoded_phase_in_ai_listing_python_literals():
    """src/ai_listing/ Python 파일의 string 리터럴에 Phase NNN 없어야 함."""
    offenders = []
    base = ROOT / "src" / "ai_listing"
    if not base.exists():
        return
    for path in base.rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for lineno, line in _py_has_hardcoded_phase_literal(text):
            offenders.append(f"{rel}:{lineno}: {line}")

    assert not offenders, (
        "❌ Python 코드 문자열 리터럴에 하드코딩된 Phase 발견:\n"
        + "\n".join(offenders)
    )


def test_routes_py_no_hardcoded_phase_status_message():
    """routes.py api_status 응답에 'Phase NNN' 하드코딩 없어야 함."""
    path = ROOT / "src" / "ai_listing" / "routes.py"
    text = path.read_text(encoding="utf-8")

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if re.search(r'["\'].*Phase\s+\d+.*["\']', line):
            assert False, (
                f"routes.py:{lineno} 에 'Phase NNN' 하드코딩 문자열 리터럴 발견:\n  {stripped}"
            )


def test_admin_views_ai_card_no_hardcoded_phase():
    """admin_views.py AI listing 카드 영역에 'Phase NNN' 하드코딩 없어야 함.

    AI listing 카드 섹션 (<!-- AI 상품등록 진단 -->)만 검사.
    이 영역에서는 {{ current_phase }} 동적 변수를 사용해야 함.
    """
    path = ROOT / "src" / "dashboard" / "admin_views.py"
    text = path.read_text(encoding="utf-8")

    # AI 카드 섹션만 추출
    ai_card_start = "<!-- AI 상품등록 진단 -->"
    ai_card_end = "</div>\n    </div>"

    start_idx = text.find(ai_card_start)
    if start_idx == -1:
        return  # 섹션 없으면 패스

    # 섹션 종료 지점 (다음 카드까지)
    end_idx = text.find("</div>\n    </div>\n\n  </main>", start_idx)
    if end_idx == -1:
        end_idx = start_idx + 3000  # 최대 3000자

    ai_card_text = text[start_idx:end_idx]

    for lineno_offset, line in enumerate(ai_card_text.splitlines(), 1):
        stripped = line.strip()
        if "{{ current_phase" in line:
            continue
        if re.search(r'["\'].*Phase\s+\d+.*["\']', line):
            assert False, (
                f"admin_views.py AI 카드 섹션에 'Phase NNN' 하드코딩 발견:\n  {stripped}"
            )

