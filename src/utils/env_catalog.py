"""src/utils/env_catalog.py — 외부 API 환경변수 카탈로그 (Phase 128).

모든 외부 API 환경변수를 한 곳에서 관리.
- 누락 시 stub 모드로 자동 폴백
- /health/deep 에 어떤 키가 활성/누락인지 노출 (마스킹된 상태로)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal, Optional

ApiStatus = Literal["active", "missing"]


@dataclass
class ApiKey:
    """단일 외부 API 키 정보."""

    name: str
    env_vars: list  # 필요한 모든 환경변수
    purpose: str    # 한국어 용도
    docs_url: str
    optional: bool = True

    @property
    def status(self) -> ApiStatus:
        """환경변수 존재 여부로 상태 판단."""
        if all(os.getenv(v) for v in self.env_vars):
            return "active"
        return "missing"

    @property
    def masked_values(self) -> dict:
        """환경변수 값을 마스킹해 반환 (앞4***뒤4)."""
        result = {}
        for v in self.env_vars:
            val = os.getenv(v)
            if val:
                result[v] = val[:4] + "***" + val[-4:] if len(val) > 12 else "***"
            else:
                result[v] = None
        return result


# ---------------------------------------------------------------------------
# 전체 API 레지스트리
# ---------------------------------------------------------------------------

API_REGISTRY: list = [
    ApiKey(
        name="coupang_wing",
        env_vars=["COUPANG_VENDOR_ID", "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY"],
        purpose="쿠팡 윙 OpenAPI — 상품 등록/주문 조회",
        docs_url="https://wing.coupang.com",
    ),
    ApiKey(
        name="naver_commerce",
        env_vars=["NAVER_COMMERCE_CLIENT_ID", "NAVER_COMMERCE_CLIENT_SECRET"],
        purpose="네이버 커머스 API — 스마트스토어",
        docs_url="https://commerce.naver.com",
    ),
    ApiKey(
        name="elevenst",
        env_vars=["ELEVENST_API_KEY"],
        purpose="11번가 셀러 API",
        docs_url="https://soffice.11st.co.kr",
    ),
    ApiKey(
        name="exchange_rate",
        env_vars=["EXCHANGE_RATE_API_KEY"],
        purpose="실시간 환율 (USD/JPY/EUR/CNY)",
        docs_url="https://app.exchangerate-api.com",
    ),
    ApiKey(
        name="amazon_paapi",
        env_vars=["AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"],
        purpose="Amazon Product Advertising API 5.0 — 미국 소싱",
        docs_url="https://affiliate-program.amazon.com",
    ),
    ApiKey(
        name="rakuten",
        env_vars=["RAKUTEN_APP_ID"],
        purpose="라쿠텐 Web Service — 일본 소싱",
        docs_url="https://webservice.rakuten.co.jp",
    ),
    ApiKey(
        name="openai",
        env_vars=["OPENAI_API_KEY"],
        purpose="번역 + 광고 카피 자동 생성",
        docs_url="https://platform.openai.com",
    ),
    ApiKey(
        name="deepl",
        env_vars=["DEEPL_API_KEY"],
        purpose="번역 (OpenAI 대체)",
        docs_url="https://www.deepl.com/pro-api",
    ),
]


def get_api_status() -> list:
    """전체 API 상태 목록 반환 (마스킹된 값 포함).

    Returns:
        각 API의 상태 정보를 담은 dict 목록
    """
    return [
        {
            "name": k.name,
            "purpose": k.purpose,
            "status": k.status,
            "env_vars": k.masked_values,
            "docs_url": k.docs_url,
            "hint": (
                f"{k.docs_url} 에서 API 발급 후 "
                f"{', '.join(k.env_vars)} 등록"
                if k.status == "missing" else None
            ),
        }
        for k in API_REGISTRY
    ]


def get_api_key(name: str) -> Optional[ApiKey]:
    """이름으로 ApiKey 인스턴스 조회."""
    for k in API_REGISTRY:
        if k.name == name:
            return k
    return None


def is_active(name: str) -> bool:
    """특정 API 활성 여부 확인."""
    k = get_api_key(name)
    return k is not None and k.status == "active"
