"""publisher/woocommerce_client.py — WooCommerce REST API client.

Covers issue #90: draft publisher using WC_URL/WC_KEY/WC_SECRET env vars
and HTTP Basic Auth to /wp-json/wc/v3/products.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

_WC_URL = os.getenv("WC_URL", "")
_WC_KEY = os.getenv("WC_KEY", "")
_WC_SECRET = os.getenv("WC_SECRET", "")

_API_PATH = "/wp-json/wc/v3/products"


class WooCommerceClient:
    """Minimal WooCommerce REST API client (Basic Auth)."""

    def __init__(
        self,
        wc_url: Optional[str] = None,
        wc_key: Optional[str] = None,
        wc_secret: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = (wc_url or _WC_URL).rstrip("/")
        self.auth = HTTPBasicAuth(wc_key or _WC_KEY, wc_secret or _WC_SECRET)
        self.timeout = timeout

    def _url(self, path: str = "") -> str:
        return urljoin(self.base_url + "/", (_API_PATH + path).lstrip("/"))

    def create_product(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /wp-json/wc/v3/products — create a new product."""
        url = self._url()
        logger.debug("WooCommerce POST %s payload=%s", url, payload)
        resp = requests.post(url, json=payload, auth=self.auth, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def update_product(self, product_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """PUT /wp-json/wc/v3/products/{id} — update an existing product."""
        url = self._url(f"/{product_id}")
        logger.debug("WooCommerce PUT %s payload=%s", url, payload)
        resp = requests.put(url, json=payload, auth=self.auth, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_product(self, product_id: int) -> Dict[str, Any]:
        """GET /wp-json/wc/v3/products/{id}."""
        url = self._url(f"/{product_id}")
        resp = requests.get(url, auth=self.auth, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def list_products(self, **params: Any) -> list:
        """GET /wp-json/wc/v3/products with optional query params."""
        url = self._url()
        resp = requests.get(url, params=params, auth=self.auth, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _meta_value(product: Dict[str, Any], key: str) -> Optional[str]:
        for item in product.get("meta_data", []):
            if item.get("key") == key:
                value = item.get("value")
                return None if value is None else str(value)
        return None

    def find_product_by_idempotency(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Find an existing product by idempotency metadata.

        Primary key:
            _idempotency_key = "{source}:{source_product_id}"

        Backward-compatible fallback:
            _source + _source_product_id
        """
        if ":" in idempotency_key:
            source, source_product_id = idempotency_key.split(":", 1)
        else:
            source, source_product_id = "", ""

        page = 1
        while True:
            products = self.list_products(status="any", page=page, per_page=100)
            if not products:
                return None

            for product in products:
                if self._meta_value(product, "_idempotency_key") == idempotency_key:
                    return product
                if (
                    source
                    and source_product_id
                    and self._meta_value(product, "_source") == source
                    and self._meta_value(product, "_source_product_id") == source_product_id
                ):
                    return product
            page += 1
