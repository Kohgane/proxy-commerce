"""src/seller_console/upload_dispatcher.py — 마켓 업로드 디스패처 (Phase 122).

UploadDispatcher: 선택된 마켓들로 상품 업로드 요청을 디스패치.
기존 Phase 71/109 모듈 재사용 (graceful import).
모듈 미존재 시 큐에 적재만 수행.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 지원 마켓 코드
SUPPORTED_MARKETS = ["coupang", "smartstore", "elevenst", "woocommerce"]

# 마켓 표시명
MARKET_LABELS = {
    "coupang": "쿠팡",
    "smartstore": "스마트스토어",
    "elevenst": "11번가",
    "woocommerce": "코가네멀티샵(WC)",
}


@dataclass
class UploadResult:
    """업로드 결과 항목."""

    market: str
    success: bool
    message: str
    queued: bool = False  # 모듈 없어 큐에만 적재된 경우


@dataclass
class DispatchResult:
    """전체 디스패치 결과."""

    product_url: str
    results: List[UploadResult] = field(default_factory=list)
    total: int = 0
    succeeded: int = 0
    queued: int = 0
    failed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화용 딕셔너리 반환."""
        return {
            "product_url": self.product_url,
            "total": self.total,
            "succeeded": self.succeeded,
            "queued": self.queued,
            "failed": self.failed,
            "results": [
                {
                    "market": r.market,
                    "market_label": MARKET_LABELS.get(r.market, r.market),
                    "success": r.success,
                    "message": r.message,
                    "queued": r.queued,
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# 인메모리 큐 (모듈 미존재 시 폴백)
# ---------------------------------------------------------------------------
_pending_queue: List[Dict[str, Any]] = []


class UploadDispatcher:
    """마켓 업로드 디스패처.

    선택된 마켓 목록으로 ProductDraft를 업로드.
    각 마켓 업로더 모듈은 graceful import로 로드.
    모듈이 없으면 큐에 적재만 수행.
    """

    def dispatch(
        self,
        product_data: Dict[str, Any],
        markets: List[str],
    ) -> DispatchResult:
        """상품 데이터를 선택된 마켓들로 업로드.

        Args:
            product_data: ProductDraft.to_dict() 결과
            markets: 업로드 대상 마켓 코드 목록

        Returns:
            DispatchResult 인스턴스
        """
        url = product_data.get("url", "")
        result = DispatchResult(product_url=url)

        for market in markets:
            if market not in SUPPORTED_MARKETS:
                result.results.append(
                    UploadResult(
                        market=market,
                        success=False,
                        message=f"지원하지 않는 마켓: {market}",
                    )
                )
                result.failed += 1
                continue

            upload_result = self._upload_to_market(product_data, market)
            result.results.append(upload_result)
            if upload_result.success:
                result.succeeded += 1
            elif upload_result.queued:
                result.queued += 1
            else:
                result.failed += 1

        result.total = len(markets)
        return result

    def _upload_to_market(
        self,
        product_data: Dict[str, Any],
        market: str,
    ) -> UploadResult:
        """단일 마켓으로 업로드 시도.

        Args:
            product_data: 상품 데이터 딕셔너리
            market: 마켓 코드

        Returns:
            UploadResult
        """
        if market == "coupang":
            return self._upload_coupang(product_data)
        elif market == "smartstore":
            return self._upload_smartstore(product_data)
        elif market == "elevenst":
            return self._upload_elevenst(product_data)
        elif market == "woocommerce":
            return self._upload_woocommerce(product_data)
        else:
            return UploadResult(
                market=market,
                success=False,
                message="알 수 없는 마켓",
            )

    def _upload_coupang(self, product_data: Dict[str, Any]) -> UploadResult:
        """쿠팡 업로드 (Phase 71/109 모듈 재사용)."""
        try:
            # graceful import: 모듈 존재 시 실제 업로드
            from src.channel_sync import coupang_uploader  # type: ignore
            coupang_uploader.upload(product_data)
            return UploadResult(market="coupang", success=True, message="쿠팡 업로드 성공")
        except ImportError:
            # 모듈 없음 → 큐에 적재
            _pending_queue.append({"market": "coupang", "data": product_data})
            logger.info("쿠팡 업로더 모듈 없음 — 큐에 적재 완료 (큐 크기: %d)", len(_pending_queue))
            return UploadResult(
                market="coupang",
                success=False,
                queued=True,
                message="큐에 적재됨 (쿠팡 업로더 모듈 준비 중)",
            )
        except Exception as exc:
            logger.warning("쿠팡 업로드 오류: %s", exc)
            return UploadResult(market="coupang", success=False, message=f"오류: {exc}")

    def _upload_smartstore(self, product_data: Dict[str, Any]) -> UploadResult:
        """스마트스토어 업로드 (Phase 71/109 모듈 재사용)."""
        try:
            from src.channel_sync import smartstore_uploader  # type: ignore
            smartstore_uploader.upload(product_data)
            return UploadResult(market="smartstore", success=True, message="스마트스토어 업로드 성공")
        except ImportError:
            _pending_queue.append({"market": "smartstore", "data": product_data})
            logger.info("스마트스토어 업로더 모듈 없음 — 큐에 적재 완료 (큐 크기: %d)", len(_pending_queue))
            return UploadResult(
                market="smartstore",
                success=False,
                queued=True,
                message="큐에 적재됨 (스마트스토어 업로더 모듈 준비 중)",
            )
        except Exception as exc:
            logger.warning("스마트스토어 업로드 오류: %s", exc)
            return UploadResult(market="smartstore", success=False, message=f"오류: {exc}")

    def _upload_elevenst(self, product_data: Dict[str, Any]) -> UploadResult:
        """11번가 업로드 (Phase 71/109 모듈 재사용)."""
        try:
            from src.channel_sync import elevenst_uploader  # type: ignore
            elevenst_uploader.upload(product_data)
            return UploadResult(market="elevenst", success=True, message="11번가 업로드 성공")
        except ImportError:
            _pending_queue.append({"market": "elevenst", "data": product_data})
            logger.info("11번가 업로더 모듈 없음 — 큐에 적재 완료 (큐 크기: %d)", len(_pending_queue))
            return UploadResult(
                market="elevenst",
                success=False,
                queued=True,
                message="큐에 적재됨 (11번가 업로더 모듈 준비 중)",
            )
        except Exception as exc:
            logger.warning("11번가 업로드 오류: %s", exc)
            return UploadResult(market="elevenst", success=False, message=f"오류: {exc}")

    def _upload_woocommerce(self, product_data: Dict[str, Any]) -> UploadResult:
        """WooCommerce(코가네멀티샵) 업로드."""
        try:
            from src.vendors import woocommerce_client  # type: ignore
            woocommerce_client.create_product(product_data)
            return UploadResult(market="woocommerce", success=True, message="WooCommerce 업로드 성공")
        except ImportError:
            _pending_queue.append({"market": "woocommerce", "data": product_data})
            logger.info("WooCommerce 클라이언트 없음 — 큐에 적재 완료 (큐 크기: %d)", len(_pending_queue))
            return UploadResult(
                market="woocommerce",
                success=False,
                queued=True,
                message="큐에 적재됨 (WooCommerce 클라이언트 준비 중)",
            )
        except Exception as exc:
            logger.warning("WooCommerce 업로드 오류: %s", exc)
            return UploadResult(market="woocommerce", success=False, message=f"오류: {exc}")

    @staticmethod
    def get_pending_queue() -> List[Dict[str, Any]]:
        """현재 대기 큐 반환."""
        return list(_pending_queue)

    @staticmethod
    def clear_pending_queue() -> int:
        """대기 큐 초기화. 초기화된 항목 수 반환."""
        count = len(_pending_queue)
        _pending_queue.clear()
        return count
