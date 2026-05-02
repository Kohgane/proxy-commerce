"""src/returns_automation/models.py — Phase 118: 반품/교환 자동화 데이터 모델."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


class ReturnReasonCategory(str, Enum):
    """반품/교환 사유 분류."""
    defective = 'defective'                    # 상품 불량
    damaged_in_transit = 'damaged_in_transit'  # 배송 중 파손
    wrong_item = 'wrong_item'                  # 잘못된 상품 발송
    size_mismatch = 'size_mismatch'            # 사이즈 불일치
    change_of_mind = 'change_of_mind'          # 단순 변심
    not_as_described = 'not_as_described'      # 설명과 다름
    late_delivery = 'late_delivery'            # 배송 지연
    other = 'other'                            # 기타


class ReturnClassification(str, Enum):
    """자동 분류 결과."""
    auto_approve = 'auto_approve'    # 자동 승인
    manual_review = 'manual_review'  # 수동 검토 필요
    auto_reject = 'auto_reject'      # 자동 거절
    dispute = 'dispute'              # 분쟁 처리


class ReturnStatus(str, Enum):
    """반품/교환 진행 상태 (상태 머신)."""
    requested = 'requested'                  # 요청 접수
    classified = 'classified'                # 분류 완료
    approved = 'approved'                    # 승인
    rejected = 'rejected'                    # 거절
    disputed = 'disputed'                    # 분쟁 처리 중
    pickup_scheduled = 'pickup_scheduled'    # 회수 픽업 예약
    in_return_transit = 'in_return_transit'  # 반품 운송 중
    received = 'received'                    # 반품 수령 완료
    inspected = 'inspected'                  # 검수 완료
    refunded = 'refunded'                    # 환불 완료
    exchanged = 'exchanged'                  # 교환 완료
    partially_refunded = 'partially_refunded'  # 부분 환불 완료


@dataclass
class ReturnItem:
    """반품 요청 상품 정보."""
    sku: str
    product_name: str
    quantity: int
    unit_price: Decimal
    order_item_id: str = ''


@dataclass
class ReturnDecision:
    """반품 처리 결정."""
    decision: str                                     # approved / rejected / manual_review
    refund_amount: Decimal = Decimal('0')             # 환불 금액
    restocking_fee: Decimal = Decimal('0')            # 재입고 수수료
    shipping_fee_borne_by: str = 'customer'           # 반품 배송비 부담 주체 (customer/seller)
    notes: str = ''                                   # 처리 메모


@dataclass
class AutoReturnRequest:
    """자동 반품 요청 모델."""
    order_id: str
    user_id: str
    items: List[ReturnItem]
    reason_code: ReturnReasonCategory
    reason_text: str
    # 기본값이 있는 필드
    request_id: str = field(default_factory=lambda: f'RET-{str(uuid4())[:8].upper()}')
    photos: List[str] = field(default_factory=list)   # 사진 URL 목록
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: ReturnStatus = ReturnStatus.requested
    classification: Optional[ReturnClassification] = None
    decision: Optional[ReturnDecision] = None
    waybill_no: str = ''                              # 회수 운송장 번호
    carrier: str = ''                                 # 회수 택배사
    inspection_grade: str = ''                        # 검수 등급 (A/B/C/D)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """직렬화."""
        return {
            'request_id': self.request_id,
            'order_id': self.order_id,
            'user_id': self.user_id,
            'items': [
                {
                    'sku': it.sku,
                    'product_name': it.product_name,
                    'quantity': it.quantity,
                    'unit_price': str(it.unit_price),
                    'order_item_id': it.order_item_id,
                }
                for it in self.items
            ],
            'reason_code': self.reason_code.value if isinstance(self.reason_code, ReturnReasonCategory) else self.reason_code,
            'reason_text': self.reason_text,
            'photos': self.photos,
            'requested_at': self.requested_at,
            'status': self.status.value if isinstance(self.status, ReturnStatus) else self.status,
            'classification': self.classification.value if self.classification else None,
            'decision': {
                'decision': self.decision.decision,
                'refund_amount': str(self.decision.refund_amount),
                'restocking_fee': str(self.decision.restocking_fee),
                'shipping_fee_borne_by': self.decision.shipping_fee_borne_by,
                'notes': self.decision.notes,
            } if self.decision else None,
            'waybill_no': self.waybill_no,
            'carrier': self.carrier,
            'inspection_grade': self.inspection_grade,
            'metadata': self.metadata,
        }


@dataclass
class ExchangeRequest(AutoReturnRequest):
    """교환 요청 모델 (AutoReturnRequest 확장)."""
    target_sku: str = ''      # 교환 대상 SKU
    target_option: str = ''   # 교환 대상 옵션 (사이즈/색상 등)

    def to_dict(self) -> dict:
        """직렬화 (교환 전용 필드 포함)."""
        d = super().to_dict()
        d['target_sku'] = self.target_sku
        d['target_option'] = self.target_option
        d['request_type'] = 'exchange'
        return d
