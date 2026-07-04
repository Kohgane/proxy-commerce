"""tests/test_v45_p8_env_sanitize.py — v45 P8: OPENAI/DEEPL '미설정'(값·재배포 완료 상태) 근본 수리.

증상: Render에 키 설정+재배포했는데 앱은 '미설정' → AI 초안·번역 안 됨.
근본: v44 0-1은 seller_console/ai/translator만 env_str로 정제 — copywriter(AI 초안)·
translator_quality·ai_listing 등은 raw os.getenv라 값에 따옴표/공백이 섞이면 여전히 '안 먹음'.
수리: 부팅 시 sanitize_env_inplace로 키를 os.environ에서 in-place 정제 → 이후 어떤 모듈이
raw os.getenv로 읽어도 깨끗한 값(단일 소스). 값은 로깅하지 않음.
"""
from __future__ import annotations

import os

import pytest

from src.utils.env import sanitize_env_inplace, env_present


@pytest.fixture
def clean_env(monkeypatch):
    for k in ("OPENAI_API_KEY", "DEEPL_API_KEY", "OPENAI_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    yield


def test_strips_wrapping_double_quotes(clean_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", '"sk-abc123"')
    changed = sanitize_env_inplace()
    assert "OPENAI_API_KEY" in changed
    assert os.getenv("OPENAI_API_KEY") == "sk-abc123"   # raw 읽기도 깨끗


def test_strips_wrapping_single_quotes_and_whitespace(clean_env, monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "  'dl-xyz'  ")
    sanitize_env_inplace()
    assert os.getenv("DEEPL_API_KEY") == "dl-xyz"


def test_empty_after_strip_removes_key(clean_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", '""')   # 감쌈만 → 빈 값
    sanitize_env_inplace()
    assert os.getenv("OPENAI_API_KEY") is None     # 미설정으로 정직 처리
    assert env_present("OPENAI_API_KEY") is False


def test_clean_value_unchanged_not_reported(clean_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-clean")
    changed = sanitize_env_inplace()
    assert "OPENAI_API_KEY" not in changed         # 이미 깨끗 → 변경 없음
    assert os.getenv("OPENAI_API_KEY") == "sk-clean"


def test_downstream_raw_getenv_sees_clean_value(clean_env, monkeypatch):
    """AI 초안/번역 모듈이 쓰는 raw os.getenv 패턴이 정제 후 키를 인식."""
    monkeypatch.setenv("OPENAI_API_KEY", ' "sk-live" ')
    monkeypatch.setenv("DEEPL_API_KEY", '"dl-live"')
    sanitize_env_inplace()
    # copywriter/translator_quality가 하는 것과 동일한 raw 읽기
    assert bool(os.getenv("OPENAI_API_KEY", "")) is True
    assert os.getenv("OPENAI_API_KEY") == "sk-live"
    assert os.getenv("DEEPL_API_KEY") == "dl-live"


def test_boot_calls_sanitize_before_report(clean_env, monkeypatch):
    """order_webhook 부팅이 리포트 전에 정제를 부르는지(소스 계약)."""
    from pathlib import Path
    src = Path("src/order_webhook.py").read_text(encoding="utf-8")
    assert "sanitize_env_inplace" in src
    assert src.index("sanitize_env_inplace(") < src.index("boot_env_report()")
