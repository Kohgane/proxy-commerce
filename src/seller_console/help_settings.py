"""도움말 설정값 — 아이폰 단축어 설치 링크(M3-iOS 보충, 오너 2026-09-28).

오너가 아이폰에서 단축어를 만들고 「iCloud 링크 복사」한 값을 **관리자 화면에서 붙여넣는다**.
저장은 `app_state`(PG, 없으면 메모리) — D3-8·F53과 같은 자리. 환경변수 `IOS_SHORTCUT_URL`은 폴백.
비어 있으면 안내 화면은 버튼 대신 「준비 중」이라고 말한다(없는 링크를 지어내지 않는다).
"""
from __future__ import annotations

import os
import re

_KEY = "help:ios_shortcut_url"
# iCloud 단축어 공유 링크 모양만 받는다(다른 주소를 「단축어 설치」 버튼에 걸면 유저가 엉뚱한 곳으로 간다).
_ICLOUD_RE = re.compile(r"^https://www\.icloud\.com/shortcuts/[0-9A-Za-z]{8,64}/?$")


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def ios_shortcut_url() -> str:
    try:
        v = str((_st().state_get(_KEY) or {}).get("url") or "").strip()
    except Exception:
        v = ""
    return v or os.getenv("IOS_SHORTCUT_URL", "").strip()


def save_ios_shortcut_url(url: str) -> str:
    """빈 문자열이면 지운다(「준비 중」으로 돌아간다). 모양이 틀리면 ValueError."""
    u = str(url or "").strip()
    if u and not _ICLOUD_RE.match(u):
        raise ValueError("iCloud 단축어 링크(https://www.icloud.com/shortcuts/…)만 넣을 수 있어요.")
    _st().state_set(_KEY, {"url": u})
    return u
