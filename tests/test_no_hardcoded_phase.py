"""UI-visible hardcoded phase regression guard."""
from __future__ import annotations

import ast
import os
import re

PHASE_RE = re.compile(r"Phase\s+\d+", re.IGNORECASE)


def _root() -> str:
    return os.path.dirname(os.path.dirname(__file__))


def _python_ui_strings(path: str, required_hints: tuple[str, ...]) -> list[str]:
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value
        for line in text.splitlines():
            if not PHASE_RE.search(line):
                continue
            if required_hints and not any(hint in line for hint in required_hints):
                continue
            if "current_phase" in line:
                continue
            if "<" not in line and "message" not in line and "card-header" not in line:
                continue
            offenders.append(line.strip()[:120])
    return offenders


def _html_visible_phase_strings(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r"\{#.*?#\}", "", content, flags=re.DOTALL)
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    return [match.group(0) for match in PHASE_RE.finditer(content) if "current_phase" not in content[max(0, match.start()-40):match.end()+40]]


def test_no_hardcoded_phase_in_runtime_ui_strings():
    root = _root()
    targets = {
        os.path.join(root, "src", "ai_listing", "routes.py"): ("AI 상품등록", "mock status"),
        os.path.join(root, "src", "dashboard", "admin_views.py"): ("AI 상품등록",),
    }
    offenders = {path: _python_ui_strings(path, hints) for path, hints in targets.items()}
    offenders = {path: matches for path, matches in offenders.items() if matches}
    assert not offenders, f"런타임 UI 문자열에 하드코딩 Phase 문구가 남아있습니다: {offenders}"


def test_no_hardcoded_phase_in_phase_macro_pages():
    root = _root()
    targets = [
        os.path.join(root, "src", "templates", "_macros.html"),
        os.path.join(root, "src", "templates", "_base_app.html"),
    ]
    offenders = {path: _html_visible_phase_strings(path) for path in targets}
    # `_macros.html` is the single allowed template that intentionally contains
    # the reusable dynamic `Phase {{ current_phase }}` markup for page headers.
    offenders = {path: matches for path, matches in offenders.items() if matches and not path.endswith("_macros.html")}
    assert not offenders, f"템플릿에 하드코딩 Phase 문구가 남아있습니다: {offenders}"
