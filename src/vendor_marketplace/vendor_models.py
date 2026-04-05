"""src/vendor_marketplace/vendor_models.py — 멀티벤더 마켓플레이스 데이터 모델 (Phase 98)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class VendorStatus(Enum):
    """판매자 상태 머신."""
    pending = 'pending'               # 신청 접수
    under_review = 'under_review'     # 심사 중
    approved = 'approved'             # 승인됨 (계약/동의 완료 필요)
    active = 'active'                 # 활성 (판매 가능)
    suspended = 'suspended'           # 정지
    deactivated = 'deactivated'       # 비활성화


class VendorTier(Enum):
    """판매자 티어 — 수수료율 및 기능 제한 차등."""
    basic = 'basic'
    standard = 'standard'
    premium = 'premium'
    enterprise = 'enterprise'


# 티어별 기본 수수료율 (%)
TIER_COMMISSION_RATES: Dict[str, float] = {
    VendorTier.basic.value: 15.0,
    VendorTier.standard.value: 12.0,
    VendorTier.premium.value: 10.0,
    VendorTier.enterprise.value: 8.0,   # 협의 기본값
}

# 티어별 상품 등록 수 제한
TIER_PRODUCT_LIMITS: Dict[str, Optional[int]] = {
    VendorTier.basic.value: 50,
    VendorTier.standard.value: 200,
    VendorTier.premium.value: 1000,
    VendorTier.enterprise.value: None,  # 무제한
}


@dataclass
class Vendor:
    """판매자 데이터 모델."""
    vendor_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ''
    email: str = ''
    phone: str = ''
    business_number: str = ''          # 사업자등록번호
    status: VendorStatus = VendorStatus.pending
    tier: VendorTier = VendorTier.basic
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'vendor_id': self.vendor_id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'business_number': self.business_number,
            'status': self.status.value,
            'tier': self.tier.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'metadata': self.metadata,
        }

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


@dataclass
class VendorProfile:
    """판매자 프로필 (상세 정보)."""
    vendor_id: str = ''
    brand_name: str = ''
    logo_url: str = ''
    description: str = ''
    shipping_policy: str = ''
    return_policy: str = ''
    cs_email: str = ''
    cs_phone: str = ''
    bank_name: str = ''
    bank_account: str = ''
    bank_holder: str = ''
    address: str = ''
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            'vendor_id': self.vendor_id,
            'brand_name': self.brand_name,
            'logo_url': self.logo_url,
            'description': self.description,
            'shipping_policy': self.shipping_policy,
            'return_policy': self.return_policy,
            'cs_email': self.cs_email,
            'cs_phone': self.cs_phone,
            'bank_name': self.bank_name,
            'bank_account': self.bank_account,
            'bank_holder': self.bank_holder,
            'address': self.address,
            'updated_at': self.updated_at.isoformat(),
        }


@dataclass
class VendorAgreementRecord:
    """입점 계약서 동의 기록."""
    agreement_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    vendor_id: str = ''
    terms_version: str = '1.0'
    agreed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    required_terms_agreed: bool = False
    optional_terms_agreed: bool = False
    ip_address: str = ''

    def to_dict(self) -> dict:
        return {
            'agreement_id': self.agreement_id,
            'vendor_id': self.vendor_id,
            'terms_version': self.terms_version,
            'agreed_at': self.agreed_at.isoformat(),
            'required_terms_agreed': self.required_terms_agreed,
            'optional_terms_agreed': self.optional_terms_agreed,
            'ip_address': self.ip_address,
        }


@dataclass
class VendorDocument:
    """판매자 제출 서류."""
    doc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    vendor_id: str = ''
    doc_type: str = ''   # business_license, bank_statement, id_card 등
    file_name: str = ''
    file_size: int = 0
    status: str = 'pending'   # pending, verified, rejected
    uploaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    verified_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            'doc_id': self.doc_id,
            'vendor_id': self.vendor_id,
            'doc_type': self.doc_type,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'status': self.status,
            'uploaded_at': self.uploaded_at.isoformat(),
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
        }
