from __future__ import annotations

import pathlib
import re


def test_no_fstring_with_backslash_in_expression():
    pattern = re.compile(r"""f["'][^"\n]*\{[^}\n]*\\[^}\n]*\}[^"\n]*["']""")
    offenders: list[str] = []
    for path in pathlib.Path("src").rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path}:{i}: {line.strip()}")
    assert not offenders, "f-string 표현식 내부 백슬래시 발견:\n" + "\n".join(offenders)
