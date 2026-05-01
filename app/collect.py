"""app/collect.py — CLI runner for the collector pipeline.

Covers issue #86: CLI with --source test scaffold that runs one sample item
through the pipeline and prints success/failed counts as JSON.

Usage:
    python -m app.collect --source test
    python -m app.collect --source test --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Dict

from collectors.base import BaseCollectorPipeline
from schemas.product import Product

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Test/sample pipeline (scaffold)
# ---------------------------------------------------------------------------

SAMPLE_ITEM = {
    "id": "TEST-001",
    "raw": {
        "title": "Sample Running Shoes",
        "brand": "TestBrand",
        "price": 89.99,
        "currency": "USD",
        "images": ["https://example.com/img/shoe1.jpg", "https://example.com/img/shoe2.jpg"],
        "url": "https://example.com/products/sample-running-shoes",
        "description": "Lightweight running shoes for everyday training.",
        "stock": "in_stock",
    },
}


class TestPipeline(BaseCollectorPipeline):
    """Minimal scaffold pipeline for --source test."""

    source = "test"

    def fetch(self, source_id: str) -> Any:
        if source_id == SAMPLE_ITEM["id"]:
            return SAMPLE_ITEM["raw"]
        raise ValueError(f"Unknown test source_id: {source_id!r}")

    def parse(self, raw: Any) -> Dict[str, Any]:
        return dict(raw)

    def normalize(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source": "test",
            "source_product_id": "TEST-001",
            "source_url": parsed.get("url", "https://example.com"),
            "brand": parsed.get("brand"),
            "title": parsed.get("title", ""),
            "description": parsed.get("description"),
            "currency": parsed.get("currency", "USD"),
            "cost_price": float(parsed.get("price", 0)),
            "images": parsed.get("images", []),
            "stock_status": parsed.get("stock", "unknown"),
        }


# ---------------------------------------------------------------------------
# Pipeline registry
# ---------------------------------------------------------------------------

PIPELINES: dict[str, BaseCollectorPipeline] = {
    "test": TestPipeline(),
}


def run(source: str, dry_run: bool = False) -> Dict[str, Any]:
    pipeline = PIPELINES.get(source)
    if pipeline is None:
        available = list(PIPELINES.keys())
        raise ValueError(f"Unknown source {source!r}. Available: {available}")

    # For the test scaffold, run a single sample item
    source_ids = [SAMPLE_ITEM["id"]] if source == "test" else []

    report = pipeline.run_batch_report(source_ids)

    output = {
        "source": source,
        "total": report["total"],
        "success": report["success"],
        "failed": report["failed"],
    }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Proxy Commerce collector runner")
    parser.add_argument("--source", required=True, help="Collector source name (e.g. test)")
    parser.add_argument("--dry-run", action="store_true", help="Do not publish; only validate")
    args = parser.parse_args()

    try:
        result = run(source=args.source, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["failed"] == 0 else 1)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
