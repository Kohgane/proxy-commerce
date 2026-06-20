from __future__ import annotations

import os

# KOHgogane(코고가네) — 셀러용 SaaS 툴. KOH 대문자 + gogane 소문자(KOHGANE 가문 표기와 연결).
_DEFAULT_BRAND_EN = "KOHgogane"
_DEFAULT_BRAND_KO = "코고가네"


def get_brand_name() -> str:
    """영문 브랜드명 (기본 KOHgogane). BRAND_NAME env로 override."""
    return (os.getenv("BRAND_NAME") or _DEFAULT_BRAND_EN).strip() or _DEFAULT_BRAND_EN


def get_brand_name_ko() -> str:
    """한글 브랜드명 (기본 코고가네). BRAND_NAME_KO env로 override."""
    return (os.getenv("BRAND_NAME_KO") or _DEFAULT_BRAND_KO).strip() or _DEFAULT_BRAND_KO
