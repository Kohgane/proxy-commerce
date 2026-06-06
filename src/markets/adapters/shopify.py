"""Shopify Admin API adapter."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

import requests

from .base import ListingPayload, ListingResult, MarketAdapter, OrderStatus


class ShopifyAdapter(MarketAdapter):
    market = "shopify"
    country = "US"
    currency = "USD"
    locale = "en-US"
    region = "북미"
    _idempotency_map: Dict[str, str] = {}
    _idempotency_lock = threading.Lock()

    def __init__(self, session: Optional[requests.Session] = None, sleep_fn=None) -> None:
        self._session = session or requests.Session()
        self._sleep = sleep_fn or time.sleep

    def _shop_domain(self) -> str:
        raw = (os.getenv("SHOPIFY_SHOP") or "").strip()
        if raw.startswith("https://"):
            raw = raw[len("https://"):]
        if raw.startswith("http://"):
            raw = raw[len("http://"):]
        return raw.strip("/").lower()

    def _access_token(self) -> str:
        return (os.getenv("SHOPIFY_ADMIN_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN") or "").strip()

    def _api_version(self) -> str:
        return (os.getenv("SHOPIFY_ADMIN_API_VERSION") or "2024-10").strip() or "2024-10"

    def is_configured(self) -> bool:
        return bool(self._shop_domain()) and bool(self._access_token())

    def _base_url(self) -> str:
        return f"https://{self._shop_domain()}/admin/api/{self._api_version()}"

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        retries_raw = os.getenv("SHOPIFY_RETRY_MAX", "3")
        timeout_raw = os.getenv("SHOPIFY_TIMEOUT_SEC", "10")
        try:
            retries = min(max(int(retries_raw), 1), 5)
        except ValueError:
            retries = 3
        try:
            timeout = max(float(timeout_raw), 1.0)
        except ValueError:
            timeout = 10.0

        url = f"{self._base_url()}{path}"
        headers = {"X-Shopify-Access-Token": self._access_token(), "Content-Type": "application/json"}

        for attempt in range(retries):
            try:
                response = self._session.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    params=params,
                    timeout=timeout,
                )
            except requests.RequestException:
                if attempt == retries - 1:
                    raise
                self._sleep(min(0.5 * (2**attempt), 2.0))
                continue

            if response.status_code == 429 and attempt < retries - 1:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait_sec = float(retry_after) if retry_after else 0.0
                except ValueError:
                    wait_sec = 0.0
                if wait_sec <= 0:
                    wait_sec = min(0.5 * (2**attempt), 2.0)
                self._sleep(wait_sec)
                continue
            return response
        raise RuntimeError("Shopify request retry limit exhausted")

    @staticmethod
    def _locale_region(locale: str, country: str) -> str:
        normalized = (locale or "").strip()
        if not normalized:
            return "en-US"
        if "-" in normalized:
            return normalized
        region = (country or "US").upper()
        return f"{normalized}-{region}"

    def _shop_profile(self) -> Tuple[str, str]:
        currency = (os.getenv("SHOPIFY_SHOP_CURRENCY") or self.currency or "USD").upper()
        locale = os.getenv("SHOPIFY_SHOP_LOCALE") or self.locale or "en-US"
        if not self.is_configured():
            return currency, locale
        try:
            response = self._request_with_retry("GET", "/shop.json")
            if response.status_code == 200:
                shop = response.json().get("shop", {})
                currency = (shop.get("currency") or currency).upper()
                locale = self._locale_region(
                    str(shop.get("primary_locale") or locale),
                    str(shop.get("country_code") or self.country),
                )
        except Exception:
            pass
        return currency, locale

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _convert_amount(self, amount: float, from_currency: str, to_currency: str) -> Tuple[Optional[float], bool]:
        source = (from_currency or "USD").upper()
        target = (to_currency or "USD").upper()
        if source == target:
            return float(amount), True
        try:
            from src.seller_console.market_status import convert_amount

            return convert_amount(float(amount), source, target)
        except Exception:
            return None, False

    @staticmethod
    def _select_localized_text(payload: ListingPayload, target_locale: str, field_name: str) -> Tuple[str, bool]:
        options = payload.options if isinstance(payload.options, dict) else {}
        localized_map = options.get("localized") if isinstance(options.get("localized"), dict) else {}
        locale = (target_locale or "en-US").strip()
        language = locale.split("-")[0].lower() if locale else "en"

        candidate = localized_map.get(locale)
        if isinstance(candidate, dict):
            value = str(candidate.get(field_name) or "").strip()
            if value:
                return value, False

        for key, row in localized_map.items():
            if not isinstance(row, dict):
                continue
            if str(key).split("-")[0].lower() != language:
                continue
            value = str(row.get(field_name) or "").strip()
            if value:
                return value, False

        original = str(getattr(payload, field_name, "") or "").strip()
        return original, bool(localized_map)

    @staticmethod
    def _error_summary(response: requests.Response) -> str:
        try:
            body = response.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            errors = body.get("errors")
            if isinstance(errors, str):
                return errors
            if isinstance(errors, dict):
                parts = []
                for key, value in errors.items():
                    parts.append(f"{key}: {value}")
                if parts:
                    return "; ".join(parts)
        return response.reason or "요청이 거절되었습니다."

    def _idempotency_key(self, payload: ListingPayload) -> str:
        options = payload.options if isinstance(payload.options, dict) else {}
        candidate = (
            options.get("idempotency_key")
            or options.get("internal_product_id")
            or options.get("product_key")
            or payload.sku
        )
        if candidate:
            return str(candidate)
        digest = hashlib.sha256(f"{payload.title}|{payload.description}|{payload.price}".encode("utf-8")).hexdigest()
        return f"title:{digest}"

    def validate_listing(self, payload: ListingPayload) -> ListingResult:
        if not self.is_configured():
            return self._mock_result(
                "Shopify 설정이 없어 업로드를 실행할 수 없습니다. /admin/diagnostics 에서 SHOPIFY_SHOP/SHOPIFY_ACCESS_TOKEN(또는 SHOPIFY_ADMIN_TOKEN)을 설정하세요.",
                ok=False,
                raw={
                    "status": "not_configured",
                    "required_env": ["SHOPIFY_SHOP", "SHOPIFY_ACCESS_TOKEN"],
                    "simulated": False,
                },
            )

        errors = []
        warnings = []

        title = str(payload.title or "").strip()
        if not title:
            errors.append({"field": "title", "reason": "상품명(title)은 필수입니다."})

        price = self._to_float(payload.price)
        if price is None:
            errors.append({"field": "price", "reason": "가격(price)은 숫자로 입력해야 합니다."})
        elif price < 0:
            errors.append({"field": "price", "reason": "가격(price)은 0 이상이어야 합니다."})

        if int(payload.qty or 0) < 0:
            errors.append({"field": "qty", "reason": "재고(qty)는 0 이상이어야 합니다."})

        shop_currency = (os.getenv("SHOPIFY_SHOP_CURRENCY") or self.currency or "USD").upper()
        if price is not None and payload.currency.upper() != shop_currency:
            converted, ok = self._convert_amount(price, payload.currency, shop_currency)
            if ok and converted is not None:
                warnings.append(
                    {
                        "field": "currency",
                        "reason": f"{payload.currency.upper()} 가격을 {shop_currency}로 환산해 등록합니다.",
                    }
                )
            else:
                errors.append(
                    {
                        "field": "currency",
                        "reason": f"{payload.currency.upper()}→{shop_currency} 환율 변환에 실패했습니다.",
                    }
                )

        ok = not errors
        status = "validated" if ok else "invalid_payload"
        message = "Shopify 등록 전 검증 완료" if ok else "Shopify 등록 전 검증 실패"
        return ListingResult(
            ok=ok,
            market=self.market,
            message=message,
            raw={
                "status": status,
                "errors": errors,
                "warnings": warnings,
                "shop_currency": shop_currency,
                "shop_locale": os.getenv("SHOPIFY_SHOP_LOCALE") or self.locale,
            },
        )

    def _build_product_payload(
        self,
        payload: ListingPayload,
        *,
        shop_currency: str,
        shop_locale: str,
    ) -> Tuple[Dict[str, Any], list]:
        warnings = []
        title, title_fallback = self._select_localized_text(payload, shop_locale, "title")
        description, desc_fallback = self._select_localized_text(payload, shop_locale, "description")
        if not title:
            title = str(payload.title or "Untitled").strip()
        description = description or str(payload.description or "")

        if title_fallback or desc_fallback:
            warnings.append("미현지화 번역본이 없어 원문을 사용했습니다.")

        base_price = self._to_float(payload.price)
        if base_price is None:
            base_price = 0.0
        display_price = base_price
        if payload.currency.upper() != shop_currency:
            converted, ok = self._convert_amount(base_price, payload.currency, shop_currency)
            if ok and converted is not None:
                display_price = round(converted, 2)
            else:
                warnings.append(f"{payload.currency.upper()}→{shop_currency} 환산 실패로 원통화 가격을 사용했습니다.")

        options = payload.options if isinstance(payload.options, dict) else {}
        status = str(options.get("status") or "active").lower()
        if status not in {"active", "draft"}:
            status = "draft"

        compare_at_raw = self._to_float(options.get("compare_at_price"))
        variant = {
            "price": f"{display_price:.2f}",
            "sku": payload.sku or str(options.get("sku") or ""),
            "inventory_quantity": max(int(payload.qty or 0), 0),
        }
        if compare_at_raw is not None and compare_at_raw >= 0:
            compare_at_price = compare_at_raw
            if payload.currency.upper() != shop_currency:
                converted, ok = self._convert_amount(compare_at_raw, payload.currency, shop_currency)
                if ok and converted is not None:
                    compare_at_price = round(converted, 2)
            variant["compare_at_price"] = f"{compare_at_price:.2f}"

        images = []
        image_values = options.get("images")
        if isinstance(image_values, list):
            for url in image_values:
                if isinstance(url, str) and url.strip():
                    images.append({"src": url.strip()})

        tags = options.get("tags")
        tag_list = []
        if isinstance(tags, list):
            tag_list = [str(x).strip() for x in tags if str(x).strip()]
        elif isinstance(tags, str):
            tag_list = [x.strip() for x in tags.split(",") if x.strip()]
        if title_fallback or desc_fallback:
            tag_list.append("미현지화")

        product = {
            "title": title,
            "body_html": description,
            "vendor": str(options.get("vendor") or ""),
            "product_type": str(options.get("product_type") or ""),
            "status": status,
            "tags": ", ".join(sorted(set(tag_list))),
            "variants": [variant],
        }
        if images:
            product["images"] = images
        return product, warnings

    def upload_product(self, payload: ListingPayload) -> ListingResult:
        validation = self.validate_listing(payload)
        if not validation.ok:
            return validation

        try:
            shop_currency, shop_locale = self._shop_profile()
            product_payload, build_warnings = self._build_product_payload(
                payload,
                shop_currency=shop_currency,
                shop_locale=shop_locale,
            )
            warnings = list(validation.raw.get("warnings") or []) + build_warnings

            options = payload.options if isinstance(payload.options, dict) else {}
            idempotency_key = self._idempotency_key(payload)
            with self._idempotency_lock:
                cached_product_id = self._idempotency_map.get(idempotency_key)
            existing_product_id = str(options.get("shopify_product_id") or cached_product_id or "").strip()

            if existing_product_id:
                response = self._request_with_retry(
                    "PUT",
                    f"/products/{existing_product_id}.json",
                    json_body={"product": {"id": int(existing_product_id), **product_payload}},
                )
                status = "updated"
            else:
                response = self._request_with_retry("POST", "/products.json", json_body={"product": product_payload})
                status = "created"

            if not (200 <= response.status_code < 300):
                summary = self._error_summary(response)
                return ListingResult(
                    ok=False,
                    market=self.market,
                    message=f"Shopify 업로드 실패 (HTTP {response.status_code}): {summary}",
                    raw={
                        "status": "api_error",
                        "http_status": response.status_code,
                        "reason": summary,
                        "warnings": warnings,
                    },
                )

            body = response.json()
            product = body.get("product", {}) if isinstance(body, dict) else {}
            external_id = str(product.get("id") or existing_product_id or "")
            if idempotency_key and external_id:
                with self._idempotency_lock:
                    self._idempotency_map[idempotency_key] = external_id
            handle = str(product.get("handle") or "").strip()
            shop = self._shop_domain()
            admin_url = f"https://{shop}/admin/products/{external_id}" if external_id else ""
            storefront_url = f"https://{shop}/products/{handle}" if handle else ""

            message = f"Shopify 상품 {status} 완료"
            if warnings:
                message = f"{message} (경고 {len(warnings)}건)"
            return ListingResult(
                ok=True,
                market=self.market,
                external_id=external_id,
                message=message,
                raw={
                    "status": status,
                    "admin_url": admin_url,
                    "storefront_url": storefront_url,
                    "warnings": warnings,
                    "shop_currency": shop_currency,
                    "shop_locale": shop_locale,
                    "idempotency_key": idempotency_key,
                },
            )
        except requests.RequestException:
            return ListingResult(
                ok=False,
                market=self.market,
                message="Shopify API 요청이 실패했습니다. 네트워크 상태를 확인 후 다시 시도하세요.",
                raw={"status": "network_error"},
            )
        except Exception:
            return ListingResult(
                ok=False,
                market=self.market,
                message="Shopify 업로드 처리 중 오류가 발생했습니다.",
                raw={"status": "internal_error"},
            )

    def create_listing(self, payload: ListingPayload) -> ListingResult:
        return self.upload_product(payload)

    def update_inventory(self, sku: str, qty: int) -> bool:
        return False

    def get_order_status(self, external_order_id: str) -> OrderStatus:
        return OrderStatus(external_order_id=external_order_id, status="stub")
