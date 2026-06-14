"""Shopify Admin API adapter."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

import requests

from .base import ListingPayload, ListingResult, MarketAdapter, OrderStatus

# client_credentials grant로 발급한 Admin API 액세스 토큰 캐시: key "{shop}:{client_id}" -> {token, expires_at}
_cc_token_cache: Dict[str, Dict[str, Any]] = {}


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

    def _direct_token(self) -> str:
        """환경변수에 직접 저장된 액세스 토큰.

        atkn_(앱 자동화 토큰)은 Admin API에서 401로 거부되므로 직접 토큰으로 쓰지 않고 건너뛴다.
        우선순위: SHOPIFY_AUTO_TOKEN → SHOPIFY_ACCESS_TOKEN → SHOPIFY_ADMIN_TOKEN.
        """
        for name in ("SHOPIFY_AUTO_TOKEN", "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_ADMIN_TOKEN"):
            val = (os.getenv(name) or "").strip()
            if val and not val.startswith("atkn_"):
                return val
        return ""

    def _client_credentials(self) -> Tuple[str, str]:
        # Shopify에서 Client ID = API key. 명명 혼용을 흡수해 여러 이름을 허용한다.
        client_id = (
            os.getenv("SHOPIFY_CLIENT_ID")
            or os.getenv("SHOPIFY_API_KEY")
            or os.getenv("SHOPIFY_APIKEY")
            or ""
        ).strip()
        client_secret = (
            os.getenv("SHOPIFY_CLIENT_SECRET")
            or os.getenv("SHOPIFY_API_SECRET_KEY")
            or os.getenv("SHOPIFY_API_SECRET")
            or ""
        ).strip()
        return client_id, client_secret

    def _has_client_credentials(self) -> bool:
        cid, csec = self._client_credentials()
        return bool(cid and csec and self._shop_domain())

    def fetch_token_via_client_credentials(self) -> Optional[str]:
        """client_credentials grant로 Admin API 액세스 토큰(shpat_) 발급.

        개발자 대시보드 앱은 atkn_(앱 자동화 토큰)이 Admin API 액세스 토큰으로 인식되지 않으므로,
        client_id/client_secret으로 POST /admin/oauth/access_token (grant_type=client_credentials)
        하여 shpat_ 토큰을 받아 캐시한다.
        """
        cid, csec = self._client_credentials()
        shop = self._shop_domain()
        if not (cid and csec and shop):
            return None
        key = f"{shop}:{cid}"
        now = time.time()
        cached = _cc_token_cache.get(key)
        if cached and cached.get("expires_at", 0) > now + 30:
            return cached["token"]
        try:
            resp = self._session.post(
                f"https://{shop}/admin/oauth/access_token",
                json={"client_id": cid, "client_secret": csec, "grant_type": "client_credentials"},
                timeout=float(os.getenv("SHOPIFY_TIMEOUT_SEC", "10") or 10),
            )
            if resp.status_code != 200:
                return None
            data = resp.json() if callable(getattr(resp, "json", None)) else {}
            token = str((data or {}).get("access_token") or "").strip()
            if not token:
                return None
            try:
                ttl = float(data.get("expires_in")) if data.get("expires_in") else 3600.0
            except (TypeError, ValueError):
                ttl = 3600.0
            _cc_token_cache[key] = {"token": token, "expires_at": now + ttl}
            return token
        except requests.RequestException:
            return None
        except Exception:
            return None

    def _access_token(self) -> str:
        """실제 요청에 사용할 Admin API 액세스 토큰.

        client_id/secret이 있으면 client_credentials grant로 받은 shpat_ 토큰을 우선 사용,
        실패하거나 미설정이면 환경변수의 직접 토큰으로 폴백.
        """
        if self._has_client_credentials():
            token = self.fetch_token_via_client_credentials()
            if token:
                return token
        return self._direct_token()

    def _has_legacy_token(self) -> bool:
        return bool((os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_TOKEN") or "").strip())

    def _api_version(self) -> str:
        return (os.getenv("SHOPIFY_API_VERSION") or os.getenv("SHOPIFY_ADMIN_API_VERSION") or "2026-04").strip() or "2026-04"

    def is_configured(self) -> bool:
        # 네트워크 없이 자격증명 존재 여부만 확인 (client_credentials 또는 직접 토큰).
        return bool(self._shop_domain()) and (self._has_client_credentials() or bool(self._direct_token()))

    def _missing_config_env(self) -> list[str]:
        missing = []
        if not self._shop_domain():
            missing.append("SHOPIFY_SHOP")
        # client_id+secret(권장) 또는 직접 토큰 중 하나가 있어야 함
        if not self._has_client_credentials() and not self._direct_token():
            missing.append("SHOPIFY_CLIENT_ID/SECRET 또는 SHOPIFY_AUTO_TOKEN")
        return missing

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
    def _friendly_http_reason(status_code: int, summary: str, *, action: str) -> str:
        if status_code == 401:
            return f"{action} 인증 실패(401)."
        if status_code == 403:
            return f"{action} 권한 부족(403). Shopify 앱 스코프(read_products/write_products 등)를 확인하세요."
        if status_code == 404:
            return f"{action} 대상 스토어를 찾지 못했습니다. SHOPIFY_SHOP 도메인을 확인하세요."
        if status_code == 429:
            return f"{action} 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요."
        if status_code >= 500:
            return f"Shopify 서버 오류로 {action}에 실패했습니다. 잠시 후 다시 시도하세요."
        if summary:
            return summary
        return "요청이 거절되었습니다."

    def _append_auth_diagnostics(self, message: str) -> str:
        """401/인증 실패 시 테스트 상점·토큰 접두사·종류 진단을 덧붙인다."""
        token = self._access_token()
        token_prefix = (token.split("_")[0] + "_…") if (token and "_" in token) else (token[:4] + "…" if token else "(없음)")
        message += f" [테스트한 상점: {self._shop_domain()} · 토큰 접두사: {token_prefix}]"
        valid_prefixes = ("shpat_", "atkn_", "shpca_")
        if token and token.startswith("shpss_"):
            message += " ⚠️ 'shpss_'는 Client secret(암호)입니다 — 토큰칸엔 Admin API access token(shpat_)을 넣으세요."
        elif token and not token.startswith(valid_prefixes):
            message += " ⚠️ 토큰 종류 확인: Admin API access token(shpat_)이어야 합니다."
        elif token and token.startswith("atkn_"):
            cid, csec = self._client_credentials()
            if not (cid and csec):
                missing_cc = []
                if not cid:
                    missing_cc.append("SHOPIFY_CLIENT_ID(또는 SHOPIFY_API_KEY)")
                if not csec:
                    missing_cc.append("SHOPIFY_CLIENT_SECRET")
                message += (f" 원인: {', '.join(missing_cc)} 미설정 → client_credentials 발급을 못 하고 atkn_로 폴백 중입니다."
                            f" atkn_은 Admin API에서 거부됩니다. {', '.join(missing_cc)}를 설정하면 자동으로 shpat_를 발급해 연결됩니다.")
            else:
                message += " atkn_ 토큰 사용 중(client_credentials 발급 실패 가능) — CLIENT_ID/SECRET 값을 확인하세요."
        else:
            message += " 401은 스코프가 아니라 토큰 인증 거부입니다(Admin API access token이 맞는지/유효한지 확인)."
        return message

    def check_connection(self) -> Dict[str, Any]:
        missing_env = self._missing_config_env()
        if missing_env:
            return {
                "ok": False,
                "status": "not_configured",
                "message": "Shopify 연결 설정이 누락되었습니다.",
                "missing_env": missing_env,
                "required_env": ["SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET", "SHOPIFY_AUTO_TOKEN", "SHOPIFY_API_VERSION", "SHOPIFY_SHOP"],
            }

        # client_credentials grant 방식이면 토큰 발급부터 명확히 검증.
        if self._has_client_credentials():
            cc_token = self.fetch_token_via_client_credentials()
            if not cc_token:
                return {
                    "ok": False,
                    "status": "api_error",
                    "message": ("client_credentials 토큰 발급 실패 — POST /admin/oauth/access_token이 거부됨."
                                f" [상점: {self._shop_domain()}] SHOPIFY_CLIENT_ID/SECRET 값과 상점 도메인을 확인하세요"
                                " (atkn_ 앱 자동화 토큰 대신 client_id/secret로 발급)."),
                }

        try:
            # GraphQL Admin API 사용(신규 개발자대시보드 앱은 REST가 막혀 GraphQL만 동작).
            query = "{ shop { name myshopifyDomain currencyCode plan { displayName } } }"
            response = self._request_with_retry("POST", "/graphql.json", json_body={"query": query})

            if not (200 <= response.status_code < 300):
                summary = self._error_summary(response)
                message = self._friendly_http_reason(response.status_code, summary, action="Shopify 연결 확인")
                if response.status_code in (401, 403):
                    message = self._append_auth_diagnostics(message)
                return {
                    "ok": False,
                    "status": "api_error",
                    "http_status": response.status_code,
                    "reason": summary,
                    "message": message,
                }

            try:
                body = response.json()
            except ValueError:
                body = {}
            errors = body.get("errors") if isinstance(body, dict) else None
            shop = ((body.get("data") or {}).get("shop")) if isinstance(body, dict) else None

            if errors or not isinstance(shop, dict):
                err_msg = ""
                if isinstance(errors, list) and errors:
                    err_msg = str(errors[0].get("message") or "").strip()
                message = self._append_auth_diagnostics(
                    f"Shopify GraphQL 인증/권한 오류. {err_msg}".strip()
                )
                return {
                    "ok": False,
                    "status": "scope_insufficient" if "access" in err_msg.lower() or "scope" in err_msg.lower() else "api_error",
                    "http_status": response.status_code,
                    "reason": err_msg or "GraphQL shop 조회 실패",
                    "message": message,
                }

            plan = shop.get("plan") if isinstance(shop.get("plan"), dict) else {}
            return {
                "ok": True,
                "status": "connected",
                "message": "Shopify 연결 확인 완료 (GraphQL)",
                "shop_name": str(shop.get("name") or "").strip(),
                "shop_domain": str(shop.get("myshopifyDomain") or self._shop_domain()).strip(),
                "currency": str(shop.get("currencyCode") or "").strip(),
                "plan_name": str(plan.get("displayName") or "").strip(),
            }
        except requests.RequestException:
            return {
                "ok": False,
                "status": "network_error",
                "message": "Shopify API 연결 요청에 실패했습니다. 네트워크 상태를 확인 후 다시 시도하세요.",
            }
        except Exception:
            return {
                "ok": False,
                "status": "internal_error",
                "message": "Shopify 연결 확인 중 오류가 발생했습니다.",
            }

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
                "Shopify 설정이 없어 업로드를 실행할 수 없습니다. SHOPIFY_SHOP/SHOPIFY_AUTO_TOKEN을 확인하세요. (하위호환: SHOPIFY_ACCESS_TOKEN)",
                ok=False,
                raw={
                    "status": "not_configured",
                    "required_env": ["SHOPIFY_SHOP", "SHOPIFY_AUTO_TOKEN"],
                    "missing_env": self._missing_config_env(),
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
                friendly = self._friendly_http_reason(response.status_code, summary, action="Shopify 상품 등록")
                return ListingResult(
                    ok=False,
                    market=self.market,
                    message=f"Shopify 업로드 실패 (HTTP {response.status_code}): {friendly}",
                    raw={
                        "status": "api_error",
                        "http_status": response.status_code,
                        "reason": summary,
                        "friendly_reason": friendly,
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
