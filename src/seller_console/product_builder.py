"""T4(오너 2026-09-30-H) — 등록 상품 몸통 **서버 빌더 하나**.

데스크톱 편집 서랍은 브라우저의 `buildProductData()`로 몸통을 만들어 보냈고, 폰(M5)은 저장값에서 따로 만들었다 —
**두 벌**이었다. 이제 몸통의 기준은 여기 하나다:

- 폰(카드·쿠팡 미리보기·등록): `build_product(item)` — 저장된 값 그대로.
- 데스크톱: 브라우저가 모은 값은 **오너가 방금 고친 값(edits)**으로 얹는다 — `build_product(item, edits=form)`.
  브라우저가 보내는 키 집합과 이 빌더의 키 집합이 같으므로 데스크톱 등록 결과는 바뀌지 않는다(계약이 잰다).

키 집합 = `collect_preview.html buildProductData()`가 보내는 것(`PRODUCT_KEYS`). 저장값에 없는 칸은
비워 둔다(0·임의값 금지).
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

# buildProductData()가 보내는 키 — 계약(test_t4)이 템플릿과 대조한다.
PRODUCT_KEYS = (
    "title", "title_ko", "title_en", "title_en_input", "coupang_name", "coupang_name_source", "coupang_brand_pos",
    "price", "price_original", "currency", "description", "description_ko", "images", "options", "keywords", "tags",
    "images_effective", "thumbnail", "url", "source", "brand", "category", "category_code", "gallery_images",
    "detail_images", "detail_blocks", "coupang_attributes", "coupang_option_pick", "skus", "option_values_ko",
    "option_value_overrides", "option_names_ko", "option_name_overrides",
)


def _extra(item: dict) -> dict:
    try:
        ex = json.loads((item or {}).get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    return ex if isinstance(ex, dict) else {}


def _values_ko_map(options: list) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for o in options or []:
        if not isinstance(o, dict):
            continue
        vs, ks = list(o.get("values") or []), list(o.get("values_ko") or [])
        for i, v in enumerate(vs):
            k = (v or {}).get("name") if isinstance(v, dict) else v
            if k and i < len(ks) and ks[i]:
                out[str(k)] = str(ks[i])
    return out


def build_product(item: dict, edits: Optional[Dict[str, Any]] = None, *, seller_id: str = "") -> Dict[str, Any]:
    """저장된 수집 행 → 등록 몸통. `edits`(데스크톱 폼)가 준 키는 그 값이 이긴다(빈 값이어도 — 오너가 지운 것)."""
    it = item or {}
    ex = _extra(it)
    from src.collectors.ko_polish import polish_ko
    title_raw = str(ex.get("title_ko") or ex.get("title") or it.get("title") or "")
    title = polish_ko(title_raw) or title_raw
    images = [u for u in (ex.get("images") or []) if isinstance(u, str) and u]
    try:
        from src.services import image_translate_store as _its
        eff = _its.effective_images(ex, originals=images)
    except Exception:
        eff = list(images)
    options = ex.get("options") if isinstance(ex.get("options"), list) else []
    kw = ex.get("keywords") if isinstance(ex.get("keywords"), list) else []
    cat = str(ex.get("category_code") or ex.get("category") or "")
    price = str(ex.get("price") or it.get("price") or "")
    base: Dict[str, Any] = {
        "title": title, "title_ko": title, "title_en": str(ex.get("title_en") or title), "title_en_input": "",
        # T3: 원문 제목(상표·유통기한 어휘 판정용 — 번역·정리 전 글자에 있다)
        "title_src": str(ex.get("title") or it.get("title") or ""),
        "coupang_name": str(ex.get("coupang_name") or ""),
        "coupang_name_source": "manual" if ex.get("coupang_name") else "",
        "coupang_brand_pos": str(ex.get("coupang_brand_pos") or ""),
        "price": price, "price_original": price, "currency": str(ex.get("currency") or it.get("currency") or ""),
        "description": str(ex.get("description_ko") or ex.get("description") or ""),
        "description_ko": str(ex.get("description_ko") or ex.get("description") or ""),
        "images": images, "options": options, "keywords": kw, "tags": kw,
        "images_effective": eff, "thumbnail": (eff[0] if eff else (images[0] if images else "")),
        "url": str(it.get("url") or ex.get("url") or ""), "source": str(it.get("source") or ex.get("source") or ""),
        "brand": str(ex.get("brand") or ""), "category": cat, "category_code": cat,
        "gallery_images": images,
        "detail_images": [u for u in (ex.get("detail_images") or []) if isinstance(u, str) and u],
        "detail_blocks": ex.get("detail_blocks") or {},
        "coupang_attributes": list(ex.get("coupang_attributes") or []),
        "coupang_option_pick": dict(ex.get("coupang_option_pick") or {}),
        "skus": ex.get("skus") if isinstance(ex.get("skus"), list) else [],
        "option_values_ko": _values_ko_map(options),
        "option_value_overrides": dict(ex.get("option_value_overrides") or {}),
        "option_names_ko": {str(o.get("name")): str(o.get("name_ko")) for o in options
                            if isinstance(o, dict) and o.get("name") and o.get("name_ko")},
        "option_name_overrides": dict(ex.get("option_name_overrides") or {}),
    }
    if not base["coupang_name"]:
        # F53 규칙안 — 서랍이 처음 열릴 때 채우는 그 값(오너가 안 고쳤으면).
        try:
            from src.uploaders import coupang_title as ct
            from .views import _coupang_name_input
            pos = base["coupang_brand_pos"] or ct.brand_pos_for(seller_id, cat)
            res = ct.build_name(_coupang_name_input(it, ex), pos)
            base["coupang_name"] = str(res.get("name") or "")
            base["coupang_name_source"] = str(res.get("source") or "") if res.get("name") else ""
            base["coupang_brand_pos"] = pos
        except Exception:
            pass
    if edits:
        for k, v in edits.items():
            base[k] = v
    return base
