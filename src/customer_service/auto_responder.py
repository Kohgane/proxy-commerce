"""src/customer_service/auto_responder.py — FAQ-based auto responder."""

from __future__ import annotations

from typing import Dict, Optional

DEFAULT_FAQS: Dict[str, str] = {
    '배송': '배송은 주문 후 영업일 기준 2~3일 내 출고되며, 출고 후 1~2일 내 수령 가능합니다.',
    '반품': '수령 후 7일 이내 반품 신청 가능합니다. 고객센터로 문의해 주세요.',
    '교환': '수령 후 7일 이내 교환 신청 가능합니다. 동일 상품으로만 교환 가능합니다.',
    '환불': '반품 접수 후 상품 회수 확인 시 3~5 영업일 내 환불 처리됩니다.',
    '취소': '주문 후 배송 전이라면 마이페이지에서 직접 취소 가능합니다.',
    '결제': '신용카드, 계좌이체, 카카오페이 등 다양한 결제 수단을 지원합니다.',
    '회원': '회원가입은 이메일 또는 소셜 계정으로 간편하게 가입할 수 있습니다.',
    '포인트': '구매 금액의 1%가 포인트로 적립되며, 1포인트 = 1원으로 사용 가능합니다.',
    '쿠폰': '쿠폰은 결제 시 쿠폰 입력란에 코드를 입력하여 사용하실 수 있습니다.',
    '사이즈': '상품 페이지의 사이즈 가이드를 참고하시거나 고객센터로 문의해 주세요.',
    '재고': '품절 상품은 재입고 알림 신청을 통해 입고 시 안내받으실 수 있습니다.',
    '영업시간': '고객센터 운영 시간은 평일 오전 9시 ~ 오후 6시입니다.',
}


class AutoResponder:
    """Keyword-based FAQ auto responder."""

    def __init__(self, threshold: int = 1) -> None:
        self._faqs: Dict[str, str] = dict(DEFAULT_FAQS)
        self._threshold = threshold

    def suggest(self, text: str) -> Optional[str]:
        """Return best FAQ response if a keyword matches, else None."""
        best_key: Optional[str] = None
        best_score = 0

        for keyword, response in self._faqs.items():
            if keyword in text:
                score = len(keyword)
                if score > best_score:
                    best_score = score
                    best_key = keyword

        if best_key is not None and best_score >= self._threshold:
            return self._faqs[best_key]
        return None

    def add_faq(self, keyword: str, response: str) -> None:
        self._faqs[keyword] = response
