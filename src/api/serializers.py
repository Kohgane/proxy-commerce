"""src/api/serializers.py — API 응답 직렬화 헬퍼.

주문/상품/환율/재고 데이터를 JSON 직렬화 가능한 형식으로 변환한다.
한국어 필드명을 영문 API 필드명으로 매핑한다.

date/datetime 값은 ISO 8601 포맷으로 변환한다.
페이지네이션 메타데이터를 포함한다.
"""

import datetime
from decimal import Decimal
from typing import Any, Dict, List


def _to_json_safe(value: Any) -> Any:
    """JSON 직렬화 가능한 타입으로 변환한다."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(i) for i in value]
    return value


def serialize_order(row: Dict[str, Any]) -> Dict[str, Any]:
    """주문 행 데이터를 API 응답 필드명으로 직렬화한다."""
    return {
        "order_id": row.get("order_id", ""),
        "order_number": row.get("order_number", ""),
        "customer_name": row.get("customer_name", ""),
        "customer_email": row.get("customer_email", ""),
        "order_date": row.get("order_date", ""),
        "sku": row.get("sku", ""),
        "vendor": row.get("vendor", ""),
        "buy_price": _to_json_safe(row.get("buy_price", 0)),
        "buy_currency": row.get("buy_currency", ""),
        "sell_price_krw": _to_json_safe(row.get("sell_price_krw", 0)),
        "sell_price_usd": _to_json_safe(row.get("sell_price_usd", 0)),
        "margin_pct": _to_json_safe(row.get("margin_pct", 0)),
        "status": row.get("status", ""),
        "status_updated_at": row.get("status_updated_at", ""),
        "shipping_country": row.get("shipping_country", ""),
    }


def serialize_product(row: Dict[str, Any]) -> Dict[str, Any]:
    """상품 행 데이터를 API 응답 필드명으로 직렬화한다."""
    return {
        "sku": row.get("sku", ""),
        "title_ko": row.get("title_ko", ""),
        "title_en": row.get("title_en", ""),
        "vendor": row.get("vendor", ""),
        "buy_currency": row.get("buy_currency", ""),
        "buy_price": _to_json_safe(row.get("buy_price", 0)),
        "sell_price_krw": _to_json_safe(row.get("sell_price_krw", 0)),
        "margin_pct": _to_json_safe(row.get("margin_pct", 0)),
        "stock": _to_json_safe(row.get("stock", 0)),
        "stock_status": row.get("stock_status", ""),
        "status": row.get("status", ""),
        "source_country": row.get("source_country", ""),
    }


def serialize_fx_rate(pair: str, rate: Any) -> Dict[str, Any]:
    """환율 데이터를 API 응답 형식으로 직렬화한다."""
    return {
        "pair": pair,
        "rate": _to_json_safe(rate),
    }


def paginate(
    items: List[Any],
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    """항목 목록에 페이지네이션을 적용한다.

    Args:
        items: 전체 항목 목록
        page: 현재 페이지 (1부터 시작)
        per_page: 페이지당 항목 수

    Returns:
        {
            "items": [...],
            "pagination": {
                "page": int,
                "per_page": int,
                "total": int,
                "total_pages": int,
                "has_next": bool,
                "has_prev": bool,
            }
        }
    """
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "items": items[start:end],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }
