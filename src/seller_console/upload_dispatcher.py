"""src/seller_console/upload_dispatcher.py — 마켓 업로드 디스패처 (Phase 122/190).

UploadDispatcher: 선택된 마켓들로 상품 업로드 요청을 디스패치.
기존 Phase 71/109 모듈 재사용 (graceful import).
모듈 미존재 시 큐에 적재만 수행.
Phase 190: prevalidate(), external_product_id/url, error_code/hint 추가.
"""
from __future__ import annotations

import html as _html
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 초안이 상품 주소를 담는 **이름들**. 한 필드에 두 이름이 붙은 것이 F39의 근원이었다.
#   F40 실측(2026-09-20): 텔레그램/공유 수집은 `extra`에 **`final_url`**(폰이 편 최종 주소)을 담고
#   `url` 키는 **아예 안 만든다**(`share_collect.py`의 extra 키 실측: title·…·final_url·share_raw).
#   행의 `url` 컬럼(= 「원본 보기」가 읽는 그 값)은 정규형이지만 **extra에는 없다.**
DRAFT_URL_KEYS = ("url", "final_url", "source_url", "product_url")

# F42d: 한글이 섞여 있으면 영문 제목이 아니다 — 글자로 재는 판정(짐작 0).
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]")


def draft_url(product_data: Dict[str, Any]) -> str:
    """초안에서 **상품 주소**를 꺼낸다 — 이름이 뭐든 (F39).

    ## 실측 (오너 2026-09-20)

    수행방패 쿠팡 등록이 **「SKU 추출 실패 … `''`」**로 중단됐다. 그런데
    `vendor_sku('https://detail.tmall.com/item.htm?id=617129397971')`는
    **`'617129397971'`**을 잘 낸다 — 규칙은 멀쩡했다.

    갈라 보니 **주소가 페이로드에 없었다.** `ProductDraft.to_dict()`는
    `source_url`을 내고 **`url` 키를 아예 안 만든다**(`listing/auto_publish.py:124`).
    그런데 페이로드를 만드는 자리들은 전부 `product_data.get("url")`을 읽었다 →
    빈 문자열 → `vendor_sku("")` → `''` → 정직 중단.

    > ★★★ **한 필드에 두 이름이 붙으면, 쓰는 쪽과 읽는 쪽은 반드시 갈린다.**
    > 갈린 순간을 사람이 못 보므로(둘 다 정상으로 보인다) **꺼내는 자리를 하나로 만든다.**

    F34-2의 사본 드리프트와 **같은 모양**이다 — 거기선 한 사실이 두 표에 있었고,
    여기선 한 값이 두 이름으로 있다. 둘 다 답은 「한 자리에서 꺼낸다」다.

    ## F40 — **펴진 최종 주소**를 고른다

    2차 실측(2026-09-20): F39 배포 뒤에도 빈값이었다. 「원본 보기」는 티몰 정규형을 여는데
    페이로드는 아무것도 못 찾았다 — **읽는 자리가 달랐다**(그쪽은 행의 `url` 컬럼, 이쪽은 `extra`).

    그리고 이름이 여럿일 때 **어느 것을 고르느냐**도 문제다. 공유 링크(`e.tb.cn/h.…?tk=…`)는
    주소이긴 하지만 **상품번호가 없다.** 먼저 나온 이름이 그거면 빈 SKU가 그대로 나간다.

    > ★★ **후보가 여럿이면 「있는 것」이 아니라 「쓸 수 있는 것」을 고른다.**
    > 상품번호가 나오는 주소를 먼저 찾고, 없을 때만 아무 주소나 쓴다.

    공유 링크는 그래서 **최후 폴백**이 된다 — 규칙을 따로 쓰지 않아도(호스트 목록 하드코딩
    없이) 그렇게 된다.
    """
    d = product_data if isinstance(product_data, dict) else {}
    cands = [str(d.get(k) or "").strip() for k in DRAFT_URL_KEYS]
    cands = [c for c in cands if c]
    if not cands:
        return ""
    try:
        from src.collectors.product_key import vendor_sku
        for c in cands:
            if vendor_sku(c):
                return c
    except Exception as exc:                  # 식별자 계산 실패가 주소 선택을 막지 않는다
        logger.warning("[등록] 주소 선택 중 식별자 계산 실패(첫 후보 사용): %s", exc)
    return cands[0]


def render_detail_blocks_html(detail_blocks: Any, market: str) -> str:
    """v86-N: 드로어 '상세페이지 꾸미기'(v40-C) 블록 → 마켓 상세설명 HTML.

    detail_blocks = {common:[{type,content}...], <market>:[...]} (마켓 오버라이드는 선택).
    현재 마켓 오버라이드가 있으면 그것을, 없으면 공통(common)을 렌더한다 — 드로어 미리보기
    (dpPreview)와 **동일 시맨틱**(text=<p>, highlight=<div>, image=<img>, divider=<hr>)이라
    '미리보기=실제 등록물'이 성립한다. 내용은 전부 이스케이프(마크업 주입 방지).
    블록이 없거나 렌더 결과가 비면 '' 반환(호출측이 기존 description 폴백 유지 → 회귀 0).
    """
    if not isinstance(detail_blocks, dict):
        return ""
    blocks = detail_blocks.get(market)
    if not isinstance(blocks, list):
        blocks = detail_blocks.get("common")
    if not isinstance(blocks, list):
        return ""
    parts: List[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        btype = b.get("type")
        content = str(b.get("content") or "")
        if btype == "text":
            if content.strip():
                parts.append(
                    '<p style="font-size:.95rem;white-space:pre-wrap;margin:0 0 .8rem">'
                    + _html.escape(content) + "</p>")
        elif btype == "highlight":
            if content.strip():
                parts.append(
                    '<div style="background:#fff8e6;border:1px solid #f0d68a;border-radius:8px;'
                    'padding:10px 12px;margin:0 0 .8rem;white-space:pre-wrap">'
                    + _html.escape(content) + "</div>")
        elif btype == "image":
            if content.strip():
                parts.append(
                    '<img src="' + _html.escape(content, quote=True)
                    + '" style="max-width:100%;border-radius:6px;margin:0 0 .8rem" alt="">')
        elif btype == "divider":
            parts.append('<hr style="margin:.8rem 0">')
    return "".join(parts).strip()

# 채널 브리지 예외 (자격증명 미설정 식별용). 브리지 미존재 시 폴백 정의.
try:
    from src.channel_sync._channel_bridge import ChannelCredentialsMissing
except Exception:  # pragma: no cover - 브리지 모듈 부재 시 안전 폴백
    class ChannelCredentialsMissing(RuntimeError):
        """채널 API 자격증명 미설정 (폴백 정의)."""

# 지원 마켓 코드
SUPPORTED_MARKETS = ["coupang", "smartstore", "elevenst", "woocommerce", "shopify"]


def smartstore_approved() -> bool:
    """v61 STEP3: 스마트스토어(네이버 커머스솔루션) 승인 여부. 승인 전엔 업로드 시도 차단.
    승인 완료 시 관리자가 SMARTSTORE_APPROVED=1(또는 true/yes) 설정으로 오픈."""
    return str(os.getenv("SMARTSTORE_APPROVED", "")).strip().lower() in ("1", "true", "yes", "on")

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
    # F35-2: **「닿나」를 쟀는가.** None = 안 쟀다(측정 안 한 것을 통과로 읽지 않는다).
    reach_ok: Optional[bool] = None
    reach_ms: Optional[int] = None
    reach_detail: str = ""


# F35-2: 사전검증에서 **도달성만** 재는 자리들. 자격은 보내지 않는다 — 「닿나」만 묻는다.
#   쿠팡·스마트스토어는 IP 화이트리스트라 릴레이를 타고, 무자격 GET이 의미가 없어 제외한다
#   (그 둘의 도달성은 릴레이 상태가 답이다).
_REACH_TIMEOUT_SEC = 5


def market_reach(market: str) -> Dict[str, Any]:
    """가벼운 GET 1회로 「닿나」만 잰다 — `{ok, ms, detail}`. 못 재면 `ok=None` (F35-2).

    ## 왜 이게 필요했나 (오너 실측 2026-09-19)

    멀티샵(WooCommerce) 사전검증이 **「통과」**였는데, 같은 시각 그 사이트는
    **45초 동안 0바이트**였다(Bluehost PHP 전면 정지). 사전검증이 잰 것은
    **자격이 입력돼 있나**였지 **사이트가 살아 있나**가 아니었다.

    > ★ **「키가 있다」는 「닿는다」가 아니다.** 등록 직전에 한 번은 실제로 두드려 봐야
    > 「통과」가 거짓말이 아니게 된다.

    어떤 HTTP 응답이든 **도달**로 본다(401·403·404도 서버가 살아 있다는 뜻이다).
    연결 실패·타임아웃만 **도달 불가**다. 재시도는 하지 않는다 — 사전검증은 사람이
    기다리는 화면이고, 여기서 백오프를 돌면 5초 예산이 30초가 된다.
    """
    import time as _time

    url = ""
    if market == "woocommerce":
        base = (os.getenv("WC_URL") or os.getenv("WOO_BASE_URL") or "").strip().rstrip("/")
        if base and not base.startswith("http"):
            base = "https://" + base
        url = f"{base}/wp-json/" if base else ""
    elif market == "elevenst":
        url = "https://api.11st.co.kr/rest"
    elif market == "shopify":
        shop = (os.getenv("SHOPIFY_SHOP") or "").strip().rstrip("/")
        if shop and not shop.startswith("http"):
            shop = "https://" + shop
        url = shop
    if not url:
        return {"ok": None, "ms": None, "detail": "주소가 없어 도달을 재지 못했습니다"}

    try:
        from src.market_throttle import pace
        pace(market)                              # 페이싱은 지키되 재시도는 하지 않는다
    except Exception:                             # noqa: BLE001 — 페이싱 실패가 검증을 막지 않는다
        pass
    started = _time.monotonic()
    try:
        import requests
        resp = requests.get(url, timeout=_REACH_TIMEOUT_SEC,
                            headers={"User-Agent": "gogabridj-reachcheck/1.0",
                                     "Accept": "*/*"})
        ms = int((_time.monotonic() - started) * 1000)
        return {"ok": True, "ms": ms, "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:                      # noqa: BLE001 — 사유 종류를 그대로 싣는다
        ms = int((_time.monotonic() - started) * 1000)
        return {"ok": False, "ms": ms, "detail": f"{type(exc).__name__}"}


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

        # v61 STEP3: 스마트스토어 약관 준수 게이트 — 커머스솔루션 승인 전에는 업로드 시도 자체 차단
        #   (토큰 발급·실패 노출 금지). SMARTSTORE_APPROVED=1(env 또는 admin 토글) 시에만 활성.
        if market == "smartstore" and not smartstore_approved():
            return PrevalidationResult(
                market=market,
                ok=False,
                error_code="smartstore_pending_review",
                message="스마트스토어는 심사중입니다 — 커머스솔루션 승인 후 오픈됩니다.",
                hint="네이버 커머스솔루션 승인 완료 후 관리자가 오픈합니다(현재는 등록 시도가 차단됩니다).",
            )

        # 토큰/환경변수 검증
        required_envs = _MARKET_REQUIRED_ENVS.get(market, [])
        # F29: 쿠팡은 **계정 접두**(`COUPANG_GOGANE_ACCESS_KEY`)로도 들어온다. 여기서
        #   무접두만 보면 대시보드는 「자격 설정됨」인데 여기만 「미입력」이 된다(오너 실측).
        #   판정은 아래 `coupang_api_state`가 대시보드와 **같은 함수**로 한다.
        missing = ([] if market == "coupang"
                   else [k for k in required_envs if not os.getenv(k)])
        _cred_source = ""          # F29-5: 어느 저장소를 보고 판정했는지(문장에 싣는다)
        _empty_label = "비어 있는 값: "   # F34-1: 읽지 못했으면 이 말이 바뀐다

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
            # F29 실측(2026-09-16): 여기만 **무접두 이름**(`COUPANG_RETURN_CENTER_CODE`)을 봤다.
            #   오너는 계정 접두(`COUPANG_GOGANE_*`)로 넣어 뒀고, 실제 업로더는 접두를 읽는다.
            #   그래서 **업로더는 값을 찾는데 사전검증은 「미입력」**이라고 했다 — 같은 자격을
            #   두 자리가 다른 규약으로 읽으면, 한쪽은 반드시 거짓말을 한다.
            #   판정기를 새로 쓰지 않고 **업로더의 읽기(`_ship_env`)를 그대로 부른다**(재구현 0).
            from src.seller_console.market_cred_view import (
                coupang_api_state, coupang_shipping_state)
            _api = coupang_api_state()
            _state = coupang_shipping_state(_api.get("account") or "")
            for env, label in list(_api["missing"]) + list(_state["missing"]):
                missing.append(f"{env}({label})")
            _cred_source = _state["source"]
            # **못 물어본 것을 「없다」고 하지 않는다** — 조회 자체가 실패했으면 그렇게 말한다.
            if _api.get("unknown") or _state.get("unknown"):
                _cred_source = "자격 저장소를 확인하지 못했습니다"
            # F34-1: 저장소를 **읽지 못한** 것과 값이 **비어 있는** 것은 다른 사건이다.
            #   섞어 말하면 셀러는 이미 넣어 둔 값을 또 넣는다(오너가 실제로 그랬다).
            if _state.get("read_failed"):
                _empty_label = "읽지 못해 확인하지 못한 값: "

        # WooCommerce: 실제 업로드 경로는 WOO_* 사용, 진단은 WC_* 사용 → 둘 다 허용
        if market == "woocommerce":
            if not (os.getenv("WC_URL") or os.getenv("WOO_BASE_URL")):
                missing.append("WC_URL (또는 WOO_BASE_URL)")
            if not (os.getenv("WC_KEY") or os.getenv("WOO_CK")):
                missing.append("WC_KEY (또는 WOO_CK)")
            if not (os.getenv("WC_SECRET") or os.getenv("WOO_CS")):
                missing.append("WC_SECRET (또는 WOO_CS)")

        if missing:
            # F29-5: 「미입력」만 말하면 셀러는 **이미 넣어 둔 값을 또 넣는다**(오너가 그랬다).
            #   어느 저장소를 봤는지와 빈 필드를 그대로 싣는다.
            _where = ("확인한 곳: " + _cred_source + ". ") if _cred_source else ""
            return PrevalidationResult(
                market=market,
                ok=False,
                error_code="token_missing",
                message="이 마켓의 API 키(또는 배송정보)가 아직 입력되지 않았어요.",
                hint=("‘마켓 연동’ 화면에서 이 마켓의 키를 입력하세요 (/seller/markets/connect/" + market + "). "
                      "이 키는 앱에 입력하는 ‘내 마켓 키’이며, 서버 환경변수(MARKET_CRED_ENC_KEY 등 인프라 키)와는 다릅니다. "
                      + _where + _empty_label + ", ".join(missing)),
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

        # F35-2: **등록 직전에 한 번** 두드려 본다 — 「키가 있다」를 「닿는다」로 읽지 않는다.
        if market in ("woocommerce", "elevenst", "shopify"):
            reach = market_reach(market)
            if reach["ok"] is False:
                return PrevalidationResult(
                    market=market, ok=False, error_code="market_unreachable",
                    message=f"이 마켓에 닿지 못했습니다 ({reach['detail']}).",
                    hint=(f"{reach['ms']}ms 동안 기다렸지만 응답이 없었습니다. "
                          "사이트(또는 마켓 API)가 멈춰 있으면 등록도 실패합니다 — "
                          "사이트가 열리는지 먼저 확인하세요."),
                    reach_ok=False, reach_ms=reach["ms"], reach_detail=reach["detail"])
            return PrevalidationResult(market=market, ok=True, message="사전검증 통과",
                                       reach_ok=reach["ok"], reach_ms=reach["ms"],
                                       reach_detail=reach["detail"])
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
        # F39: `url` 하나만 읽으면 `ProductDraft.to_dict()`(→ `source_url`) 초안에서 빈값이 된다.
        url = draft_url(product_data)
        # F40: **고른 주소를 로그에 남긴다.** 오너 지시 — 이건 URL이라 마스킹 대상이 아니다.
        #   2차 실측 때 이 한 줄이 있었으면 한 판 아꼈다(화면은 열리는데 등록은 빈값이었다).
        logger.info("[등록] 주소 선택 url=%s 후보키=%s",
                    url or "(없음)",
                    [k for k in DRAFT_URL_KEYS if str(product_data.get(k) or "").strip()])
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
    def _landed_krw(product_data: Dict[str, Any]) -> float:
        """원가 → 랜딩코스트 기반 **원화 판매가**. 못 내면 0 (F42a).

        `calc_landed_cost` 하나만 쓴다 — 식이 두 벌이 되면 마켓마다 값이 갈린다.
        """
        raw = product_data.get("price_original")
        if raw is None:
            raw = product_data.get("price")
        try:
            cost = float(raw)
        except (TypeError, ValueError):
            return 0.0
        if cost <= 0:
            return 0.0
        cur = str(product_data.get("currency") or "").strip().upper()
        if not cur:
            return 0.0
        try:
            margin = float(product_data.get("target_margin_pct"))
        except (TypeError, ValueError):
            margin = float(os.getenv("IMPORT_MARGIN_PCT", "25"))
        try:
            from src.price import _build_fx_rates, calc_landed_cost
            return float(calc_landed_cost(buy_price=cost, buy_currency=cur,
                                          margin_pct=margin, fx_rates=_build_fx_rates()))
        except Exception as exc:
            logger.warning("[등록] 판매가 산정 실패(%s %s): %s", cost, cur, exc)
            return 0.0

    @staticmethod
    def sell_price_in(product_data: Dict[str, Any], currency: str) -> tuple:
        """목표 통화 **판매가** — `(값, 사유)`. 못 내면 `(None, 사유)` (F42a).

        ## 마진 정의 (실측 · 오너 지시로 계약에 명기)

        `src/price.calc_landed_cost`가 정본이고, **markup**이다(gross margin 아님):

            판매가KRW = (원가KRW + 배대지수수료KRW + 국제배송비KRW)
                        × (1 + 관부가세율) × (1 + 마진율)

        - 포함: 배대지 수수료(`FORWARDER_FEE_JPY`) · 국제배송비(`SHIPPING_FEE_DEFAULT`) ·
          관부가세(면세 기준 `CUSTOMS_THRESHOLD_KRW` 초과 시)
        - **미포함: 마켓 판매수수료**(쿠팡·11번가·Shopify 결제수수료 등). `target_margin_pct`는
          그 수수료를 덮지 않는다 — 실수령 마진은 이보다 **낮다.**

        ## 왜 이 함수가 생겼나

        오너 실측(2026-09-20 카나리 1호): Shopify에 **$4.10**이 떴다 — **원가 그대로**다.
        마진도 배송비도 안 붙었다. 원인은 `_ensure_sell_price_krw`의 docstring이 그대로 적어
        둔 그것이다: 「**Shopify는 원문가/통화를 직접 사용하므로 영향받지 않는다**」.
        원화 마켓만 산정하고 **외화 마켓은 원가를 그대로 냈다.**

        > ★★★ **판매가 산정식이 마켓마다 따로면, 안 고친 마켓이 원가로 나간다.**
        > 식은 하나여야 한다 — 여기서 KRW로 한 번 내고, 통화만 환산한다.

        환율을 못 구하면 **원가로 폴백하지 않는다.** `(None, 사유)`를 내고 호출부가 등록을
        보류한다 — 원가로 파는 것은 손해고, 조용한 손해는 가짜 성공보다 나쁘다.
        """
        cur = str(currency or "").strip().upper()
        if not cur:
            return None, "대상 통화를 알 수 없습니다"
        try:
            krw = float(product_data.get("sell_price_krw") or 0)
        except (TypeError, ValueError):
            krw = 0.0
        if krw <= 0:
            # `_ensure_sell_price_krw`는 **원가 통화가 KRW면 일찍 돌아간다**(원화 마켓은
            #   다운스트림 `price_if_krw`가 처리하므로). 그 경우에도 외화 마켓은 판매가가
            #   있어야 한다 — **같은 식으로** 한 번 더 낸다(식을 두 벌로 만들지 않는다).
            krw = UploadDispatcher._landed_krw(product_data)
        if krw <= 0:
            return None, ("판매가를 산정하지 못했습니다 — 원가·통화·환율을 확인하세요"
                          "(원가 그대로 등록하지 않습니다).")
        if cur == "KRW":
            return round(krw), ""
        try:
            from src.price import _build_fx_rates
            rate = float(_build_fx_rates().get(f"{cur}KRW") or 0)
        except Exception as exc:
            return None, f"{cur} 환율을 구하지 못했습니다: {type(exc).__name__}"
        if rate <= 0:
            return None, f"{cur} 환율이 없습니다(원가 그대로 등록하지 않습니다)"
        return round(krw / rate, 2), ""

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
        # v86-N: 드로어 '상세페이지 꾸미기' 블록(detail_blocks)을 이 마켓의 description_html로 렌더.
        #   블록이 있으면(셀러의 명시적 상세 구성) 그것을 상세설명 HTML로 채운다 → 채널 브리지
        #   (description_html or description)가 이를 사용해 실제 등록에 반영(coupang/smartstore/11st).
        #   블록 없으면 미설정 → 기존 plain description 폴백 유지(회귀 0). AI 경로는 detail_blocks가
        #   없으므로 무영향(선-설정된 description_html 있으면 그대로 존중).
        _blocks_html = render_detail_blocks_html(payload.get("detail_blocks"), market)
        if _blocks_html:
            payload["description_html"] = _blocks_html
        # F42b 실측(오너 2026-09-20 카나리 1호): 상세설명에 **티몰 셀러 카드**가 들어갔다
        #   (旗舰店·88VIP·发货·回复). 남의 가게 광고를 우리 상세로 내보낸 셈이다.
        #   **여기가 모든 마켓이 지나는 한 자리**다 — 마켓마다 걸면 언젠가 한 마켓이 빠진다
        #   (F42a에서 Shopify가 그렇게 빠져 있었다).
        #   셀러가 직접 꾸민 블록(`detail_blocks`)은 **사람이 만든 것**이라 건드리지 않는다.
        if not _blocks_html:
            try:
                from src.collectors.universal_scraper import strip_seller_card
                for _k in ("description_html", "description"):
                    _v = payload.get(_k)
                    if isinstance(_v, str) and _v.strip():
                        payload[_k] = strip_seller_card(_v)
            except Exception as exc:        # 정제 실패가 등록을 막지 않는다
                logger.warning("[등록] 셀러 카드 정제 실패(원문 유지): %s", exc)
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
                # v86-O: 셀러가 꾸민 상세(블록→description_html) → WC 상품 설명 본문에 반영.
                #   비면 woocommerce_client가 기존 벤더 템플릿(배송·관부가세·교환반품)으로 폴백.
                "description": collected.get("description_html") or "",
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
                # v88-C 파일럿 카나리: draft 상태 + 파일럿 메타(비노출) + 재고(무재고 모델) 통과. 수동 업로드는 미지정→기존 동작.
                "status": product_data.get("status") or "",
                "extra_meta": product_data.get("pilot_meta") or [],
                # F42c 실측(오너 2026-09-20 카나리 1호): WC 상품이 **Out of stock**으로 떴다.
                #   `stock`이 없으면 0으로 나가고, `woocommerce_client`가 `0 → outofstock`으로
                #   바꾼다. 그런데 우리 모델은 **무재고 구매대행**이다 — 우리 창고 재고가 0인 게
                #   정상이고, 그걸 「품절」로 번역하면 **등록하자마자 못 판다.**
                #   파일럿 경로는 이미 `manage_stock=False · instock`으로 보내고 있었다(views:8108).
                #   수동 업로드 경로만 안 보내고 있었다 — 같은 모델이면 같은 값이어야 한다.
                #   호출부가 명시하면 그게 이긴다(재고 관리형 셀러를 막지 않는다).
                "manage_stock": (product_data.get("manage_stock")
                                 if product_data.get("manage_stock") is not None else False),
                "stock_status": (str(product_data.get("stock_status") or "").strip()
                                 or "instock"),
                # v88-C: 상품 타입(자사 결제형 simple) — 미지정이면 기존 동작 불변.
                "product_type": product_data.get("product_type") or "",
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

            # F42a: 예전엔 `price or price_original` — **원가 그대로**였다(실측 $4.10).
            #   판매가 산정식은 하나뿐이고(`sell_price_in`), 못 내면 **등록하지 않는다.**
            store_cur = (os.getenv("SHOPIFY_STORE_CURRENCY", "").strip().upper()
                         or "USD")     # US 스토어 기준. 다른 통화면 env로 지정한다.
            price, _why = self.sell_price_in(product_data, store_cur)
            if price is None:
                return UploadResult(
                    market="shopify", success=False, error_code="price_unresolved",
                    message=f"판매가를 정하지 못해 등록하지 않았습니다 — {_why}",
                    hint=("원가·통화·환율을 확인하세요. 원가 그대로 올리면 마진·배송비가 빠져 "
                          "팔수록 손해입니다."))

            # F42d 실측(오너 2026-09-20): Shopify(US 스토어)에 **한국어 제목**이 올라갔다.
            #   미국 손님은 그 제목을 못 읽는다 — 「원문 사용」은 답이 아니다(오너).
            #   영문 제목이 없으면 **등록하지 않는다.** 한글이 섞여 있으면 영문 제목이 아니다
            #   (호스트별 짐작이 아니라 **글자로 재는** 판정이다).
            _title = str(product_data.get("title_en")
                         or product_data.get("title_original") or "").strip()
            if not _title or _HANGUL_RE.search(_title):
                _title = ""
            if not _title:
                _ko = str(product_data.get("title") or product_data.get("title_ko") or "").strip()
                if _ko and not _HANGUL_RE.search(_ko):
                    _title = _ko        # 애초에 영문 제목이면 그대로 쓴다
            if not _title:
                return UploadResult(
                    market="shopify", success=False, error_code="title_not_english",
                    message="영문 제목이 없어 등록하지 않았습니다(한국어 제목을 그대로 올리지 않습니다).",
                    hint="편집 화면에서 영문 상품명을 채우거나 번역을 돌린 뒤 다시 등록하세요.")

            payload = ListingPayload(
                title=_title,
                # v86-O: 셀러가 꾸민 상세(블록→description_html, _payload_for_market서 주입)를
                #   Shopify body_html로 반영. 블록 없으면 기존 plain description 폴백(회귀 0).
                description=str(product_data.get("description_html") or product_data.get("description") or "").strip(),
                price=price,
                # F42a: 통화도 **스토어 통화**다. 공급사 통화를 그대로 내면 숫자는 그대로인데
                #   스토어가 제 통화로 읽어 값이 통째로 달라진다.
                currency=store_cur,
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
                    or draft_url(product_data),          # F39: 이름이 뭐든 꺼낸다
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
