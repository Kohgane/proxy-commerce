"""src/sourcing_discovery/discovery_alerts.py — 발굴 알림 서비스 (Phase 115)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    high_score_opportunity = 'high_score_opportunity'
    trending_category = 'trending_category'
    competitor_new_product = 'competitor_new_product'
    price_drop_source = 'price_drop_source'
    seasonal_reminder = 'seasonal_reminder'
    supplier_new_product = 'supplier_new_product'


@dataclass
class DiscoveryAlert:
    alert_id: str
    alert_type: AlertType
    severity: str
    message: str
    opportunity_id: Optional[str]
    details: Dict[str, Any]
    created_at: datetime
    acknowledged: bool = False


_MOCK_ALERTS_DATA = [
    {
        'alert_type': 'high_score_opportunity',
        'severity': 'high',
        'message': '고점수 소싱 기회 발견: 자동화장실 (점수: 92.3)',
        'opportunity_id': 'opp_001',
        'details': {'product': '자동화장실', 'score': 92.3, 'platform': 'taobao'},
    },
    {
        'alert_type': 'trending_category',
        'severity': 'medium',
        'message': '건강식품 카테고리 급상승 트렌드 감지 (성장률: +85.6%)',
        'opportunity_id': None,
        'details': {'category': '건강식품', 'growth_rate': 85.6, 'top_keyword': '아쉬와간다'},
    },
    {
        'alert_type': 'high_score_opportunity',
        'severity': 'high',
        'message': '고점수 소싱 기회: NAD+ 영양제 (점수: 89.5)',
        'opportunity_id': 'opp_002',
        'details': {'product': 'NAD+', 'score': 89.5, 'platform': 'alibaba'},
    },
    {
        'alert_type': 'price_drop_source',
        'severity': 'medium',
        'message': '1688 무선이어폰 소싱가 15% 하락 감지',
        'opportunity_id': None,
        'details': {'platform': '1688', 'product': '무선이어폰', 'drop_rate': 15.0},
    },
    {
        'alert_type': 'seasonal_reminder',
        'severity': 'low',
        'message': '겨울 시즌 핫 키워드 준비: 강아지옷, 후리스집업, 공기청정기',
        'opportunity_id': None,
        'details': {'season': '겨울', 'keywords': ['강아지옷', '후리스집업', '공기청정기']},
    },
    {
        'alert_type': 'competitor_new_product',
        'severity': 'medium',
        'message': '경쟁사 신규 카테고리 진입 감지: 반려동물 스마트기기',
        'opportunity_id': None,
        'details': {'competitor': '경쟁셀러A', 'category': '반려동물 스마트기기'},
    },
    {
        'alert_type': 'supplier_new_product',
        'severity': 'low',
        'message': 'Alibaba TechGlobal 신규 상품 등록: 포터블 프로젝터 2024',
        'opportunity_id': None,
        'details': {'supplier': 'Alibaba TechGlobal Co.', 'product': '포터블 프로젝터 2024'},
    },
    {
        'alert_type': 'high_score_opportunity',
        'severity': 'high',
        'message': '고점수 소싱 기회: 레티놀앰플 (점수: 88.7)',
        'opportunity_id': 'opp_003',
        'details': {'product': '레티놀앰플', 'score': 88.7, 'platform': 'taobao'},
    },
    {
        'alert_type': 'trending_category',
        'severity': 'medium',
        'message': '뷰티 카테고리 폭발적 성장 감지 (성장률: +75.6%)',
        'opportunity_id': None,
        'details': {'category': '뷰티', 'growth_rate': 75.6, 'top_keyword': '레티놀앰플'},
    },
    {
        'alert_type': 'price_drop_source',
        'severity': 'high',
        'message': '타오바오 고양이자동화장실 소싱가 22% 대폭 하락',
        'opportunity_id': None,
        'details': {'platform': 'taobao', 'product': '고양이자동화장실', 'drop_rate': 22.0},
    },
    {
        'alert_type': 'seasonal_reminder',
        'severity': 'medium',
        'message': '여름 시즌 준비: 선크림, 수영복, 버킷햇 소싱 시작',
        'opportunity_id': None,
        'details': {'season': '여름', 'keywords': ['선크림', '수영복', '버킷햇']},
    },
    {
        'alert_type': 'high_score_opportunity',
        'severity': 'high',
        'message': '고점수 소싱 기회: 포터블모니터 (점수: 87.2)',
        'opportunity_id': 'opp_004',
        'details': {'product': '포터블모니터', 'score': 87.2, 'platform': 'alibaba'},
    },
    {
        'alert_type': 'competitor_new_product',
        'severity': 'low',
        'message': '경쟁사 뷰티 카테고리 신규 브랜드 론칭 감지',
        'opportunity_id': None,
        'details': {'competitor': '경쟁셀러B', 'category': '클린뷰티'},
    },
    {
        'alert_type': 'supplier_new_product',
        'severity': 'medium',
        'message': 'Alibaba PetCare 신규 스마트 펫케어 라인 출시',
        'opportunity_id': None,
        'details': {'supplier': 'Alibaba PetCare Solutions', 'product': '스마트 펫케어 라인'},
    },
    {
        'alert_type': 'trending_category',
        'severity': 'high',
        'message': '전자기기 IoT 카테고리 급부상 (성장률: +67.2%)',
        'opportunity_id': None,
        'details': {'category': '전자기기', 'growth_rate': 67.2, 'top_keyword': '스마트홈허브'},
    },
    {
        'alert_type': 'high_score_opportunity',
        'severity': 'medium',
        'message': '주목할 소싱 기회: 스쿼트밴드 (점수: 85.4)',
        'opportunity_id': 'opp_005',
        'details': {'product': '스쿼트밴드', 'score': 85.4, 'platform': '1688'},
    },
    {
        'alert_type': 'price_drop_source',
        'severity': 'medium',
        'message': '1688 스포츠용품 도매 전체 가격 10% 인하',
        'opportunity_id': None,
        'details': {'platform': '1688', 'category': '스포츠', 'drop_rate': 10.0},
    },
    {
        'alert_type': 'seasonal_reminder',
        'severity': 'low',
        'message': '신학기 시즌: 오피스체어, 책상조명, 모니터암 수요 예상',
        'opportunity_id': None,
        'details': {'season': '신학기', 'keywords': ['오피스체어', '책상조명', '모니터암']},
    },
    {
        'alert_type': 'supplier_new_product',
        'severity': 'low',
        'message': 'Alibaba HealthPro 글루타치온 신제품 출시 (함량 50% 향상)',
        'opportunity_id': None,
        'details': {'supplier': 'Alibaba HealthPro Trading', 'product': '글루타치온 프리미엄'},
    },
    {
        'alert_type': 'competitor_new_product',
        'severity': 'medium',
        'message': '경쟁사 건강식품 카테고리 대규모 확장 감지',
        'opportunity_id': None,
        'details': {'competitor': '경쟁셀러C', 'category': '건강기능식품'},
    },
]


class DiscoveryAlertService:
    """발굴 알림 서비스."""

    def __init__(self) -> None:
        self._alerts: List[DiscoveryAlert] = []
        for data in _MOCK_ALERTS_DATA:
            alert = DiscoveryAlert(
                alert_id=str(uuid.uuid4())[:12],
                alert_type=AlertType(data['alert_type']),
                severity=data['severity'],
                message=data['message'],
                opportunity_id=data.get('opportunity_id'),
                details=data.get('details', {}),
                created_at=datetime.now(),
                acknowledged=False,
            )
            self._alerts.append(alert)

    def check_alerts(self) -> List[DiscoveryAlert]:
        """미확인 알림 조회."""
        return [a for a in self._alerts if not a.acknowledged]

    def get_alerts(
        self,
        severity: str = None,
        alert_type: str = None,
        acknowledged: bool = None,
    ) -> List[DiscoveryAlert]:
        """알림 목록 조회."""
        alerts = self._alerts[:]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if alert_type:
            alerts = [a for a in alerts if a.alert_type.value == alert_type]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        return alerts

    def acknowledge_alert(self, alert_id: str) -> DiscoveryAlert:
        """알림 확인 처리."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return alert
        raise ValueError(f'알림을 찾을 수 없습니다: {alert_id}')

    def get_alert_summary(self) -> Dict[str, Any]:
        """알림 요약."""
        unacked = [a for a in self._alerts if not a.acknowledged]
        severity_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {}
        for alert in self._alerts:
            severity_counts[alert.severity] = severity_counts.get(alert.severity, 0) + 1
            type_counts[alert.alert_type.value] = type_counts.get(alert.alert_type.value, 0) + 1

        return {
            'total_alerts': len(self._alerts),
            'unacknowledged': len(unacked),
            'severity_distribution': severity_counts,
            'type_distribution': type_counts,
            'high_priority_count': sum(1 for a in self._alerts if a.severity == 'high' and not a.acknowledged),
        }
