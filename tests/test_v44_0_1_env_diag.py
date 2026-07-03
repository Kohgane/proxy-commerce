"""tests/test_v44_0_1_env_diag.py — v44 0-1: 환경변수 진단(키 있는데 '미설정' 헛걸음 방지).

env_str이 따옴표/공백을 제거해 읽고, 부팅 로그가 값 마스킹으로 도달 여부를 1줄 출력.
translator 프로바이더 선택이 정제된 값을 쓴다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils.env import env_str, env_present, env_mask, boot_env_report  # noqa: E402


def test_env_str_strips_quotes_and_whitespace(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", '  "sk-xyz"  ')
    assert env_str("OPENAI_API_KEY") == "sk-xyz"
    monkeypatch.setenv("OPENAI_API_KEY", "'sk-single'")
    assert env_str("OPENAI_API_KEY") == "sk-single"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-plain")
    assert env_str("OPENAI_API_KEY") == "sk-plain"


def test_env_present_false_for_empty_or_whitespace(monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "   ")
    assert env_present("DEEPL_API_KEY") is False
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    assert env_present("DEEPL_API_KEY") is False


def test_boot_report_masks_value(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value-123")
    line = boot_env_report()
    assert "환경변수 체크" in line
    assert "OPENAI_API_KEY=설정됨" in line
    assert "sk-secret-value-123" not in line   # 값 절대 노출 금지


def test_translator_provider_uses_cleaned_env(monkeypatch):
    # 따옴표가 섞여도 프로바이더가 openai로 선택돼야(옛 os.getenv 직판정은 따옴표 그대로라도 truthy였지만
    # 값 정제로 실제 호출까지 정상).
    monkeypatch.setenv("OPENAI_API_KEY", '  "sk-abc"  ')
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    from src.seller_console.ai.translator import AITranslator
    assert AITranslator()._select_provider() == "openai"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPL_API_KEY", "dl-key")
    assert AITranslator()._select_provider() == "deepl"
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    assert AITranslator()._select_provider() == "stub"


def test_boot_log_line_in_order_webhook():
    from pathlib import Path
    src = Path("src/order_webhook.py").read_text(encoding="utf-8")
    assert "boot_env_report" in src   # 부팅 시 체크라인 출력
