"""src/live_chat/auto_reply.py — 자동 응답 서비스 (Phase 107)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── FAQ 카테고리 ──────────────────────────────────────────────────────────────

FAQ_CATEGORIES = ['배송조회', '환불문의', '주문상태', '가격문의', '기타']


@dataclass
class FAQEntry:
    faq_id: str
    keywords: List[str]
    question: str
    answer: str
    category: str = '기타'
    hit_count: int = 0

    def to_dict(self) -> dict:
        return {
            'faq_id': self.faq_id,
            'keywords': self.keywords,
            'question': self.question,
            'answer': self.answer,
            'category': self.category,
            'hit_count': self.hit_count,
        }


@dataclass
class QuickReply:
    label: str
    value: str

    def to_dict(self) -> dict:
        return {'label': self.label, 'value': self.value}


# ── 기본 FAQ 데이터 ────────────────────────────────────────────────────────────

_DEFAULT_FAQS: List[FAQEntry] = [
    FAQEntry(
        faq_id='faq-001',
        keywords=['배송', '배달', '언제', '도착', '배송조회'],
        question='배송은 얼마나 걸리나요?',
        answer='국내 배송은 보통 2-3 영업일 소요됩니다. 배송조회는 마이페이지 > 주문내역에서 확인하실 수 있습니다.',
        category='배송조회',
    ),
    FAQEntry(
        faq_id='faq-002',
        keywords=['환불', '반품', '취소', '교환'],
        question='환불/반품 신청은 어떻게 하나요?',
        answer='상품 수령 후 7일 이내에 마이페이지 > 주문내역에서 환불/반품 신청이 가능합니다.',
        category='환불문의',
    ),
    FAQEntry(
        faq_id='faq-003',
        keywords=['주문', '주문상태', '확인', '처리'],
        question='주문 상태를 어떻게 확인하나요?',
        answer='마이페이지 > 주문내역에서 실시간으로 주문 처리 상태를 확인하실 수 있습니다.',
        category='주문상태',
    ),
    FAQEntry(
        faq_id='faq-004',
        keywords=['가격', '할인', '쿠폰', '비용'],
        question='가격 문의는 어떻게 하나요?',
        answer='상품 상세 페이지에서 정확한 가격을 확인하실 수 있습니다. 추가 할인은 이벤트 페이지를 참고해주세요.',
        category='가격문의',
    ),
    FAQEntry(
        faq_id='faq-005',
        keywords=['운송장', '송장', '추적번호'],
        question='운송장 번호는 어디서 확인하나요?',
        answer='배송 시작 후 마이페이지 > 주문내역에서 운송장 번호를 확인하실 수 있습니다.',
        category='배송조회',
    ),
]


class AutoReplyService:
    """FAQ 기반 자동 응답 서비스."""

    # 영업 시간 (기본값)
    BUSINESS_HOURS = {'start': 9, 'end': 18}  # 09:00 ~ 18:00

    def __init__(self, business_hours: Optional[Dict] = None):
        self._faqs: Dict[str, FAQEntry] = {f.faq_id: f for f in _DEFAULT_FAQS}
        self._hours = business_hours or self.BUSINESS_HOURS

    # ── FAQ 관리 ────────────────────────────────────────────────────────────

    def add_faq(self, faq: FAQEntry) -> FAQEntry:
        self._faqs[faq.faq_id] = faq
        logger.info("FAQ 추가: %s (%s)", faq.faq_id, faq.question[:30])
        return faq

    def get_faq(self, faq_id: str) -> Optional[FAQEntry]:
        return self._faqs.get(faq_id)

    def list_faqs(self, category: Optional[str] = None) -> List[FAQEntry]:
        faqs = list(self._faqs.values())
        if category:
            faqs = [f for f in faqs if f.category == category]
        return faqs

    # ── 자동 응답 ────────────────────────────────────────────────────────────

    def get_reply(
        self, message: str
    ) -> Tuple[Optional[FAQEntry], List[QuickReply], bool]:
        """메시지에 대한 자동 응답 조회.

        Returns:
            (faq, quick_replies, needs_agent)
            - faq: 매칭된 FAQ (없으면 None)
            - quick_replies: 빠른 응답 버튼 목록
            - needs_agent: 상담원 연결 필요 여부
        """
        if not self.is_business_hours():
            faq = FAQEntry(
                faq_id='off-hours',
                keywords=[],
                question='영업 시간 외',
                answer=(
                    '현재 영업 시간이 아닙니다. '
                    f"영업 시간은 {self._hours['start']}:00 ~ {self._hours['end']}:00입니다. "
                    '문의 내용은 기록되어 영업 시간 후 처리됩니다.'
                ),
                category='기타',
            )
            return faq, [], False

        faq, score = self._match_faq(message)
        if faq is not None and score > 0:
            faq.hit_count += 1
            quick_replies = self._build_quick_replies(faq.category)
            return faq, quick_replies, False

        # 매칭 실패 → 상담원 연결
        quick_replies = [
            QuickReply('상담원 연결', 'connect_agent'),
            QuickReply('다른 문의', 'other'),
        ]
        return None, quick_replies, True

    def is_business_hours(self, now: Optional[datetime] = None) -> bool:
        if now is None:
            now = datetime.now(tz=timezone.utc)
        return self._hours['start'] <= now.hour < self._hours['end']

    def get_categories(self) -> List[str]:
        return list(FAQ_CATEGORIES)

    def get_stats(self) -> dict:
        faqs = list(self._faqs.values())
        total_hits = sum(f.hit_count for f in faqs)
        by_category: Dict[str, int] = {}
        for f in faqs:
            by_category[f.category] = by_category.get(f.category, 0) + 1
        return {
            'total_faqs': len(faqs),
            'total_hits': total_hits,
            'by_category': by_category,
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _match_faq(self, message: str) -> Tuple[Optional[FAQEntry], int]:
        """키워드 매칭으로 FAQ 선택 (TF-IDF 유사도 간이 구현)."""
        normalized = message.lower()
        best_faq: Optional[FAQEntry] = None
        best_score = 0
        for faq in self._faqs.values():
            score = sum(
                1 for kw in faq.keywords
                if re.search(re.escape(kw.lower()), normalized)
            )
            if score > best_score:
                best_score = score
                best_faq = faq
        return best_faq, best_score

    def _build_quick_replies(self, category: str) -> List[QuickReply]:
        replies_map = {
            '배송조회': [
                QuickReply('배송 상태 확인', 'check_delivery'),
                QuickReply('배송 지연 문의', 'delivery_delay'),
            ],
            '환불문의': [
                QuickReply('환불 신청', 'request_refund'),
                QuickReply('반품 신청', 'request_return'),
            ],
            '주문상태': [
                QuickReply('주문 확인', 'check_order'),
                QuickReply('주문 취소', 'cancel_order'),
            ],
            '가격문의': [
                QuickReply('가격 문의', 'price_inquiry'),
                QuickReply('할인 쿠폰', 'coupon'),
            ],
        }
        base = replies_map.get(category, [])
        base.append(QuickReply('상담원 연결', 'connect_agent'))
        return base
