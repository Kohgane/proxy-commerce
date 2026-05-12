"""JSON-LD helpers for AI listing Phase 151."""
from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

_SIZE_TOKEN_RE = re.compile(
    r"\b(?:XXXL|XXL|2XL|3XL|XL|XS|S|M|L|FREE|OS)\b|\b\d{2,3}\b",
    re.IGNORECASE,
)
_MATERIAL_PERCENT_RE = re.compile(
    r"\b\d{1,3}%\s*[A-Za-z가-힣]+(?:\s*,\s*\d{1,3}%\s*[A-Za-z가-힣]+)*",
    re.IGNORECASE,
)
_MADE_OF_RE = re.compile(r"(?:made\s+of|material|소재)\s*[:\-]?\s*([^.;\n]+)", re.IGNORECASE)
_FALLBACK_RATE_DEFAULTS = {
    "USD": "1375",
    "JPY": "9.2",
    "EUR": "1500",
    "CNY": "190",
}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _flatten_jsonld(raw_list: Iterable[Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for item in raw_list or []:
        if not isinstance(item, dict):
            continue
        items.append(item)
        for node in _as_list(item.get("@graph")):
            if isinstance(node, dict):
                items.append(node)
    return items


def _has_type(item: Dict[str, Any], expected: str) -> bool:
    type_value = item.get("@type")
    if isinstance(type_value, list):
        type_value = " ".join(str(v) for v in type_value)
    return expected.lower() in str(type_value or "").lower()


def _normalize_brand(value: Any) -> Dict[str, str]:
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip()
    else:
        name = str(value or "").strip()
    return {"name": name} if name else {}


def _normalize_images(value: Any) -> List[str]:
    images: List[str] = []
    for image in _as_list(value):
        if isinstance(image, str) and image.strip():
            images.append(image.strip())
        elif isinstance(image, dict):
            url = str(image.get("url") or image.get("contentUrl") or "").strip()
            if url:
                images.append(url)
    return list(dict.fromkeys(images))


def _extract_primary_product(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    for preferred in ("ProductGroup", "Product"):
        for item in items:
            if _has_type(item, preferred):
                return item
    for item in items:
        if _has_type(item, "Offer"):
            return {"offers": item}
    return {}


def _normalize_offers(value: Any) -> Dict[str, Any]:
    offers = _as_list(value)
    for offer in offers:
        if isinstance(offer, dict) and any(
            offer.get(key) is not None for key in ("price", "lowPrice", "highPrice", "priceCurrency")
        ):
            return offer
    return {}


def _price_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def normalize_jsonld(raw_list: Iterable[Any]) -> Dict[str, Any]:
    items = _flatten_jsonld(raw_list)
    product = _extract_primary_product(items)
    offers = _normalize_offers(product.get("offers"))
    variants = [variant for variant in _as_list(product.get("hasVariant")) if isinstance(variant, dict)]

    if not offers:
        for variant in variants:
            offers = _normalize_offers(variant.get("offers"))
            if offers:
                break

    normalized = {
        "name": str(product.get("name") or "").strip(),
        "brand": _normalize_brand(product.get("brand")),
        "category": str(product.get("category") or "").strip(),
        "description": str(product.get("description") or "").strip(),
        "image_urls": _normalize_images(product.get("image")),
        "offers": offers,
        "hasVariant": variants,
        "sku": str(product.get("sku") or "").strip(),
        "gtin": str(
            product.get("gtin")
            or product.get("gtin13")
            or product.get("gtin12")
            or product.get("gtin14")
            or ""
        ).strip(),
    }
    if not normalized["name"]:
        for variant in variants:
            name = str(variant.get("name") or "").strip()
            if name:
                normalized["name"] = name
                break
    return normalized


def extract_price_from_jsonld(json_ld: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not json_ld:
        return None

    candidates = [
        ("offers.price", _normalize_offers(json_ld.get("offers"))),
    ]
    variants = _as_list(json_ld.get("hasVariant"))
    if variants:
        candidates.append(("hasVariant[0].offers.price", _normalize_offers(variants[0].get("offers"))))
    for source, offer in candidates:
        price = _price_decimal(offer.get("price"))
        currency = str(offer.get("priceCurrency") or "").upper().strip() or "KRW"
        if price is not None:
            return {"amount": price, "currency": currency, "source": source}
        low_price = _price_decimal(offer.get("lowPrice"))
        high_price = _price_decimal(offer.get("highPrice"))
        if low_price is not None:
            return {"amount": low_price, "currency": currency, "source": f"{source}.lowPrice"}
        if high_price is not None:
            return {"amount": high_price, "currency": currency, "source": f"{source}.highPrice"}
    return None


def extract_size_color_from_name(variant_name: str) -> Dict[str, str]:
    raw = str(variant_name or "").strip()
    if not raw:
        return {"color": "", "size": ""}

    normalized = raw.replace("·", "/").replace("•", "/")
    normalized = re.sub(r"\s+-\s+", "/", normalized)
    segments = [seg.strip(" -/") for seg in normalized.split("/") if seg.strip(" -/")]
    size = ""
    color = ""
    for segment in reversed(segments):
        size_match = _SIZE_TOKEN_RE.search(segment)
        if size_match:
            size = size_match.group(0).upper()
            remaining = _SIZE_TOKEN_RE.sub("", segment).strip(" -/·•")
            if remaining and not color:
                color = remaining
            break

    if not color:
        for segment in reversed(segments):
            cleaned = _SIZE_TOKEN_RE.sub("", segment).strip(" -/·•")
            if cleaned:
                color = cleaned
                break
    return {"color": color.upper().strip(), "size": size.upper().strip()}


def extract_variants(has_variant: Any) -> List[Dict[str, Any]]:
    variants: List[Dict[str, Any]] = []
    for variant in _as_list(has_variant):
        if not isinstance(variant, dict):
            continue
        parsed = extract_size_color_from_name(str(variant.get("name") or ""))
        offer = _normalize_offers(variant.get("offers"))
        image_urls = _normalize_images(variant.get("image"))
        variants.append(
            {
                "name": str(variant.get("name") or "").strip(),
                "color": str(variant.get("color") or parsed["color"]).strip().upper(),
                "size": str(variant.get("size") or parsed["size"]).strip().upper(),
                "sku": str(variant.get("sku") or "").strip(),
                "gtin": str(
                    variant.get("gtin")
                    or variant.get("gtin13")
                    or variant.get("gtin12")
                    or variant.get("gtin14")
                    or ""
                ).strip(),
                "image": image_urls[0] if image_urls else "",
                "price": _price_decimal(offer.get("price") or offer.get("lowPrice") or offer.get("highPrice")),
                "currency": str(offer.get("priceCurrency") or "").upper().strip() or "KRW",
            }
        )
    return variants


def extract_material(description: str) -> str:
    text = str(description or "").strip()
    if not text:
        return ""
    match = _MATERIAL_PERCENT_RE.search(text)
    if match:
        return match.group(0).strip()
    match = _MADE_OF_RE.search(text)
    if match:
        return match.group(1).strip()
    return ""


def get_exchange_rate_to_krw(currency: str) -> Decimal:
    code = str(currency or "KRW").upper().strip()
    if code == "KRW":
        return Decimal("1")
    try:
        from src.price import _build_fx_rates

        fx_rates = _build_fx_rates(use_live=False)
        value = fx_rates.get(f"{code}KRW")
        if value is not None:
            return Decimal(str(value))
    except Exception:
        pass

    env_name = f"FALLBACK_{code}_KRW"
    fallback = os.getenv(env_name) or _FALLBACK_RATE_DEFAULTS.get(code, "1")
    try:
        return Decimal(str(fallback))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid exchange rate config for {env_name}: {fallback}") from exc


def convert_to_krw(amount: Decimal | int | float | str, currency: str) -> Dict[str, Any]:
    value = _price_decimal(amount)
    if value is None:
        raise ValueError("유효하지 않은 금액")
    code = str(currency or "KRW").upper().strip() or "KRW"
    rate = get_exchange_rate_to_krw(code)
    amount_krw = int((value * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {"amount_krw": amount_krw, "rate": rate, "currency": code, "amount": value}
