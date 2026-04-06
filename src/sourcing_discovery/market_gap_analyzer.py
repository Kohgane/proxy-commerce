"""src/sourcing_discovery/market_gap_analyzer.py — 마켓 갭 분석 (Phase 115)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class GapType(str, Enum):
    unserved_demand = 'unserved_demand'
    price_gap = 'price_gap'
    quality_gap = 'quality_gap'
    feature_gap = 'feature_gap'
    availability_gap = 'availability_gap'


@dataclass
class MarketGap:
    gap_id: str
    category: str
    description: str
    gap_type: GapType
    demand_score: float
    supply_score: float
    gap_score: float
    example_products: List[str]
    recommended_action: str
    analyzed_at: datetime


_MOCK_GAPS: List[Dict[str, Any]] = [
    {
        'gap_id': 'gap_001', 'category': '전자기기',
        'description': '국내 시장에서 저가형 노이즈캔슬링 이어폰 공급 부족',
        'gap_type': 'price_gap',
        'demand_score': 85.0, 'supply_score': 35.0,
        'example_products': ['소니 WF-1000XM5 대체품', '저가 ANC 이어폰'],
        'recommended_action': '중국산 저가 ANC 이어폰 소싱 검토',
    },
    {
        'gap_id': 'gap_002', 'category': '전자기기',
        'description': '스마트홈 연동 가능한 저가 IoT 기기 부족',
        'gap_type': 'feature_gap',
        'demand_score': 78.0, 'supply_score': 30.0,
        'example_products': ['스마트 콘센트', '스마트 도어락', 'IoT 온습도계'],
        'recommended_action': '알리바바 스마트홈 IoT 기기 소싱',
    },
    {
        'gap_id': 'gap_003', 'category': '전자기기',
        'description': '포터블 충전 거치대 다기능 제품 미흡',
        'gap_type': 'feature_gap',
        'demand_score': 72.0, 'supply_score': 45.0,
        'example_products': ['3-in-1 무선 충전기', '맥세이프 거치대'],
        'recommended_action': '멀티 기기 무선 충전 제품 소싱 검토',
    },
    {
        'gap_id': 'gap_004', 'category': '뷰티',
        'description': '프리미엄 성분 기반 저가 스킨케어 공백',
        'gap_type': 'price_gap',
        'demand_score': 90.0, 'supply_score': 40.0,
        'example_products': ['레티놀크림', '나이아신아마이드세럼', '펩타이드앰플'],
        'recommended_action': '성분 집중형 중저가 스킨케어 소싱',
    },
    {
        'gap_id': 'gap_005', 'category': '뷰티',
        'description': '남성 전용 스킨케어 라인 부족',
        'gap_type': 'unserved_demand',
        'demand_score': 75.0, 'supply_score': 25.0,
        'example_products': ['남성 올인원 크림', '남성 선크림', '남성 토너'],
        'recommended_action': '남성 뷰티 카테고리 집중 소싱',
    },
    {
        'gap_id': 'gap_006', 'category': '뷰티',
        'description': '클린뷰티(무독성) 제품 공급 부족',
        'gap_type': 'quality_gap',
        'demand_score': 82.0, 'supply_score': 28.0,
        'example_products': ['유기농 선크림', '비건 마스카라', '클린 파운데이션'],
        'recommended_action': '클린뷰티 인증 제품 소싱',
    },
    {
        'gap_id': 'gap_007', 'category': '스포츠',
        'description': '홈트레이닝용 컴팩트 운동기구 수요 미충족',
        'gap_type': 'unserved_demand',
        'demand_score': 88.0, 'supply_score': 42.0,
        'example_products': ['접이식 런닝머신', '미니 사이클', '스마트 줄넘기'],
        'recommended_action': '홈트 소형 운동기구 라인업 확충',
    },
    {
        'gap_id': 'gap_008', 'category': '스포츠',
        'description': '필라테스/요가 전문용품 다양성 부족',
        'gap_type': 'availability_gap',
        'demand_score': 71.0, 'supply_score': 38.0,
        'example_products': ['필라테스 소도구', '요가블록 코르크', '스트랩 세트'],
        'recommended_action': '요가/필라테스 전문 도구 소싱',
    },
    {
        'gap_id': 'gap_009', 'category': '스포츠',
        'description': '시니어 운동용품 전문 라인 공백',
        'gap_type': 'unserved_demand',
        'demand_score': 76.0, 'supply_score': 20.0,
        'example_products': ['시니어 요가매트', '가벼운 아령', '스트레칭 밴드'],
        'recommended_action': '시니어 타겟 운동용품 소싱',
    },
    {
        'gap_id': 'gap_010', 'category': '주방용품',
        'description': '친환경 주방용품 공급 부족',
        'gap_type': 'quality_gap',
        'demand_score': 80.0, 'supply_score': 32.0,
        'example_products': ['대나무 도마', '실리콘 랩', '스테인레스 빨대 세트'],
        'recommended_action': '친환경 소재 주방용품 소싱 강화',
    },
    {
        'gap_id': 'gap_011', 'category': '주방용품',
        'description': '1인 가구용 소형 가전 다양성 부족',
        'gap_type': 'feature_gap',
        'demand_score': 85.0, 'supply_score': 45.0,
        'example_products': ['미니 밥솥', '소형 식기세척기', '1인 에스프레소머신'],
        'recommended_action': '1인 가구 타겟 소형 주방 가전 소싱',
    },
    {
        'gap_id': 'gap_012', 'category': '주방용품',
        'description': '푸드프렙용 전문 도구 공백',
        'gap_type': 'availability_gap',
        'demand_score': 68.0, 'supply_score': 25.0,
        'example_products': ['채소 스파이럴라이저', '만두피 기계', '쿠키커터 세트'],
        'recommended_action': '베이킹/푸드프렙 전문 도구 소싱',
    },
    {
        'gap_id': 'gap_013', 'category': '가구/인테리어',
        'description': '소형 원룸 최적화 수납 가구 부족',
        'gap_type': 'unserved_demand',
        'demand_score': 87.0, 'supply_score': 35.0,
        'example_products': ['벽걸이 수납함', '침대 하부 수납박스', '문뒤 수납'],
        'recommended_action': '원룸/소형 공간 최적화 수납 소싱',
    },
    {
        'gap_id': 'gap_014', 'category': '가구/인테리어',
        'description': '재택근무 환경 최적화 제품 공백',
        'gap_type': 'feature_gap',
        'demand_score': 83.0, 'supply_score': 40.0,
        'example_products': ['높낮이 조절 책상', '모니터 리스트레스트', '집중 조명'],
        'recommended_action': '홈오피스 필수품 라인업 구성',
    },
    {
        'gap_id': 'gap_015', 'category': '가구/인테리어',
        'description': '포스터/아트프린트 인테리어 제품 공백',
        'gap_type': 'availability_gap',
        'demand_score': 65.0, 'supply_score': 30.0,
        'example_products': ['미니멀 포스터 프레임', '아트 캔버스', '인테리어 스티커'],
        'recommended_action': '벽 인테리어 소품 다양성 확보',
    },
    {
        'gap_id': 'gap_016', 'category': '반려동물',
        'description': '스마트 반려동물 관리 기기 공급 부족',
        'gap_type': 'feature_gap',
        'demand_score': 89.0, 'supply_score': 28.0,
        'example_products': ['AI 펫 카메라', '자동 레이저 장난감', '스마트 목욕기'],
        'recommended_action': '스마트 반려동물 용품 소싱 강화',
    },
    {
        'gap_id': 'gap_017', 'category': '반려동물',
        'description': '고양이 전용 프리미엄 식기 공백',
        'gap_type': 'quality_gap',
        'demand_score': 74.0, 'supply_score': 22.0,
        'example_products': ['경사 고양이 식기', '세라믹 물그릇', '자동 급수기'],
        'recommended_action': '고양이 전용 프리미엄 식기 소싱',
    },
    {
        'gap_id': 'gap_018', 'category': '반려동물',
        'description': '천연/유기농 반려동물 간식 공백',
        'gap_type': 'quality_gap',
        'demand_score': 81.0, 'supply_score': 30.0,
        'example_products': ['동결건조 닭가슴살', '유기농 강아지 쿠키', '무첨가 고양이 간식'],
        'recommended_action': '천연 성분 반려동물 간식 소싱',
    },
    {
        'gap_id': 'gap_019', 'category': '건강식품',
        'description': '스포츠 영양제 저가 시장 공백',
        'gap_type': 'price_gap',
        'demand_score': 86.0, 'supply_score': 42.0,
        'example_products': ['저가 단백질 파우더', '실속형 BCAA', '가성비 크레아틴'],
        'recommended_action': '스포츠 영양제 저가 라인 소싱',
    },
    {
        'gap_id': 'gap_020', 'category': '건강식품',
        'description': '여성 전용 건강기능식품 공백',
        'gap_type': 'unserved_demand',
        'demand_score': 84.0, 'supply_score': 35.0,
        'example_products': ['여성 호르몬 지원제', '철분+비타민 복합제', '콜라겐 음료'],
        'recommended_action': '여성 타겟 건강기능식품 소싱',
    },
    {
        'gap_id': 'gap_021', 'category': '건강식품',
        'description': '노화방지(안티에이징) 기능성 식품 공백',
        'gap_type': 'unserved_demand',
        'demand_score': 79.0, 'supply_score': 22.0,
        'example_products': ['NMN 서플리먼트', 'NAD+ 부스터', '레스베라트롤'],
        'recommended_action': '안티에이징 성분 건강기능식품 소싱',
    },
    {
        'gap_id': 'gap_022', 'category': '패션',
        'description': '빅사이즈 전문 트렌디 의류 공백',
        'gap_type': 'unserved_demand',
        'demand_score': 82.0, 'supply_score': 20.0,
        'example_products': ['빅사이즈 오버핏 티셔츠', '빅사이즈 스트릿 패션', '빅사이즈 원피스'],
        'recommended_action': '빅사이즈 트렌디 패션 소싱 강화',
    },
    {
        'gap_id': 'gap_023', 'category': '패션',
        'description': '친환경/지속가능 패션 제품 공백',
        'gap_type': 'quality_gap',
        'demand_score': 77.0, 'supply_score': 18.0,
        'example_products': ['리사이클 소재 티셔츠', '유기농 면 바지', '비건 레더 가방'],
        'recommended_action': '지속가능 패션 브랜드 소싱 검토',
    },
    {
        'gap_id': 'gap_024', 'category': '패션',
        'description': '성인 캐주얼 운동화 가성비 제품 공백',
        'gap_type': 'price_gap',
        'demand_score': 88.0, 'supply_score': 50.0,
        'example_products': ['데일리 운동화', '캐주얼 로퍼', '기능성 슬리퍼'],
        'recommended_action': '가성비 운동화/신발 소싱 확대',
    },
    {
        'gap_id': 'gap_025', 'category': '전자기기',
        'description': '어린이 전용 스마트 학습 기기 공백',
        'gap_type': 'unserved_demand',
        'demand_score': 83.0, 'supply_score': 25.0,
        'example_products': ['어린이 태블릿', '스마트 학습 펜', '코딩 로봇 장난감'],
        'recommended_action': '어린이 교육 스마트 기기 소싱',
    },
    {
        'gap_id': 'gap_026', 'category': '스포츠',
        'description': '아웃도어 캠핑 스포츠 장비 공백',
        'gap_type': 'availability_gap',
        'demand_score': 76.0, 'supply_score': 35.0,
        'example_products': ['경량 텐트', '캠핑 의자', '휴대용 BBQ 그릴'],
        'recommended_action': '캠핑 기어 소싱 라인업 확충',
    },
    {
        'gap_id': 'gap_027', 'category': '주방용품',
        'description': '디저트/베이킹 전문 도구 공백',
        'gap_type': 'availability_gap',
        'demand_score': 72.0, 'supply_score': 28.0,
        'example_products': ['실리콘 케이크몰드', '아이싱 도구 세트', '반죽기'],
        'recommended_action': '홈베이킹 전문 도구 소싱',
    },
    {
        'gap_id': 'gap_028', 'category': '가구/인테리어',
        'description': '감성 캠핑 인테리어 소품 공백',
        'gap_type': 'unserved_demand',
        'demand_score': 69.0, 'supply_score': 22.0,
        'example_products': ['LED 전구 가랜드', '캠핑 랜턴', '야외용 러그'],
        'recommended_action': '캠핑/글램핑 인테리어 소품 소싱',
    },
    {
        'gap_id': 'gap_029', 'category': '반려동물',
        'description': '반려동물 의료/건강 관리 용품 공백',
        'gap_type': 'unserved_demand',
        'demand_score': 85.0, 'supply_score': 20.0,
        'example_products': ['반려동물 혈당 측정기', '치아 관리 용품', '관절 보호 용품'],
        'recommended_action': '반려동물 헬스케어 전문 용품 소싱',
    },
    {
        'gap_id': 'gap_030', 'category': '건강식품',
        'description': '스트레스/수면 개선 기능성 식품 공백',
        'gap_type': 'unserved_demand',
        'demand_score': 87.0, 'supply_score': 30.0,
        'example_products': ['마그네슘 글리시네이트', '멜라토닌 서방형', 'L-테아닌'],
        'recommended_action': '수면/스트레스 관리 건강기능식품 소싱',
    },
    {
        'gap_id': 'gap_031', 'category': '뷰티',
        'description': '더마코스메틱(피부과학) 브랜드 가성비 제품 공백',
        'gap_type': 'price_gap',
        'demand_score': 88.0, 'supply_score': 32.0,
        'example_products': ['센텔라아시아티카 크림', '아토피 케어 로션', '저자극 클렌저'],
        'recommended_action': '더마코스메틱 가성비 라인 소싱',
    },
    {
        'gap_id': 'gap_032', 'category': '전자기기',
        'description': '스마트 수면 트래킹 기기 공백',
        'gap_type': 'feature_gap',
        'demand_score': 78.0, 'supply_score': 18.0,
        'example_products': ['수면 밴드', '스마트 베개 스피커', '수면 분석 앱 연동 기기'],
        'recommended_action': '스마트 수면 관리 기기 소싱',
    },
]


class MarketGapAnalyzer:
    """마켓 갭 분석기."""

    def __init__(self) -> None:
        self._gaps: List[MarketGap] = [
            MarketGap(
                gap_id=g['gap_id'],
                category=g['category'],
                description=g['description'],
                gap_type=GapType(g['gap_type']),
                demand_score=g['demand_score'],
                supply_score=g['supply_score'],
                gap_score=round(g['demand_score'] - g['supply_score'], 1),
                example_products=g['example_products'],
                recommended_action=g['recommended_action'],
                analyzed_at=datetime.now(),
            )
            for g in _MOCK_GAPS
        ]

    def analyze_gaps(self, category: str = None) -> List[MarketGap]:
        """갭 분석."""
        gaps = self._gaps
        if category:
            gaps = [g for g in gaps if g.category == category]
        return sorted(gaps, key=lambda x: x.gap_score, reverse=True)

    def get_top_gaps(self, limit: int = 5) -> List[MarketGap]:
        """상위 갭 조회."""
        return sorted(self._gaps, key=lambda x: x.gap_score, reverse=True)[:limit]

    def get_gap_by_category(self) -> Dict[str, List[MarketGap]]:
        """카테고리별 갭 분류."""
        result: Dict[str, List[MarketGap]] = {}
        for gap in self._gaps:
            result.setdefault(gap.category, []).append(gap)
        return result
