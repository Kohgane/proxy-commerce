"""src/reviews/responder.py — 자동 응답 생성기.

리뷰 평점에 따른 템플릿 기반 자동 응답 (KO/EN).
응답 내역은 Google Sheets에 기록한다.

환경변수:
  AUTO_RESPONSE_ENABLED  — 자동 응답 활성화 여부 (기본 "0")
  REVIEW_SHEET_NAME      — 리뷰 워크시트명 (기본 "reviews")
  GOOGLE_SHEET_ID        — Google Sheets ID
"""

import datetime
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("AUTO_RESPONSE_ENABLED", "0") == "1"
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
_RESPONSE_SHEET = "review_responses"

# 응답 템플릿 (KO/EN)
_TEMPLATES = {
    "ko": {
        5: (
            "소중한 리뷰 감사드립니다! 😊\n"
            "최고 평점을 주셔서 저희 팀 모두 정말 기쁩니다. "
            "앞으로도 변함없는 서비스로 보답하겠습니다."
        ),
        4: (
            "좋은 리뷰 감사드립니다! 🙏\n"
            "더 나은 서비스를 위해 지속적으로 개선해 나가겠습니다. "
            "소중한 의견 감사합니다."
        ),
        3: (
            "리뷰를 남겨주셔서 감사합니다.\n"
            "더 나은 경험을 제공하지 못해 죄송합니다. "
            "고객님의 불편을 해소하기 위해 최선을 다하겠습니다."
        ),
        2: (
            "불편을 드려 진심으로 사과드립니다. 😔\n"
            "문제를 빠르게 해결하고 더 나은 서비스를 제공할 것을 약속드립니다. "
            "고객센터로 문의 주시면 적극 도와드리겠습니다."
        ),
        1: (
            "불편을 드려 진심으로 사과드립니다. 😔\n"
            "이런 경험을 드린 것에 대해 매우 유감스럽게 생각합니다. "
            "즉시 담당자가 연락드려 문제를 해결해 드리겠습니다."
        ),
    },
    "en": {
        5: (
            "Thank you so much for your wonderful review! 😊\n"
            "We're thrilled to hear you had such a great experience. "
            "We look forward to serving you again!"
        ),
        4: (
            "Thank you for your kind review! 🙏\n"
            "We're glad you had a positive experience and we'll keep working "
            "to make it even better."
        ),
        3: (
            "Thank you for your feedback.\n"
            "We're sorry we didn't fully meet your expectations. "
            "We'll use your comments to improve our service."
        ),
        2: (
            "We sincerely apologize for any inconvenience. 😔\n"
            "We promise to resolve this issue and improve our service. "
            "Please contact our support team and we'll be happy to help."
        ),
        1: (
            "We sincerely apologize for this experience. 😔\n"
            "We take this very seriously and will contact you immediately "
            "to resolve this issue."
        ),
    },
}

_RESPONSE_HEADERS = [
    "response_id", "review_id", "order_id", "product_sku",
    "rating", "language", "response_text", "responded_at",
]


class ReviewResponder:
    """리뷰 자동 응답 생성기."""

    def __init__(self, sheet_id: str = ""):
        self._sheet_id = sheet_id or _SHEET_ID

    def is_enabled(self) -> bool:
        """자동 응답 기능 활성화 여부를 반환한다."""
        return os.getenv("AUTO_RESPONSE_ENABLED", "0") == "1"

    def generate_response(
        self,
        review: Dict[str, Any],
        language: str = "ko",
    ) -> Optional[str]:
        """리뷰 평점에 따른 자동 응답을 생성한다.

        Args:
            review: 리뷰 딕셔너리 (rating 필드 필수).
            language: 응답 언어 ("ko" 또는 "en").

        Returns:
            응답 텍스트 또는 None (비활성화 시).
        """
        if not self.is_enabled():
            return None

        try:
            rating = int(review.get("rating", 3))
        except (ValueError, TypeError):
            rating = 3

        rating = max(1, min(5, rating))
        lang = language if language in ("ko", "en") else "ko"
        return _TEMPLATES[lang][rating]

    def respond_and_record(
        self,
        review: Dict[str, Any],
        language: str = "ko",
    ) -> Optional[Dict[str, Any]]:
        """응답을 생성하고 Google Sheets에 기록한다.

        Args:
            review: 리뷰 딕셔너리.
            language: 응답 언어.

        Returns:
            기록된 응답 딕셔너리 또는 None.
        """
        if not self.is_enabled():
            return None

        text = self.generate_response(review, language)
        if text is None:
            return None

        import uuid
        record = {
            "response_id": str(uuid.uuid4())[:8],
            "review_id": str(review.get("review_id", "")),
            "order_id": str(review.get("order_id", "")),
            "product_sku": str(review.get("product_sku", "")),
            "rating": int(review.get("rating", 0)),
            "language": language,
            "response_text": text,
            "responded_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
        self._save_response(record)
        return record

    def get_response_template(self, rating: int, language: str = "ko") -> str:
        """평점과 언어에 해당하는 응답 템플릿을 반환한다.

        Args:
            rating: 평점 (1-5).
            language: 언어 코드 ("ko" 또는 "en").
        """
        rating = max(1, min(5, int(rating)))
        lang = language if language in ("ko", "en") else "ko"
        return _TEMPLATES[lang][rating]

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _save_response(self, record: Dict[str, Any]) -> None:
        """응답 내역을 Google Sheets에 저장한다."""
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, _RESPONSE_SHEET)
            existing = ws.get_all_values()
            if not existing:
                ws.append_row(_RESPONSE_HEADERS)
            ws.append_row([record.get(h, "") for h in _RESPONSE_HEADERS])
            logger.info("응답 기록 완료: response_id=%s", record.get("response_id"))
        except Exception as exc:
            logger.warning("응답 기록 실패: %s", exc)
