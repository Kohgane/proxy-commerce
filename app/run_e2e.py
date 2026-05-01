"""app/run_e2e.py — End-to-end dry-run flow.

Covers issue #88: orchestrates the full pipeline:
  collect → normalize/validate → pricing → draft publish (dry-run)

Usage:
    python -m app.run_e2e --source test
    python -m app.run_e2e --source test --pricing-preset standard
    python -m app.run_e2e --source test --no-dry-run   # CAUTION: actually publishes

Output: JSON summary to stdout.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Dict, List

from collectors.base import BaseCollectorPipeline
from pricing.engine import PRESETS, MarginBelowThresholdError, calculate_sell_price
from publisher.draft_publish import DraftPublisher
from schemas.product import Product


class _NullWooClient:
    """No-op WooCommerce client used in dry-run mode (no network calls)."""

    def find_product_by_idempotency(self, key: str):
        return None

    def create_product(self, payload):
        return {}

    def update_product(self, product_id, payload):
        return {}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Import known collectors (gracefully handle missing HTTP deps)
# ---------------------------------------------------------------------------

def _build_pipeline_registry() -> Dict[str, type]:
    """Import available pipelines and return a name → class mapping."""
    registry: Dict[str, type] = {}

    # Built-in test pipeline (always available)
    from app.collect import TestPipeline
    registry["test"] = TestPipeline

    # ALO Yoga
    try:
        from collectors.alo import AloPipeline
        registry["alo"] = AloPipeline
    except ImportError:
        pass

    # lululemon
    try:
        from collectors.lululemon import LululemonPipeline
        registry["lululemon"] = LululemonPipeline
    except ImportError:
        pass

    return registry


PIPELINE_REGISTRY = _build_pipeline_registry()

# Sample product IDs per source used in dry-run mode
_SAMPLE_IDS: Dict[str, List[str]] = {
    "test": ["TEST-001"],
    "alo": ["https://www.aloyoga.com/products/high-waist-airlift-legging"],
    "lululemon": ["https://www.lululemon.com/en-us/p/align-pant-28/LW5CQAS.html"],
}


# ---------------------------------------------------------------------------
# E2E runner
# ---------------------------------------------------------------------------


def run_e2e(
    source: str,
    pricing_preset: str = "standard",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Run the collect → price → publish pipeline.

    Parameters
    ----------
    source:
        Collector source name (``test``, ``alo``, ``lululemon``).
    pricing_preset:
        One of the pricing presets defined in ``pricing/engine.py``
        (``entry``, ``standard``, ``aggressive``).
    dry_run:
        When ``True`` (default), the publish step is simulated only.

    Returns
    -------
    dict with keys: source, total, success, failed, priced, published
    """
    pipeline_cls = PIPELINE_REGISTRY.get(source)
    if pipeline_cls is None:
        raise ValueError(
            f"Unknown source {source!r}. Available: {sorted(PIPELINE_REGISTRY)}"
        )

    pricing_config = PRESETS.get(pricing_preset)
    if pricing_config is None:
        raise ValueError(
            f"Unknown pricing preset {pricing_preset!r}. Available: {sorted(PRESETS)}"
        )

    source_ids = _SAMPLE_IDS.get(source, [])
    if not source_ids:
        logger.warning("[e2e] No sample IDs defined for source '%s' — nothing to run", source)
        return {"source": source, "total": 0, "success": 0, "failed": 0, "priced": 0, "published": 0}

    # ------------------------------------------------------------------
    # Step 1 — Collect
    # ------------------------------------------------------------------
    logger.info("[e2e] Step 1/3 — Collect (source=%s, ids=%s)", source, source_ids)
    pipeline: BaseCollectorPipeline = pipeline_cls()
    products: List[Product] = pipeline.run_batch(source_ids)
    total = len(source_ids)
    success = len(products)
    failed = total - success
    logger.info("[e2e] Collect done: %d/%d succeeded", success, total)

    # ------------------------------------------------------------------
    # Step 2 — Pricing
    # ------------------------------------------------------------------
    logger.info("[e2e] Step 2/3 — Pricing (preset=%s)", pricing_preset)
    priced_products: List[Product] = []
    pricing_errors: List[str] = []
    for product in products:
        try:
            sell_price = calculate_sell_price(product.cost_price, config=pricing_config)
            priced = product.model_copy(update={"sell_price": sell_price})
            priced_products.append(priced)
            logger.info(
                "[e2e] Priced %s: cost=%.2f → sell=%.2f",
                product.title,
                product.cost_price,
                sell_price,
            )
        except MarginBelowThresholdError as exc:
            logger.warning("[e2e] Pricing skipped for %s: %s", product.title, exc)
            pricing_errors.append(f"{product.source_product_id}: {exc}")
            priced_products.append(product)  # keep original, no sell_price set

    # ------------------------------------------------------------------
    # Step 3 — Draft publish
    # ------------------------------------------------------------------
    logger.info("[e2e] Step 3/3 — Publish (dry_run=%s)", dry_run)
    client = _NullWooClient() if dry_run else None
    publisher = DraftPublisher(client=client, dry_run=dry_run)
    publish_results: List[Dict[str, Any]] = []
    publish_errors: List[str] = []
    for product in priced_products:
        try:
            result = publisher.publish(product)
            publish_results.append(result)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("[e2e] Publish failed for %s: %s", product.source_product_id, exc)
            publish_errors.append(f"{product.source_product_id}: {exc}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    summary: Dict[str, Any] = {
        "source": source,
        "pricing_preset": pricing_preset,
        "dry_run": dry_run,
        "total": total,
        "collect_success": success,
        "collect_failed": failed,
        "priced": len(priced_products),
        "pricing_errors": pricing_errors,
        "published": len(publish_results),
        "publish_errors": publish_errors,
        "results": publish_results,
    }
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Proxy Commerce E2E dry-run runner")
    parser.add_argument(
        "--source",
        required=True,
        choices=sorted(PIPELINE_REGISTRY),
        help="Collector source name",
    )
    parser.add_argument(
        "--pricing-preset",
        default="standard",
        choices=sorted(PRESETS),
        help="Pricing preset to use (default: standard)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        dest="no_dry_run",
        help="Disable dry-run: actually publish to WooCommerce (CAUTION)",
    )
    args = parser.parse_args()

    try:
        result = run_e2e(
            source=args.source,
            pricing_preset=args.pricing_preset,
            dry_run=not args.no_dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        sys.exit(0 if result["collect_failed"] == 0 and not result["publish_errors"] else 1)
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
