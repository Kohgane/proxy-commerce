#!/usr/bin/env python3
"""scripts/build_extension_zip.py — v83.1 STEP2: 확장 ZIP CLI 래퍼(로직은 src/build_extension.py).

CI 아티팩트·오너 로컬 빌드용. 실제 패키징 로직은 배포 이미지에도 들어가는 `src/build_extension.py`에 있다
(Dockerfile이 scripts/를 통째로 COPY하지 않기 때문 — #423 재발 방지).

사용: python scripts/build_extension_zip.py [출력경로.zip]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.build_extension import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
