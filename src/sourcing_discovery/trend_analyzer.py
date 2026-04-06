"""src/sourcing_discovery/trend_analyzer.py — 트렌드 기반 키워드 분석 (Phase 115)."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TrendDirection(str, Enum):
    rising = 'rising'
    stable = 'stable'
    declining = 'declining'
    seasonal = 'seasonal'
    explosive = 'explosive'


class CompetitionLevel(str, Enum):
    low = 'low'
    medium = 'medium'
    high = 'high'
    saturated = 'saturated'


@dataclass
class TrendData:
    trend_id: str
    keyword: str
    category: str
    platform: str
    search_volume: int
    growth_rate: float
    seasonality_score: float
    competition_level: CompetitionLevel
    trend_direction: TrendDirection
    peak_month: int
    data_points: List[int]
    analyzed_at: datetime


_MOCK_KEYWORDS: List[Dict[str, Any]] = [
    # 전자기기
    {'keyword': '무선이어폰', 'category': '전자기기', 'search_volume': 95000, 'growth_rate': 32.5, 'seasonality_score': 0.3, 'competition_level': 'high', 'trend_direction': 'rising', 'peak_month': 12},
    {'keyword': '블루투스스피커', 'category': '전자기기', 'search_volume': 72000, 'growth_rate': 18.2, 'seasonality_score': 0.4, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 12},
    {'keyword': '스마트워치', 'category': '전자기기', 'search_volume': 88000, 'growth_rate': 45.1, 'seasonality_score': 0.35, 'competition_level': 'high', 'trend_direction': 'explosive', 'peak_month': 11},
    {'keyword': '보조배터리', 'category': '전자기기', 'search_volume': 65000, 'growth_rate': 12.0, 'seasonality_score': 0.2, 'competition_level': 'saturated', 'trend_direction': 'stable', 'peak_month': 5},
    {'keyword': '태블릿거치대', 'category': '전자기기', 'search_volume': 42000, 'growth_rate': 28.7, 'seasonality_score': 0.15, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 3},
    {'keyword': '노이즈캔슬링헤드폰', 'category': '전자기기', 'search_volume': 38000, 'growth_rate': 55.3, 'seasonality_score': 0.3, 'competition_level': 'medium', 'trend_direction': 'explosive', 'peak_month': 12},
    {'keyword': '게이밍마우스', 'category': '전자기기', 'search_volume': 55000, 'growth_rate': 22.1, 'seasonality_score': 0.2, 'competition_level': 'high', 'trend_direction': 'rising', 'peak_month': 1},
    {'keyword': '기계식키보드', 'category': '전자기기', 'search_volume': 48000, 'growth_rate': 19.4, 'seasonality_score': 0.18, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 12},
    {'keyword': '웹캠', 'category': '전자기기', 'search_volume': 32000, 'growth_rate': 38.9, 'seasonality_score': 0.1, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 3},
    {'keyword': '스마트홈허브', 'category': '전자기기', 'search_volume': 25000, 'growth_rate': 67.2, 'seasonality_score': 0.25, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 12},
    {'keyword': 'USB허브', 'category': '전자기기', 'search_volume': 58000, 'growth_rate': 14.5, 'seasonality_score': 0.12, 'competition_level': 'saturated', 'trend_direction': 'stable', 'peak_month': 9},
    {'keyword': '무선충전기', 'category': '전자기기', 'search_volume': 70000, 'growth_rate': 25.8, 'seasonality_score': 0.3, 'competition_level': 'high', 'trend_direction': 'rising', 'peak_month': 12},
    {'keyword': '스마트전구', 'category': '전자기기', 'search_volume': 29000, 'growth_rate': 43.6, 'seasonality_score': 0.2, 'competition_level': 'low', 'trend_direction': 'rising', 'peak_month': 10},
    {'keyword': '포터블모니터', 'category': '전자기기', 'search_volume': 33000, 'growth_rate': 72.4, 'seasonality_score': 0.15, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 9},
    {'keyword': '홈CCTV', 'category': '전자기기', 'search_volume': 44000, 'growth_rate': 31.0, 'seasonality_score': 0.1, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 6},
    {'keyword': '전동킥보드', 'category': '전자기기', 'search_volume': 52000, 'growth_rate': 8.5, 'seasonality_score': 0.7, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 4},
    {'keyword': '드론', 'category': '전자기기', 'search_volume': 61000, 'growth_rate': 15.3, 'seasonality_score': 0.5, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 5},
    {'keyword': '미니프로젝터', 'category': '전자기기', 'search_volume': 36000, 'growth_rate': 48.2, 'seasonality_score': 0.25, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 10},
    {'keyword': '스마트체중계', 'category': '전자기기', 'search_volume': 27000, 'growth_rate': 22.7, 'seasonality_score': 0.6, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 1},
    {'keyword': '전기면도기', 'category': '전자기기', 'search_volume': 43000, 'growth_rate': 9.8, 'seasonality_score': 0.3, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 12},
    {'keyword': '전동칫솔', 'category': '전자기기', 'search_volume': 39000, 'growth_rate': 18.6, 'seasonality_score': 0.25, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 12},
    {'keyword': '에어프라이어', 'category': '전자기기', 'search_volume': 82000, 'growth_rate': 5.2, 'seasonality_score': 0.2, 'competition_level': 'saturated', 'trend_direction': 'declining', 'peak_month': 12},
    {'keyword': '공기청정기', 'category': '전자기기', 'search_volume': 77000, 'growth_rate': 11.4, 'seasonality_score': 0.55, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 3},
    {'keyword': '로봇청소기', 'category': '전자기기', 'search_volume': 68000, 'growth_rate': 35.7, 'seasonality_score': 0.2, 'competition_level': 'high', 'trend_direction': 'rising', 'peak_month': 12},
    {'keyword': '스팀다리미', 'category': '전자기기', 'search_volume': 34000, 'growth_rate': 7.1, 'seasonality_score': 0.3, 'competition_level': 'medium', 'trend_direction': 'stable', 'peak_month': 12},
    # 패션
    {'keyword': '오버핏티셔츠', 'category': '패션', 'search_volume': 89000, 'growth_rate': 42.3, 'seasonality_score': 0.65, 'competition_level': 'high', 'trend_direction': 'explosive', 'peak_month': 5},
    {'keyword': '와이드팬츠', 'category': '패션', 'search_volume': 75000, 'growth_rate': 28.9, 'seasonality_score': 0.6, 'competition_level': 'high', 'trend_direction': 'rising', 'peak_month': 4},
    {'keyword': '크롭자켓', 'category': '패션', 'search_volume': 53000, 'growth_rate': 61.5, 'seasonality_score': 0.7, 'competition_level': 'medium', 'trend_direction': 'explosive', 'peak_month': 9},
    {'keyword': '버킷햇', 'category': '패션', 'search_volume': 48000, 'growth_rate': 35.2, 'seasonality_score': 0.75, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 6},
    {'keyword': '스니커즈', 'category': '패션', 'search_volume': 96000, 'growth_rate': 12.8, 'seasonality_score': 0.4, 'competition_level': 'saturated', 'trend_direction': 'stable', 'peak_month': 4},
    {'keyword': '카고바지', 'category': '패션', 'search_volume': 67000, 'growth_rate': 78.4, 'seasonality_score': 0.5, 'competition_level': 'medium', 'trend_direction': 'explosive', 'peak_month': 9},
    {'keyword': '반팔니트', 'category': '패션', 'search_volume': 44000, 'growth_rate': 22.6, 'seasonality_score': 0.8, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 6},
    {'keyword': '가죽크로스백', 'category': '패션', 'search_volume': 38000, 'growth_rate': 17.3, 'seasonality_score': 0.3, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 10},
    {'keyword': '워커부츠', 'category': '패션', 'search_volume': 55000, 'growth_rate': 19.8, 'seasonality_score': 0.7, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 10},
    {'keyword': '숄더백', 'category': '패션', 'search_volume': 71000, 'growth_rate': 14.5, 'seasonality_score': 0.25, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 9},
    {'keyword': '맨투맨', 'category': '패션', 'search_volume': 93000, 'growth_rate': 8.2, 'seasonality_score': 0.55, 'competition_level': 'saturated', 'trend_direction': 'stable', 'peak_month': 10},
    {'keyword': '후리스집업', 'category': '패션', 'search_volume': 62000, 'growth_rate': 45.7, 'seasonality_score': 0.75, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 10},
    {'keyword': '데님자켓', 'category': '패션', 'search_volume': 57000, 'growth_rate': 11.3, 'seasonality_score': 0.65, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 9},
    {'keyword': '반바지', 'category': '패션', 'search_volume': 84000, 'growth_rate': 6.5, 'seasonality_score': 0.9, 'competition_level': 'saturated', 'trend_direction': 'seasonal', 'peak_month': 6},
    {'keyword': '선글라스', 'category': '패션', 'search_volume': 79000, 'growth_rate': 23.1, 'seasonality_score': 0.8, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 6},
    {'keyword': '스카프', 'category': '패션', 'search_volume': 41000, 'growth_rate': 16.4, 'seasonality_score': 0.7, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 11},
    # 뷰티
    {'keyword': '선크림', 'category': '뷰티', 'search_volume': 110000, 'growth_rate': 28.5, 'seasonality_score': 0.75, 'competition_level': 'saturated', 'trend_direction': 'seasonal', 'peak_month': 5},
    {'keyword': '비타민C세럼', 'category': '뷰티', 'search_volume': 68000, 'growth_rate': 52.3, 'seasonality_score': 0.2, 'competition_level': 'medium', 'trend_direction': 'explosive', 'peak_month': 3},
    {'keyword': '히알루론산크림', 'category': '뷰티', 'search_volume': 55000, 'growth_rate': 39.8, 'seasonality_score': 0.3, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 11},
    {'keyword': '클렌징오일', 'category': '뷰티', 'search_volume': 72000, 'growth_rate': 15.7, 'seasonality_score': 0.2, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 12},
    {'keyword': '토너패드', 'category': '뷰티', 'search_volume': 84000, 'growth_rate': 67.4, 'seasonality_score': 0.2, 'competition_level': 'medium', 'trend_direction': 'explosive', 'peak_month': 7},
    {'keyword': '에센스', 'category': '뷰티', 'search_volume': 91000, 'growth_rate': 18.2, 'seasonality_score': 0.25, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 10},
    {'keyword': '마스크팩', 'category': '뷰티', 'search_volume': 98000, 'growth_rate': 9.5, 'seasonality_score': 0.3, 'competition_level': 'saturated', 'trend_direction': 'stable', 'peak_month': 10},
    {'keyword': '립글로스', 'category': '뷰티', 'search_volume': 47000, 'growth_rate': 34.6, 'seasonality_score': 0.4, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 12},
    {'keyword': '쿠션팩트', 'category': '뷰티', 'search_volume': 78000, 'growth_rate': 12.3, 'seasonality_score': 0.35, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 5},
    {'keyword': '아이브로우펜슬', 'category': '뷰티', 'search_volume': 53000, 'growth_rate': 21.8, 'seasonality_score': 0.15, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 3},
    {'keyword': '두피에센스', 'category': '뷰티', 'search_volume': 31000, 'growth_rate': 58.9, 'seasonality_score': 0.2, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 9},
    {'keyword': '콜라겐크림', 'category': '뷰티', 'search_volume': 43000, 'growth_rate': 44.2, 'seasonality_score': 0.25, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 11},
    {'keyword': '레티놀앰플', 'category': '뷰티', 'search_volume': 37000, 'growth_rate': 75.6, 'seasonality_score': 0.15, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 10},
    {'keyword': 'BB크림', 'category': '뷰티', 'search_volume': 66000, 'growth_rate': 5.8, 'seasonality_score': 0.3, 'competition_level': 'saturated', 'trend_direction': 'declining', 'peak_month': 5},
    {'keyword': '젤네일키트', 'category': '뷰티', 'search_volume': 29000, 'growth_rate': 48.7, 'seasonality_score': 0.5, 'competition_level': 'low', 'trend_direction': 'rising', 'peak_month': 5},
    # 스포츠
    {'keyword': '요가매트', 'category': '스포츠', 'search_volume': 76000, 'growth_rate': 23.4, 'seasonality_score': 0.6, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 1},
    {'keyword': '폼롤러', 'category': '스포츠', 'search_volume': 52000, 'growth_rate': 17.8, 'seasonality_score': 0.5, 'competition_level': 'medium', 'trend_direction': 'stable', 'peak_month': 1},
    {'keyword': '운동복세트', 'category': '스포츠', 'search_volume': 68000, 'growth_rate': 38.5, 'seasonality_score': 0.65, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 1},
    {'keyword': '덤벨세트', 'category': '스포츠', 'search_volume': 45000, 'growth_rate': 29.3, 'seasonality_score': 0.6, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 1},
    {'keyword': '러닝화', 'category': '스포츠', 'search_volume': 87000, 'growth_rate': 15.6, 'seasonality_score': 0.55, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 4},
    {'keyword': '필라테스링', 'category': '스포츠', 'search_volume': 24000, 'growth_rate': 62.4, 'seasonality_score': 0.5, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 1},
    {'keyword': '수영복', 'category': '스포츠', 'search_volume': 73000, 'growth_rate': 8.9, 'seasonality_score': 0.9, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 6},
    {'keyword': '등산화', 'category': '스포츠', 'search_volume': 61000, 'growth_rate': 19.2, 'seasonality_score': 0.7, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 9},
    {'keyword': '자전거헬멧', 'category': '스포츠', 'search_volume': 38000, 'growth_rate': 31.7, 'seasonality_score': 0.65, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 4},
    {'keyword': '테니스라켓', 'category': '스포츠', 'search_volume': 33000, 'growth_rate': 55.8, 'seasonality_score': 0.6, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 5},
    {'keyword': '골프장갑', 'category': '스포츠', 'search_volume': 29000, 'growth_rate': 14.3, 'seasonality_score': 0.65, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 4},
    {'keyword': '배드민턴라켓', 'category': '스포츠', 'search_volume': 41000, 'growth_rate': 22.5, 'seasonality_score': 0.6, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 5},
    {'keyword': '스쿼트밴드', 'category': '스포츠', 'search_volume': 18000, 'growth_rate': 71.3, 'seasonality_score': 0.5, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 1},
    {'keyword': '등산스틱', 'category': '스포츠', 'search_volume': 27000, 'growth_rate': 12.8, 'seasonality_score': 0.7, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 9},
    # 주방용품
    {'keyword': '유리밀폐용기', 'category': '주방용품', 'search_volume': 58000, 'growth_rate': 24.6, 'seasonality_score': 0.2, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 1},
    {'keyword': '스텐냄비', 'category': '주방용품', 'search_volume': 46000, 'growth_rate': 11.3, 'seasonality_score': 0.25, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 12},
    {'keyword': '세라믹프라이팬', 'category': '주방용품', 'search_volume': 71000, 'growth_rate': 35.8, 'seasonality_score': 0.3, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 12},
    {'keyword': '미니오븐', 'category': '주방용품', 'search_volume': 39000, 'growth_rate': 18.7, 'seasonality_score': 0.4, 'competition_level': 'medium', 'trend_direction': 'stable', 'peak_month': 12},
    {'keyword': '전기포트', 'category': '주방용품', 'search_volume': 53000, 'growth_rate': 8.4, 'seasonality_score': 0.2, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 12},
    {'keyword': '커피그라인더', 'category': '주방용품', 'search_volume': 32000, 'growth_rate': 47.2, 'seasonality_score': 0.15, 'competition_level': 'low', 'trend_direction': 'rising', 'peak_month': 12},
    {'keyword': '에스프레소머신', 'category': '주방용품', 'search_volume': 28000, 'growth_rate': 53.6, 'seasonality_score': 0.2, 'competition_level': 'medium', 'trend_direction': 'explosive', 'peak_month': 12},
    {'keyword': '착즙기', 'category': '주방용품', 'search_volume': 22000, 'growth_rate': 29.8, 'seasonality_score': 0.5, 'competition_level': 'low', 'trend_direction': 'seasonal', 'peak_month': 1},
    {'keyword': '실리콘주방도구', 'category': '주방용품', 'search_volume': 44000, 'growth_rate': 21.5, 'seasonality_score': 0.15, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 12},
    {'keyword': '수납바구니', 'category': '주방용품', 'search_volume': 61000, 'growth_rate': 16.9, 'seasonality_score': 0.35, 'competition_level': 'medium', 'trend_direction': 'stable', 'peak_month': 3},
    {'keyword': '진공포장기', 'category': '주방용품', 'search_volume': 19000, 'growth_rate': 42.7, 'seasonality_score': 0.3, 'competition_level': 'low', 'trend_direction': 'rising', 'peak_month': 1},
    # 가구/인테리어
    {'keyword': '책상조명', 'category': '가구/인테리어', 'search_volume': 49000, 'growth_rate': 36.4, 'seasonality_score': 0.2, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 3},
    {'keyword': '캐노피침대', 'category': '가구/인테리어', 'search_volume': 22000, 'growth_rate': 58.3, 'seasonality_score': 0.3, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 3},
    {'keyword': '폴딩테이블', 'category': '가구/인테리어', 'search_volume': 34000, 'growth_rate': 27.9, 'seasonality_score': 0.15, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 3},
    {'keyword': '행거', 'category': '가구/인테리어', 'search_volume': 67000, 'growth_rate': 14.6, 'seasonality_score': 0.25, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 3},
    {'keyword': '벽선반', 'category': '가구/인테리어', 'search_volume': 41000, 'growth_rate': 22.3, 'seasonality_score': 0.2, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 3},
    {'keyword': '커튼', 'category': '가구/인테리어', 'search_volume': 82000, 'growth_rate': 9.7, 'seasonality_score': 0.3, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 3},
    {'keyword': '러그', 'category': '가구/인테리어', 'search_volume': 55000, 'growth_rate': 31.5, 'seasonality_score': 0.3, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 9},
    {'keyword': '오피스체어', 'category': '가구/인테리어', 'search_volume': 78000, 'growth_rate': 42.8, 'seasonality_score': 0.15, 'competition_level': 'high', 'trend_direction': 'rising', 'peak_month': 3},
    {'keyword': '모니터암', 'category': '가구/인테리어', 'search_volume': 38000, 'growth_rate': 49.6, 'seasonality_score': 0.1, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 3},
    {'keyword': '미니화분', 'category': '가구/인테리어', 'search_volume': 31000, 'growth_rate': 25.4, 'seasonality_score': 0.5, 'competition_level': 'low', 'trend_direction': 'seasonal', 'peak_month': 4},
    {'keyword': '아크릴선반', 'category': '가구/인테리어', 'search_volume': 17000, 'growth_rate': 68.9, 'seasonality_score': 0.15, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 3},
    # 반려동물
    {'keyword': '강아지옷', 'category': '반려동물', 'search_volume': 63000, 'growth_rate': 28.7, 'seasonality_score': 0.6, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 11},
    {'keyword': '고양이터널', 'category': '반려동물', 'search_volume': 35000, 'growth_rate': 45.2, 'seasonality_score': 0.2, 'competition_level': 'low', 'trend_direction': 'rising', 'peak_month': 12},
    {'keyword': '자동급식기', 'category': '반려동물', 'search_volume': 48000, 'growth_rate': 52.8, 'seasonality_score': 0.15, 'competition_level': 'medium', 'trend_direction': 'explosive', 'peak_month': 12},
    {'keyword': '펫카메라', 'category': '반려동물', 'search_volume': 27000, 'growth_rate': 61.3, 'seasonality_score': 0.1, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 12},
    {'keyword': '반려동물유모차', 'category': '반려동물', 'search_volume': 21000, 'growth_rate': 38.6, 'seasonality_score': 0.5, 'competition_level': 'low', 'trend_direction': 'seasonal', 'peak_month': 4},
    {'keyword': '고양이스크래처', 'category': '반려동물', 'search_volume': 42000, 'growth_rate': 19.4, 'seasonality_score': 0.15, 'competition_level': 'medium', 'trend_direction': 'stable', 'peak_month': 12},
    {'keyword': '강아지간식', 'category': '반려동물', 'search_volume': 76000, 'growth_rate': 14.8, 'seasonality_score': 0.2, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 12},
    {'keyword': '반려동물영양제', 'category': '반려동물', 'search_volume': 39000, 'growth_rate': 43.7, 'seasonality_score': 0.15, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 1},
    {'keyword': '자동화장실', 'category': '반려동물', 'search_volume': 18000, 'growth_rate': 82.4, 'seasonality_score': 0.1, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 12},
    {'keyword': '펫드라이어', 'category': '반려동물', 'search_volume': 25000, 'growth_rate': 36.9, 'seasonality_score': 0.2, 'competition_level': 'low', 'trend_direction': 'rising', 'peak_month': 11},
    # 건강식품
    {'keyword': '유산균', 'category': '건강식품', 'search_volume': 120000, 'growth_rate': 22.4, 'seasonality_score': 0.2, 'competition_level': 'saturated', 'trend_direction': 'stable', 'peak_month': 1},
    {'keyword': '비타민D', 'category': '건강식품', 'search_volume': 98000, 'growth_rate': 31.7, 'seasonality_score': 0.4, 'competition_level': 'high', 'trend_direction': 'rising', 'peak_month': 11},
    {'keyword': '오메가3', 'category': '건강식품', 'search_volume': 87000, 'growth_rate': 15.3, 'seasonality_score': 0.2, 'competition_level': 'high', 'trend_direction': 'stable', 'peak_month': 1},
    {'keyword': '마그네슘', 'category': '건강식품', 'search_volume': 64000, 'growth_rate': 42.8, 'seasonality_score': 0.15, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 7},
    {'keyword': '콜라겐파우더', 'category': '건강식품', 'search_volume': 51000, 'growth_rate': 58.4, 'seasonality_score': 0.2, 'competition_level': 'medium', 'trend_direction': 'explosive', 'peak_month': 3},
    {'keyword': '단백질쉐이크', 'category': '건강식품', 'search_volume': 73000, 'growth_rate': 26.5, 'seasonality_score': 0.55, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 1},
    {'keyword': 'BCAA', 'category': '건강식품', 'search_volume': 38000, 'growth_rate': 19.7, 'seasonality_score': 0.5, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 1},
    {'keyword': '글루타치온', 'category': '건강식품', 'search_volume': 29000, 'growth_rate': 72.3, 'seasonality_score': 0.15, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 5},
    {'keyword': '루테인', 'category': '건강식품', 'search_volume': 44000, 'growth_rate': 28.9, 'seasonality_score': 0.15, 'competition_level': 'medium', 'trend_direction': 'rising', 'peak_month': 3},
    {'keyword': '밀크씨슬', 'category': '건강식품', 'search_volume': 36000, 'growth_rate': 21.4, 'seasonality_score': 0.2, 'competition_level': 'medium', 'trend_direction': 'stable', 'peak_month': 1},
    {'keyword': 'NAD+', 'category': '건강식품', 'search_volume': 12000, 'growth_rate': 94.7, 'seasonality_score': 0.1, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 1},
    {'keyword': '아쉬와간다', 'category': '건강식품', 'search_volume': 18000, 'growth_rate': 85.6, 'seasonality_score': 0.1, 'competition_level': 'low', 'trend_direction': 'explosive', 'peak_month': 7},
    {'keyword': '비타민C고함량', 'category': '건강식품', 'search_volume': 52000, 'growth_rate': 33.8, 'seasonality_score': 0.5, 'competition_level': 'high', 'trend_direction': 'seasonal', 'peak_month': 11},
    {'keyword': '아연', 'category': '건강식품', 'search_volume': 47000, 'growth_rate': 25.1, 'seasonality_score': 0.4, 'competition_level': 'medium', 'trend_direction': 'seasonal', 'peak_month': 11},
    {'keyword': '흑마늘', 'category': '건강식품', 'search_volume': 34000, 'growth_rate': 18.6, 'seasonality_score': 0.3, 'competition_level': 'medium', 'trend_direction': 'stable', 'peak_month': 1},
]

_PLATFORMS = ['naver', 'coupang', 'amazon', 'taobao']


class TrendAnalyzer:
    """트렌드 기반 키워드 분석기."""

    def __init__(self) -> None:
        self._data: List[Dict[str, Any]] = _MOCK_KEYWORDS

    def _make_trend_data(self, item: Dict[str, Any], platform: str) -> TrendData:
        import hashlib
        trend_id = hashlib.md5(f"{item['keyword']}:{platform}".encode()).hexdigest()[:12]
        base_volume = item['search_volume']
        data_points = [
            max(0, int(base_volume * (0.7 + random.uniform(-0.2, 0.5))))
            for _ in range(12)
        ]
        return TrendData(
            trend_id=trend_id,
            keyword=item['keyword'],
            category=item['category'],
            platform=platform,
            search_volume=base_volume,
            growth_rate=item['growth_rate'],
            seasonality_score=item['seasonality_score'],
            competition_level=CompetitionLevel(item['competition_level']),
            trend_direction=TrendDirection(item['trend_direction']),
            peak_month=item['peak_month'],
            data_points=data_points,
            analyzed_at=datetime.now(),
        )

    def analyze_keyword_trend(self, keyword: str, platform: str = 'naver') -> TrendData:
        """키워드 트렌드 분석."""
        for item in self._data:
            if item['keyword'] == keyword:
                return self._make_trend_data(item, platform)
        # 키워드가 없으면 기본값 반환
        fallback = {
            'keyword': keyword,
            'category': '기타',
            'search_volume': random.randint(1000, 50000),
            'growth_rate': random.uniform(-10, 50),
            'seasonality_score': random.uniform(0.1, 0.8),
            'competition_level': 'medium',
            'trend_direction': 'stable',
            'peak_month': random.randint(1, 12),
        }
        return self._make_trend_data(fallback, platform)

    def analyze_category_trends(self, category: str = None, platform: str = 'naver') -> List[TrendData]:
        """카테고리별 트렌드 분석."""
        items = self._data
        if category:
            items = [i for i in items if i['category'] == category]
        return [self._make_trend_data(item, platform) for item in items]

    def get_rising_trends(self, limit: int = 10, platform: str = None) -> List[TrendData]:
        """상승 트렌드 상위 목록."""
        p = platform or 'naver'
        rising = [
            i for i in self._data
            if i['trend_direction'] in ('rising', 'explosive')
        ]
        rising.sort(key=lambda x: x['growth_rate'], reverse=True)
        return [self._make_trend_data(item, p) for item in rising[:limit]]

    def get_seasonal_opportunities(self, month: int = None) -> List[TrendData]:
        """시즌별 기회 분석."""
        import datetime as dt
        target_month = month if month is not None else dt.datetime.now().month
        if isinstance(target_month, str):
            target_month = int(target_month)
        seasonal = [
            i for i in self._data
            if i['trend_direction'] == 'seasonal' and i['peak_month'] == target_month
        ]
        if not seasonal:
            seasonal = [i for i in self._data if i['trend_direction'] == 'seasonal'][:5]
        return [self._make_trend_data(item, 'naver') for item in seasonal]

    def get_trend_summary(self) -> Dict[str, Any]:
        """트렌드 전체 요약."""
        direction_counts: Dict[str, int] = {}
        for item in self._data:
            d = item['trend_direction']
            direction_counts[d] = direction_counts.get(d, 0) + 1

        category_counts: Dict[str, int] = {}
        for item in self._data:
            c = item['category']
            category_counts[c] = category_counts.get(c, 0) + 1

        top_explosive = sorted(
            [i for i in self._data if i['trend_direction'] == 'explosive'],
            key=lambda x: x['growth_rate'],
            reverse=True,
        )[:5]

        return {
            'total_keywords': len(self._data),
            'direction_distribution': direction_counts,
            'category_distribution': category_counts,
            'avg_growth_rate': sum(i['growth_rate'] for i in self._data) / len(self._data),
            'top_explosive_keywords': [i['keyword'] for i in top_explosive],
            'platforms_tracked': _PLATFORMS,
        }
