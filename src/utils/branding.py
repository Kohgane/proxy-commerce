from __future__ import annotations

import os
import re

# 고가브릿지(gogabridj) — 셀러용 크로스보더 커머스 SaaS. 수집→등록 사이를 잇는 '다리(Bridj)'.
# ※ v38 확정 표기: 영문 'gogabridj'(전부 소문자·붙임), 한글 '고가브릿지'(붙여쓰기). 띄어쓴 옛 표기 폐기.
_DEFAULT_BRAND_EN = "gogabridj"
_DEFAULT_BRAND_KO = "고가브릿지"


def get_brand_name() -> str:
    """영문 브랜드명 (기본 gogabridj). BRAND_NAME env로 override."""
    return (os.getenv("BRAND_NAME") or _DEFAULT_BRAND_EN).strip() or _DEFAULT_BRAND_EN


def get_brand_name_ko() -> str:
    """한글 브랜드명 (기본 고가브릿지). BRAND_NAME_KO env로 override.
    v37: 한글 표기는 붙여쓰기('고가브릿지')가 정식 — env override에 공백이 섞여 들어와도
    내부 공백을 모두 제거해 단일 표기로 정규화한다(사용자 노출 한글 표기 일관성, 단일소스).
    """
    raw = (os.getenv("BRAND_NAME_KO") or _DEFAULT_BRAND_KO).strip() or _DEFAULT_BRAND_KO
    normalized = re.sub(r"\s+", "", raw)
    return normalized or _DEFAULT_BRAND_KO
