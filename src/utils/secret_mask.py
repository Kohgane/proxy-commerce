"""src/utils/secret_mask.py — v61 STEP0(P0 보안): 자격증명 마스킹 공통 유틸.

모든 마켓 어댑터의 예외·로그·UI 에러에서 URL 쿼리·헤더·본문 내 자격증명(consumer_key·secret·토큰류)을
자동 마스킹한다. 형식 = 접두어 + **** + 뒤 4자(예: ck_****d4a7). 평문 노출 0.
"""
from __future__ import annotations

import re

# 마스킹 대상 쿼리/필드 키(값을 가림). authorization/auth는 _AUTH_HDR_RE가 헤더 값을 전담(여기 제외).
_SECRET_KEYS = (
    "consumer_key", "consumer_secret", "client_secret", "client_id",
    "access_token", "refresh_token", "api_key", "apikey", "app_secret",
    "secret", "token", "password", "passwd", "sign", "signature",
    "openApiKey",
)
_QS_RE = re.compile(
    r"((?:" + "|".join(re.escape(k) for k in _SECRET_KEYS) + r")\s*[=:]\s*[\"']?)"
    r"([^&\s\"'}\],]+)",
    re.I,
)
# Authorization/토큰 헤더의 실제 값(Basic/Bearer 뒤 base64·토큰) 전담 마스킹.
_AUTH_HDR_RE = re.compile(
    r"((?:Authorization|X-[A-Za-z-]*(?:Token|Key|Secret))\s*[:=]\s*[\"']?(?:Basic|Bearer)\s+)"
    r"([A-Za-z0-9+/=._~-]{6,})",
    re.I,
)


def mask_value(v, keep: int = 4) -> str:
    """단일 자격증명 값 마스킹 — 접두어(ck_/cs_/shpat_ 등) + **** + 뒤 keep자.
    짧으면(<=8) 전부 ****. 접두어 없으면 앞 3자 유지."""
    s = str(v if v is not None else "")
    if not s:
        return ""
    if len(s) <= keep + 4:
        return "****"
    m = re.match(r"^([A-Za-z]{1,8}_)", s)      # ck_, cs_, shpat_, shpss_, atkn_ …
    prefix = m.group(1) if m else s[:3]
    return f"{prefix}****{s[-keep:]}"


def mask_text(text, secrets=()) -> str:
    """문자열(URL·에러 메시지·응답 본문)에서 자격증명 값을 마스킹.
    - 쿼리/필드 `key=값`·`"key":"값"` 형태의 시크릿 값을 가림.
    - Authorization/토큰 헤더 값을 가림.
    - 추가로 넘긴 secrets 리터럴(실제 키 문자열)은 통째로 치환(가장 확실).
    """
    s = str(text if text is not None else "")
    if not s:
        return s
    # 실제 키 리터럴 먼저(가장 확실 — 어디에 있든 가림). 짧은 값은 오탐 방지로 제외.
    for sec in (secrets or ()):
        sv = str(sec or "")
        if sv and len(sv) >= 6:
            s = s.replace(sv, mask_value(sv))
    s = _QS_RE.sub(lambda m: m.group(1) + mask_value(m.group(2)), s)
    s = _AUTH_HDR_RE.sub(lambda m: m.group(1) + mask_value(m.group(2)), s)
    return s


def mask_url(url) -> str:
    """URL의 쿼리스트링 자격증명만 마스킹(경로·호스트 보존)."""
    return _QS_RE.sub(lambda m: m.group(1) + mask_value(m.group(2)), str(url or ""))
