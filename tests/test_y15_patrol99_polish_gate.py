"""순찰 99(2026-10-25) — 번역 직후 자동 다듬기는 인스턴스 메모리 여유가 있을 때만.

실측(운영 DB `rss:recent` render 줄, 15:35~15:50 KST): 다듬기 그리기 7장의 인스턴스 피크 469·438·388·369·472·466·483MB(512MB
인스턴스), 바탕 345~444MB. detail#17·#18은 그리는 중 프로세스가 죽어(`rss:restart` boot ×6, 우리 상한 기록 없음 = 바깥 종료)
같은 장을 다시 집는 되풀이. 다듬기를 미루면 번역본은 남고 큐는 계속 간다.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def calls(monkeypatch):
    from src.services import image_polish as ip
    seen = []
    monkeypatch.setattr(ip, "polish_job", lambda *a, **k: seen.append(a) or {"ok": True})
    return seen


def _mb(monkeypatch, value: int):
    from src.utils import rss
    monkeypatch.setattr(rss, "instance_mb", lambda: value)


def test_polish_runs_when_memory_low(monkeypatch, calls):
    from src.services import image_translate_auto as ita
    monkeypatch.delenv("IMAGE_POLISH_AUTO_MAX_MB", raising=False)
    _mb(monkeypatch, 220)
    assert ita._maybe_polish("item1", "u1", "detail", 3) is True
    assert calls == [("item1", "u1", "detail", 3)]


def test_polish_deferred_when_memory_high(monkeypatch, calls):
    from src.services import image_translate_auto as ita
    monkeypatch.delenv("IMAGE_POLISH_AUTO_MAX_MB", raising=False)
    _mb(monkeypatch, 345)                                        # 15:35 실측 바탕 — 그 위에 +130이면 475
    assert ita._maybe_polish("item1", "u1", "detail", 0) is False
    assert calls == []


def test_default_threshold_and_env_override(monkeypatch, calls):
    from src.services import image_translate_auto as ita
    monkeypatch.delenv("IMAGE_POLISH_AUTO_MAX_MB", raising=False)
    assert ita.polish_auto_max_mb() == 300
    monkeypatch.setenv("IMAGE_POLISH_AUTO_MAX_MB", "400")
    _mb(monkeypatch, 345)
    assert ita._maybe_polish("i", "u", "gallery", 1) is True     # 상한을 올리면 돈다
    monkeypatch.setenv("IMAGE_POLISH_AUTO_MAX_MB", "0")
    _mb(monkeypatch, 999)
    assert ita._maybe_polish("i", "u", "gallery", 2) is True     # 0 = 끔(예전처럼 언제나)
    monkeypatch.setenv("IMAGE_POLISH_AUTO_MAX_MB", "abc")
    assert ita.polish_auto_max_mb() == 300


def test_translate_job_calls_gate_not_polish_directly():
    import inspect

    from src.services import image_translate_auto as ita
    src = inspect.getsource(ita._translate_job)
    assert "_maybe_polish(item_id, uid, kind, idx)" in src
    assert "_ip.polish_job(" not in src
