"""
벤더 플러그인 추상 베이스 클래스.

새 벤더를 추가할 때 이 클래스를 상속하고 필수 메서드를 구현한다.
"""

from abc import ABC, abstractmethod
from typing import List, Optional


class VendorPlugin(ABC):
    """소싱 벤더 플러그인 추상 베이스 클래스.

    새 벤더 플러그인을 작성할 때는 이 클래스를 상속하고
    필수 추상 메서드를 반드시 구현해야 한다.

    플러그인 메타데이터 (클래스 속성으로 정의):
        name (str): 벤더 고유 식별자 (예: "porter", "memo_paris")
        display_name (str): 사람이 읽기 좋은 벤더명 (예: "Porter Exchange")
        currency (str): 소싱 통화 코드 (예: "JPY", "EUR")
        country (str): 소싱 국가 코드 (예: "JP", "FR")
        base_url (str): 벤더 웹사이트 기본 URL
    """

    # 서브클래스에서 반드시 정의해야 하는 메타데이터
    name: str = ""
    display_name: str = ""
    currency: str = ""
    country: str = ""
    base_url: str = ""

    # ── 필수 추상 메서드 ──────────────────────────────────────

    @abstractmethod
    def fetch_products(self) -> List[dict]:
        """벤더에서 상품 목록을 가져온다.

        반환:
            카탈로그 표준 형식의 딕셔너리 리스트.
            각 딕셔너리는 'sku', 'title_ko', 'buy_price', 'stock' 등의 필드를 포함해야 한다.
        """

    @abstractmethod
    def check_stock(self, url: str) -> bool:
        """주어진 상품 URL에서 재고 여부를 확인한다.

        인자:
            url: 상품 상세 페이지 URL

        반환:
            재고 있으면 True, 품절이면 False
        """

    @abstractmethod
    def get_vendor_info(self) -> dict:
        """벤더 기본 정보 딕셔너리를 반환한다.

        반환:
            'name', 'display_name', 'currency', 'country', 'base_url' 키를 포함하는 딕셔너리
        """

    # ── 선택 메서드 (기본 구현 제공) ────────────────────────────

    def parse_price(self, html: str) -> Optional[float]:
        """HTML 문자열에서 가격을 파싱한다.

        기본 구현은 None을 반환한다. 필요 시 서브클래스에서 오버라이드.

        인자:
            html: 가격 정보가 포함된 HTML 문자열

        반환:
            파싱된 가격(float) 또는 None
        """
        return None

    def get_shipping_estimate(self) -> Optional[int]:
        """예상 배송 기간(일)을 반환한다.

        기본 구현은 None을 반환한다. 필요 시 서브클래스에서 오버라이드.

        반환:
            예상 배송 기간(일) 또는 None
        """
        return None

    def normalize_row(self, raw_row: dict) -> dict:
        """크롤링 원시 행을 카탈로그 표준 형식으로 변환한다.

        기본 구현은 원시 행을 그대로 반환한다. 필요 시 서브클래스에서 오버라이드.

        인자:
            raw_row: 크롤링된 원시 데이터 딕셔너리

        반환:
            카탈로그 표준 형식 딕셔너리
        """
        return raw_row

    def __repr__(self) -> str:
        return f"<VendorPlugin name={self.name!r} currency={self.currency!r} country={self.country!r}>"
