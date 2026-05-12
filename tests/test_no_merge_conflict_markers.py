from __future__ import annotations

import pathlib
import re

PATTERN = re.compile(r"^(<{7}|={7}|>{7})( |$)", re.MULTILINE)


def test_no_merge_conflict_markers():
    offenders = []
    for root in ["src", "templates", "tests"]:
        base = pathlib.Path(root)
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in (".py", ".html", ".js", ".css", ".md", ".yml", ".yaml", ".toml"):
                text = path.read_text(errors="ignore")
                if PATTERN.search(text):
                    offenders.append(str(path))
    assert not offenders, "머지 충돌 마커:\n" + "\n".join(offenders)
