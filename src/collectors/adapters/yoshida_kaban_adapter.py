"""src/collectors/adapters/yoshida_kaban_adapter.py — Yoshida & Co. (PORTER) 어댑터 (Phase 135).

도메인: yoshidakaban.com (일본 PORTER 가방)
- 일본어 → AI 번역 hook (OpenAI/DeepL, 없으면 원문 유지)
- 엔화 가격 → 원화 변환 (exchange_rate)
- 카테고리: 가방/지갑/액세서리
"""
from __future__ import annotations

import json
import logging
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from .base_adapter import BrandAdapter
from ..universal_scraper import ScrapedProduct, _extract_domain, _fetch_html, _parse_price

logger = logging.getLogger(__name__)

_DRY_RUN = os.getenv("ADAPTER_DRY_RUN", "0") == "1"

# カテゴリ キーワード (일본어) — 더 구체적인 키워드 우선
_CATEGORY_KEYWORDS: dict = {
    "トートバッグ": "토트백",
    "ショルダーバッグ": "숄더백",
    "ブリーフケース": "브리프케이스",
    "リュックサック": "백팩",
    "リュック": "백팩",
    "ウォレット": "지갑",
    "財布": "지갑",
    "ポーチ": "파우치",
    "アクセサリー": "액세서리",
    "ケース": "케이스",
    "トート": "토트백",
    "ショルダー": "숄더백",
    "バッグ": "가방",
}


def _translate_text(text: str, source_lang: str = "JA", target_lang: str = "KO") -> str:
    """AI 번역 훅 — OpenAI/DeepL, 없으면 원문 반환."""
    if not text or _DRY_RUN:
        return text
    # DeepL 시도
    deepl_key = os.getenv("DEEPL_API_KEY")
    if deepl_key:
        try:
            import requests
            resp = requests.post(
                "https://api-free.deepl.com/v2/translate",
                data={"text": text[:1000], "source_lang": source_lang, "target_lang": target_lang},
                headers={"Authorization": f"DeepL-Auth-Key {deepl_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                translations = resp.json().get("translations", [])
                if translations:
                    return translations[0].get("text", text)
        except Exception as exc:
            logger.debug("DeepL 번역 실패: %s", exc)

    # OpenAI 시도
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            import requests
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": f"Translate the following {source_lang} text to {target_lang}. Return only the translation, no explanation."},
                        {"role": "user", "content": text[:1000]},
                    ],
                    "max_tokens": 500,
                },
                headers={"Authorization": f"Bearer {openai_key}"},
                timeout=15,
            )
            if resp.status_code == 200:
                choices = resp.json().get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", text).strip()
        except Exception as exc:
            logger.debug("OpenAI 번역 실패: %s", exc)

    return text


def _jpy_to_krw(amount: Decimal) -> Optional[Decimal]:
    """엔화 → 원화 변환 (환율 API 또는 기본값 9.0)."""
    try:
        from src.utils.sheets import open_sheet
        import os
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        if sheet_id:
            ws = open_sheet(sheet_id, "fx_rates")
            records = ws.get_all_records()
            for row in records:
                if row.get("pair") == "JPYKRW":
                    rate = Decimal(str(row.get("rate", 9.0)))
                    return amount * rate
    except Exception:
        pass
    # 기본 환율
    default_rate = Decimal(os.getenv("JPY_KRW_RATE", "9.0"))
    return amount * default_rate


def _detect_category(title_ja: str) -> str:
    """일본어 상품명에서 카테고리 감지."""
    for keyword, category in _CATEGORY_KEYWORDS.items():
        if keyword in title_ja:
            return category
    return "가방"


class YoshidaKabanAdapter(BrandAdapter):
    """Yoshida & Co. PORTER (yoshidakaban.com) 전용 어댑터."""

    name = "yoshida_kaban"
    domain = "yoshidakaban.com"

    def fetch(self, url: str) -> ScrapedProduct:
        """Yoshida Kaban 상품 페이지에서 메타 추출 (일본어, 엔화)."""
        domain = _extract_domain(url)

        if _DRY_RUN:
            return ScrapedProduct(
                source_url=url, domain=domain,
                title="PORTER DRY_RUN 가방 (TEST TOTE)",
                description="Porter Test Product",
                images=["https://example.com/porter.jpg"],
                price=Decimal("33000"), currency="JPY",
                brand="PORTER / 吉田カバン",
                extraction_method="adapter:yoshida_kaban", confidence=1.0,
                raw_meta={"price_krw": "297000", "category": "토트백"},
            )

        html = _fetch_html(url)
        if not html:
            return ScrapedProduct(
                source_url=url, domain=domain,
                title="", description="",
                extraction_method="adapter:yoshida_kaban", confidence=0.0,
            )

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except ImportError:
            return ScrapedProduct(source_url=url, domain=domain, title="", description="", confidence=0.0)

        return self._parse(soup, url, domain)

    def _parse(self, soup, url: str, domain: str) -> ScrapedProduct:
        # 1. JSON-LD 우선
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                schemas = data if isinstance(data, list) else [data]
                for schema in schemas:
                    if schema.get("@type") != "Product":
                        continue
                    title_ja = schema.get("name", "")
                    desc_ja = schema.get("description", "")
                    sku = schema.get("sku", "")
                    imgs = schema.get("image", [])
                    if isinstance(imgs, str):
                        imgs = [imgs]
                    offers = schema.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price_val = _parse_price(str(offers.get("price", "")))
                    currency = offers.get("priceCurrency", "JPY") or "JPY"
                    if not title_ja:
                        continue

                    return self._build_product(
                        url, domain, title_ja, desc_ja, imgs[:10],
                        price_val, currency, sku,
                    )
            except (json.JSONDecodeError, AttributeError):
                continue

        # 2. CSS 폴백
        title_ja = ""
        h1 = soup.find("h1")
        if h1:
            title_ja = h1.get_text(strip=True)

        desc_ja = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            desc_ja = meta_desc.get("content", "")

        price_val = None
        currency = "JPY"
        # 엔화 가격 패턴: ¥XX,XXX or XX,XXX円
        price_el = soup.select_one(".price, [class*='price'], .product-price")
        if price_el:
            price_text = price_el.get_text(strip=True)
            price_val = _parse_price(re.sub(r"[¥￥円,]", "", price_text).strip())

        imgs = []
        for img in soup.select(".product-image img, .gallery img"):
            src = img.get("src") or img.get("data-src") or ""
            if src and src.startswith("http"):
                imgs.append(src)
        imgs = list(dict.fromkeys(imgs))[:10]

        return self._build_product(url, domain, title_ja, desc_ja, imgs, price_val, currency, "")

    def _build_product(
        self, url: str, domain: str, title_ja: str, desc_ja: str,
        imgs: list, price_val: Optional[Decimal], currency: str, sku: str,
    ) -> ScrapedProduct:
        """번역 + 환율 변환 후 ScrapedProduct 생성."""
        title_ko = _translate_text(title_ja, "JA", "KO") if title_ja else ""
        desc_ko = _translate_text(desc_ja, "JA", "KO") if desc_ja else ""

        category = _detect_category(title_ja)

        price_krw = None
        if price_val and currency == "JPY":
            price_krw_val = _jpy_to_krw(price_val)
            if price_krw_val:
                price_krw = str(int(price_krw_val))

        confidence = 0.5 if title_ja else 0.2
        if imgs:
            confidence = min(confidence + 0.2, 1.0)
        if price_val:
            confidence = min(confidence + 0.2, 1.0)

        return ScrapedProduct(
            source_url=url, domain=domain,
            title=title_ko or title_ja,
            description=desc_ko or desc_ja,
            images=imgs, price=price_val, currency=currency,
            brand="PORTER / 吉田カバン", sku=sku or None,
            extraction_method="adapter:yoshida_kaban", confidence=confidence,
            raw_meta={
                "title_ja": title_ja,
                "desc_ja": desc_ja,
                "price_krw": price_krw,
                "category": category,
            },
        )
