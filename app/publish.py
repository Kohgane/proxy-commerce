"""app/publish.py — CLI runner for WooCommerce draft publisher."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Dict

from app.collect import PIPELINES, SAMPLE_ITEM
from publisher.draft_publish import DraftPublisher

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def run(source: str, dry_run: bool = False) -> Dict[str, Any]:
    pipeline = PIPELINES.get(source)
    if pipeline is None:
        available = list(PIPELINES.keys())
        raise ValueError(f"Unknown source {source!r}. Available: {available}")

    source_ids = [SAMPLE_ITEM["id"]] if source == "test" else []
    products = pipeline.run_batch(source_ids)
    publisher = DraftPublisher(dry_run=dry_run)

    created = 0
    updated = 0
    failed = 0
    results = []
    for product in products:
        try:
            result = publisher.publish(product)
            action = result.get("action")
            if action == "update":
                updated += 1
            elif action == "create":
                created += 1
            results.append({"source_product_id": product.source_product_id, "result": result})
        except Exception as exc:
            failed += 1
            logger.error("Failed to publish source_product_id=%s: %s", product.source_product_id, exc)
            results.append({"source_product_id": product.source_product_id, "error": str(exc)})

    return {
        "source": source,
        "total": len(products),
        "created": created,
        "updated": updated,
        "failed": failed,
        "dry_run": dry_run,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Proxy Commerce WooCommerce draft publisher")
    parser.add_argument("--source", required=True, help="Collector source name (e.g. test)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not publish; only simulate and report create/update actions",
    )
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
