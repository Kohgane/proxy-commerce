"""src/seller_console/upload_dispatcher.py — 마켓 업로드 디스패처 (Phase 122/190).

UploadDispatcher: 선택된 마켓들로 상품 업로드 요청을 디스패치.
기존 Phase 71/109 모듈 재사용 (graceful import).
모듈 미존재 시 큐에 적재만 수행.
Phase 190: prevalidate(), external_product_id/url, error_code/hint 추가.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 채널 브리지 예외 (자격증명 미설정 식별용). 브리지 미존재 시 폴백 정의.
try:
    from src.channel_sync._channel_bridge import ChannelCredentialsMissing
except Exception:  # pragma: no cover - 브리지 모듈 부재 시 안전 폴백
    class ChannelCredentialsMissing(RuntimeError):
        """채널 API 자격증명 미설정 (폴백 정의)."""

# 지원 마켓 코드
SUPPORTED_MARKETS = ["coupang", "smartstore", "elevenst", "woocommerce", "shopify"]

# 마켓 표시명
MARKET_LABELS = {
    "coupang": "쿠팡",
    "smartstore": "스마트스토어",
    "elevenst": "11번가",
    "woocommerce": "코가네멀티샵(WC)",
    "shopify": "Shopify",
}

# 마켓별 필수 환경변수 (사전검증용)
# 마켓별 필수 환경변수. 별칭(둘 중 하나) 검증은 _prevalidate_market에서 특수 처리한다.
#   shopify   : SHOPIFY_SHOP + (SHOPIFY_AUTO_TOKEN | SHOPIFY_ACCESS_TOKEN)
#   smartstore: (NAVER_CLIENT_ID | NAVER_COMMERCE_CLIENT_ID) + (..._SECRET)
#   woocommerce: (WC_URL | WOO_BASE_URL) + (WC_KEY | WOO_CK) + (WC_SECRET | WOO_CS)
_MARKET_REQUIRED_ENVS: Dict[str, List[str]] = {
    "coupang": ["COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID"],
    "smartstore": [],
    "elevenst": ["ELEVENST_API_KEY"],
    "woocommerce": [],
    "shopify": ["SHOPIFY_SHOP"],
}

# 마켓별 업로드 힌트 (토큰/권한 미설정 시 안내)
_MARKET_TOKEN_HINTS: Dict[str, str] = {
    "coupang": "/admin/diagnostics 에서 COUPANG_ACCESS_KEY / SECRET_KEY / VENDOR_ID 를 설정하세요.",
    "smartstore": "/admin/diagnostics 에서 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 를 설정하세요.",
    "elevenst": "/admin/diagnostics 에서 ELEVENST_API_KEY 를 설정하세요.",
    "woocommerce": "/admin/diagnostics 에서 WC_URL / WC_KEY / WC_SECRET (또는 WOO_BASE_URL / WOO_CK / WOO_CS) 를 설정하세요.",
    "shopify": "/admin/diagnostics 에서 SHOPIFY_SHOP 및 SHOPIFY_AUTO_TOKEN 을 설정하세요.",
}


@dataclass
class UploadResult:
    """업로드 결과 항목 (Phase 190: external_product_id/url, error_code, hint 추가)."""

    market: str
    success: bool
    message: str
    queued: bool = False                        # 모듈 없어 큐에만 적재된 경우
    external_product_id: Optional[str] = None  # 마켓 등록 상품 ID
    external_url: Optional[str] = None         # 마켓 상품 URL
    error_code: Optional[str] = None           # 오류 코드 (token_missing, scope_insufficient 등)
    hint: Optional[str] = None                 # 즉시 행동 가이드


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
                    "external_product_id": r.external_product_id,
                    "external_url": r.external_url,
                    "error_code": r.error_code,
                    "hint": r.hint,
                }
                for r in self.results
            ],
        }


@dataclass
class PrevalidationResult:
    """사전검증 결과."""

    market: str
    ok: bool
    error_code: Optional[str] = None
    message: str = ""
    hint: str = ""


# ---------------------------------------------------------------------------
# 인메모리 큐 (모듈 미존재 시 폴백)
# ---------------------------------------------------------------------------
_pending_queue: List[Dict[str, Any]] = []


class UploadDispatcher:
    """마켓 업로드 디스패처.

    선택된 마켓 목록으로 ProductDraft를 업로드.
    각 마켓 업로더 모듈은 graceful import로 로드.
    모듈이 없으면 큐에 적재만 수행.
    Phase 190: prevalidate() 추가 — 토큰/필수필드/이미지 사전검증.
    """

    def prevalidate(
        self,
        product_data: Dict[str, Any],
        markets: List[str],
    ) -> List[PrevalidationResult]:
        """마켓별 업로드 사전검증 (토큰/권한/필수필드/이미지 접근성).

        Returns:
            PrevalidationResult 목록 (마켓당 1개)
        """
        results = []
        for market in markets:
            results.append(self._prevalidate_market(product_data, market))
        return results

    def _prevalidate_market(
        self,
        product_data: Dict[str, Any],
        market: str,
    ) -> PrevalidationResult:
        """단일 마켓 사전검증."""
        if market not in SUPPORTED_MARKETS:
            return PrevalidationResult(
                market=market,
                ok=False,
                error_code="unsupported_market",
                message=f"지원하지 않는 마켓: {market}",
                hint="지원 마켓: " + ", ".join(SUPPORTED_MARKETS),
            )

        # 토큰/환경변수 검증
        required_envs = _MARKET_REQUIRED_ENVS.get(market, [])
        missing = [k for k in required_envs if not os.getenv(k)]

        # Shopify: SHOPIFY_AUTO_TOKEN 또는 SHOPIFY_ACCESS_TOKEN 중 하나만 있어도 됨
        # (required_envs에는 SHOPIFY_SHOP만 있어서 토큰 별도 체크 필요)
        if market == "shopify":
            _sh_cid = os.getenv("SHOPIFY_CLIENT_ID") or os.getenv("SHOPIFY_API_KEY")
            _sh_csec = os.getenv("SHOPIFY_CLIENT_SECRET") or os.getenv("SHOPIFY_API_SECRET_KEY")
            has_client_creds = bool(_sh_cid and _sh_csec)
            has_token = bool(os.getenv("SHOPIFY_AUTO_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN") or has_client_creds)
            if not has_token:
                missing.append("SHOPIFY_CLIENT_ID/SECRET (또는 SHOPIFY_AUTO_TOKEN)")

        # 스마트스토어: NAVER_CLIENT_* 또는 NAVER_COMMERCE_CLIENT_* 어느 쪽이든 허용
        if market == "smartstore":
            if not (os.getenv("NAVER_CLIENT_ID") or os.getenv("NAVER_COMMERCE_CLIENT_ID")):
                missing.append("NAVER_CLIENT_ID (또는 NAVER_COMMERCE_CLIENT_ID)")
            if not (os.getenv("NAVER_CLIENT_SECRET") or os.getenv("NAVER_COMMERCE_CLIENT_SECRET")):
                missing.append("NAVER_CLIENT_SECRET (또는 NAVER_COMMERCE_CLIENT_SECRET)")

        # 쿠팡: API 키 외에 출고지/반품지(Wing 배송정보)도 필수 — 없으면 등록 거부됨
        if market == "coupang":
            _coupang_ship = {
                "COUPANG_VENDOR_USER_ID": "Wing 로그인 ID",
                "COUPANG_RETURN_CENTER_CODE": "반품지센터코드",
                "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": "출고지코드",
                "COUPANG_RETURN_ZIP_CODE": "반품지우편번호",
                "COUPANG_RETURN_ADDRESS": "반품지주소",
                "COUPANG_RETURN_CHARGE_NAME": "반품지담당자명",
                "COUPANG_COMPANY_CONTACT_NUMBER": "반품지연락처",
            }
            for env, label in _coupang_ship.items():
                if not os.getenv(env):
                    missing.append(f"{env}({label})")

        # WooCommerce: 실제 업로드 경로는 WOO_* 사용, 진단은 WC_* 사용 → 둘 다 허용
        if market == "woocommerce":
            if not (os.getenv("WC_URL") or os.getenv("WOO_BASE_URL")):
                missing.append("WC_URL (또는 WOO_BASE_URL)")
            if not (os.getenv("WC_KEY") or os.getenv("WOO_CK")):
                missing.append("WC_KEY (또는 WOO_CK)")
            if not (os.getenv("WC_SECRET") or os.getenv("WOO_CS")):
                missing.append("WC_SECRET (또는 WOO_CS)")

        if missing:
            return PrevalidationResult(
                market=market,
                ok=False,
                error_code="token_missing",
                message="이 마켓의 API 키(또는 배송정보)가 아직 입력되지 않았어요.",
                hint=("‘마켓 연동’ 화면에서 이 마켓의 키를 입력하세요 (/seller/markets/connect/" + market + "). "
                      "이 키는 앱에 입력하는 ‘내 마켓 키’이며, 서버 환경변수(MARKET_CRED_ENC_KEY 등 인프라 키)와는 다릅니다. "
                      "누락: " + ", ".join(missing)),
            )

        # 필수 필드 검증
        title = str(product_data.get("title") or product_data.get("title_ko") or "").strip()
        if not title:
            return PrevalidationResult(
                market=market,
                ok=False,
                error_code="missing_field",
                message="상품명(title)이 없습니다.",
                hint="수집 후 상품명을 직접 입력하거나 AI 카피 생성을 활용하세요.",
            )

        price_raw = product_data.get("price") or product_data.get("price_original")
        try:
            price = float(price_raw) if price_raw is not None else None
        except (TypeError, ValueError):
            price = None
        if price is None or price <= 0:
            return PrevalidationResult(
                market=market,
                ok=False,
                error_code="missing_field",
                message="판매가가 0이거나 비어 있어 마켓이 등록을 거부합니다.",
                hint="편집 화면에서 판매가를 입력하세요(외화면 ‘원화로 환산’ 버튼으로 원화 판매가를 채울 수 있어요).",
            )

        # 이미지 URL 접근성 (첫 번째 이미지만 HEAD 체크, 타임아웃 3초)
        images = product_data.get("images")
        if images and isinstance(images, list):
            first_img = str(images[0]).strip()
            if first_img.startswith("http"):
                try:
                    import urllib.request
                    req = urllib.request.Request(first_img, method="HEAD")
                    with urllib.request.urlopen(req, timeout=3):
                        pass
                except Exception as img_exc:
                    logger.debug("이미지 HEAD 체크 실패(%s): %s", first_img, img_exc)
                    return PrevalidationResult(
                        market=market,
                        ok=False,
                        error_code="image_inaccessible",
                        message=f"상품 이미지 URL에 접근할 수 없습니다: {first_img[:60]}",
                        hint="마켓에서 접근 가능한 공개 이미지 URL을 사용하세요.",
                    )

        return PrevalidationResult(market=market, ok=True, message="사전검증 통과")

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

        # 원화 마켓용 sell_price_krw가 없으면 원문가+목표 마진율로 산정해 주입.
        enriched = self._ensure_sell_price_krw(product_data)

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

            upload_result = self._upload_to_market(enriched, market)
            result.results.append(upload_result)
            if upload_result.success:
                result.succeeded += 1
            elif upload_result.queued:
                result.queued += 1
            else:
                result.failed += 1

        result.total = len(markets)
        return result

    @staticmethod
    def _ensure_sell_price_krw(product_data: Dict[str, Any]) -> Dict[str, Any]:
        """원화 마켓용 sell_price_krw 주입.

        쿠팡/스마트스토어/11번가/WooCommerce는 원화 판매가가 필요하다.
        이미 양수 KRW 판매가(sell_price_krw / recommended_price(_krw) / price_krw)가
        있으면 그대로 둔다. 없고 원문가(외화 포함) + 통화가 있으면
        목표 마진율(target_margin_pct, 없으면 IMPORT_MARGIN_PCT, 기본 25)로
        landed cost 기반 원화 판매가를 산정해 주입한다.
        (KRW 원문가는 브리지의 price_if_krw 경로가 처리하므로 별도 산정하지 않는다.
         Shopify는 원문가/통화를 직접 사용하므로 영향받지 않는다.)
        """
        pd = dict(product_data or {})

        # 이미 양수 KRW 판매가가 있으면 그대로 사용
        for key in ("sell_price_krw", "recommended_price_krw", "recommended_price", "price_krw"):
            try:
                if float(pd.get(key)) > 0:
                    return pd
            except (TypeError, ValueError):
                continue

        currency = str(pd.get("currency") or "").upper()
        if currency == "KRW":
            # KRW 원문가는 to_collected의 price_if_krw 경로가 처리
            return pd

        raw_price = pd.get("price_original")
        if raw_price is None:
            raw_price = pd.get("price")
        try:
            price_orig = float(raw_price)
        except (TypeError, ValueError):
            price_orig = None
        if not price_orig or price_orig <= 0:
            return pd

        margin_pct = pd.get("target_margin_pct")
        try:
            margin_pct = float(margin_pct)
        except (TypeError, ValueError):
            margin_pct = float(os.getenv("IMPORT_MARGIN_PCT", "25"))

        try:
            from src.price import calc_landed_cost, _build_fx_rates

            fx_rates = _build_fx_rates()
            sell_krw = float(
                calc_landed_cost(
                    buy_price=price_orig,
                    buy_currency=currency,
                    margin_pct=margin_pct,
                    fx_rates=fx_rates,
                )
            )
            if sell_krw > 0:
                pd["sell_price_krw"] = int(round(sell_krw))
                rate = fx_rates.get(f"{currency}KRW")
                if rate:
                    pd["price_krw"] = int(round(price_orig * float(rate)))
        except Exception as exc:
            # 통화 미지원/환율 실패 등 → 산정 불가. 다운스트림에서 honest 오류 처리.
            logger.warning("원화 판매가 산정 실패(%s, %s): %s", price_orig, currency, exc)

        return pd

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
        market_payload, localized = self._payload_for_market(product_data, market)
        if market == "coupang":
            result = self._upload_coupang(market_payload)
        elif market == "smartstore":
            result = self._upload_smartstore(market_payload)
        elif market == "elevenst":
            result = self._upload_elevenst(market_payload)
        elif market == "woocommerce":
            result = self._upload_woocommerce(market_payload)
        elif market == "shopify":
            result = self._upload_shopify(market_payload)
        else:
            return UploadResult(
                market=market,
                success=False,
                message="알 수 없는 마켓",
            )
        if not localized and result.success:
            result.message = f"{result.message} (미현지화: 원문 사용)"
        return result

    @staticmethod
    def _payload_for_market(product_data: Dict[str, Any], market: str) -> tuple[Dict[str, Any], bool]:
        payload = dict(product_data or {})
        localized_map = payload.get("localized") if isinstance(payload.get("localized"), dict) else {}
        try:
            from src.markets.adapters.base import get_marketplace_meta

            locale = str(get_marketplace_meta(market).get("locale") or "ko-KR")
        except Exception:
            locale = "ko-KR"
        language = locale.split("-")[0].lower()

        localized = localized_map.get(locale)
        if not isinstance(localized, dict):
            localized = None
            for key, row in localized_map.items():
                if str(key).split("-")[0].lower() == language and isinstance(row, dict):
                    localized = row
                    break
        if isinstance(localized, dict):
            if localized.get("title"):
                payload["title"] = localized.get("title")
                if language == "ko":
                    payload["title_ko"] = localized.get("title")
            if localized.get("description"):
                payload["description"] = localized.get("description")
            if isinstance(localized.get("keywords"), list):
                payload["keywords"] = localized.get("keywords")
            if isinstance(localized.get("options"), list):
                payload["options"] = localized.get("options")
            return payload, True
        return payload, False

    def _upload_coupang(self, product_data: Dict[str, Any]) -> UploadResult:
        """쿠팡 업로드 (Phase 71/109 모듈 재사용)."""
        try:
            # graceful import: 모듈 존재 시 실제 업로드
            from src.channel_sync import coupang_uploader  # type: ignore
            upload_resp = coupang_uploader.upload(product_data)
            ext_id = None
            ext_url = None
            if isinstance(upload_resp, dict):
                ext_id = str(upload_resp.get("product_id") or upload_resp.get("id") or "").strip() or None
                ext_url = str(upload_resp.get("url") or "").strip() or None
            return UploadResult(
                market="coupang",
                success=True,
                message="쿠팡 업로드 성공",
                external_product_id=ext_id,
                external_url=ext_url,
            )
        except ImportError:
            # 모듈 없음 → 큐에 적재
            _pending_queue.append({"market": "coupang", "data": product_data})
            logger.info("쿠팡 업로더 모듈 없음 — 큐에 적재 완료 (큐 크기: %d)", len(_pending_queue))
            return UploadResult(
                market="coupang",
                success=False,
                queued=True,
                message="큐에 적재됨 (쿠팡 업로더 모듈 준비 중)",
                error_code="module_missing",
                hint=_MARKET_TOKEN_HINTS.get("coupang"),
            )
        except ChannelCredentialsMissing as exc:
            logger.info("쿠팡 자격증명 미설정: %s", exc)
            return UploadResult(
                market="coupang",
                success=False,
                message=str(exc),
                error_code="token_missing",
                hint=_MARKET_TOKEN_HINTS.get("coupang"),
            )
        except Exception as exc:
            logger.warning("쿠팡 업로드 오류: %s", exc)
            return UploadResult(
                market="coupang",
                success=False,
                message=f"오류: {exc}",
                error_code="api_error",
                hint="오류 내용을 확인 후 재시도하거나 /admin/diagnostics 에서 자격증명을 점검하세요.",
            )

    def _upload_smartstore(self, product_data: Dict[str, Any]) -> UploadResult:
        """스마트스토어 업로드 (Phase 71/109 모듈 재사용)."""
        try:
            from src.channel_sync import smartstore_uploader  # type: ignore
            upload_resp = smartstore_uploader.upload(product_data)
            ext_id = None
            ext_url = None
            if isinstance(upload_resp, dict):
                ext_id = str(upload_resp.get("product_id") or upload_resp.get("id") or "").strip() or None
                ext_url = str(upload_resp.get("url") or "").strip() or None
            return UploadResult(
                market="smartstore",
                success=True,
                message="스마트스토어 업로드 성공",
                external_product_id=ext_id,
                external_url=ext_url,
            )
        except ImportError:
            _pending_queue.append({"market": "smartstore", "data": product_data})
            logger.info("스마트스토어 업로더 모듈 없음 — 큐에 적재 완료 (큐 크기: %d)", len(_pending_queue))
            return UploadResult(
                market="smartstore",
                success=False,
                queued=True,
                message="큐에 적재됨 (스마트스토어 업로더 모듈 준비 중)",
                error_code="module_missing",
                hint=_MARKET_TOKEN_HINTS.get("smartstore"),
            )
        except ChannelCredentialsMissing as exc:
            logger.info("스마트스토어 자격증명 미설정: %s", exc)
            return UploadResult(
                market="smartstore",
                success=False,
                message=str(exc),
                error_code="token_missing",
                hint=_MARKET_TOKEN_HINTS.get("smartstore"),
            )
        except Exception as exc:
            logger.warning("스마트스토어 업로드 오류: %s", exc)
            return UploadResult(
                market="smartstore",
                success=False,
                message=f"오류: {exc}",
                error_code="api_error",
                hint="오류 내용을 확인 후 재시도하거나 /admin/diagnostics 에서 자격증명을 점검하세요.",
            )

    def _upload_elevenst(self, product_data: Dict[str, Any]) -> UploadResult:
        """11번가 업로드 (Phase 71/109 모듈 재사용)."""
        try:
            from src.channel_sync import elevenst_uploader  # type: ignore
            upload_resp = elevenst_uploader.upload(product_data)
            ext_id = None
            ext_url = None
            if isinstance(upload_resp, dict):
                ext_id = str(upload_resp.get("product_id") or upload_resp.get("id") or "").strip() or None
                ext_url = str(upload_resp.get("url") or "").strip() or None
            return UploadResult(
                market="elevenst",
                success=True,
                message="11번가 업로드 성공",
                external_product_id=ext_id,
                external_url=ext_url,
            )
        except ImportError:
            _pending_queue.append({"market": "elevenst", "data": product_data})
            logger.info("11번가 업로더 모듈 없음 — 큐에 적재 완료 (큐 크기: %d)", len(_pending_queue))
            return UploadResult(
                market="elevenst",
                success=False,
                queued=True,
                message="큐에 적재됨 (11번가 업로더 모듈 준비 중)",
                error_code="module_missing",
                hint=_MARKET_TOKEN_HINTS.get("elevenst"),
            )
        except ChannelCredentialsMissing as exc:
            logger.info("11번가 자격증명 미설정: %s", exc)
            return UploadResult(
                market="elevenst",
                success=False,
                message=str(exc),
                error_code="token_missing",
                hint=_MARKET_TOKEN_HINTS.get("elevenst"),
            )
        except Exception as exc:
            logger.warning("11번가 업로드 오류: %s", exc)
            return UploadResult(
                market="elevenst",
                success=False,
                message=f"오류: {exc}",
                error_code="api_error",
                hint="오류 내용을 확인 후 재시도하거나 /admin/diagnostics 에서 자격증명을 점검하세요.",
            )

    def _upload_woocommerce(self, product_data: Dict[str, Any]) -> UploadResult:
        """WooCommerce(코가네멀티샵) 업로드."""
        try:
            from src.vendors import woocommerce_client  # type: ignore
            from src.channel_sync._channel_bridge import to_collected

            # 공통 정규화(원화 판매가 포함) → WooCommerce catalog_row 매핑
            collected = to_collected(product_data)
            sell_price_krw = collected.get("sell_price_krw") or 0
            if sell_price_krw <= 0:
                return UploadResult(
                    market="woocommerce",
                    success=False,
                    message="WooCommerce 업로드 불가: 원화 판매가(sell_price_krw)가 0입니다.",
                    error_code="api_error",
                    hint="마진 계산기에서 권장 판매가를 계산 후 적용하거나 목표 마진율을 설정하세요.",
                )

            catalog_row = {
                "title_ko": collected.get("title_ko"),
                "title_en": collected.get("title_original"),
                "sku": collected.get("sku"),
                "category": collected.get("category_code"),
                "tags": ",".join(str(t) for t in (collected.get("tags") or [])),
                "images": ",".join(str(i) for i in (collected.get("images") or [])),
                "brand": collected.get("brand"),
                "stock": product_data.get("stock") or product_data.get("qty") or 0,
                "source_country": product_data.get("source_country")
                or product_data.get("country")
                or "",
                "buy_price": product_data.get("price_original")
                or product_data.get("price")
                or "",
                "buy_currency": product_data.get("currency") or "",
                "vendor": product_data.get("vendor") or "",
            }

            prod = woocommerce_client.prepare_product_data(catalog_row, sell_price_krw)
            upload_resp = woocommerce_client.upsert_product(prod)
            ext_id = None
            ext_url = None
            if isinstance(upload_resp, dict):
                ext_id = str(upload_resp.get("id") or "").strip() or None
                ext_url = str(upload_resp.get("permalink") or upload_resp.get("url") or "").strip() or None
            return UploadResult(
                market="woocommerce",
                success=True,
                message="WooCommerce 업로드 성공",
                external_product_id=ext_id,
                external_url=ext_url,
            )
        except ImportError:
            _pending_queue.append({"market": "woocommerce", "data": product_data})
            logger.info("WooCommerce 클라이언트 없음 — 큐에 적재 완료 (큐 크기: %d)", len(_pending_queue))
            return UploadResult(
                market="woocommerce",
                success=False,
                queued=True,
                message="큐에 적재됨 (WooCommerce 클라이언트 준비 중)",
                error_code="module_missing",
                hint=_MARKET_TOKEN_HINTS.get("woocommerce"),
            )
        except Exception as exc:
            logger.warning("WooCommerce 업로드 오류: %s", exc)
            return UploadResult(
                market="woocommerce",
                success=False,
                message=f"오류: {exc}",
                error_code="api_error",
                hint="오류 내용을 확인 후 재시도하거나 /admin/diagnostics 에서 자격증명을 점검하세요.",
            )

    def _upload_shopify(self, product_data: Dict[str, Any]) -> UploadResult:
        """Shopify 업로드 (Phase 183/190: src.markets.adapters.shopify 실연동 사용)."""
        try:
            from src.markets.adapters.base import ListingPayload
            from src.markets.adapters.shopify import ShopifyAdapter

            raw_price = product_data.get("price") or product_data.get("price_original")
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                price = None

            payload = ListingPayload(
                title=str(product_data.get("title") or product_data.get("title_ko") or "").strip(),
                description=str(product_data.get("description") or "").strip(),
                price=price,
                currency=str(product_data.get("currency") or "USD").upper(),
                sku=str(product_data.get("sku") or product_data.get("asin") or "").strip(),
                qty=int(product_data.get("qty") or 0),
                options={
                    "images": product_data.get("images") if isinstance(product_data.get("images"), list) else [],
                    "localized": product_data.get("localized") if isinstance(product_data.get("localized"), dict) else {},
                    "product_type": str(product_data.get("category") or "").strip(),
                    "vendor": str(product_data.get("brand") or "").strip(),
                    "tags": product_data.get("keywords") if isinstance(product_data.get("keywords"), list) else [],
                    "idempotency_key": product_data.get("idempotency_key")
                    or product_data.get("sku")
                    or product_data.get("asin")
                    or product_data.get("url"),
                },
            )

            adapter = ShopifyAdapter()
            validation = adapter.validate_listing(payload)
            if not validation.ok:
                return UploadResult(
                    market="shopify",
                    success=False,
                    message=validation.message,
                    error_code="validation_failed",
                    hint="상품명, 가격, 이미지가 모두 채워졌는지 확인하세요.",
                )

            result = adapter.upload_product(payload)
            if not result.ok:
                return UploadResult(
                    market="shopify",
                    success=False,
                    message=result.message,
                    error_code="api_error",
                    hint="SHOPIFY_SHOP / SHOPIFY_AUTO_TOKEN 설정 및 Admin API 권한을 /admin/diagnostics 에서 확인하세요.",
                )

            admin_url = str(result.raw.get("admin_url") or "").strip()
            storefront_url = str(result.raw.get("storefront_url") or "").strip() or None
            suffix = f" · 관리자: {admin_url}" if admin_url else ""
            return UploadResult(
                market="shopify",
                success=True,
                message=f"Shopify 업로드 성공 (ID: {result.external_id}){suffix}",
                external_product_id=str(result.external_id) if result.external_id else None,
                external_url=storefront_url or (admin_url if admin_url else None),
            )
        except Exception as exc:
            logger.warning("Shopify 업로드 오류: %s", exc)
            return UploadResult(
                market="shopify",
                success=False,
                message="오류: Shopify 업로드 처리 실패",
                error_code="api_error",
                hint="SHOPIFY_SHOP / SHOPIFY_AUTO_TOKEN 설정 및 Admin API 권한을 /admin/diagnostics 에서 확인하세요.",
            )

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
