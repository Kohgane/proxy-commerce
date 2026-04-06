"""src/china_marketplace/seller_verification.py — 셀러 검증 서비스 (Phase 104)."""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class VerificationStatus(str, Enum):
    unverified = 'unverified'
    pending = 'pending'
    verified = 'verified'
    rejected = 'rejected'
    blacklisted = 'blacklisted'
    whitelisted = 'whitelisted'


@dataclass
class SellerProfile:
    seller_id: str
    name: str
    marketplace: str
    rating: float
    sales_count: int
    years_active: float
    verification_status: VerificationStatus = VerificationStatus.unverified
    categories: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    response_rate: float = 0.95
    return_rate: float = 0.02
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verified_at: Optional[str] = None
    notes: str = ''

    def to_dict(self) -> Dict:
        return {
            'seller_id': self.seller_id,
            'name': self.name,
            'marketplace': self.marketplace,
            'rating': self.rating,
            'sales_count': self.sales_count,
            'years_active': self.years_active,
            'verification_status': self.verification_status.value,
            'categories': self.categories,
            'certifications': self.certifications,
            'response_rate': self.response_rate,
            'return_rate': self.return_rate,
            'created_at': self.created_at,
            'verified_at': self.verified_at,
            'notes': self.notes,
        }


@dataclass
class SellerScore:
    seller_id: str
    reliability: float  # 0~100
    quality: float
    shipping_speed: float
    communication: float
    overall: float
    recommendation: str  # 'approved' | 'caution' | 'rejected'

    def to_dict(self) -> Dict:
        return {
            'seller_id': self.seller_id,
            'reliability': self.reliability,
            'quality': self.quality,
            'shipping_speed': self.shipping_speed,
            'communication': self.communication,
            'overall': self.overall,
            'recommendation': self.recommendation,
        }


class SellerVerificationService:
    """셀러 신뢰도 종합 평가 서비스."""

    def __init__(self):
        self._profiles: Dict[str, SellerProfile] = {}
        self._blacklist: Set[str] = set()
        self._whitelist: Set[str] = set()

    # ── 셀러 프로필 ──────────────────────────────────────────────────────────

    def register_seller(
        self,
        seller_id: str,
        name: str,
        marketplace: str,
        rating: float,
        sales_count: int,
        years_active: float,
        categories: Optional[List[str]] = None,
    ) -> SellerProfile:
        profile = SellerProfile(
            seller_id=seller_id,
            name=name,
            marketplace=marketplace,
            rating=rating,
            sales_count=sales_count,
            years_active=years_active,
            categories=categories or [],
        )
        self._profiles[seller_id] = profile
        return profile

    def get_seller(self, seller_id: str) -> Optional[SellerProfile]:
        return self._profiles.get(seller_id)

    def list_sellers(self, marketplace: Optional[str] = None) -> List[SellerProfile]:
        sellers = list(self._profiles.values())
        if marketplace:
            sellers = [s for s in sellers if s.marketplace == marketplace]
        return sellers

    # ── 셀러 검증 ────────────────────────────────────────────────────────────

    def verify_seller(self, seller_id: str) -> SellerScore:
        """셀러 신뢰도 종합 평가 (mock)."""
        if seller_id in self._blacklist:
            profile = self._profiles.get(seller_id)
            return SellerScore(
                seller_id=seller_id,
                reliability=0.0,
                quality=0.0,
                shipping_speed=0.0,
                communication=0.0,
                overall=0.0,
                recommendation='rejected',
            )

        profile = self._profiles.get(seller_id)
        if profile:
            reliability = min(100, profile.rating * 18 + profile.years_active * 2)
            quality = min(100, profile.rating * 20)
            shipping_speed = round(random.uniform(60, 95), 1)
            communication = min(100, profile.response_rate * 100)
        else:
            # 미등록 셀러 — mock 점수
            reliability = round(random.uniform(50, 90), 1)
            quality = round(random.uniform(60, 90), 1)
            shipping_speed = round(random.uniform(60, 90), 1)
            communication = round(random.uniform(70, 95), 1)

        overall = round((reliability * 0.35 + quality * 0.30 + shipping_speed * 0.20 + communication * 0.15), 1)

        if overall >= 75:
            recommendation = 'approved'
        elif overall >= 50:
            recommendation = 'caution'
        else:
            recommendation = 'rejected'

        score = SellerScore(
            seller_id=seller_id,
            reliability=round(reliability, 1),
            quality=round(quality, 1),
            shipping_speed=round(shipping_speed, 1),
            communication=round(communication, 1),
            overall=overall,
            recommendation=recommendation,
        )

        # 프로필 상태 업데이트
        if seller_id in self._profiles:
            p = self._profiles[seller_id]
            if overall >= 75:
                p.verification_status = VerificationStatus.verified
            elif overall < 40:
                p.verification_status = VerificationStatus.rejected
            else:
                p.verification_status = VerificationStatus.pending
            p.verified_at = datetime.now(timezone.utc).isoformat()

        return score

    # ── 블랙리스트 ───────────────────────────────────────────────────────────

    def add_to_blacklist(self, seller_id: str, reason: str = '') -> None:
        self._blacklist.add(seller_id)
        if seller_id in self._profiles:
            self._profiles[seller_id].verification_status = VerificationStatus.blacklisted
            self._profiles[seller_id].notes = reason
        logger.warning("블랙리스트 추가: %s (사유: %s)", seller_id, reason)

    def remove_from_blacklist(self, seller_id: str) -> None:
        self._blacklist.discard(seller_id)
        if seller_id in self._profiles:
            self._profiles[seller_id].verification_status = VerificationStatus.unverified

    def get_blacklist(self) -> List[str]:
        return list(self._blacklist)

    def is_blacklisted(self, seller_id: str) -> bool:
        return seller_id in self._blacklist

    # ── 화이트리스트 ─────────────────────────────────────────────────────────

    def add_to_whitelist(self, seller_id: str) -> None:
        self._whitelist.add(seller_id)
        if seller_id in self._profiles:
            self._profiles[seller_id].verification_status = VerificationStatus.whitelisted
        logger.info("화이트리스트 추가: %s", seller_id)

    def remove_from_whitelist(self, seller_id: str) -> None:
        self._whitelist.discard(seller_id)

    def get_whitelist(self) -> List[str]:
        return list(self._whitelist)

    def is_whitelisted(self, seller_id: str) -> bool:
        return seller_id in self._whitelist

    def get_stats(self) -> Dict:
        sellers = list(self._profiles.values())
        by_status: Dict[str, int] = {}
        for s in sellers:
            by_status[s.verification_status.value] = by_status.get(s.verification_status.value, 0) + 1
        return {
            'total': len(sellers),
            'blacklisted': len(self._blacklist),
            'whitelisted': len(self._whitelist),
            'by_status': by_status,
        }
