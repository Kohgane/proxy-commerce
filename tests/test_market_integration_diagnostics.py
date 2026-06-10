from __future__ import annotations

from src.seller_console.market_integration_diagnostics import build_market_ui_state, run_market_diagnostic


def test_run_market_diagnostic_exposes_last_checked_at(monkeypatch):
    monkeypatch.setattr(
        "src.seller_console.market_integration_diagnostics._adapter_health_step",
        lambda market: {
            "ok": True,
            "market": market,
            "step": "read_connection",
            "error_code": "",
            "hint": "실제 연결 확인 성공",
            "detail": "연결 성공",
            "raw": {},
        },
    )
    monkeypatch.setattr(
        "src.seller_console.market_integration_diagnostics._write_dry_run_step",
        lambda market: {
            "ok": True,
            "market": market,
            "step": "write_dry_run",
            "error_code": "",
            "hint": "실 쓰기 대신 안전 dry-run 검증 완료",
            "detail": "dry_run",
            "raw": {},
        },
    )

    result = run_market_diagnostic("coupang")

    assert result["checked_at"] == result["last_checked_at"]


def test_run_market_diagnostic_maps_missing_credentials(monkeypatch):
    monkeypatch.setattr(
        "src.seller_console.market_integration_diagnostics._adapter_health_step",
        lambda market: {
            "ok": False,
            "market": market,
            "step": "read_connection",
            "error_code": "token_missing",
            "hint": "필수 환경변수를 먼저 설정하세요.",
            "detail": "COUPANG_ACCESS_KEY 누락",
            "raw": {},
        },
    )
    monkeypatch.setattr(
        "src.seller_console.market_integration_diagnostics._write_dry_run_step",
        lambda market: {
            "ok": False,
            "market": market,
            "step": "write_dry_run",
            "error_code": "token_missing",
            "hint": "safe write 검증 불가",
            "detail": "자격증명 미설정",
            "raw": {},
        },
    )

    result = run_market_diagnostic("coupang")

    assert result["status"] == "token_missing"
    assert result["steps"][0]["error_code"] == "token_missing"
    assert result["ui"]["badge_label"] == "token_missing"


def test_run_market_diagnostic_maps_scope_insufficient(monkeypatch):
    monkeypatch.setattr(
        "src.seller_console.market_integration_diagnostics._shopify_read_step",
        lambda: {
            "ok": False,
            "market": "shopify",
            "step": "read_connection",
            "error_code": "scope_insufficient",
            "hint": "앱 스코프를 확인하세요.",
            "detail": "HTTP 403",
            "raw": {},
        },
    )
    monkeypatch.setattr(
        "src.seller_console.market_integration_diagnostics._write_dry_run_step",
        lambda market: {
            "ok": True,
            "market": market,
            "step": "write_dry_run",
            "error_code": "",
            "hint": "실 쓰기 대신 안전 dry-run 검증 완료",
            "detail": "dry_run",
            "raw": {},
        },
    )

    result = run_market_diagnostic("shopify")

    assert result["status"] == "scope_insufficient"
    assert result["hint"] == "앱 스코프를 확인하세요."
    assert result["ui"]["disabled_reason"] == "앱 권한을 보강한 뒤 다시 시도하세요."
    assert result["ui"]["recommended_action"] == "scope"


def test_run_market_diagnostic_connected_when_read_and_write_pass(monkeypatch):
    monkeypatch.setattr(
        "src.seller_console.market_integration_diagnostics._adapter_health_step",
        lambda market: {
            "ok": True,
            "market": market,
            "step": "read_connection",
            "error_code": "",
            "hint": "실제 연결 확인 성공",
            "detail": "연결 성공",
            "raw": {},
        },
    )
    monkeypatch.setattr(
        "src.seller_console.market_integration_diagnostics._write_dry_run_step",
        lambda market: {
            "ok": True,
            "market": market,
            "step": "write_dry_run",
            "error_code": "",
            "hint": "실 쓰기 대신 안전 dry-run 검증 완료",
            "detail": "dry_run",
            "raw": {},
        },
    )

    result = run_market_diagnostic("woocommerce")

    assert result["ok"] is True
    assert result["status"] == "connected"
    assert result["steps"][1]["step"] == "write_dry_run"
    assert result["ui"]["badge_text"] == "✅ 연결됨"


def test_build_market_ui_state_exposes_technical_detail():
    ui = build_market_ui_state(
        {
            "status": "api_error",
            "summary": "연결 실패",
            "hint": "잠시 후 다시 시도하세요.",
            "steps": [
                {"ok": False, "detail": "HTTP 500", "error_code": "api_error"},
            ],
        }
    )

    assert ui["badge_label"] == "api_error"
    assert ui["technical_detail"] == "HTTP 500"
    assert ui["action_text"].startswith("재시도 버튼")
