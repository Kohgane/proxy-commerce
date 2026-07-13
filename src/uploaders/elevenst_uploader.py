"""11번가(11st) OpenAPI 상품 업로더.

11번가 OpenAPI는 XML 기반 상품 등록을 사용한다.
  POST https://api.11st.co.kr/rest/prodservices/product
  헤더: openapikey: <ELEVENST_API_KEY>
  바디: <Product>...</Product> (XML)
응답 XML에서 결과 코드와 상품번호를 파싱한다.

CoupangUploader / NaverSmartStoreUploader와 동일한 인터페이스
(`prepare_product`, `upload_product` → {'success', 'product_id', 'url'})를 따른다.

환경변수:
  ELEVENST_API_KEY     — 11번가 OpenAPI 키 (필수)
  ELEVENST_DISP_CTGR_NO — 기본 표시 카테고리 번호 (선택)

주의: 11번가 상품 등록은 배송 템플릿/카테고리 등 셀러별 설정값이 필요하다.
본 모듈은 OpenAPI 표준 핵심 필드를 채우며, 운영 시 셀러 계정 설정에 맞춰
카테고리/배송 코드를 조정해야 한다(라이브 검증은 운영 환경에서 수행).
"""

import logging
import math
import os
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import requests

from .base_uploader import BaseUploader

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.11st.co.kr/rest"


class ElevenStUploader(BaseUploader):
    """11번가 OpenAPI 상품 업로더."""

    uploader_name = "elevenst"
    marketplace = "11st"

    # 수집 카테고리 코드 → 11번가 표시 카테고리 번호 (대표값, 운영 시 조정)
    CATEGORY_MAP = {
        "ELC": "1001819",
        "HOM": "1002420",
        "BTY": "1004269",
        "HLT": "1012387",
        "TOY": "1008180",
        "SPT": "1008599",
        "CLO": "1001068",
        "BAG": "1003205",
        "BBY": "1009974",
        "PET": "1013183",
        "FOD": "1009491",
        "OFC": "1010657",
        "DIG": "1001819",
    }
    DEFAULT_CATEGORY = "1001819"

    def __init__(self):
        """11번가 업로더 초기화. 환경변수에서 API 키를 읽는다."""
        self.api_key = os.getenv("ELEVENST_API_KEY", "")
        self.default_category = os.getenv("ELEVENST_DISP_CTGR_NO", self.DEFAULT_CATEGORY)
        if not self.api_key:
            logger.warning("ELEVENST_API_KEY is not set")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload_product(self, product: dict) -> dict:
        """11번가에 상품을 등록한다.

        Returns:
            성공: {'success': True, 'product_id': '...', 'url': '...'}
            실패: {'success': False, 'error': '...'}
        """
        if not self.api_key:
            return {"success": False, "error": "Missing ELEVENST_API_KEY", "sku": product.get("sku", "")}
        try:
            xml_body = self._build_product_xml(product)
            from src.market_throttle import throttled_request
            resp = throttled_request(
                lambda: requests.post(
                    f"{_BASE_URL}/prodservices/product",
                    headers={"openapikey": self.api_key, "Content-Type": "text/xml; charset=utf-8"},
                    data=xml_body.encode("utf-8"),
                    timeout=15,
                ),
                market="elevenst",
            )
            if resp.status_code not in (200, 201):
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                    "sku": product.get("sku", ""),
                }
            parsed = self._parse_response(resp.text)
            if not parsed["ok"]:
                return {"success": False, "error": parsed["message"], "sku": product.get("sku", "")}
            product_no = parsed["product_no"]
            url = f"https://www.11st.co.kr/products/{product_no}" if product_no else ""
            return {"success": True, "product_id": product_no, "url": url, "sku": product.get("sku", "")}
        except Exception as exc:
            logger.error("upload_product failed for sku=%s: %s", product.get("sku", ""), exc)
            return {"success": False, "error": str(exc), "sku": product.get("sku", "")}

    def update_product(self, product_id: str, updates: dict) -> dict:
        """11번가 상품 정보를 업데이트한다."""
        if not self.api_key:
            return {"success": False, "error": "Missing ELEVENST_API_KEY"}
        try:
            price = int(updates.get("price") or 0)
            xml_body = (
                "<?xml version='1.0' encoding='UTF-8'?>"
                f"<PriceRequest><sellprc>{price}</sellprc></PriceRequest>"
            )
            from src.market_throttle import throttled_request
            resp = throttled_request(
                lambda: requests.post(
                    f"{_BASE_URL}/prodservices/product/{product_id}/price",
                    headers={"openapikey": self.api_key, "Content-Type": "text/xml; charset=utf-8"},
                    data=xml_body.encode("utf-8"),
                    timeout=10,
                ),
                market="elevenst",
            )
            if resp.status_code in (200, 201):
                return {"success": True}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as exc:
            logger.error("update_product failed for product_id=%s: %s", product_id, exc)
            return {"success": False, "error": str(exc)}

    def delete_product(self, product_id: str) -> bool:
        """11번가 상품을 삭제(판매중지)한다."""
        if not self.api_key:
            return False
        try:
            resp = requests.delete(
                f"{_BASE_URL}/prodservices/product/{product_id}",
                headers={"openapikey": self.api_key},
                timeout=10,
            )
            return resp.status_code in (200, 201, 204)
        except Exception as exc:
            logger.error("delete_product failed for product_id=%s: %s", product_id, exc)
            return False

    def get_categories(self) -> list:
        """11번가 카테고리 목록을 반환한다(표준 매핑 키)."""
        return [{"code": code, "category_id": cid} for code, cid in self.CATEGORY_MAP.items()]

    def prepare_product(self, collected: dict) -> dict:
        """수집된 상품을 11번가 업로드 형식으로 변환한다."""
        if not collected:
            return {}
        title = collected.get("title_ko") or collected.get("title_original", "")
        title = "[해외직구] " + title
        if len(title) > 100:
            title = title[:100]
        category_code = collected.get("category_code", "GEN")
        category_id = self.CATEGORY_MAP.get(category_code, self.default_category)
        sell_price = collected.get("sell_price_krw", 0) or 0
        # 11번가는 10원 단위 판매가
        price = int(math.ceil(sell_price / 10) * 10)
        images = (collected.get("images") or [])[:10]
        return {
            "sku": collected.get("sku", ""),
            "title": title,
            "description_html": collected.get("description_html", ""),
            "price": price,
            "images": images,
            "category_id": category_id,
            "brand": collected.get("brand", ""),
            "stock": 999,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_product_xml(self, product: dict) -> str:
        """11번가 OpenAPI용 상품 등록 XML을 구성한다."""
        images = product.get("images") or []
        image_tags = "".join(
            f"<prdImage0{i}>{escape(str(url))}</prdImage0{i}>"
            for i, url in enumerate(images[:4], start=1)
        )
        title = escape(str(product.get("title", "")))
        brand = escape(str(product.get("brand", "")))
        detail = escape(str(product.get("description_html", "")) or title)
        category_id = escape(str(product.get("category_id", self.default_category)))
        price = int(product.get("price", 0) or 0)
        stock = int(product.get("stock", 999) or 0)
        return (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<Product>"
            "<selMthdCd>02</selMthdCd>"
            f"<dispCtgrNo>{category_id}</dispCtgrNo>"
            "<prdTypCd>01</prdTypCd>"
            f"<prdNm>{title}</prdNm>"
            f"<brand>{brand}</brand>"
            "<orgnTypCd>03</orgnTypCd>"
            f"<selPrc>{price}</selPrc>"
            f"<prdSelQty>{stock}</prdSelQty>"
            f"{image_tags}"
            f"<htmlDetail>{detail}</htmlDetail>"
            "<dlvCnAreaCd>01</dlvCnAreaCd>"
            "</Product>"
        )

    @staticmethod
    def _parse_response(xml_text: str) -> dict:
        """11번가 등록 응답 XML을 파싱한다.

        Returns:
            {'ok': bool, 'product_no': str, 'message': str}
        """
        try:
            root = ET.fromstring(xml_text)
        except Exception as exc:
            logger.warning("11번가 응답 XML 파싱 실패: %s", exc)
            return {"ok": False, "product_no": "", "message": "응답 파싱 실패"}

        def _find(*names):
            for name in names:
                node = root.find(f".//{name}")
                if node is not None and (node.text or "").strip():
                    return node.text.strip()
            return ""

        code = _find("result_code", "resultCode", "ErrCode")
        raw_msg = _find("result_text", "resultMsg", "ErrMsg")
        product_no = _find("ProductNo", "product_no", "prdNo")
        ok = code in ("100", "200", "0") or bool(product_no)
        # v61 STEP4: '등록 실패: 등록 실패' 동어반복 금지 — 응답 코드·메시지 원문(마스킹)으로 구체화.
        try:
            from src.utils.secret_mask import mask_text
        except Exception:
            mask_text = lambda s, **k: s   # noqa: E731
        if raw_msg and code:
            message = mask_text(f"[{code}] {raw_msg}")
        elif raw_msg:
            message = mask_text(raw_msg)
        elif code:
            message = f"11번가 응답 코드 {code} (메시지 없음 — 코드로 원인 확인 필요)"
        else:
            # 코드·메시지 둘 다 없음 → 원문 앞부분을 마스킹해 진단(뭉뚱그림 금지).
            _raw = ""
            try:
                import xml.etree.ElementTree as _ET
                _raw = _ET.tostring(root, encoding="unicode")[:300]
            except Exception:
                _raw = ""
            message = ("11번가 응답을 해석하지 못했어요 — 원문: " + mask_text(_raw)) if _raw else "11번가 응답 없음(연결·키 확인 필요)"
        return {"ok": ok, "code": code, "product_no": product_no, "message": message}
