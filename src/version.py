"""src/version.py — Phase 버전 자동화 (Phase 148).

CURRENT_PHASE: ROADMAP.md 최신 Phase 번호 (수동 상수 + 파싱 fallback)
"""
from __future__ import annotations

import os
import re
import logging

logger = logging.getLogger(__name__)

# 하드코딩 상수 — Phase PR마다 이 줄만 변경
CURRENT_PHASE: int = 149

APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")


def _parse_roadmap_phase() -> int | None:
    """ROADMAP.md에서 최신 Phase 번호를 파싱한다.

    Returns:
        최신 Phase 번호 (int), 파싱 실패 시 None
    """
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "ROADMAP.md"),
        "ROADMAP.md",
    ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            matches = re.findall(r"##\s+Phase\s+(\d+)", content, re.MULTILINE)
            if matches:
                return max(int(m) for m in matches)
        except Exception as exc:
            logger.debug("ROADMAP 파싱 실패 (%s): %s", path, exc)
    return None


def get_current_phase() -> int:
    """현재 Phase 번호를 반환한다.

    우선순위:
      1. CURRENT_PHASE_OVERRIDE 환경변수 (CI 빌드 주입용)
      2. CURRENT_PHASE 상수 (이 파일의 하드코딩)
      3. ROADMAP.md 파싱 fallback
    """
    override = os.getenv("CURRENT_PHASE_OVERRIDE")
    if override and override.isdigit():
        return int(override)
    return CURRENT_PHASE


def get_version_string() -> str:
    """'Phase NNN · x.y.z' 형식 버전 문자열 반환."""
    return f"Phase {get_current_phase()} · {APP_VERSION}"
