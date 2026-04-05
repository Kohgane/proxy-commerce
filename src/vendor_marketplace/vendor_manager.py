"""src/vendor_marketplace/vendor_manager.py — 판매자 온보딩 관리 (Phase 98)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .vendor_models import (
    Vendor,
    VendorAgreementRecord,
    VendorDocument,
    VendorProfile,
    VendorStatus,
    VendorTier,
)

logger = logging.getLogger(__name__)

# 허용 상태 전환 맵
_VALID_TRANSITIONS: Dict[VendorStatus, List[VendorStatus]] = {
    VendorStatus.pending: [VendorStatus.under_review],
    VendorStatus.under_review: [VendorStatus.approved, VendorStatus.pending],
    VendorStatus.approved: [VendorStatus.active, VendorStatus.pending],
    VendorStatus.active: [VendorStatus.suspended, VendorStatus.deactivated],
    VendorStatus.suspended: [VendorStatus.active, VendorStatus.deactivated],
    VendorStatus.deactivated: [],
}


class VendorVerification:
    """사업자등록번호 유효성 검사 및 본인 인증 (mock)."""

    # 사업자등록번호 형식: 000-00-00000
    _BIZ_NUM_RE = re.compile(r'^\d{3}-\d{2}-\d{5}$')

    def validate_business_number(self, business_number: str) -> bool:
        """사업자등록번호 형식 + checksum 검증 (mock)."""
        if not self._BIZ_NUM_RE.match(business_number):
            return False
        # Mock: 000-00-00000 형식이면 통과 (실제 API 연동 시 교체)
        digits = business_number.replace('-', '')
        return len(digits) == 10

    def verify_identity(self, vendor_id: str, id_number: str) -> dict:
        """본인 인증 (mock)."""
        if not id_number or len(id_number) < 6:
            return {'success': False, 'message': '유효하지 않은 인증 정보'}
        return {
            'success': True,
            'vendor_id': vendor_id,
            'verified_at': datetime.now(timezone.utc).isoformat(),
            'message': '본인 인증 완료 (mock)',
        }

    def simulate_document_upload(
        self, vendor_id: str, doc_type: str, file_name: str, file_size: int
    ) -> VendorDocument:
        """서류 업로드 시뮬레이션."""
        doc = VendorDocument(
            vendor_id=vendor_id,
            doc_type=doc_type,
            file_name=file_name,
            file_size=file_size,
            status='pending',
        )
        return doc


class VendorAgreement:
    """입점 계약서 동의 관리."""

    CURRENT_TERMS_VERSION = '2.0'

    def __init__(self) -> None:
        self._agreements: Dict[str, VendorAgreementRecord] = {}

    def record_agreement(
        self,
        vendor_id: str,
        required: bool,
        optional: bool = False,
        ip_address: str = '',
        terms_version: str = '',
    ) -> VendorAgreementRecord:
        """약관 동의 기록."""
        record = VendorAgreementRecord(
            vendor_id=vendor_id,
            terms_version=terms_version or self.CURRENT_TERMS_VERSION,
            required_terms_agreed=required,
            optional_terms_agreed=optional,
            ip_address=ip_address,
        )
        self._agreements[vendor_id] = record
        return record

    def get_agreement(self, vendor_id: str) -> Optional[VendorAgreementRecord]:
        return self._agreements.get(vendor_id)

    def has_valid_agreement(self, vendor_id: str) -> bool:
        rec = self._agreements.get(vendor_id)
        if rec is None:
            return False
        return rec.required_terms_agreed


class VendorOnboardingManager:
    """판매자 신청 접수, 서류 검증, 심사 승인/거절, 상태 전환."""

    def __init__(self) -> None:
        self._vendors: Dict[str, Vendor] = {}
        self._documents: Dict[str, List[VendorDocument]] = {}  # vendor_id → docs
        self._verification = VendorVerification()
        self._agreement = VendorAgreement()

    # ── 신청 ──────────────────────────────────────────────────────────────

    def apply(
        self,
        name: str,
        email: str,
        phone: str,
        business_number: str,
        tier: str = 'basic',
        metadata: dict | None = None,
    ) -> Vendor:
        """판매자 신청 접수."""
        if not self._verification.validate_business_number(business_number):
            raise ValueError(f'유효하지 않은 사업자등록번호: {business_number}')
        vendor = Vendor(
            name=name,
            email=email,
            phone=phone,
            business_number=business_number,
            tier=VendorTier(tier),
            metadata=metadata or {},
        )
        self._vendors[vendor.vendor_id] = vendor
        logger.info('판매자 신청 접수: %s (%s)', vendor.name, vendor.vendor_id)
        return vendor

    # ── 상태 전환 ─────────────────────────────────────────────────────────

    def transition(self, vendor_id: str, new_status: VendorStatus, reason: str = '') -> Vendor:
        """상태 전환 (유효성 검사 포함)."""
        vendor = self._get_or_raise(vendor_id)
        allowed = _VALID_TRANSITIONS.get(vendor.status, [])
        if new_status not in allowed:
            raise ValueError(
                f'상태 전환 불가: {vendor.status.value} → {new_status.value}'
            )
        vendor.status = new_status
        vendor.touch()
        if reason:
            vendor.metadata['last_status_reason'] = reason
        logger.info('판매자 상태 전환: %s → %s (%s)', vendor_id, new_status.value, reason)
        return vendor

    def submit_for_review(self, vendor_id: str) -> Vendor:
        return self.transition(vendor_id, VendorStatus.under_review)

    def approve(self, vendor_id: str, reason: str = '') -> Vendor:
        return self.transition(vendor_id, VendorStatus.approved, reason)

    def reject(self, vendor_id: str, reason: str = '') -> Vendor:
        """거절: under_review → pending (재신청 가능)."""
        return self.transition(vendor_id, VendorStatus.pending, reason)

    def activate(self, vendor_id: str) -> Vendor:
        """승인 상태에서 활성화."""
        return self.transition(vendor_id, VendorStatus.active)

    def suspend(self, vendor_id: str, reason: str = '') -> Vendor:
        return self.transition(vendor_id, VendorStatus.suspended, reason)

    def deactivate(self, vendor_id: str, reason: str = '') -> Vendor:
        return self.transition(vendor_id, VendorStatus.deactivated, reason)

    # ── 서류 관리 ─────────────────────────────────────────────────────────

    def upload_document(
        self, vendor_id: str, doc_type: str, file_name: str, file_size: int = 0
    ) -> VendorDocument:
        """서류 업로드."""
        self._get_or_raise(vendor_id)
        doc = self._verification.simulate_document_upload(
            vendor_id, doc_type, file_name, file_size
        )
        self._documents.setdefault(vendor_id, []).append(doc)
        return doc

    def verify_document(self, vendor_id: str, doc_id: str) -> VendorDocument:
        """서류 검증 (mock)."""
        docs = self._documents.get(vendor_id, [])
        for doc in docs:
            if doc.doc_id == doc_id:
                doc.status = 'verified'
                doc.verified_at = datetime.now(timezone.utc)
                return doc
        raise KeyError(f'문서 없음: {doc_id}')

    def get_documents(self, vendor_id: str) -> List[VendorDocument]:
        return self._documents.get(vendor_id, [])

    # ── 약관 동의 ─────────────────────────────────────────────────────────

    def record_agreement(
        self,
        vendor_id: str,
        required: bool,
        optional: bool = False,
        ip_address: str = '',
    ) -> VendorAgreementRecord:
        self._get_or_raise(vendor_id)
        return self._agreement.record_agreement(vendor_id, required, optional, ip_address)

    def has_valid_agreement(self, vendor_id: str) -> bool:
        return self._agreement.has_valid_agreement(vendor_id)

    # ── 조회 ──────────────────────────────────────────────────────────────

    def get_vendor(self, vendor_id: str) -> Optional[Vendor]:
        return self._vendors.get(vendor_id)

    def list_vendors(
        self,
        status: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> List[Vendor]:
        vendors = list(self._vendors.values())
        if status:
            vendors = [v for v in vendors if v.status.value == status]
        if tier:
            vendors = [v for v in vendors if v.tier.value == tier]
        return vendors

    def _get_or_raise(self, vendor_id: str) -> Vendor:
        vendor = self._vendors.get(vendor_id)
        if vendor is None:
            raise KeyError(f'판매자 없음: {vendor_id}')
        return vendor


class VendorProfileManager:
    """판매자 프로필 CRUD."""

    def __init__(self) -> None:
        self._profiles: Dict[str, VendorProfile] = {}

    def create_or_update(self, vendor_id: str, **kwargs) -> VendorProfile:
        profile = self._profiles.get(vendor_id) or VendorProfile(vendor_id=vendor_id)
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        profile.updated_at = datetime.now(timezone.utc)
        self._profiles[vendor_id] = profile
        return profile

    def get(self, vendor_id: str) -> Optional[VendorProfile]:
        return self._profiles.get(vendor_id)

    def delete(self, vendor_id: str) -> bool:
        if vendor_id in self._profiles:
            del self._profiles[vendor_id]
            return True
        return False

    def list_profiles(self) -> List[VendorProfile]:
        return list(self._profiles.values())
