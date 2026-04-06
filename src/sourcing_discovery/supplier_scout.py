"""src/sourcing_discovery/supplier_scout.py — 공급사 탐색 (Phase 115)."""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CandidateStatus(str, Enum):
    scouted = 'scouted'
    contacting = 'contacting'
    evaluating = 'evaluating'
    approved = 'approved'
    rejected = 'rejected'


@dataclass
class SupplierCandidate:
    candidate_id: str
    supplier_name: str
    platform: str
    location: str
    product_categories: List[str]
    min_order_quantity: int
    avg_price_level: str
    estimated_reliability: float
    response_rate: float
    sample_products: List[str]
    contact_info: Dict[str, str]
    scouted_at: datetime
    status: CandidateStatus


_SUPPLIER_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    'taobao': [
        {
            'supplier_name': '타오바오 전자기기 전문점A',
            'location': '중국 광저우',
            'product_categories': ['전자기기', '스마트기기'],
            'min_order_quantity': 10,
            'avg_price_level': '저가',
            'estimated_reliability': 88.5,
            'response_rate': 92.0,
            'sample_products': ['무선이어폰', '스마트워치밴드', '포터블충전기'],
        },
        {
            'supplier_name': '타오바오 뷰티 전문샵B',
            'location': '중국 상하이',
            'product_categories': ['뷰티', '스킨케어'],
            'min_order_quantity': 20,
            'avg_price_level': '중저가',
            'estimated_reliability': 85.2,
            'response_rate': 88.0,
            'sample_products': ['토너패드', '세럼', '마스크팩'],
        },
        {
            'supplier_name': '타오바오 반려동물 전문C',
            'location': '중국 선전',
            'product_categories': ['반려동물'],
            'min_order_quantity': 15,
            'avg_price_level': '중가',
            'estimated_reliability': 82.0,
            'response_rate': 85.5,
            'sample_products': ['자동급식기', '고양이터널', '강아지장난감'],
        },
        {
            'supplier_name': '타오바오 패션잡화D',
            'location': '중국 항저우',
            'product_categories': ['패션', '잡화'],
            'min_order_quantity': 30,
            'avg_price_level': '저가',
            'estimated_reliability': 79.5,
            'response_rate': 80.0,
            'sample_products': ['카고바지', '크롭자켓', '버킷햇'],
        },
        {
            'supplier_name': '타오바오 주방용품E',
            'location': '중국 베이징',
            'product_categories': ['주방용품', '생활용품'],
            'min_order_quantity': 25,
            'avg_price_level': '중저가',
            'estimated_reliability': 87.3,
            'response_rate': 91.0,
            'sample_products': ['세라믹프라이팬', '실리콘도구세트', '유리밀폐용기'],
        },
    ],
    '1688': [
        {
            'supplier_name': '1688 전자부품 도매F',
            'location': '중국 선전',
            'product_categories': ['전자기기', '부품'],
            'min_order_quantity': 50,
            'avg_price_level': '최저가',
            'estimated_reliability': 83.0,
            'response_rate': 78.0,
            'sample_products': ['이어폰 부품', 'USB 케이블', '충전 모듈'],
        },
        {
            'supplier_name': '1688 스포츠용품 도매G',
            'location': '중국 의우',
            'product_categories': ['스포츠', '아웃도어'],
            'min_order_quantity': 100,
            'avg_price_level': '최저가',
            'estimated_reliability': 80.5,
            'response_rate': 75.0,
            'sample_products': ['요가매트', '운동복', '폼롤러'],
        },
        {
            'supplier_name': '1688 건강식품 도매H',
            'location': '중국 상하이',
            'product_categories': ['건강식품', '영양제'],
            'min_order_quantity': 200,
            'avg_price_level': '저가',
            'estimated_reliability': 76.0,
            'response_rate': 72.0,
            'sample_products': ['콜라겐파우더', '유산균', '비타민C'],
        },
        {
            'supplier_name': '1688 가구인테리어 도매I',
            'location': '중국 포산',
            'product_categories': ['가구', '인테리어'],
            'min_order_quantity': 30,
            'avg_price_level': '저가',
            'estimated_reliability': 84.5,
            'response_rate': 82.0,
            'sample_products': ['오피스체어', '수납선반', '러그'],
        },
    ],
    'alibaba': [
        {
            'supplier_name': 'Alibaba TechGlobal Co.',
            'location': '중국 선전',
            'product_categories': ['전자기기', '스마트기기', 'IoT'],
            'min_order_quantity': 100,
            'avg_price_level': '중저가',
            'estimated_reliability': 91.0,
            'response_rate': 94.0,
            'sample_products': ['포터블모니터', '스마트홈허브', '웹캠'],
        },
        {
            'supplier_name': 'Alibaba HealthPro Trading',
            'location': '중국 광저우',
            'product_categories': ['건강식품', '뷰티', '의약외품'],
            'min_order_quantity': 500,
            'avg_price_level': '중가',
            'estimated_reliability': 89.5,
            'response_rate': 91.5,
            'sample_products': ['글루타치온', '레티놀앰플', '오메가3'],
        },
        {
            'supplier_name': 'Alibaba SportsPeak International',
            'location': '중국 의우',
            'product_categories': ['스포츠', '아웃도어', '캠핑'],
            'min_order_quantity': 200,
            'avg_price_level': '중저가',
            'estimated_reliability': 87.0,
            'response_rate': 89.0,
            'sample_products': ['테니스라켓', '필라테스링', '등산스틱'],
        },
        {
            'supplier_name': 'Alibaba PetCare Solutions',
            'location': '중국 선전',
            'product_categories': ['반려동물', '펫케어'],
            'min_order_quantity': 50,
            'avg_price_level': '중가',
            'estimated_reliability': 85.5,
            'response_rate': 87.0,
            'sample_products': ['자동화장실', '펫카메라', '자동급식기'],
        },
        {
            'supplier_name': 'Alibaba HomeFurnish Group',
            'location': '중국 포산',
            'product_categories': ['가구', '인테리어', '생활용품'],
            'min_order_quantity': 50,
            'avg_price_level': '중가',
            'estimated_reliability': 88.0,
            'response_rate': 90.0,
            'sample_products': ['오피스체어', '높낮이조절책상', '모니터암'],
        },
    ],
    'amazon': [
        {
            'supplier_name': 'Amazon US Electronics Wholesaler',
            'location': '미국 캘리포니아',
            'product_categories': ['전자기기', '컴퓨터주변기기'],
            'min_order_quantity': 5,
            'avg_price_level': '고가',
            'estimated_reliability': 95.0,
            'response_rate': 97.0,
            'sample_products': ['게이밍마우스', '기계식키보드', '웹캠'],
        },
        {
            'supplier_name': 'Amazon US Beauty Distributor',
            'location': '미국 뉴욕',
            'product_categories': ['뷰티', '퍼스널케어'],
            'min_order_quantity': 10,
            'avg_price_level': '고가',
            'estimated_reliability': 93.0,
            'response_rate': 95.5,
            'sample_products': ['비타민C세럼', '레티놀크림', '클렌징밤'],
        },
        {
            'supplier_name': 'Amazon JP Sports Supplier',
            'location': '일본 도쿄',
            'product_categories': ['스포츠', '아웃도어'],
            'min_order_quantity': 10,
            'avg_price_level': '중고가',
            'estimated_reliability': 94.5,
            'response_rate': 96.0,
            'sample_products': ['러닝화', '압박양말', '스포츠타월'],
        },
    ],
}


class SupplierScout:
    """공급사 탐색기."""

    def __init__(self) -> None:
        self._candidates: Dict[str, SupplierCandidate] = {}

    def scout_suppliers(
        self,
        category: str = None,
        platform: str = None,
        region: str = None,
    ) -> List[SupplierCandidate]:
        """공급사 탐색."""
        platforms = [platform] if platform else list(_SUPPLIER_TEMPLATES.keys())
        new_candidates: List[SupplierCandidate] = []

        for p in platforms:
            templates = _SUPPLIER_TEMPLATES.get(p, [])
            if category:
                templates = [t for t in templates if category in t['product_categories']]
            count = min(len(templates), random.randint(3, 5))
            selected = random.sample(templates, min(count, len(templates)))

            for tmpl in selected:
                if region and region not in tmpl['location']:
                    continue
                cid = str(uuid.uuid4())[:12]
                candidate = SupplierCandidate(
                    candidate_id=cid,
                    supplier_name=tmpl['supplier_name'],
                    platform=p,
                    location=tmpl['location'],
                    product_categories=tmpl['product_categories'],
                    min_order_quantity=tmpl['min_order_quantity'],
                    avg_price_level=tmpl['avg_price_level'],
                    estimated_reliability=tmpl['estimated_reliability'],
                    response_rate=tmpl['response_rate'],
                    sample_products=tmpl['sample_products'],
                    contact_info={
                        'email': f'contact@{p}-supplier.com',
                        'wechat': f'supplier_{cid[:6]}',
                    },
                    scouted_at=datetime.now(),
                    status=CandidateStatus.scouted,
                )
                self._candidates[cid] = candidate
                new_candidates.append(candidate)

        return new_candidates

    def evaluate_supplier(self, candidate_id: str) -> Dict[str, Any]:
        """공급사 평가."""
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise ValueError(f'후보 공급사를 찾을 수 없습니다: {candidate_id}')
        candidate.status = CandidateStatus.evaluating
        return {
            'candidate_id': candidate_id,
            'status': candidate.status.value,
            'evaluation': {
                'reliability_score': candidate.estimated_reliability,
                'response_score': candidate.response_rate,
                'price_competitiveness': 90 if candidate.avg_price_level in ('최저가', '저가') else 70,
                'product_variety': len(candidate.sample_products) * 20,
                'overall_score': round(
                    (candidate.estimated_reliability + candidate.response_rate) / 2, 1
                ),
            },
            'recommendation': '승인 권장' if candidate.estimated_reliability >= 85 else '추가 검토 필요',
            'evaluated_at': datetime.now().isoformat(),
        }

    def get_candidates(
        self,
        status: str = None,
        platform: str = None,
    ) -> List[SupplierCandidate]:
        """후보 공급사 목록 조회."""
        candidates = list(self._candidates.values())
        if status:
            candidates = [c for c in candidates if c.status.value == status]
        if platform:
            candidates = [c for c in candidates if c.platform == platform]
        return candidates

    def approve_supplier(self, candidate_id: str) -> SupplierCandidate:
        """공급사 승인."""
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise ValueError(f'후보 공급사를 찾을 수 없습니다: {candidate_id}')
        candidate.status = CandidateStatus.approved
        return candidate

    def reject_supplier(self, candidate_id: str, reason: str = '') -> SupplierCandidate:
        """공급사 거절."""
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise ValueError(f'후보 공급사를 찾을 수 없습니다: {candidate_id}')
        candidate.status = CandidateStatus.rejected
        return candidate
