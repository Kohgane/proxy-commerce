"""src/reviews/collector.py — 리뷰 수집기.

Google Sheets 기반 리뷰 저장소. Shopify/WooCommerce 웹훅에서 리뷰 수신.

환경변수:
  REVIEW_COLLECTION_ENABLED  — 수집 활성화 여부 (기본 "0")
  REVIEW_SHEET_NAME          — 리뷰 워크시트명 (기본 "reviews")
  GOOGLE_SHEET_ID            — Google Sheets ID
"""

import datetime
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("REVIEW_COLLECTION_ENABLED", "0") == "1"
_SHEET_NAME = os.getenv("REVIEW_SHEET_NAME", "reviews")
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# 리뷰 상태 상수
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

_HEADERS = [
    "review_id", "order_id", "product_sku", "rating",
    "text", "platform", "customer_email",
    "created_at", "status",
]


class ReviewCollector:
    """Google Sheets 기반 리뷰 수집기."""

    def __init__(self, sheet_id: str = "", sheet_name: str = ""):
        self._sheet_id = sheet_id or _SHEET_ID
        self._sheet_name = sheet_name or _SHEET_NAME
        self._enabled = _ENABLED

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        """수집 기능 활성화 여부를 반환한다."""
        return os.getenv("REVIEW_COLLECTION_ENABLED", "0") == "1"

    def submit_review(self, review_data: Dict[str, Any]) -> Dict[str, Any]:
        """리뷰를 제출하고 저장한다.

        Args:
            review_data: order_id, product_sku, rating, text, platform,
                         customer_email 필드를 포함한 딕셔너리.

        Returns:
            저장된 리뷰 딕셔너리 (review_id, created_at, status 포함).

        Raises:
            ValueError: 필수 필드 누락 또는 중복 리뷰.
            RuntimeError: 수집 기능 비활성화.
        """
        if not self.is_enabled():
            raise RuntimeError("REVIEW_COLLECTION_ENABLED is not set")

        self._validate(review_data)

        order_id = str(review_data.get("order_id", "")).strip()
        product_sku = str(review_data.get("product_sku", "")).strip()

        existing = self.get_reviews()
        if self._is_duplicate(existing, order_id, product_sku):
            raise ValueError(
                f"Duplicate review: order_id={order_id}, product_sku={product_sku}"
            )

        review = self._build_review(review_data)
        self._save(review)
        return review

    def get_reviews(
        self,
        rating: Optional[int] = None,
        status: Optional[str] = None,
        product_sku: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """저장된 리뷰 목록을 반환한다.

        Args:
            rating: 평점 필터 (1-5).
            status: 상태 필터 (pending/approved/rejected).
            product_sku: 제품 SKU 필터.
        """
        rows = self._load()
        if rating is not None:
            rows = [r for r in rows if int(r.get("rating", 0)) == int(rating)]
        if status:
            rows = [r for r in rows if r.get("status", "") == status]
        if product_sku:
            rows = [r for r in rows if r.get("product_sku", "") == product_sku]
        return rows

    def update_status(self, review_id: str, new_status: str) -> bool:
        """리뷰 상태를 변경한다.

        Args:
            review_id: 리뷰 ID.
            new_status: 새 상태 (approved/rejected/pending).

        Returns:
            업데이트 성공 여부.
        """
        if new_status not in (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED):
            raise ValueError(f"Invalid status: {new_status}")

        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._sheet_name)
            records = ws.get_all_records()
            for idx, rec in enumerate(records, start=2):  # 헤더 행 = 1
                if str(rec.get("review_id", "")) == review_id:
                    status_col = _HEADERS.index("status") + 1
                    ws.update_cell(idx, status_col, new_status)
                    logger.info("리뷰 상태 업데이트: review_id=%s status=%s", review_id, new_status)
                    return True
        except Exception as exc:
            logger.warning("리뷰 상태 업데이트 실패: %s", exc)
        return False

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _validate(self, data: Dict[str, Any]) -> None:
        """필수 필드를 검증한다."""
        required = ("order_id", "product_sku", "rating")
        missing = [f for f in required if not data.get(f)]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        rating = int(data.get("rating", 0))
        if not 1 <= rating <= 5:
            raise ValueError(f"rating must be between 1 and 5, got {rating}")

    def _is_duplicate(
        self,
        existing: List[Dict[str, Any]],
        order_id: str,
        product_sku: str,
    ) -> bool:
        """같은 order_id + product_sku 조합의 리뷰가 있는지 확인한다."""
        for r in existing:
            if (
                str(r.get("order_id", "")) == order_id
                and str(r.get("product_sku", "")) == product_sku
            ):
                return True
        return False

    def _build_review(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """리뷰 딕셔너리를 생성한다."""
        import uuid
        return {
            "review_id": str(uuid.uuid4())[:8],
            "order_id": str(data.get("order_id", "")),
            "product_sku": str(data.get("product_sku", "")),
            "rating": int(data.get("rating", 0)),
            "text": str(data.get("text", "")),
            "platform": str(data.get("platform", "")),
            "customer_email": str(data.get("customer_email", "")),
            "created_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "status": STATUS_PENDING,
        }

    def _save(self, review: Dict[str, Any]) -> None:
        """리뷰를 Google Sheets에 저장한다."""
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._sheet_name)
            # 헤더가 없으면 추가
            existing = ws.get_all_values()
            if not existing:
                ws.append_row(_HEADERS)
            ws.append_row([review.get(h, "") for h in _HEADERS])
            logger.info("리뷰 저장 완료: review_id=%s", review.get("review_id"))
        except Exception as exc:
            logger.warning("리뷰 저장 실패 (Sheets 미연결): %s", exc)

    def _load(self) -> List[Dict[str, Any]]:
        """Google Sheets에서 리뷰 목록을 로드한다."""
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(self._sheet_id, self._sheet_name)
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("리뷰 로드 실패: %s", exc)
            return []
