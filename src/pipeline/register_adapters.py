"""src/pipeline/register_adapters.py — P5: 검수표 → 마켓별 페이로드 변환 계층(어댑터 인터페이스).

쿠팡이 관통(카나리 10차)하며 확정된 것: **마켓별로 달라지는 지점은 4개뿐**이다.
그 4개를 인터페이스로 못박아 다음 마켓이 같은 6차 왕복을 반복하지 않게 한다.

  ① 고시정보(notice)     — 카테고리별 필수 항목·실값 규칙
  ② 배송(delivery)       — 배송방식·택배사·비용 구조
  ③ 옵션 필수값(options) — 필수 구매 옵션/속성의 값 대체 규칙
  ④ 카테고리 매핑(category) — 내부 코드 → 마켓 리프 카테고리

**정본 우선 원칙(6차 왕복의 교훈):** 각 어댑터는 `canon_status()`로 **네 지점의 정본 확보 여부**를
스스로 신고한다. 하나라도 미확보면 `register()`가 **전송 전에 차단**한다 — 추측 페이로드로 카나리를
태우지 않는다. 정본 = 통과 이력이 있는 스크립트(오너 SSH) 또는 마켓 메타 API 응답.
"""
from __future__ import annotations

from typing import Optional

# 마켓별로 갈리는 4지점 — 인터페이스의 전부(이 밖은 공통 파이프라인이 처리).
CANON_POINTS = ("notice", "delivery", "options", "category")

_POINT_KO = {"notice": "고시정보", "delivery": "배송", "options": "옵션 필수값",
             "category": "카테고리 매핑"}


class MarketAdapter:
    """검수표 행 → 마켓 등록. 4지점의 정본 확보 상태를 스스로 신고한다."""

    market = ""
    market_ko = ""

    def canon_status(self) -> dict:
        """4지점 정본 확보 상태. 반환 {ready: bool, points: {p: {ok, source|gap}}, gaps: [...]}.

        ok=True는 **통과 이력이 있는 값**(검증 스크립트 승계 또는 마켓 메타 API)일 때만 참이다.
        '그럴듯한 기본값이 코드에 있다'는 ok가 아니다 — 그게 카나리 6차를 태운 상태다.
        """
        raise NotImplementedError

    def register(self, product_data: dict, account: str) -> dict:
        """실등록. 정본 미확보면 **전송 없이** 정직 차단({success: False, held: True, error})."""
        raise NotImplementedError

    # 편의: 게이트 공통 구현.
    def _canon_gate(self) -> Optional[dict]:
        st = self.canon_status()
        if st.get("ready"):
            return None
        gaps = ", ".join(f"{_POINT_KO.get(p, p)}" for p in st.get("gaps") or [])
        return {"success": False, "held": True, "canon_gaps": st.get("gaps") or [],
                "error": (f"{self.market_ko or self.market} 페이로드 정본 미확보로 등록 중단"
                          f"(추측 전송 금지): {gaps}. "
                          "통과 이력이 있는 스크립트를 승계하거나 마켓 메타 API로 확정하세요.")}


class CoupangAdapter(MarketAdapter):
    """쿠팡 — **정본 확보 완료**(카나리 10차 관통). 4지점 전부 검증값.

    구현은 기존 `CoupangUploader`가 정본(재구현 0). 이 어댑터는 인터페이스 편입용 얇은 위임이다.
    """

    market = "coupang"
    market_ko = "쿠팡"

    def canon_status(self) -> dict:
        return {"ready": True, "gaps": [], "points": {
            # 출처를 남긴다 — 다음 세션이 "왜 ok인가"를 되묻지 않게.
            "notice": {"ok": True, "source": "카테고리 메타 API(category-related-metas) — #655"},
            "delivery": {"ok": True, "source": "오너 SSH 실측 coupang_upload.py:125 (AGENT_BUY/CJGLS) — #660·#661"},
            "options": {"ok": True, "source": "오너 SSH 실측 build_opt.py::attr_safe — #664"},
            "category": {"ok": True, "source": "쿠팡 카테고리 예측 API(실패 시 등록 중단) — #662"},
        }}

    def register(self, product_data: dict, account: str) -> dict:
        from src.seller_console.views import _coupang_account_dispatch
        return _coupang_account_dispatch(product_data, account)


class WooCommerceAdapter(MarketAdapter):
    """WooCommerce(멀티샵) — **편입만**(신규 구현 0). 자사몰이라 마켓 심사 4지점이 없다.

    고시정보·필수 옵션·택배사 코드 enum이 존재하지 않고 카테고리도 자유 문자열 → 정본 문제 자체가 없다.
    실제 등록은 v88-C 파일럿이 쓰는 기존 배선(`coupang_replicate`의 WC 경로)이 정본.
    """

    market = "woocommerce"
    market_ko = "멀티샵(WooCommerce)"

    def canon_status(self) -> dict:
        na = "해당 없음(자사몰 — 마켓 심사 규격 없음)"
        return {"ready": True, "gaps": [], "points": {
            "notice": {"ok": True, "source": na},
            "delivery": {"ok": True, "source": "자사 배송 정책(마켓 enum 아님)"},
            "options": {"ok": True, "source": na},
            "category": {"ok": True, "source": "자유 카테고리(리프 ID 강제 없음)"},
        }}

    def register(self, product_data: dict, account: str) -> dict:
        # 파일럿이 쓰는 기존 WC 경로가 정본 — 등록 파이프에서의 호출은 오너 승인 후 배선한다.
        return {"success": False, "held": True,
                "error": ("멀티샵은 파일럿 경로(v88-C)가 정본입니다 — 등록 파이프에서의 직접 등록은 "
                          "아직 배선하지 않았습니다(신규 구현 0 방침).")}


class SmartStoreAdapter(MarketAdapter):
    """스마트스토어(네이버) — **정본 미확보. 등록 차단 상태.**

    기존 `naver_uploader._build_product_payload`가 존재하지만 **통과 이력이 확인되지 않은 값**이 4지점
    전부에 들어 있다(아래 gap 사유). 쿠팡이 6차 왕복을 태운 것과 **같은 모양**이라, 정본을 승계하기
    전까지 전송을 막는다. 정본 확보 = 오너 SSH의 naver_* 통과 스크립트 승계 또는 네이버 메타 API 확정.
    """

    market = "smartstore"
    market_ko = "스마트스토어"

    # 미확보 사유 — 실측(기존 페이로드 코드에서 확인한 값). 추측이 아니라 '검증 안 됨'의 근거다.
    GAP_REASONS = {
        "notice": "originAreaCode='0200037'·importer='해외직구' 하드코딩 · A/S 전화번호 빈 문자열 "
                  "— 통과 이력 미확인(쿠팡 5차 고시정보 거부와 동형 위험)",
        "delivery": "deliveryType='DIRECT_DELIVERY' 고정 — 구매대행에 맞는 값인지 미검증 "
                    "(쿠팡 6차에서 같은 이름의 값이 거부된 전례)",
        "options": "필수 구매 옵션(optionInfo) 배선 자체가 없음 — 쿠팡 9차 거부와 동형",
        "category": "leafCategoryId 기본값 '50000000' 임의 지정 — 예측/검증 경로 없음",
    }

    def canon_status(self) -> dict:
        return {"ready": False, "gaps": list(CANON_POINTS),
                "points": {p: {"ok": False, "gap": self.GAP_REASONS[p]} for p in CANON_POINTS},
                "note": ("오너 SSH의 naver_* 통과 스크립트를 승계하면 해제됩니다. "
                         "승계 전 등록은 차단됩니다(추측 전송 금지).")}

    def register(self, product_data: dict, account: str) -> dict:
        gate = self._canon_gate()
        if gate:
            return gate
        raise NotImplementedError("정본 승계 후 배선")   # 게이트 해제 시점에 구현


_ADAPTERS = {a.market: a for a in (CoupangAdapter(), WooCommerceAdapter(), SmartStoreAdapter())}


def get_adapter(market: str) -> Optional[MarketAdapter]:
    return _ADAPTERS.get(str(market or "").strip().lower())


def adapters() -> dict:
    return dict(_ADAPTERS)


def canon_report() -> dict:
    """마켓별 정본 확보 현황 — 어디까지 열렸는지 한눈에(오너 판단용·정직 표기)."""
    out = {}
    for name, ad in _ADAPTERS.items():
        st = ad.canon_status()
        out[name] = {"market_ko": ad.market_ko, "ready": bool(st.get("ready")),
                     "gaps": st.get("gaps") or [], "points": st.get("points") or {},
                     "note": st.get("note", "")}
    return out
