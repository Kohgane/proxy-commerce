"""tests/test_pricing_cron.py — 재가격 cron 라우트 테스트 (Phase 136)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_app():
    from src.utils import bg_job
    bg_job.reset()
    from flask import Flask
    from src.pricing.cron import cron_bp
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(cron_bp)
    return app


class TestRepriceCronRoute:
    def test_reprice_dry_run(self):
        app = _make_app()

        mock_results = {
            "evaluated": 5,
            "changed": 2,
            "skipped": 0,
            "errors": [],
            "details": [
                {"sku": "A", "old": 100000, "new": 105000, "delta_pct": 5.0, "rules": ["test"]},
            ],
            "dry_run": True,
            "run_at": "2026-05-06T00:00:00+00:00",
        }

        with patch("src.pricing.engine.PricingEngine.evaluate", return_value=mock_results), \
             patch("src.pricing.cron._send_summary_notification"):
            client = app.test_client()
            resp = client.post("/cron/reprice?dry_run=1")
            # Z8: 엔진은 요청 밖 — 즉시 202, 결과는 작업 상태(/cron/jobs)에
            assert resp.status_code == 202 and resp.get_json()["started"] is True
            from src.utils import bg_job
            st = bg_job.join("reprice")

        assert st["state"] == "done"
        data = st["result"]
        assert data["ok"] is True
        assert data["results"]["evaluated"] == 5
        jobs = client.get("/cron/jobs").get_json()["jobs"]
        assert jobs["reprice"]["result"]["results"]["evaluated"] == 5 and jobs["reprice"]["elapsed_ms"] is not None

    def test_reprice_unauthorized(self, monkeypatch):
        monkeypatch.setenv("CRON_SECRET", "supersecret")
        app = _make_app()

        client = app.test_client()
        resp = client.post("/cron/reprice")
        assert resp.status_code == 401

    def test_reprice_with_correct_secret(self, monkeypatch):
        monkeypatch.setenv("CRON_SECRET", "supersecret")
        app = _make_app()

        mock_results = {"evaluated": 0, "changed": 0, "skipped": 0,
                        "errors": [], "details": [], "dry_run": True, "run_at": ""}

        with patch("src.pricing.engine.PricingEngine.evaluate", return_value=mock_results), \
             patch("src.pricing.cron._send_summary_notification"):
            client = app.test_client()
            resp = client.post("/cron/reprice", headers={"X-Cron-Secret": "supersecret"})
            from src.utils import bg_job
            bg_job.join("reprice")

        assert resp.status_code == 202

    def test_reprice_engine_error_is_recorded_as_failed(self):
        """Z8: 응답은 이미 202로 나갔다 — 엔진 오류는 작업 상태에 failed + 사유로 남는다."""
        app = _make_app()

        with patch("src.pricing.engine.PricingEngine.evaluate", side_effect=RuntimeError("DB error")):
            client = app.test_client()
            resp = client.post("/cron/reprice")
            from src.utils import bg_job
            st = bg_job.join("reprice")

        assert resp.status_code == 202
        assert st["state"] == "failed" and st["result"]["ok"] is False and "DB error" in st["result"]["error"]
