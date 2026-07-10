"""build_info — 라이브 배포 커밋 판정용 단일 소스(v53 STEP0).

증상: 코드는 main에 머지됐는데 라이브에 안 보임 → 머지/배포 누락 여부를 **curl 한 줄**로 판정할 수 있게
페이지 `<meta name="build">` + `/health` build 필드에 배포 커밋 7자리를 노출한다.

우선순위: RENDER_GIT_COMMIT(Render 런타임 자동 주입) → BUILD_SHA/GIT_COMMIT/SOURCE_COMMIT env →
빌드타임 기록 파일(BUILD_SHA) → 개발 git → "unknown". 값 없으면 정직하게 unknown(가짜 커밋 날조 금지).
"""
from __future__ import annotations

import functools
import os
import subprocess


@functools.lru_cache(maxsize=1)
def get_build_sha() -> str:
    for key in ("RENDER_GIT_COMMIT", "BUILD_SHA", "GIT_COMMIT", "SOURCE_COMMIT", "SOURCE_VERSION"):
        v = os.getenv(key)
        if v and v.strip():
            return v.strip()[:7]
    # 빌드타임 기록 파일(Dockerfile이 남길 수 있음)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        for cand in (os.path.join(here, "..", "..", "BUILD_SHA"), "/app/BUILD_SHA"):
            if os.path.exists(cand):
                with open(cand, "r", encoding="utf-8") as f:
                    s = f.read().strip()
                    if s:
                        return s[:7]
    except Exception:
        pass
    # 개발 환경 폴백: git
    try:
        s = subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=2,
        ).decode().strip()
        if s:
            return s
    except Exception:
        pass
    return "unknown"
