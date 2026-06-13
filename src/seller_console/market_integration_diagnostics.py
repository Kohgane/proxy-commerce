from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any


MARKET_GUIDES: dict[str, dict[str, Any]] = {
    "coupang": {
        "label": "Coupang",
        "docs_path": "docs/operations/COUPANG.md",
        "required_env": ["COUPANG_VENDOR_ID", "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY"],
        "required_scopes": ["상품 조회", "상품 등록/수정", "주문 조회", "배송 처리"],
        "check_locations": ["/admin/diagnostics", "/seller/markets", "Coupang Wing 판매자센터"],
    },
    "smartstore": {
        "label": "Naver Smartstore",
        "docs_path": "docs/operations/NAVER_SMARTSTORE.md",
        "required_env": ["NAVER_COMMERCE_CLIENT_ID", "NAVER_COMMERCE_CLIENT_SECRET", "NAVER_COMMERCE_API_BASE"],
        "required_scopes": ["상품 조회", "상품 등록/수정", "주문 조회", "발송 처리"],
        "check_locations": ["/admin/diagnostics", "/seller/markets", "네이버 커머스API센터"],
    },
    "11st": {
        "label": "11st",
        "docs_path": "docs/operations/ELEVENST.md",
        "required_env": ["ELEVENST_API_KEY"],
        "required_scopes": ["상품 조회", "상품 등록/수정", "주문 조회", "배송 처리"],
        "check_locations": ["/admin/diagnostics", "/seller/markets", "11번가 seller office"],
    },
    "shopify": {
        "label": "Shopify",
        "docs_path": "docs/operations/SHOPIFY_MARKET.md",
        "required_env": ["SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET", "SHOPIFY_AUTO_TOKEN", "SHOPIFY_API_VERSION", "SHOPIFY_SHOP"],
        "required_scopes": ["read_products", "write_products", "read_inventory", "write_inventory", "read_orders", "write_orders"],
        "check_locations": ["/admin/diagnostics", "/seller/markets", "Shopify Admin > Apps"],
    },
    "woocommerce": {
        "label": "WooCommerce",
        "docs_path": "docs/operations/WOOCOMMERCE_MARKET.md",
        "required_env": ["WC_URL", "WC_KEY", "WC_SECRET"],
        "required_scopes": ["Read", "Write"],
        "check_locations": ["/admin/diagnostics", "/seller/markets", "WordPress 관리자 > WooCommerce > REST API"],
    },
}

_STATUS_BADGES = {
    "connected": {"label": "connected", "class_name": "pc-market-badge pc-market-badge-connected", "icon": "✅", "title": "연결됨"},
    "token_missing": {"label": "token_missing", "class_name": "pc-market-badge pc-market-badge-token-missing", "icon": "🪪", "title": "토큰 없음"},
    "token_expired": {"label": "token_expired", "class_name": "pc-market-badge pc-market-badge-token-expired", "icon": "⏰", "title": "토큰 만료"},
    "scope_insufficient": {"label": "scope_insufficient", "class_name": "pc-market-badge pc-market-badge-scope-insufficient", "icon": "🔐", "title": "권한 부족"},
    "api_error": {"label": "api_error", "class_name": "pc-market-badge pc-market-badge-api-error", "icon": "⚠️", "title": "API 오류"},
}


@contextmanager
def _temporary_env(**updates: str | None):
    original = {name: os.environ.get(name) for name in updates}
    try:
        for name, value in updates.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _step(ok: bool, market: str, step: str, *, error_code: str = "", hint: str = "", detail: str = "", raw: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "market": market,
        "step": step,
        "error_code": error_code,
        "hint": hint,
        "detail": detail,
        "raw": raw or {},
    }


def _parse_error_code(detail: str, *, fallback: str = "api_error") -> str:
    normalized = (detail or "").lower()
    if "http 401" in normalized or "token" in normalized or "인증" in normalized:
        return "token_expired"
    if "http 403" in normalized or "scope" in normalized or "권한" in normalized:
        return "scope_insufficient"
    return fallback


def _shopify_read_step() -> dict[str, Any]:
    from src.markets.adapters.shopify import ShopifyAdapter

    raw = ShopifyAdapter().check_connection()
    if raw.get("ok"):
        detail = " / ".join(filter(None, [str(raw.get("shop_name") or "").strip(), str(raw.get("shop_domain") or "").strip(), str(raw.get("plan_name") or "").strip()]))
        return _step(True, "shopify", "read_connection", hint="shop.json 조회 성공", detail=detail or "Shopify 연결 확인 완료", raw=raw)

    http_status = int(raw.get("http_status") or 0)
    error_code = "api_error"
    if raw.get("status") == "not_configured":
        error_code = "token_missing"
    elif http_status == 401:
        error_code = "token_expired"
    elif http_status == 403:
        error_code = "scope_insufficient"
    return _step(False, "shopify", "read_connection", error_code=error_code, hint=str(raw.get("message") or "").strip(), detail=str(raw.get("reason") or raw.get("message") or "").strip(), raw=raw)


def _adapter_health_step(market: str) -> dict[str, Any]:
    adapter_specs = {
        "coupang": ("src.seller_console.market_adapters.coupang_adapter", "CoupangAdapter"),
        "smartstore": ("src.seller_console.market_adapters.smartstore_adapter", "SmartStoreAdapter"),
        "11st": ("src.seller_console.market_adapters.eleven_adapter", "ElevenAdapter"),
        "woocommerce": ("src.seller_console.market_adapters.woocommerce_adapter", "WooCommerceAdapter"),
    }
    module_path, class_name = adapter_specs[market]

    import importlib

    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    with _temporary_env(ADAPTER_DRY_RUN=None):
        raw = adapter_cls().health_check()

    status = str(raw.get("status") or "").strip().lower()
    detail = str(raw.get("detail") or "").strip()
    hint = str(raw.get("hint") or "").strip()
    if status == "ok":
        return _step(True, market, "read_connection", hint=hint or "실제 연결 확인 성공", detail=detail or "연결 성공", raw=raw)
    if status == "missing":
        return _step(False, market, "read_connection", error_code="token_missing", hint=hint or "필수 환경변수를 먼저 설정하세요.", detail=detail, raw=raw)
    return _step(False, market, "read_connection", error_code=_parse_error_code(detail), hint=hint or detail or "API 연결 실패", detail=detail or status or "연결 실패", raw=raw)


def _build_write_probe(market: str) -> dict[str, Any]:
    base = {
        "name": "[연동 스모크] Dry Run Product",
        "title": "[연동 스모크] Dry Run Product",
        "description": "safe dry-run validation only",
        "salePrice": 10000,
        "regular_price": "10000",
        "price": "10000",
        "stock_quantity": 1,
        "sku": f"SMOKE-{market.upper()}",
    }
    if market == "coupang":
        return {"displayProductName": base["title"], "sellerProductName": base["title"], "salePrice": 10000}
    if market == "smartstore":
        return {"name": base["title"], "salePrice": 10000, "stockQuantity": 1}
    if market == "11st":
        return {"prdNm": base["title"], "selPrc": 10000, "prdStatCd": "01"}
    if market == "woocommerce":
        return {"name": base["title"], "type": "simple", "regular_price": "10000", "sku": base["sku"]}
    if market == "shopify":
        return {"title": base["title"], "body_html": base["description"], "variants": [{"sku": base["sku"], "price": "10000"}]}
    return base


def _write_dry_run_step(market: str) -> dict[str, Any]:
    adapter_specs = {
        "coupang": ("src.seller_console.market_adapters.coupang_adapter", "CoupangAdapter"),
        "smartstore": ("src.seller_console.market_adapters.smartstore_adapter", "SmartStoreAdapter"),
        "11st": ("src.seller_console.market_adapters.eleven_adapter", "ElevenAdapter"),
        "shopify": ("src.seller_console.market_adapters.shopify_adapter", "ShopifyAdapter"),
        "woocommerce": ("src.seller_console.market_adapters.woocommerce_adapter", "WooCommerceAdapter"),
    }
    module_path, class_name = adapter_specs[market]

    import importlib

    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    with _temporary_env(ADAPTER_DRY_RUN="1"):
        raw = adapter_cls().upload_product(_build_write_probe(market))

    status = str(raw.get("status") or "").strip().lower()
    detail = str(raw.get("detail") or "").strip()
    if status in {"dry_run", "ok"}:
        return _step(True, market, "write_dry_run", hint="실 쓰기 대신 안전 dry-run 검증 완료", detail=detail or status or "dry-run 검증 완료", raw=raw)
    if status == "stub":
        return _step(False, market, "write_dry_run", error_code="token_missing", hint="연동 정보가 없어 safe write 검증을 진행하지 못했습니다.", detail=detail or "자격증명 미설정", raw=raw)
    return _step(False, market, "write_dry_run", error_code=_parse_error_code(detail), hint=detail or "safe write 검증 실패", detail=detail or status or "write 검증 실패", raw=raw)


def market_status_badge(status: str) -> dict[str, str]:
    return _STATUS_BADGES.get(status, _STATUS_BADGES["api_error"])


def normalize_market_diagnostic_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result or {})
    raw_timestamp = normalized.get("last_checked_at") or normalized.get("checked_at") or ""
    checked_at = str(raw_timestamp).strip()
    if not checked_at:
        checked_at = datetime.now(timezone.utc).isoformat()
    normalized["checked_at"] = checked_at
    normalized["last_checked_at"] = checked_at
    if not normalized.get("ui") and normalized.get("status"):
        normalized["ui"] = build_market_ui_state(normalized)
    return normalized


def build_market_ui_state(result: dict[str, Any]) -> dict[str, Any]:
    badge = market_status_badge(str(result.get("status") or "api_error"))
    steps = result.get("steps") or []
    first_failure = next((step for step in steps if not step.get("ok")), None)
    status = str(result.get("status") or "api_error")
    cause_text = str(result.get("summary") or (first_failure or {}).get("detail") or (first_failure or {}).get("hint") or "상태를 확인하지 못했습니다.").strip()
    disabled_reason = ""
    action_text = "재시도 전에 운영 가이드를 확인하세요."
    recommended_action = "retry"
    if status == "connected":
        action_text = "추가 조치 없이 마지막 성공 시간과 판매자센터 결과를 함께 점검하세요."
        recommended_action = "connection"
    elif status == "token_missing":
        disabled_reason = "필수 환경변수/시크릿을 먼저 등록하세요."
        action_text = "마켓 설정에서 필수 토큰/시크릿을 등록한 뒤 연결 확인을 다시 실행하세요."
        recommended_action = "connection"
    elif status == "scope_insufficient":
        disabled_reason = "앱 권한을 보강한 뒤 다시 시도하세요."
        action_text = "권한 확인 버튼으로 필요한 scope를 대조하고 앱 권한을 보강하세요."
        recommended_action = "scope"
    elif status == "token_expired":
        disabled_reason = "토큰 재발급 후 다시 시도하세요."
        action_text = "토큰을 재발급한 뒤 재시도 버튼으로 다시 점검하세요."
    else:
        action_text = "재시도 버튼으로 다시 점검하고 지속되면 diagnostics와 판매자센터 로그를 함께 확인하세요."
    # 어댑터가 마켓별 정확한 조치 힌트를 제공하면 그것을 우선 노출(일반 상태 문구보다 정확).
    result_hint = str(result.get("hint") or "").strip()
    if result_hint:
        action_text = result_hint
    return {
        "badge_label": badge["label"],
        "badge_class": badge["class_name"],
        "badge_text": f'{badge["icon"]} {badge["title"]}',
        "summary": str(result.get("summary") or "").strip(),
        "hint": str(result.get("hint") or "").strip(),
        "cause_text": cause_text,
        "action_text": action_text,
        "recommended_action": recommended_action,
        "technical_detail": str((first_failure or {}).get("detail") or "").strip(),
        "disabled_reason": disabled_reason,
    }


def run_market_diagnostic(market: str) -> dict[str, Any]:
    market_key = (market or "").strip().lower()
    if market_key not in MARKET_GUIDES:
        raise KeyError(market_key)

    meta = MARKET_GUIDES[market_key]
    read_step = _shopify_read_step() if market_key == "shopify" else _adapter_health_step(market_key)
    write_step = _write_dry_run_step(market_key)
    steps = [read_step, write_step]

    if not read_step["ok"]:
        status = read_step["error_code"] or "api_error"
        summary = read_step["detail"] or read_step["hint"] or "연결 확인 실패"
        hint = read_step["hint"] or "환경변수/권한을 확인한 뒤 다시 시도하세요."
    elif not write_step["ok"]:
        status = write_step["error_code"] or "api_error"
        summary = write_step["detail"] or write_step["hint"] or "safe write 검증 실패"
        hint = write_step["hint"] or "안전한 검증 호출이 실패했습니다."
    else:
        status = "connected"
        summary = "read 연결 확인 + safe write dry-run 검증 완료"
        hint = "실제 운영 전 `/admin/diagnostics`와 판매자센터에서 마지막 성공 시간을 함께 확인하세요."

    result = {
        "ok": status == "connected",
        "market": market_key,
        "label": meta["label"],
        "status": status,
        "summary": summary,
        "hint": hint,
        "docs_path": meta["docs_path"],
        "required_env": list(meta["required_env"]),
        "required_scopes": list(meta["required_scopes"]),
        "check_locations": list(meta["check_locations"]),
        "steps": steps,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    return normalize_market_diagnostic_result(result)


def run_all_market_diagnostics() -> list[dict[str, Any]]:
    return [normalize_market_diagnostic_result(run_market_diagnostic(market)) for market in MARKET_GUIDES]
