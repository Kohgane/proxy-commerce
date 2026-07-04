"""src/utils/env.py — 환경변수 안전 읽기 + 부팅 진단 (v44 0-1).

Render 등에서 값에 실수로 따옴표/공백이 섞여 들어오면 os.getenv가 그대로 반환해 키가 '있는데
안 먹는' 헛걸음이 생긴다. env_str은 앞뒤 공백·감싼 따옴표를 제거해 항상 깨끗한 값을 준다.
로그엔 값을 절대 찍지 않고 '설정됨/없음'만 마스킹 출력한다.
"""
from __future__ import annotations

import os


def env_str(name: str, default: str = "") -> str:
    """환경변수 값(앞뒤 공백 + 감싼 따옴표 제거). 미설정/빈값이면 default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        v = v[1:-1].strip()
    return v or default


def env_present(name: str) -> bool:
    """깨끗한 값이 비어있지 않은지."""
    return bool(env_str(name))


def env_mask(name: str) -> str:
    """로그용 — 값은 절대 노출하지 않고 상태만."""
    return "설정됨" if env_present(name) else "없음"


# 부팅 시 진단할 핵심 키(값 마스킹). 같은 헛걸음(키 있는데 '미설정') 방지용.
_BOOT_CHECK_KEYS = (
    "OPENAI_API_KEY", "DEEPL_API_KEY", "OPENAI_MODEL",
    "CLOUDINARY_CLOUD_NAME", "GOOGLE_SHEET_ID", "SECRET_KEY",
)

# v45 P8: 부팅 시 in-place로 정제해 둘 키 — 이후 모듈들이 raw os.getenv로 읽어도 깨끗한 값을
# 보게 한다(따옴표/공백 오염으로 'AI 초안·번역이 키 있는데 안 먹는' 헛걸음 방지, 단일 소스).
_SANITIZE_KEYS = (
    "OPENAI_API_KEY", "DEEPL_API_KEY", "OPENAI_MODEL", "ANTHROPIC_API_KEY",
)


def sanitize_env_inplace(names=_SANITIZE_KEYS) -> list:
    """지정 환경변수를 os.environ에서 앞뒤 공백·감싼 따옴표를 제거한 값으로 덮어쓴다.

    부팅 1회 호출로 프로세스 전역에 적용 → 이후 어떤 모듈이 os.getenv로 읽어도 정제된 값을 본다.
    감쌈만 있어 빈 값이 되면 키를 제거해 '미설정'으로 정직 처리. 값은 로깅하지 않는다.
    Returns: 실제로 값이 바뀐 키 이름 목록(진단용, 값 제외).
    """
    changed = []
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        clean = env_str(name)
        if clean == raw:
            continue
        if clean:
            os.environ[name] = clean
        else:
            os.environ.pop(name, None)
        changed.append(name)
    return changed


def boot_env_report() -> str:
    """부팅 로그 1줄 — 어떤 키가 실제로 프로세스에 도달했는지(값 마스킹). 정제 후 호출 권장."""
    return "환경변수 체크: " + " · ".join(f"{k}={env_mask(k)}" for k in _BOOT_CHECK_KEYS)
