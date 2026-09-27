#!/usr/bin/env python3
"""SEC-1: 진단·스냅샷 파일에서 로그인 비밀 값을 `***`로 가린다(제자리 수정).

    python scripts/scrub_diag_secrets.py            # fixtures/realpages/·tests/fixtures/ 전체
    python scripts/scrub_diag_secrets.py --check    # 고치지 않고 남은 비밀 키 이름만 보고(있으면 exit 1)
    python scripts/scrub_diag_secrets.py 파일...     # 지정한 파일만

값은 절대 출력하지 않는다(파일명·키 이름·개수만). 규칙은 src/collectors/secret_scrub.py.
"""
from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collectors.secret_scrub import find_secrets, scrub_text  # noqa: E402

DEFAULT_GLOBS = ("fixtures/realpages/**/*.html", "fixtures/realpages/**/*.json",
                 "tests/fixtures/**/*.html", "tests/fixtures/**/*.json")


def targets(argv):
    files = [a for a in argv if not a.startswith("--")]
    if files:
        return files
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = []
    for g in DEFAULT_GLOBS:
        out.extend(glob.glob(os.path.join(root, g), recursive=True))
    return sorted(set(out))


def main(argv) -> int:
    check = "--check" in argv
    dirty = 0
    for path in targets(argv):
        with open(path, encoding="utf-8", errors="surrogateescape") as f:
            text = f.read()
        keys = find_secrets(text)
        if not keys:
            continue
        dirty += 1
        rel = os.path.relpath(path)
        if check:
            print(f"비밀 남음: {rel} — 키 {', '.join(keys)}")
            continue
        with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(scrub_text(text))
        print(f"가림: {rel} — 키 {', '.join(keys)}")
    if check and dirty:
        print("→ python scripts/scrub_diag_secrets.py 로 지운 뒤 커밋하세요.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
