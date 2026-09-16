"""src/utils/redact.py — 오류 문장에서 **좌표만** 지운다 (F31).

## 왜 한 곳인가

F30에서 이 세척기를 두 군데(`views._scrub_infra`, `image_ko_blobs_pg._scrub`) 썼다.
F31에서 세 번째가 필요해졌다 — 그때가 합칠 때다. 같은 일을 하는 코드가 셋이면
하나만 고친 날 나머지 둘이 샌다.

## 규율

- **사유는 남긴다** — `timeout expired` · `relation ... does not exist` ·
  `Invalid api_key`. 이게 없으면 화면이 아무 말도 안 하는 것과 같다.
- **좌표는 지운다** — URL · 아이피 · 호스트 · 포트. 그게 나가면 사유가 아니라 인프라 지도다.
- **자격은 애초에 넣지 않는다.** 여기서 지우는 건 마지막 방어선이지 허가가 아니다.
"""
from __future__ import annotations

import re

_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_QUOTED_HOST = re.compile(r'"[A-Za-z0-9.-]+\.[A-Za-z]{2,}"')
_PORT = re.compile(r"\bport\s+\d+\b", re.I)
# Cloudinary·API 키류가 문장에 섞여 들어오는 경우의 마지막 방어선(길이 20+ 영숫자 토큰).
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_-]{24,}\b")


def scrub_infra(text: str, *, limit: int = 240) -> str:
    """`text`에서 주소·아이피·호스트·포트·긴 토큰을 지우고 사유만 남긴다."""
    out = str(text or "")
    out = _URL.sub("[주소]", out)
    out = _IP.sub("[아이피]", out)
    out = _QUOTED_HOST.sub('"[호스트]"', out)
    out = _PORT.sub("port [포트]", out)
    out = _LONG_TOKEN.sub("[값]", out)
    return out[:limit]
