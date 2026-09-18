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

# F32-후속 실측(2026-09-18): 백필 사유에 **cloud name 값이 원문 그대로** 남았다
#   (`cloudciuga`). 길이가 짧아 아래 긴-토큰 규칙에 안 걸린다 — 길이로는 못 잡는다.
#   그래서 **우리가 아는 설정값**을 이름으로 안다: 그 값이 문장에 나타나면 가린다.
#   값은 **비교에만** 쓰고 로그·출력 어디에도 남기지 않는다.
_KNOWN_VALUE_ENVS = (
    "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET",
    "CLOUDINARY_FOLDER",
    "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY",
    "COUPANG_GOGANE_ACCESS_KEY", "COUPANG_GOGANE_SECRET_KEY",
    "COUPANG_WOOJOO_ACCESS_KEY", "COUPANG_WOOJOO_SECRET_KEY",
    "TENCENT_SECRET_ID", "TENCENT_SECRET_KEY",
    "DATABASE_URL", "DATABASE_URL_DIRECT", "SUPABASE_DB_URL",
    "TELEGRAM_COLLECT_BOT_TOKEN", "TELEGRAM_BOT_TOKEN",
    "SECRET_KEY", "MARKET_CRED_ENC_KEY",
)
# 네 글자 미만은 안 가린다 — 흔한 낱말을 통째로 먹어 사유가 읽을 수 없게 된다.
_MIN_VALUE_LEN = 4

_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_QUOTED_HOST = re.compile(r'"[A-Za-z0-9.-]+\.[A-Za-z]{2,}"')
_PORT = re.compile(r"\bport\s+\d+\b", re.I)
# Cloudinary·API 키류가 문장에 섞여 들어오는 경우의 마지막 방어선(길이 20+ 영숫자 토큰).
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_-]{24,}\b")


def scrub_infra(text: str, *, limit: int = 240) -> str:
    """`text`에서 주소·아이피·호스트·포트·긴 토큰·**아는 설정값**을 지우고 사유만 남긴다.

    > ★ **한 필드에 두 규칙을 두지 않는다.** 실측(2026-09-18): 같은 「사유」인데
    > `_LAST_ERROR`는 쓰기 때 세척되고 `cdn_error`는 원문 그대로 저장·출력돼,
    > cloud name 값이 화면에 남았다. **화면에 닿는 사유는 전부 여기를 지난다.**
    """
    out = str(text or "")
    # 아는 값부터 — 긴 토큰 규칙이 자르기 전에 통째로 가린다.
    out = _mask_known_values(out)
    out = _URL.sub("[주소]", out)
    out = _IP.sub("[아이피]", out)
    out = _QUOTED_HOST.sub('"[호스트]"', out)
    out = _PORT.sub("port [포트]", out)
    out = _LONG_TOKEN.sub("[값]", out)
    return out[:limit]


def _mask_known_values(text: str) -> str:
    """이름으로 아는 설정값이 문장에 있으면 `[값]`으로 가린다.

    **값을 어디에도 남기지 않는다** — 비교에만 쓴다. 긴 것부터 지워야
    짧은 값이 긴 값의 일부를 먼저 먹지 않는다(예: 폴더명이 cloud name의 접두일 때).
    """
    import os
    vals = set()
    for name in _KNOWN_VALUE_ENVS:
        v = (os.getenv(name) or "").strip()
        if len(v) >= _MIN_VALUE_LEN:
            vals.add(v)
    for v in sorted(vals, key=len, reverse=True):
        text = text.replace(v, "[값]")
    return text
