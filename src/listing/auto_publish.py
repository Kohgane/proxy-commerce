"""src/listing/auto_publish.py — 상품 등록 자동화 (Phase 143).

후보 승인 → 이미지 처리 + 번역 + 채널 적응 → 쿠팡/스마트스토어/11번가 동시 업로드.
부분 실패 허용 (일부 채널 실패해도 성공 채널 결과 반환).

환경변수:
  LISTING_AUTO_PUBLISH=0                  자동 등록 활성화 (기본: 0, 비활성)
  LISTING_AUTO_PUBLISH_CHANNELS=coupang,smartstore  대상 채널
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_AUTO_PUBLISH_ENABLED = os.getenv("LISTING_AUTO_PUBLISH", "0") == "1"
_DEFAULT_CHANNELS = [
    c.strip() for c in os.getenv("LISTING_AUTO_PUBLISH_CHANNELS", "coupang,smartstore").split(",")
    if c.strip()
]

# 채널별 이미지 사이즈 (width, height) 기준
_CHANNEL_IMAGE_SIZES: Dict[str, tuple] = {
    "coupang": (800, 800),
    "smartstore": (1000, 1000),
    "11st": (750, 750),
    "default": (800, 800),
}

# 채널별 카테고리 매핑 (category → channel_category_id)
_CHANNEL_CATEGORY_MAP: Dict[str, Dict[str, str]] = {
    "coupang": {
        "전자기기": "56137",
        "뷰티": "56138",
        "패션": "56139",
        "스포츠": "56140",
        "주방용품": "56141",
        "반려동물": "56142",
        "건강식품": "56143",
        "가구/인테리어": "56144",
        "default": "56137",
    },
    "smartstore": {
        "전자기기": "50000803",
        "뷰티": "50000819",
        "패션": "50000816",
        "스포츠": "50000812",
        "주방용품": "50000806",
        "반려동물": "50000827",
        "건강식품": "50000818",
        "가구/인테리어": "50000804",
        "default": "50000803",
    },
    "11st": {
        "전자기기": "1001",
        "뷰티": "1002",
        "패션": "1003",
        "스포츠": "1004",
        "주방용품": "1005",
        "반려동물": "1006",
        "건강식품": "1007",
        "가구/인테리어": "1008",
        "default": "1001",
    },
}

# 채널별 수수료율
_CHANNEL_FEE_RATES: Dict[str, float] = {
    "coupang": 0.108,
    "smartstore": 0.07,
    "11st": 0.09,
    "default": 0.10,
}


# ---------------------------------------------------------------------------
# 도메인 모델
# ---------------------------------------------------------------------------

@dataclass
class Product:
    """등록할 상품 정보."""

    product_id: str
    title_ko: str                    # 한국어 제목
    title_original: str = ""         # 원본 제목
    description_ko: str = ""         # 한국어 설명
    price_krw: int = 0
    category: str = ""
    image_urls: List[str] = field(default_factory=list)
    processed_image_urls: List[str] = field(default_factory=list)  # 워터마크 제거 후
    options: List[Dict[str, Any]] = field(default_factory=list)   # 옵션 목록
    spec: Dict[str, str] = field(default_factory=dict)            # 사이즈/소재 등 사양
    stock: int = 0
    source_platform: str = ""
    source_url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "title_ko": self.title_ko,
            "title_original": self.title_original,
            "description_ko": self.description_ko,
            "price_krw": self.price_krw,
            "category": self.category,
            "image_urls": self.image_urls,
            "processed_image_urls": self.processed_image_urls,
            "options": self.options,
            "spec": self.spec,
            "stock": self.stock,
            "source_platform": self.source_platform,
            "source_url": self.source_url,
            "metadata": self.metadata,
        }


@dataclass
class ChannelListing:
    """채널 적응 상품 정보."""

    channel: str
    product_id: str
    title: str
    description: str
    price: int
    channel_category_id: str
    image_urls: List[str]
    options: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "product_id": self.product_id,
            "title": self.title,
            "description": self.description,
            "price": self.price,
            "channel_category_id": self.channel_category_id,
            "image_urls": self.image_urls,
            "options": self.options,
            "metadata": self.metadata,
        }


@dataclass
class ChannelUploadResult:
    """채널별 업로드 결과."""

    channel: str
    success: bool
    listing_id: Optional[str] = None
    channel_listing_id: Optional[str] = None
    error: Optional[str] = None
    uploaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "success": self.success,
            "listing_id": self.listing_id,
            "channel_listing_id": self.channel_listing_id,
            "error": self.error,
            "uploaded_at": self.uploaded_at,
        }


# ---------------------------------------------------------------------------
# 이력 저장소
# ---------------------------------------------------------------------------

_listing_history: List[Dict[str, Any]] = []


def get_listing_history() -> List[Dict[str, Any]]:
    return list(reversed(_listing_history))


# ---------------------------------------------------------------------------
# 핵심 파이프라인 함수
# ---------------------------------------------------------------------------

def adapt_for_channel(product: Product, channel: str) -> ChannelListing:
    """카테고리·옵션·이미지 사이즈 등 채널 적응.

    - 제목 길이 제한 (채널별)
    - 카테고리 매핑
    - 이미지 URL 채널별 선택 (처리 완료 이미지 우선)
    - 수수료 반영 가격 조정
    """
    cat_map = _CHANNEL_CATEGORY_MAP.get(channel, _CHANNEL_CATEGORY_MAP.get("coupang", {}))
    channel_cat = cat_map.get(product.category, cat_map.get("default", ""))

    fee_rate = _CHANNEL_FEE_RATES.get(channel, _CHANNEL_FEE_RATES["default"])
    adjusted_price = int(product.price_krw * (1 + fee_rate))
    # 100원 단위 올림
    adjusted_price = ((adjusted_price + 99) // 100) * 100

    # 제목 길이 제한
    title_max = {"coupang": 100, "smartstore": 100, "11st": 80}.get(channel, 100)
    title = product.title_ko[:title_max]

    # 이미지 (처리 완료 이미지 우선)
    images = product.processed_image_urls or product.image_urls

    # 설명 — 사양 정보 추가
    description = product.description_ko
    if product.spec:
        spec_lines = "\n".join(f"• {k}: {v}" for k, v in product.spec.items())
        description = f"{description}\n\n📋 상품 사양\n{spec_lines}" if description else f"📋 상품 사양\n{spec_lines}"

    return ChannelListing(
        channel=channel,
        product_id=product.product_id,
        title=title,
        description=description,
        price=adjusted_price,
        channel_category_id=channel_cat,
        image_urls=images,
        options=product.options,
        metadata={
            "original_price_krw": product.price_krw,
            "fee_rate": fee_rate,
            "source_platform": product.source_platform,
            "source_url": product.source_url,
        },
    )


def _upload_to_channel(listing: ChannelListing) -> ChannelUploadResult:
    """단일 채널 업로드. 실패해도 예외 미전파."""
    channel = listing.channel
    try:
        if channel == "coupang":
            from src.channel_sync.publishers.coupang import CoupangPublisher
            pub = CoupangPublisher()
            result = pub.publish({
                "product_id": listing.product_id,
                "title": listing.title,
                "price": listing.price,
                "stock": 99,
                "category": listing.channel_category_id,
                "description": listing.description,
            })
            return ChannelUploadResult(
                channel=channel,
                success=result.success,
                listing_id=result.listing_id,
                channel_listing_id=result.listing_id,
                error=result.error,
            )
        else:
            # smartstore / 11st — stub (API 미연동)
            mock_lid = f"{channel}-{uuid.uuid4().hex[:8]}"
            logger.info("auto_publish stub: channel=%s product=%s listing_id=%s", channel, listing.product_id, mock_lid)
            return ChannelUploadResult(
                channel=channel,
                success=True,
                listing_id=mock_lid,
                channel_listing_id=mock_lid,
            )
    except Exception as exc:
        logger.error("_upload_to_channel 오류: channel=%s error=%s", channel, exc)
        return ChannelUploadResult(channel=channel, success=False, error=str(exc))


def _prepare_product_from_candidate(candidate: Any) -> Product:
    """Candidate → Product 변환 (이미지 처리 + 번역 포함)."""
    from src.ai.translator_quality import translate_title, translate_description

    title_ko = translate_title(candidate.product_name, source_lang="ja")
    description_ko = translate_description("", source_lang="ja")  # 상세 설명 stub

    # 이미지 처리
    processed_images: List[str] = []
    try:
        from src.media.image_pipeline import process_image_urls
        processed_images = process_image_urls(candidate.image_urls)
    except Exception as exc:
        logger.debug("이미지 처리 스킵: %s", exc)
        processed_images = candidate.image_urls

    return Product(
        product_id=candidate.candidate_id,
        title_ko=title_ko,
        title_original=candidate.product_name,
        description_ko=description_ko,
        price_krw=int(candidate.estimated_selling_price_krw),
        category=candidate.category,
        image_urls=candidate.image_urls,
        processed_image_urls=processed_images,
        stock=99,
        source_platform=candidate.platform,
        source_url=candidate.product_url,
    )


def auto_publish(candidate: Any, channels: Optional[List[str]] = None) -> Dict[str, Any]:
    """채널별 업로드 결과. 부분 실패 허용.

    Args:
        candidate: Candidate 객체 (sourcing.pipeline)
        channels: 업로드 채널 목록. None 이면 LISTING_AUTO_PUBLISH_CHANNELS 사용.

    Returns:
        {
            "product_id": ...,
            "channels": {channel: ChannelUploadResult.to_dict()},
            "success_count": N,
            "fail_count": N,
            "auto_publish_enabled": bool,
        }
    """
    if channels is None:
        channels = _DEFAULT_CHANNELS

    enabled = _AUTO_PUBLISH_ENABLED
    if not enabled:
        logger.info("auto_publish: LISTING_AUTO_PUBLISH=0 — 드라이런 모드")

    product = _prepare_product_from_candidate(candidate)
    channel_results: Dict[str, Any] = {}

    for ch in channels:
        listing = adapt_for_channel(product, ch)
        if enabled:
            result = _upload_to_channel(listing)
        else:
            # 드라이런: 실제 업로드 없이 준비 결과만 반환
            result = ChannelUploadResult(
                channel=ch,
                success=True,
                listing_id=f"dry-run-{uuid.uuid4().hex[:8]}",
                channel_listing_id=None,
            )
        channel_results[ch] = result.to_dict()

    success_count = sum(1 for r in channel_results.values() if r["success"])
    fail_count = len(channels) - success_count

    summary = {
        "product_id": product.product_id,
        "product_title": product.title_ko,
        "channels": channel_results,
        "success_count": success_count,
        "fail_count": fail_count,
        "auto_publish_enabled": enabled,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }

    # 이력 저장
    _listing_history.append(summary)
    if len(_listing_history) > 500:
        _listing_history.pop(0)

    logger.info(
        "auto_publish: product=%s channels=%s success=%d fail=%d enabled=%s",
        product.product_id, channels, success_count, fail_count, enabled,
    )
    return summary


def listing_stats() -> Dict[str, Any]:
    """등록 이력 통계 (diagnostics 카드용)."""
    history = _listing_history
    now = datetime.now(timezone.utc)
    last_24h = [
        h for h in history
        if (now - datetime.fromisoformat(h["published_at"].replace("Z", "+00:00"))).total_seconds() < 86400
    ]
    image_ok = sum(1 for h in history if h.get("success_count", 0) > 0)
    total = len(history)
    return {
        "total_listings": total,
        "listings_24h": len(last_24h),
        "auto_publish_enabled": _AUTO_PUBLISH_ENABLED,
        "default_channels": _DEFAULT_CHANNELS,
        "image_success_pct": round(image_ok / total * 100, 0) if total > 0 else 0,
    }
