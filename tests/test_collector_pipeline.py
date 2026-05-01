from __future__ import annotations

import json

from collectors.base import BaseCollectorPipeline


class _SamplePipeline(BaseCollectorPipeline):
    source = "sample"

    def fetch(self, source_id: str):
        return {"id": source_id, "title": "Sample", "price": 10}

    def parse(self, raw):
        return dict(raw)

    def normalize(self, parsed):
        return {
            "source": self.source,
            "source_product_id": parsed["id"],
            "source_url": "https://example.com/p/1",
            "brand": "Brand",
            "title": parsed["title"],
            "description": None,
            "currency": "USD",
            "cost_price": float(parsed["price"]),
            "images": ["https://example.com/p/1.jpg"],
            "stock_status": "in_stock",
        }


def test_run_one_logs_all_stages(caplog):
    pipeline = _SamplePipeline()
    with caplog.at_level("INFO"):
        product = pipeline.run_one("A-1")

    assert product is not None
    assert "fetch start" in caplog.text
    assert "parse start" in caplog.text
    assert "normalize start" in caplog.text
    assert "validate start" in caplog.text


def test_fetch_retry_with_exponential_backoff():
    sleeps: list[float] = []
    calls = {"count": 0}

    class _FlakyFetchPipeline(_SamplePipeline):
        def fetch(self, source_id: str):
            calls["count"] += 1
            if calls["count"] < 3:
                raise RuntimeError("temporary fetch error")
            return super().fetch(source_id)

    pipeline = _FlakyFetchPipeline(max_retries=2, backoff_factor=0.5, sleep_func=sleeps.append)
    product = pipeline.run_one("A-2")

    assert product is not None
    assert calls["count"] == 3
    assert sleeps == [0.5, 1.0]


def test_failed_items_jsonl_written_on_parse_failure(monkeypatch, tmp_path):
    import collectors.base as base_module

    class _ParseFailPipeline(_SamplePipeline):
        def parse(self, raw):
            raise ValueError("parse boom")

    logs_dir = tmp_path / "logs"
    failed_log = logs_dir / "failed_items.jsonl"
    monkeypatch.setattr(base_module, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(base_module, "FAILED_ITEMS_LOG", failed_log)

    pipeline = _ParseFailPipeline()
    assert pipeline.run_one("A-3") is None

    assert failed_log.exists()
    payload = json.loads(failed_log.read_text(encoding="utf-8").strip())
    assert payload["stage"] == "parse"
    assert "parse boom" in payload["error"]
    assert payload["raw"]["id"] == "A-3"


def test_runner_accepts_retry_backoff_options():
    from app.collect import run

    result = run("test", max_retries=1, backoff_factor=0.1)
    assert result["source"] == "test"
    assert result["success"] == 1
