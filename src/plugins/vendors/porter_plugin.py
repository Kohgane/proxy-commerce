"""
Porter Exchange (요시다포터) 벤더 플러그인.

기존 src/vendors/porter.py 의 로직을 VendorPlugin 인터페이스로 래핑한다.
"""

import re
from typing import List, Optional

from src.plugins.base import VendorPlugin
from src.plugins.registry import register_vendor
from src.vendors.porter import PorterVendor, _clean_price

# 재고 확인 시 검색할 패턴
_IN_STOCK_PATTERNS = ["カートに入れる", "add to cart"]
_OUT_OF_STOCK_PATTERNS = ["売り切れ", "sold out"]


@register_vendor
class PorterPlugin(VendorPlugin):
    """Porter Exchange (yoshidakaban.com) 벤더 플러그인."""

    name = "porter"
    display_name = "Porter Exchange"
    currency = "JPY"
    country = "JP"
    base_url = "https://www.yoshidakaban.com"

    def __init__(self):
        self._vendor = PorterVendor()

    # ── 필수 메서드 ───────────────────────────────────────────

    def fetch_products(self) -> List[dict]:
        """벤더 카탈로그를 가져온다.

        실제 운영 환경에서는 Google Sheets의 크롤링 데이터를 읽어온다.
        현재 구현은 빈 목록 반환 (외부 의존성 없는 기본 구현).
        """
        return []

    def check_stock(self, url: str) -> bool:
        """yoshidakaban.com 상품 URL에서 재고 여부를 확인한다.

        인자:
            url: 상품 상세 페이지 URL

        반환:
            재고 있으면 True, 품절이면 False
        """
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore").lower()
        except Exception:  # noqa: BLE001
            return False

        for pattern in _OUT_OF_STOCK_PATTERNS:
            if pattern.lower() in html:
                return False
        for pattern in _IN_STOCK_PATTERNS:
            if pattern.lower() in html:
                return True
        return False

    def get_vendor_info(self) -> dict:
        """벤더 기본 정보를 반환한다."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "currency": self.currency,
            "country": self.country,
            "base_url": self.base_url,
            "forwarder": self._vendor.forwarder,
        }

    # ── 선택 메서드 오버라이드 ───────────────────────────────────

    def parse_price(self, html: str) -> Optional[float]:
        """yoshidakaban.com HTML에서 가격(JPY)을 파싱한다."""
        match = re.search(r'¥\s*([\d,]+)', html)
        if match:
            return _clean_price(match.group())
        return None

    def get_shipping_estimate(self) -> Optional[int]:
        """Porter 배송 예상 기간 (젠마켓 → 배대지 → 국내, 영업일 기준)."""
        return 7

    def normalize_row(self, raw_row: dict) -> dict:
        """원시 행을 카탈로그 표준 형식으로 변환한다 (기존 PorterVendor 위임)."""
        return self._vendor.normalize_row(raw_row)
