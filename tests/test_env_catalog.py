"""tests/test_env_catalog.py — 환경변수 카탈로그 테스트 (Phase 128)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 기본 임포트
# ---------------------------------------------------------------------------

def test_import():
    """모듈 임포트가 성공해야 함."""
    from src.utils.env_catalog import API_REGISTRY, ApiKey, get_api_status, get_api_key, is_active
    assert len(API_REGISTRY) > 0


def test_api_registry_has_required_keys():
    """필수 API 키가 레지스트리에 등록되어야 함."""
    from src.utils.env_catalog import API_REGISTRY
    names = {k.name for k in API_REGISTRY}
    required = {"coupang_wing", "naver_commerce", "elevenst", "exchange_rate", "amazon_paapi", "rakuten"}
    assert required.issubset(names), f"누락된 키: {required - names}"


def test_status_missing_without_env(monkeypatch):
    """환경변수 없으면 status='missing' 반환."""
    from src.utils.env_catalog import get_api_key
    monkeypatch.delenv("EXCHANGE_RATE_API_KEY", raising=False)
    key = get_api_key("exchange_rate")
    assert key is not None
    assert key.status == "missing"


def test_status_active_with_env(monkeypatch):
    """환경변수 설정 시 status='active' 반환."""
    from src.utils.env_catalog import get_api_key
    monkeypatch.setenv("EXCHANGE_RATE_API_KEY", "test_key_1234567890")
    key = get_api_key("exchange_rate")
    assert key is not None
    assert key.status == "active"


def test_masked_values_short_key(monkeypatch):
    """12자 이하 키는 '***'으로 마스킹."""
    from src.utils.env_catalog import get_api_key
    monkeypatch.setenv("EXCHANGE_RATE_API_KEY", "shortkey")
    key = get_api_key("exchange_rate")
    assert key is not None
    assert key.masked_values["EXCHANGE_RATE_API_KEY"] == "***"


def test_masked_values_long_key(monkeypatch):
    """13자 이상 키는 앞4***뒤4 마스킹."""
    from src.utils.env_catalog import get_api_key
    monkeypatch.setenv("EXCHANGE_RATE_API_KEY", "abcd1234567890wxyz")
    key = get_api_key("exchange_rate")
    assert key is not None
    masked = key.masked_values["EXCHANGE_RATE_API_KEY"]
    assert masked.startswith("abcd")
    assert "***" in masked
    assert masked.endswith("wxyz")


def test_masked_values_none_when_missing(monkeypatch):
    """환경변수 없으면 masked_values의 값이 None."""
    from src.utils.env_catalog import get_api_key
    monkeypatch.delenv("EXCHANGE_RATE_API_KEY", raising=False)
    key = get_api_key("exchange_rate")
    assert key is not None
    assert key.masked_values["EXCHANGE_RATE_API_KEY"] is None


def test_get_api_status_returns_list():
    """get_api_status()는 dict 반환 (Phase 130: apis 키에 목록 포함)."""
    from src.utils.env_catalog import get_api_status
    result = get_api_status()
    # Phase 130: dict 반환 (apis, summary, categories, render_env_note)
    assert isinstance(result, dict)
    api_list = result.get("apis", [])
    assert len(api_list) > 0
    for item in api_list:
        assert "name" in item
        assert "status" in item
        assert item["status"] in ("active", "missing")


def test_get_api_status_missing_has_hint(monkeypatch):
    """missing 상태 API는 hint 필드 포함."""
    from src.utils.env_catalog import get_api_status
    monkeypatch.delenv("EXCHANGE_RATE_API_KEY", raising=False)
    result = get_api_status()
    api_list = result.get("apis", []) if isinstance(result, dict) else result
    er = next(r for r in api_list if r["name"] == "exchange_rate")
    assert er["status"] == "missing"
    assert er["hint"] is not None


def test_is_active_false_without_env(monkeypatch):
    """is_active: 환경변수 없으면 False."""
    from src.utils.env_catalog import is_active
    monkeypatch.delenv("ELEVENST_API_KEY", raising=False)
    assert is_active("elevenst") is False


def test_is_active_true_with_env(monkeypatch):
    """is_active: 환경변수 있으면 True."""
    from src.utils.env_catalog import is_active
    monkeypatch.setenv("ELEVENST_API_KEY", "some_test_api_key_value")
    assert is_active("elevenst") is True


def test_get_api_key_unknown_returns_none():
    """존재하지 않는 이름은 None 반환."""
    from src.utils.env_catalog import get_api_key
    assert get_api_key("nonexistent_key_xyz") is None


def test_multi_env_var_partial_missing(monkeypatch):
    """여러 환경변수 중 하나라도 없으면 missing."""
    from src.utils.env_catalog import get_api_key
    monkeypatch.setenv("COUPANG_VENDOR_ID", "V001")
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "AK001")
    monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)
    key = get_api_key("coupang_wing")
    assert key is not None
    assert key.status == "missing"


def test_multi_env_var_all_set(monkeypatch):
    """모든 환경변수 설정 시 active."""
    from src.utils.env_catalog import get_api_key
    monkeypatch.setenv("COUPANG_VENDOR_ID", "V001test00000")
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "AK001test00000")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "SK001test00000")
    key = get_api_key("coupang_wing")
    assert key is not None
    assert key.status == "active"
