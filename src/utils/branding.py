from __future__ import annotations

import os

# 고가브릿지(Goga Bridj) — 셀러용 크로스보더 커머스 SaaS. 수집→등록 사이를 잇는 '다리(Bridj)'.
# ※ 영문 정식 표기는 'Goga Bridj'(e 없음). 글로벌/수출 레인 단축형은 'Bridj'.
_DEFAULT_BRAND_EN = "Goga Bridj"
_DEFAULT_BRAND_KO = "고가브릿지"


def get_brand_name() -> str:
    """영문 브랜드명 (기본 Goga Bridj). BRAND_NAME env로 override."""
    return (os.getenv("BRAND_NAME") or _DEFAULT_BRAND_EN).strip() or _DEFAULT_BRAND_EN


def get_brand_name_ko() -> str:
    """한글 브랜드명 (기본 고가브릿지). BRAND_NAME_KO env로 override."""
    return (os.getenv("BRAND_NAME_KO") or _DEFAULT_BRAND_KO).strip() or _DEFAULT_BRAND_KO
