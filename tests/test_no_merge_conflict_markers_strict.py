from __future__ import annotations

import pathlib
import re

PATTERN = re.compile(r"^(<{7}|={7}|>{7})( |$)", re.MULTILINE)


def test_no_merge_conflict_markers_strict():
    offenders: list[str] = []
    root = pathlib.Path(__file__).resolve().parents[1]
    for rel in ("src", "tests", "templates", "static"):
        base = root / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".py", ".html", ".js", ".css", ".md", ".yml", ".yaml", ".toml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if PATTERN.search(text):
                offenders.append(str(path.relative_to(root)))
    assert not offenders, "merge conflict markers found:\n" + "\n".join(offenders)
