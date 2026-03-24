"""src/api/seo_api.py — SEO API.

Flask Blueprint 기반 SEO 메타 태그 및 구조화 데이터 API.

엔드포인트:
  GET  /api/seo/meta/<sku>             — 제품 SEO 메타 태그 조회
  POST /api/seo/generate               — 제품 목록 SEO 메타 일괄 생성
  GET  /api/seo/structured-data/<sku>  — 제품 JSON-LD 구조화 데이터 조회

환경변수:
  DASHBOARD_API_KEY  — API 인증 키
"""

import logging

from flask import Blueprint, jsonify, request

from .auth_middleware import require_api_key

logger = logging.getLogger(__name__)

seo_bp = Blueprint("seo", __name__, url_prefix="/api/seo")

# SKU 조회 실패 시 사용할 더미 제품 데이터
_DUMMY_PRODUCT = {
    "sku": "",
    "title_ko": "샘플 제품",
    "title_en": "Sample Product",
    "category": "General",
    "price_krw": 10000,
    "brand": "Brand",
    "image_url": "",
    "features": ["특징1", "특징2"],
}


def _get_meta_generator():
    """MetaGenerator 인스턴스를 반환한다."""
    from ..seo.meta_generator import MetaGenerator
    return MetaGenerator()


def _get_structured_data_generator():
    """StructuredDataGenerator 인스턴스를 반환한다."""
    from ..seo.structured_data import StructuredDataGenerator
    return StructuredDataGenerator()


def _fetch_product_data(sku: str) -> dict:
    """SKU로 제품 데이터를 조회한다. 실패 시 더미 데이터를 반환한다."""
    try:
        from ..utils.sheets import open_sheet
        import os
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        ws = open_sheet(sheet_id, "catalog")
        records = ws.get_all_records()
        for r in records:
            if str(r.get("sku", "")) == sku:
                return dict(r)
    except Exception as exc:
        logger.debug("제품 데이터 조회 실패, 더미 데이터 사용: %s", exc)
    dummy = dict(_DUMMY_PRODUCT)
    dummy["sku"] = sku
    return dummy


@seo_bp.get("/meta/<sku>")
@require_api_key
def get_seo_meta(sku: str):
    """제품 SEO 메타 태그를 반환한다."""
    language = request.args.get("lang", "ko")
    product_data = _fetch_product_data(sku)
    generator = _get_meta_generator()
    try:
        meta = generator.generate_meta(product_data, language=language)
    except Exception as exc:
        logger.warning("SEO 메타 생성 실패 (%s): %s", sku, exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify(meta)


@seo_bp.post("/generate")
@require_api_key
def bulk_generate_seo():
    """제품 목록의 SEO 메타를 일괄 생성한다.

    body: {
      "products": [...],
      "language": "ko" | "en" | "ja"
    }
    """
    data = request.get_json(silent=True) or {}
    products = data.get("products", [])
    language = data.get("language", "ko")

    generator = _get_meta_generator()
    try:
        results = generator.bulk_generate(products, language=language)
    except Exception as exc:
        logger.warning("SEO 일괄 생성 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify({"results": results, "count": len(results)})


@seo_bp.get("/structured-data/<sku>")
@require_api_key
def get_structured_data(sku: str):
    """제품 JSON-LD 구조화 데이터를 반환한다."""
    product_data = _fetch_product_data(sku)
    generator = _get_structured_data_generator()
    try:
        jsonld = generator.generate_product_jsonld(product_data)
    except Exception as exc:
        logger.warning("구조화 데이터 생성 실패 (%s): %s", sku, exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify(jsonld)
