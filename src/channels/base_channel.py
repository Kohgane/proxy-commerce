"""판매채널 공통 인터페이스 — BaseChannel ABC"""
from abc import ABC, abstractmethod


class BaseChannel(ABC):
    channel_name: str
    target_currency: str  # 해당 채널의 판매 통화

    @abstractmethod
    def prepare_product(self, catalog_row: dict, sell_price: float) -> dict:
        """카탈로그 행 → 해당 채널 형식으로 변환"""

    @abstractmethod
    def export_batch(self, products: list, output_path: str) -> str:
        """변환된 상품 목록을 파일로 내보내기 (CSV 등)"""

    @abstractmethod
    def get_category_mapping(self, catalog_category: str) -> str:
        """카탈로그 카테고리 → 채널 카테고리 코드 매핑"""
