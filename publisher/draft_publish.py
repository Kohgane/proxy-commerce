"""publisher/draft_publish.py — Draft publish adapter.

Covers issue #90: maps Product -> WooCommerce payload and supports dry_run.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from schemas.product import Product
from publisher.woocommerce_client import WooCommerceClient

logger = logging.getLogger(__name__)


def _resolve_sell_price(product: Product) -> float:
    """Return sell_price, falling back to cost_price with a warning."""
    if product.sell_price is not None:
        return product.sell_price
    logger.warning(
        "sell_price not set for product %s (%s); falling back to cost_price — margin will be zero",
        product.source_product_id,
        product.title,
    )
    return product.cost_price


def product_to_woo_payload(product: Product) -> Dict[str, Any]:
    """Convert a Product model into a WooCommerce product payload.

    Always sets status='draft' for pre-publish review.
    """
    images = [{"src": url} for url in product.images]

    attributes = []
    for opt in product.options:
        attributes.append({
            "name": opt.name,
            "options": opt.values,
            "visible": True,
            "variation": True,
        })

    payload: Dict[str, Any] = {
        "name": product.title,
        "status": "draft",
        "description": product.description or "",
        "regular_price": str(_resolve_sell_price(product)),
        "images": images,
        "attributes": attributes,
        "meta_data": [
            {"key": "_source", "value": product.source},
            {"key": "_source_product_id", "value": product.source_product_id},
            {"key": "_source_url", "value": product.source_url},
            {"key": "_cost_price", "value": str(product.cost_price)},
            {"key": "_currency", "value": product.currency},
        ],
    }

    if product.brand:
        payload["meta_data"].append({"key": "_brand", "value": product.brand})

    if product.stock_status.value == "out_of_stock":
        payload["stock_status"] = "outofstock"
    elif product.stock_status.value == "in_stock":
        payload["stock_status"] = "instock"

    return payload


class DraftPublisher:
    """Publishes Product objects to WooCommerce as drafts."""

    def __init__(
        self,
        client: Optional[WooCommerceClient] = None,
        dry_run: bool = False,
    ) -> None:
        self.client = client or WooCommerceClient()
        self.dry_run = dry_run

    def publish(self, product: Product) -> Dict[str, Any]:
        """Map product to payload and POST to WooCommerce.

        In dry_run mode, returns the payload without making HTTP requests.
        """
        payload = product_to_woo_payload(product)

        if self.dry_run:
            logger.info("[dry_run] Would publish: %s", product.title)
            return {"dry_run": True, "payload": payload}

        logger.info("Publishing draft: %s (source=%s id=%s)", product.title, product.source, product.source_product_id)
        result = self.client.create_product(payload)
        logger.info("Published WooCommerce product id=%s", result.get("id"))
        return result
