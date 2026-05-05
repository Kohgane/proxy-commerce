"""tests/test_env_catalog_extended.py — env_catalog Phase 130 확장 테스트."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 임포트
# ---------------------------------------------------------------------------

def test_import_new_symbols():
    """Phase 130 신규 심볼 임포트."""
    from src.utils.env_catalog import (
        API_REGISTRY,
        ApiCategory,
        ENV_ALIASES,
        resolve_env,
        get_api_status,
        get_api_key,
        is_active,
    )
    assert len(API_REGISTRY) >= 20  # 24개 이상


def test_api_category_enum():
    """ApiCategory 열거형 멤버 확인."""
    from src.utils.env_catalog import ApiCategory
    assert ApiCategory.MARKETPLACE.value == "marketplace"
    assert ApiCategory.PAYMENT.value == "payment"
    assert ApiCategory.AUTH.value == "auth"
    assert ApiCategory.NOTIFICATION.value == "notification"
    assert ApiCategory.LOGISTICS.value == "logistics"
    assert ApiCategory.SELF_MALL.value == "self_mall"


def test_api_registry_has_new_keys():
    """신규 32개 항목에 필수 키 포함 여부 (Phase 134 갱신)."""
    from src.utils.env_catalog import API_REGISTRY
    names = {k.name for k in API_REGISTRY}
    required = {
        "coupang_wing", "naver_commerce", "elevenst",
        "amazon_paapi", "rakuten",
        "openai", "deepl",
        "toss_payments", "paypal",
        "kakao_login", "google_oauth", "naver_login",
        "telegram", "resend",
        "trackingmore",
        "shopify", "woocommerce",
        "exchange_rate", "pexels", "unsplash",
        # Phase 134 신규
        "kakao_alimtalk", "line_notify", "line_messaging",
        "whatsapp", "wechat", "twilio_sms", "aligo_sms", "discord_webhook",
    }
    missing = required - names
    assert not missing, f"누락된 키: {missing}"


def test_api_key_has_category():
    """모든 ApiKey 인스턴스에 category 필드 존재."""
    from src.utils.env_catalog import API_REGISTRY, ApiCategory
    for k in API_REGISTRY:
        assert isinstance(k.category, ApiCategory), f"{k.name} category 누락"


def test_resolve_env_direct(monkeypatch):
    """resolve_env: 직접 이름으로 검색."""
    from src.utils.env_catalog import resolve_env
    monkeypatch.setenv("EXCHANGE_RATE_API_KEY", "test_rate_key_12345")
    assert resolve_env("EXCHANGE_RATE_API_KEY") == "test_rate_key_12345"


def test_resolve_env_alias_wc_key(monkeypatch):
    """resolve_env: WC_KEY → WOO_CK 별칭 폴백."""
    from src.utils.env_catalog import resolve_env
    monkeypatch.delenv("WC_KEY", raising=False)
    monkeypatch.setenv("WOO_CK", "woo_ck_value_test")
    # WC_KEY 별칭 목록에 WOO_CK 포함
    val = resolve_env("WC_KEY")
    assert val == "woo_ck_value_test"


def test_resolve_env_alias_wc_url(monkeypatch):
    """resolve_env: WC_URL → WOO_BASE_URL 별칭 폴백."""
    from src.utils.env_catalog import resolve_env
    monkeypatch.delenv("WC_URL", raising=False)
    monkeypatch.setenv("WOO_BASE_URL", "https://myshop.com")
    val = resolve_env("WC_URL")
    assert val == "https://myshop.com"


def test_resolve_env_no_alias(monkeypatch):
    """resolve_env: 별칭 없는 이름 — 직접 검색."""
    from src.utils.env_catalog import resolve_env
    monkeypatch.setenv("PEXELS_API_KEY", "pexels_test_key")
    assert resolve_env("PEXELS_API_KEY") == "pexels_test_key"


def test_resolve_env_missing(monkeypatch):
    """resolve_env: 없는 환경변수 — None 반환."""
    from src.utils.env_catalog import resolve_env
    monkeypatch.delenv("NONEXISTENT_VAR_XYZ", raising=False)
    assert resolve_env("NONEXISTENT_VAR_XYZ") is None


def test_get_api_status_returns_dict():
    """get_api_status()는 dict 반환 (Phase 130 변경)."""
    from src.utils.env_catalog import get_api_status
    result = get_api_status()
    assert isinstance(result, dict)
    assert "apis" in result
    assert "summary" in result
    assert "categories" in result
    assert "render_env_note" in result


def test_get_api_status_summary_structure():
    """summary 필드 구조 확인."""
    from src.utils.env_catalog import get_api_status
    result = get_api_status()
    summary = result["summary"]
    assert "total" in summary
    assert "active" in summary
    assert "missing" in summary
    assert "by_category" in summary
    assert summary["total"] == summary["active"] + summary["missing"]


def test_get_api_status_apis_have_category():
    """apis 목록 각 항목에 category 필드 존재."""
    from src.utils.env_catalog import get_api_status
    result = get_api_status()
    for api in result["apis"]:
        assert "category" in api
        assert api["category"] in [
            "marketplace", "sourcing", "ai", "payment", "auth",
            "notification", "logistics", "self_mall", "utility", "infra",
        ]


def test_get_api_status_render_env_note():
    """render_env_note 필드에 Render 관련 안내 포함."""
    from src.utils.env_catalog import get_api_status
    result = get_api_status()
    note = result["render_env_note"]
    assert "Render" in note
    assert "GitHub Secrets" in note


def test_telegram_active_with_env(monkeypatch):
    """텔레그램 키 설정 시 active."""
    from src.utils.env_catalog import is_active
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567890:testbottoken0000000")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")
    assert is_active("telegram") is True


def test_telegram_missing_without_env(monkeypatch):
    """텔레그램 키 미설정 시 missing."""
    from src.utils.env_catalog import is_active
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert is_active("telegram") is False


def test_woocommerce_alias_active(monkeypatch):
    """WooCommerce: WOO_CK/WOO_CS/WOO_BASE_URL 별칭으로 active 판단."""
    from src.utils.env_catalog import get_api_key
    monkeypatch.delenv("WC_KEY", raising=False)
    monkeypatch.delenv("WC_SECRET", raising=False)
    monkeypatch.delenv("WC_URL", raising=False)
    monkeypatch.setenv("WOO_CK", "ck_test_key_0000000000000000000")
    monkeypatch.setenv("WOO_CS", "cs_test_secret_000000000000000000")
    monkeypatch.setenv("WOO_BASE_URL", "https://myshop.com")
    key = get_api_key("woocommerce")
    assert key is not None
    assert key.status == "active"


def test_by_category_counts():
    """by_category 집계 정확성."""
    from src.utils.env_catalog import get_api_status
    result = get_api_status()
    by_cat = result["summary"]["by_category"]
    total_from_cats = sum(v["total"] for v in by_cat.values())
    assert total_from_cats == result["summary"]["total"]
