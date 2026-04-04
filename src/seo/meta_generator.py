"""src/seo/meta_generator.py — SEO 메타 태그 생성기.

제품 데이터를 기반으로 SEO 최적화된 메타 태그를 생성한다.

환경변수:
  SEO_ENABLED  — SEO 기능 활성화 여부 (기본 "0")
"""

import os
from typing import Any, Dict, List

_ENABLED = os.getenv("SEO_ENABLED", "0") == "1"

# 언어별 CTA 문구
_CTA_TEXTS = {
    "ko": "지금 구매하기",
    "en": "Buy Now",
    "ja": "今すぐ購入",
    "zh": "立即购买",
}

# 언어별 기본 설명 접두어
_FEATURE_PREFIX = {
    "ko": "특징",
    "en": "Features",
    "ja": "特徴",
    "zh": "特点",
}


class MetaGenerator:
    """SEO 메타 태그 생성기."""

    def is_enabled(self) -> bool:
        """SEO 기능 활성화 여부를 반환한다."""
        return os.getenv("SEO_ENABLED", "0") == "1"

    def _truncate(self, text: str, max_len: int) -> str:
        """텍스트를 최대 길이로 자른다."""
        if len(text) <= max_len:
            return text
        return text[:max_len - 1] + "…"

    def _get_title(self, product_data: Dict[str, Any], language: str) -> str:
        """제품 타이틀을 반환한다."""
        if language == "ko":
            name = product_data.get("title_ko") or product_data.get("title_en", "")
        else:
            name = product_data.get("title_en") or product_data.get("title_ko", "")
        brand = product_data.get("brand", "")
        category = product_data.get("category", "")
        parts = [p for p in [brand, name, category] if p]
        return " ".join(parts)

    def _get_features_str(self, product_data: Dict[str, Any]) -> str:
        """제품 특징 문자열을 반환한다."""
        features = product_data.get("features", "")
        if isinstance(features, list):
            return ", ".join(str(f) for f in features)
        return str(features) if features else ""

    def generate_meta(self, product_data: Dict[str, Any], language: str = "ko") -> Dict[str, Any]:
        """제품 데이터로 SEO 메타 정보를 생성한다.

        Args:
            product_data: 제품 딕셔너리 (sku, title_ko, title_en, category, price_krw,
                          brand, image_url, features, canonical_url).
            language: 언어 코드 (ko/en/ja/zh, 기본 "ko").

        Returns:
            {meta_title, meta_description, og_tags, twitter_tags, canonical_url} 딕셔너리.
        """
        cta = _CTA_TEXTS.get(language, _CTA_TEXTS["ko"])
        raw_title = self._get_title(product_data, language)
        meta_title = self._truncate(raw_title, 60)

        features_str = self._get_features_str(product_data)
        price_krw = product_data.get("price_krw", "")
        price_part = f"{int(float(price_krw)):,}원" if price_krw else ""
        desc_parts = [p for p in [features_str, price_part, cta] if p]
        raw_desc = " | ".join(desc_parts)
        meta_description = self._truncate(raw_desc, 160)

        image_url = product_data.get("image_url", "")
        canonical_url = product_data.get("canonical_url", "")

        og_tags: Dict[str, str] = {
            "og:title": meta_title,
            "og:description": meta_description,
            "og:image": image_url,
            "og:type": "product",
        }

        twitter_tags: Dict[str, str] = {
            "twitter:card": "summary_large_image",
            "twitter:title": meta_title,
            "twitter:description": meta_description,
            "twitter:image": image_url,
        }

        return {
            "sku": product_data.get("sku", ""),
            "meta_title": meta_title,
            "meta_description": meta_description,
            "og_tags": og_tags,
            "twitter_tags": twitter_tags,
            "canonical_url": canonical_url,
        }

    def bulk_generate(self, products_list: List[Dict[str, Any]], language: str = "ko") -> List[Dict[str, Any]]:
        """제품 목록에 대해 SEO 메타 정보를 일괄 생성한다.

        Args:
            products_list: 제품 딕셔너리 목록.
            language: 언어 코드 (기본 "ko").

        Returns:
            메타 정보 딕셔너리 리스트.
        """
        return [self.generate_meta(p, language=language) for p in products_list]
