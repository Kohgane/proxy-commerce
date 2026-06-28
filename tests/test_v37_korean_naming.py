"""tests/test_v37_korean_naming.py — v37: 한글 표기 '고가브릿지'(붙여쓰기) 통일."""
from __future__ import annotations

import os
import subprocess

import pytest


def test_brand_ko_default_no_space():
    from src.utils.branding import get_brand_name_ko
    assert get_brand_name_ko() == "고가브릿지"
    assert " " not in get_brand_name_ko()


def test_brand_ko_normalizes_spaced_env(monkeypatch):
    # env override에 공백이 섞여도('고가 브릿지') 붙여쓰기로 정규화
    import importlib
    from src.utils import branding
    monkeypatch.setenv("BRAND_NAME_KO", "고가 브릿지")
    importlib.reload(branding)
    try:
        assert branding.get_brand_name_ko() == "고가브릿지"
    finally:
        monkeypatch.delenv("BRAND_NAME_KO", raising=False)
        importlib.reload(branding)


def test_brand_en_is_gogabridj():
    # v38: 영문 정식 표기는 'gogabridj'(전부 소문자·붙임)
    from src.utils.branding import get_brand_name
    assert get_brand_name() == "gogabridj"


def test_no_spaced_korean_brand_in_source():
    # 사용자 노출 한글 표기에 '고가 브릿지'(공백) 잔존 0 (소스 전수)
    res = subprocess.run(
        ["grep", "-rIn", "고가 브릿지", "src/", "extensions/", "docs/"],
        capture_output=True, text=True,
    )
    assert res.stdout.strip() == "", f"공백 표기 잔존:\n{res.stdout}"
