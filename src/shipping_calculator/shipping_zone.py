"""src/shipping_calculator/shipping_zone.py — 배송 구역."""
from __future__ import annotations


class ShippingZone:
    """배송 구역 관리자."""

    def __init__(self) -> None:
        self._zones: list[dict] = [
            {'zone_id': 'domestic', 'name': '국내', 'regions': ['KR']},
            {'zone_id': 'east_asia', 'name': '동아시아', 'regions': ['JP', 'CN', 'TW']},
            {'zone_id': 'asia', 'name': '아시아', 'regions': ['TH', 'VN', 'SG', 'MY', 'PH']},
            {'zone_id': 'usa_europe', 'name': '미주/유럽', 'regions': ['US', 'GB', 'DE', 'FR']},
            {'zone_id': 'international', 'name': '기타 국제', 'regions': []},
        ]

    def list_zones(self) -> list:
        """구역 목록을 반환한다."""
        return list(self._zones)

    def get_zone(self, zone_id: str) -> dict | None:
        """구역 정보를 반환한다."""
        for z in self._zones:
            if z['zone_id'] == zone_id:
                return z
        return None

    def classify(self, country_code: str) -> str:
        """국가 코드로 구역을 분류한다."""
        if country_code == 'KR':
            return 'domestic'
        if country_code in ('JP', 'CN', 'TW'):
            return 'east_asia'
        if country_code in ('US', 'GB', 'DE', 'FR'):
            return 'usa_europe'
        if country_code in ('TH', 'VN', 'SG', 'MY', 'PH'):
            return 'asia'
        return 'international'
