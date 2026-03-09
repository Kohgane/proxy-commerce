"""
모든 소싱 벤더의 공통 베이스 클래스.
Listly 등으로 크롤링한 원시 데이터를 카탈로그 표준 형식으로 변환하는 역할.
"""

from abc import ABC, abstractmethod

# 카탈로그 표준 필드 목록
CATALOG_FIELDS = [
    'sku', 'title_ko', 'title_en', 'title_ja', 'title_fr',
    'src_url', 'buy_currency', 'buy_price', 'source_country',
    'images', 'stock', 'tags', 'vendor', 'status',
    'category', 'brand', 'forwarder', 'customs_category',
]


class BaseVendor(ABC):
    """소싱 벤더 추상 베이스 클래스."""

    # 서브클래스에서 반드시 설정해야 하는 클래스 속성
    vendor_name: str = ""
    source_country: str = ""
    buy_currency: str = ""
    base_url: str = ""
    forwarder: str = ""

    # ── 추상 메서드 ──────────────────────────────────────────

    @abstractmethod
    def normalize_row(self, raw_row: dict) -> dict:
        """크롤링 원시 행 → 카탈로그 표준 형식 딕셔너리로 변환."""

    @abstractmethod
    def generate_sku(self, raw_row: dict) -> str:
        """벤더별 SKU 생성 규칙."""

    @abstractmethod
    def extract_images(self, raw_row: dict) -> list:
        """이미지 URL 목록 추출."""

    # ── 공통 메서드 ──────────────────────────────────────────

    def normalize_batch(self, raw_rows: list) -> list:
        """raw_rows 리스트를 받아 normalize_row를 반복 호출하여 결과 리스트 반환."""
        return [self.normalize_row(row) for row in raw_rows]

    def to_catalog_row(self, raw_row: dict) -> dict:
        """normalize_row 호출 후 CATALOG_FIELDS 기준으로 정렬된 표준 카탈로그 딕셔너리 반환."""
        normalized = self.normalize_row(raw_row)
        # CATALOG_FIELDS 순서로 정렬하고, 없는 필드는 빈 문자열로 채움
        return {field: normalized.get(field, '') for field in CATALOG_FIELDS}
