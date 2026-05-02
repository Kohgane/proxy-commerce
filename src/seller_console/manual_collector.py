"""src/seller_console/manual_collector.py — 수동 수집기 서비스 (Phase 122).

ManualCollectorService: URL → ProductDraft 추출.
어댑터 패턴으로 소싱처별 메타데이터 추출 (현재 mock 구현; 실 스크래핑은 Phase 123 PR).

지원 소싱처:
  - Amazon (amazon.com, amazon.co.jp)
  - Taobao (taobao.com, tmall.com)
  - Alibaba/1688 (1688.com, alibaba.com)
  - Porter (en.porter.jp)
  - Memo Paris (memoparis.com)
  - Alo Yoga (aloyoga.com)
  - Lululemon (lululemon.com)
  - 프리미엄 스포츠 (nike.com, under-armour.com, arcteryx.com)
  - Generic (기타 URL)
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------

@dataclass
class ProductOption:
    """상품 옵션 항목."""
    name: str       # 옵션명 (예: 색상, 사이즈)
    values: List[str] = field(default_factory=list)  # 옵션 값 목록


@dataclass
class ProductDraft:
    """수집된 상품 초안 (업로드 전 검수 대기 상태)."""

    url: str
    source: str                       # 소싱처 코드 (amazon_us, taobao 등)
    title_en: str = ""                # 원문 제목
    title_ko: str = ""                # 한국어 번역 제목 (자동)
    price_original: float = 0.0      # 원래 가격
    currency: str = "USD"            # 통화
    images: List[str] = field(default_factory=list)    # 이미지 URL 목록
    description: str = ""            # 상품 설명
    options: List[ProductOption] = field(default_factory=list)  # 옵션 목록
    rating: float = 0.0              # 별점
    review_count: int = 0            # 리뷰 수
    brand: str = ""                  # 브랜드명
    category: str = ""               # 카테고리
    seller_id: Optional[str] = None  # 판매자 ID (타오바오 등)
    adapter_used: str = ""           # 사용된 어댑터 클래스명
    is_mock: bool = True             # mock 데이터 여부

    def to_dict(self) -> Dict:
        """JSON 직렬화용 딕셔너리 반환."""
        return {
            "url": self.url,
            "source": self.source,
            "title_en": self.title_en,
            "title_ko": self.title_ko,
            "price_original": self.price_original,
            "currency": self.currency,
            "images": self.images,
            "description": self.description,
            "options": [{"name": o.name, "values": o.values} for o in self.options],
            "rating": self.rating,
            "review_count": self.review_count,
            "brand": self.brand,
            "category": self.category,
            "seller_id": self.seller_id,
            "adapter_used": self.adapter_used,
            "is_mock": self.is_mock,
        }


# ---------------------------------------------------------------------------
# 어댑터 ABC
# ---------------------------------------------------------------------------

class SourceAdapter(ABC):
    """소싱처 어댑터 추상 기반 클래스."""

    @property
    @abstractmethod
    def source_code(self) -> str:
        """소싱처 코드."""

    @abstractmethod
    def matches(self, url: str) -> bool:
        """해당 어댑터가 URL을 처리 가능한지 확인."""

    @abstractmethod
    def extract(self, url: str) -> ProductDraft:
        """URL에서 ProductDraft 추출 (mock 구현)."""


# ---------------------------------------------------------------------------
# 구체 어댑터 구현 (mock)
# ---------------------------------------------------------------------------

class AmazonAdapter(SourceAdapter):
    """Amazon (US/JP) 어댑터 — mock 구현."""

    @property
    def source_code(self) -> str:
        return "amazon"

    def matches(self, url: str) -> bool:
        return bool(re.search(r"amazon\.(com|co\.jp|co\.uk|de|fr)", url, re.I))

    def extract(self, url: str) -> ProductDraft:
        """Amazon 상품 메타데이터 추출 (mock)."""
        # 일본 Amazon 여부 판단
        is_jp = "amazon.co.jp" in url.lower()
        currency = "JPY" if is_jp else "USD"
        price = 3800.0 if is_jp else 29.99

        return ProductDraft(
            url=url,
            source=self.source_code,
            title_en="[Mock] Premium Running Shoes — Lightweight Breathable Mesh",
            title_ko="[Mock] 프리미엄 러닝화 — 경량 통기성 메시",
            price_original=price,
            currency=currency,
            images=[
                "https://m.media-amazon.com/images/mock/product1.jpg",
                "https://m.media-amazon.com/images/mock/product2.jpg",
            ],
            description="Mock: High-performance running shoes with advanced cushioning technology.",
            options=[
                ProductOption(name="Size", values=["250", "255", "260", "265", "270", "275", "280"]),
                ProductOption(name="Color", values=["Black/White", "Navy/Grey", "Red/Black"]),
            ],
            rating=4.5,
            review_count=1243,
            brand="Nike",
            category="스포츠/신발",
            adapter_used=self.__class__.__name__,
            is_mock=True,
        )


class TaobaoAdapter(SourceAdapter):
    """Taobao / Tmall 어댑터 — mock 구현."""

    @property
    def source_code(self) -> str:
        return "taobao"

    def matches(self, url: str) -> bool:
        return bool(re.search(r"(taobao|tmall)\.com", url, re.I))

    def extract(self, url: str) -> ProductDraft:
        """타오바오 상품 메타데이터 추출 (mock)."""
        return ProductDraft(
            url=url,
            source=self.source_code,
            title_en="[Mock] Korean Style Summer Dress — Chiffon Floral Print",
            title_ko="[Mock] 한국풍 여름 원피스 — 쉬폰 플로럴 프린트",
            price_original=68.0,
            currency="CNY",
            images=[
                "https://img.alicdn.com/imgextra/mock/dress1.jpg",
                "https://img.alicdn.com/imgextra/mock/dress2.jpg",
            ],
            description="Mock: 고품질 쉬폰 소재, 여름 나들이용 플로럴 원피스.",
            options=[
                ProductOption(name="사이즈", values=["S", "M", "L", "XL", "XXL"]),
                ProductOption(name="색상", values=["화이트 플로럴", "블루 플로럴", "핑크 플로럴"]),
            ],
            rating=4.8,
            review_count=3560,
            brand="",
            category="여성의류/원피스",
            seller_id="taobao_seller_ok",
            adapter_used=self.__class__.__name__,
            is_mock=True,
        )


class AlibabaAdapter(SourceAdapter):
    """Alibaba / 1688 어댑터 — mock 구현."""

    @property
    def source_code(self) -> str:
        return "alibaba"

    def matches(self, url: str) -> bool:
        return bool(re.search(r"(1688|alibaba)\.com", url, re.I))

    def extract(self, url: str) -> ProductDraft:
        """1688 상품 메타데이터 추출 (mock)."""
        return ProductDraft(
            url=url,
            source=self.source_code,
            title_en="[Mock] Wholesale Cotton T-Shirt — Custom Logo Print MOQ 50",
            title_ko="[Mock] 도매 면 티셔츠 — 커스텀 로고 인쇄 MOQ 50개",
            price_original=15.5,
            currency="CNY",
            images=[
                "https://cbu01.alicdn.com/img/mock/tshirt1.jpg",
            ],
            description="Mock: 도매용 순면 티셔츠. 최소 주문 수량 50개.",
            options=[
                ProductOption(name="사이즈", values=["S", "M", "L", "XL"]),
                ProductOption(name="색상", values=["화이트", "블랙", "그레이", "네이비"]),
            ],
            rating=4.6,
            review_count=890,
            brand="",
            category="의류/티셔츠",
            seller_id="taobao_seller_ok",
            adapter_used=self.__class__.__name__,
            is_mock=True,
        )


class PorterAdapter(SourceAdapter):
    """Porter (en.porter.jp) 어댑터 — mock 구현."""

    @property
    def source_code(self) -> str:
        return "porter"

    def matches(self, url: str) -> bool:
        return bool(re.search(r"porter\.jp", url, re.I))

    def extract(self, url: str) -> ProductDraft:
        """Porter 상품 메타데이터 추출 (mock)."""
        return ProductDraft(
            url=url,
            source=self.source_code,
            title_en="[Mock] PORTER TANK — Nylon 2Way Shoulder Bag",
            title_ko="[Mock] 포터 탱크 — 나일론 2WAY 숄더백",
            price_original=38500,
            currency="JPY",
            images=[
                "https://www.yoshidakaban.com/img/mock/tank1.jpg",
                "https://www.yoshidakaban.com/img/mock/tank2.jpg",
            ],
            description="Mock: PORTER TANK 시리즈. 고내구성 나일론 소재, 2WAY 숄더백.",
            options=[
                ProductOption(name="Color", values=["Black", "Khaki", "Navy"]),
            ],
            rating=4.9,
            review_count=256,
            brand="PORTER",
            category="가방/숄더백",
            adapter_used=self.__class__.__name__,
            is_mock=True,
        )


class MemoAdapter(SourceAdapter):
    """Memo Paris (memoparis.com) 어댑터 — mock 구현."""

    @property
    def source_code(self) -> str:
        return "memo"

    def matches(self, url: str) -> bool:
        return bool(re.search(r"memoparis\.com", url, re.I))

    def extract(self, url: str) -> ProductDraft:
        """Memo Paris 상품 메타데이터 추출 (mock)."""
        return ProductDraft(
            url=url,
            source=self.source_code,
            title_en="[Mock] MEMO PARIS Ilha do Mel — Eau de Parfum 75ml",
            title_ko="[Mock] 메모 파리 일라 두 멜 — 오드 퍼퓸 75ml",
            price_original=220.0,
            currency="EUR",
            images=[
                "https://www.memoparis.com/img/mock/ilha1.jpg",
            ],
            description="Mock: 메모 파리 럭셔리 향수. 열대 과일과 바닐라 노트.",
            options=[
                ProductOption(name="용량", values=["75ml", "200ml"]),
            ],
            rating=4.7,
            review_count=89,
            brand="MEMO PARIS",
            category="향수/오드퍼퓸",
            adapter_used=self.__class__.__name__,
            is_mock=True,
        )


class AloAdapter(SourceAdapter):
    """Alo Yoga (aloyoga.com) 어댑터 — mock 구현 (신규 브랜드)."""

    @property
    def source_code(self) -> str:
        return "alo"

    def matches(self, url: str) -> bool:
        return bool(re.search(r"aloyoga\.com", url, re.I))

    def extract(self, url: str) -> ProductDraft:
        """Alo Yoga 상품 메타데이터 추출 (mock)."""
        return ProductDraft(
            url=url,
            source=self.source_code,
            title_en="[Mock] Alo Yoga Airlift Legging — High-Waist Compression Yoga Pants",
            title_ko="[Mock] 알로 요가 에어리프트 레깅스 — 하이웨이스트 압박 요가팬츠",
            price_original=128.0,
            currency="USD",
            images=[
                "https://www.aloyoga.com/cdn/mock/legging1.jpg",
                "https://www.aloyoga.com/cdn/mock/legging2.jpg",
            ],
            description="Mock: 알로 요가 시그니처 에어리프트 레깅스. 고압박 원단, 하이웨이스트 디자인.",
            options=[
                ProductOption(name="Size", values=["XXS", "XS", "S", "M", "L", "XL"]),
                ProductOption(name="Color", values=["Black", "Ivory", "Camel", "Navy", "Forest"]),
            ],
            rating=4.8,
            review_count=2140,
            brand="Alo Yoga",
            category="스포츠웨어/레깅스",
            adapter_used=self.__class__.__name__,
            is_mock=True,
        )


class LululemonAdapter(SourceAdapter):
    """Lululemon (lululemon.com) 어댑터 — mock 구현 (신규 브랜드)."""

    @property
    def source_code(self) -> str:
        return "lululemon"

    def matches(self, url: str) -> bool:
        return bool(re.search(r"lululemon\.com", url, re.I))

    def extract(self, url: str) -> ProductDraft:
        """Lululemon 상품 메타데이터 추출 (mock)."""
        return ProductDraft(
            url=url,
            source=self.source_code,
            title_en="[Mock] Lululemon Align Pant 28\" — Buttery Soft Yoga Legging",
            title_ko="[Mock] 룰루레몬 얼라인 팬츠 28인치 — 버터리 소프트 요가 레깅스",
            price_original=118.0,
            currency="USD",
            images=[
                "https://images.lululemon.com/is/image/lululemon/mock/align1.jpg",
                "https://images.lululemon.com/is/image/lululemon/mock/align2.jpg",
            ],
            description="Mock: 룰루레몬 베스트셀러 얼라인 팬츠. Nulu™ 원단, 초경량·초부드러운 착용감.",
            options=[
                ProductOption(name="Size", values=["0", "2", "4", "6", "8", "10", "12", "14"]),
                ProductOption(name="Color", values=["Black", "True Navy", "Bone", "Varsity Blue"]),
                ProductOption(name="Inseam", values=["25\"", "28\"", "31\""]),
            ],
            rating=4.9,
            review_count=15230,
            brand="lululemon",
            category="스포츠웨어/레깅스",
            adapter_used=self.__class__.__name__,
            is_mock=True,
        )


class PremiumSportsAdapter(SourceAdapter):
    """프리미엄 스포츠 브랜드 폴백 어댑터 (Nike, Under Armour, Arc'teryx 등)."""

    _BRANDS = {
        "nike.com": ("Nike", "스포츠/의류"),
        "under-armour.com": ("Under Armour", "스포츠/의류"),
        "underarmour.com": ("Under Armour", "스포츠/의류"),
        "arcteryx.com": ("Arc'teryx", "아웃도어/의류"),
        "arc-teryx.com": ("Arc'teryx", "아웃도어/의류"),
        "patagonia.com": ("Patagonia", "아웃도어/의류"),
        "thenorthface.com": ("The North Face", "아웃도어/의류"),
    }

    @property
    def source_code(self) -> str:
        return "premium_sports"

    def matches(self, url: str) -> bool:
        url_lower = url.lower()
        return any(domain in url_lower for domain in self._BRANDS)

    def extract(self, url: str) -> ProductDraft:
        """프리미엄 스포츠 상품 메타데이터 추출 (mock)."""
        url_lower = url.lower()
        brand, category = "Premium Sports", "스포츠/의류"
        for domain, (b, c) in self._BRANDS.items():
            if domain in url_lower:
                brand, category = b, c
                break

        return ProductDraft(
            url=url,
            source=self.source_code,
            title_en=f"[Mock] {brand} Premium Athletic Wear",
            title_ko=f"[Mock] {brand} 프리미엄 스포츠웨어",
            price_original=89.99,
            currency="USD",
            images=[
                f"https://mock.{brand.lower().replace(' ', '')}.com/img/product1.jpg",
            ],
            description=f"Mock: {brand} 프리미엄 스포츠웨어. 고성능 소재 사용.",
            options=[
                ProductOption(name="Size", values=["XS", "S", "M", "L", "XL", "XXL"]),
                ProductOption(name="Color", values=["Black", "White", "Grey"]),
            ],
            rating=4.6,
            review_count=500,
            brand=brand,
            category=category,
            adapter_used=self.__class__.__name__,
            is_mock=True,
        )


class GenericAdapter(SourceAdapter):
    """기타 URL용 범용 어댑터 — mock 구현."""

    @property
    def source_code(self) -> str:
        return "generic"

    def matches(self, url: str) -> bool:
        # 항상 매칭 (폴백)
        return True

    def extract(self, url: str) -> ProductDraft:
        """범용 상품 메타데이터 추출 (mock)."""
        parsed = urlparse(url)
        domain = parsed.netloc or "unknown"

        return ProductDraft(
            url=url,
            source=self.source_code,
            title_en=f"[Mock] Product from {domain}",
            title_ko=f"[Mock] {domain} 상품",
            price_original=50.0,
            currency="USD",
            images=[],
            description="Mock: URL에서 자동 추출한 상품 정보입니다.",
            options=[],
            rating=0.0,
            review_count=0,
            brand="",
            category="기타",
            adapter_used=self.__class__.__name__,
            is_mock=True,
        )


# ---------------------------------------------------------------------------
# ManualCollectorService
# ---------------------------------------------------------------------------

# 어댑터 등록 순서: 구체적인 것 먼저, GenericAdapter는 항상 마지막
_ADAPTERS: List[SourceAdapter] = [
    AmazonAdapter(),
    TaobaoAdapter(),
    AlibabaAdapter(),
    PorterAdapter(),
    MemoAdapter(),
    AloAdapter(),
    LululemonAdapter(),
    PremiumSportsAdapter(),
    GenericAdapter(),
]


def adapter_for_url(url: str) -> SourceAdapter:
    """URL에 맞는 어댑터 반환.

    Args:
        url: 상품 URL

    Returns:
        첫 번째 매칭 어댑터 (없으면 GenericAdapter)
    """
    for adapter in _ADAPTERS:
        if adapter.matches(url):
            return adapter
    return GenericAdapter()


class ManualCollectorService:
    """수동 수집기 서비스.

    URL을 입력받아 ProductDraft를 반환.
    어댑터 패턴을 사용하여 소싱처별 추출 로직을 분리.
    """

    def __init__(self, adapters: Optional[List[SourceAdapter]] = None):
        """초기화.

        Args:
            adapters: 사용할 어댑터 목록 (None이면 기본 어댑터 사용)
        """
        self._adapters = adapters if adapters is not None else _ADAPTERS

    def extract(self, url: str) -> ProductDraft:
        """URL에서 ProductDraft 추출.

        Args:
            url: 상품 URL

        Returns:
            ProductDraft 인스턴스
        """
        if not url or not url.strip():
            raise ValueError("URL이 비어있습니다.")

        url = url.strip()

        # URL 형식 검사
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # 어댑터 선택
        for adapter in self._adapters:
            if adapter.matches(url):
                return adapter.extract(url)

        # 폴백 (이론상 GenericAdapter가 항상 매칭하므로 여기까지 오지 않음)
        return GenericAdapter().extract(url)
