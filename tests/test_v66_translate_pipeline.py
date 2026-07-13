"""tests/test_v66_translate_pipeline.py — v66 STEP4: 번역 파이프라인 종결.

실패 실원인을 서버 로그·응답으로 특정(무음·오귀인 금지). 벌크 번역 항목별 사유 명시.
북마클릿/확장 경로(translate=true)도 서버 번역을 실제로 태우고 실패 시 원인 표기.
"""
from __future__ import annotations

from pathlib import Path

import requests

VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
EXT_API = Path("src/api/extension_api.py").read_text(encoding="utf-8")
HISTORY = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")


def test_collect_path_surfaces_cause():
    # _translate_payload(확장·북마클릿 경로)가 키 있음·실패 시 원인을 로그+필드로 남김(무음 금지).
    assert "translate_error" in EXT_API
    assert "classify_translate_error" in EXT_API
    assert "키 있음·호출 실패" in EXT_API


def test_bulk_translate_per_item_reason():
    # 벌크 번역 결과에 항목별 사유(reason) + 무료 한도 소진 사유.
    assert '"reason": _r_err' in VIEWS
    assert "무료 한도 소진" in VIEWS
    assert "item_err" in VIEWS


def test_frontend_shows_progress_and_reason():
    # 프론트가 N/total 진행 + 실패 항목 사유 표기(오귀인 금지).
    assert "r.reason" in HISTORY
    assert "실패 ${failed.length}" in HISTORY or "실패 ' + failed.length" in HISTORY
    assert "번역 실패 — ${topReason}" in HISTORY


class _FakeResp:
    def __init__(self, status):
        self.status_code = status


def test_translate_payload_carries_error(monkeypatch):
    # 키 있고 호출 401 → _translate_payload 결과에 translate_error(원인)가 실린다.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-xxxxx")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def _boom(*a, **k):
        e = requests.HTTPError("unauthorized")
        e.response = _FakeResp(401)
        raise e

    monkeypatch.setattr(requests, "post", _boom)
    import src.api.extension_api as ext
    out = ext._translate_payload({"title": "Wireless Earbuds", "description": "desc"})
    # 원문 유지 + 원인(키) 표기.
    assert out["title_ko"] == "Wireless Earbuds"
    assert out.get("translate_error") and "키" in out["translate_error"]
