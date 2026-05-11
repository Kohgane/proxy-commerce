from __future__ import annotations

import pathlib

from src.utils.fstring_guard import FSTRING_BACKSLASH_IN_EXPR_PATTERN

def test_no_fstring_with_backslash_in_expression():
    pattern = FSTRING_BACKSLASH_IN_EXPR_PATTERN
    offenders: list[str] = []
    for path in pathlib.Path("src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            snippet = match.group(0).splitlines()[0].strip()
            offenders.append(f"{path}:{line_no}: {snippet}")
    assert not offenders, "f-string 표현식 내부 백슬래시 발견:\n" + "\n".join(offenders)
