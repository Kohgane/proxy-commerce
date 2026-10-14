"""무신사 상품 페이지 파서 — __NEXT_DATA__ JSON에서 가격·상품명을 찾는다.

구조가 바뀌어도 깨지지 않도록 키 이름으로 재귀 탐색한다.
못 찾으면 None (가짜 값 금지).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

_NEXT = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_PRICE_KEYS = ("salePrice", "goodsPrice", "price", "normalPrice")
_NAME_KEYS = ("goodsNm", "goodsName", "name", "title")


def _walk(o: Any):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _num(v) -> Optional[int]:
    if isinstance(v, (int, float)) and v > 0:
        return int(v)
    if isinstance(v, str):
        d = re.sub(r"[^\d]", "", v)
        return int(d) if d else None
    return None


def parse_musinsa(html: str) -> Optional[Dict[str, Any]]:
    m = _NEXT.search(html or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    # 상품 전용 키(goodsNm)를 가진 노드를 먼저 — 추천상품 등 일반 name/price 오탐 방지
    nodes = list(_walk(data))
    nodes.sort(key=lambda n: 0 if "goodsNm" in n else 1)
    for node in nodes:
        name = next((node[k] for k in _NAME_KEYS if isinstance(node.get(k), str) and node.get(k)), None)
        price = next((_num(node[k]) for k in _PRICE_KEYS if k in node and _num(node[k])), None)
        if name and price:
            ship = _num(node.get("deliveryFee") or node.get("shippingFee") or 0) or 0
            return {"title": name, "price_krw": price, "kr_ship_krw": ship}
    return None
