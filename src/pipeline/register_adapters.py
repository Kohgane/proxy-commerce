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

    ACCOUNTS = ("multishop",)          # 자사몰 단일 스토어 — 쿠팡·스스처럼 계정 축이 갈리지 않는다.

    def register(self, product_data: dict, account: str) -> dict:
        gate = self._canon_gate()
        if gate:
            return gate
        acct = str(account or "").strip().lower()
        if acct not in self.ACCOUNTS:
            # 쿠팡(고가네/우주대행)·스스(chezgoga/gocosmos) 계정명이 잘못 들어오는 사고 방지.
            return {"success": False, "held": True,
                    "error": (f"멀티샵 계정이 아닙니다: {account!r} — "
                              f"{'/'.join(self.ACCOUNTS)} 를 쓰세요(쿠팡·스마트스토어 축과 별개).")}
        from src.seller_console.views import _woocommerce_dispatch
        return _woocommerce_dispatch(product_data, acct)


class SmartStoreAdapter(MarketAdapter):
    """스마트스토어(네이버) — **정본 승계 완료**(오너 SSH 실측 `ss_upload.py`).

    쿠팡과 **다른 축**: 계정 = chezgoga / gocosmos. 원산지·통관·반품비가 쿠팡과 다른 값을 쓴다
    (마켓별 정책 분기 — 섞으면 안 된다). 인증·호출은 기존 자산 재사용:
    `NAVER_COMMERCE_CLIENT_ID/SECRET` + **릴레이 경유**(v87-S7 — 직결 시 `GW.IP_NOT_ALLOWED`).
    """

    market = "smartstore"
    market_ko = "스마트스토어"
    ACCOUNTS = ("chezgoga", "gocosmos")

    PARTIAL: dict = {}          # 승계 완료 — 미확보 조각 없음(카테고리 11패턴 도착·#672)

    def canon_status(self) -> dict:
        return {"ready": True, "gaps": [], "partial": dict(self.PARTIAL), "points": {
            "notice": {"ok": True,
                       "source": "ss_upload.py 정본 — originAreaCode '03' + '상세설명에 표시'"
                                 "(스마트스토어 허용 문구·쿠팡과 다름)"},
            "delivery": {"ok": True,
                         "source": "ss_upload.py 정본 — 반품 25,000 / 교환 50,000 · 출고지·반품지 주소 ID(env)"},
            "options": {"ok": True,
                        "source": "ss_upload.py 정본 — 단일 옵션(재고 999·SALE). 다중 옵션은 쿠팡과 동일하게 후속"},
            "category": {"ok": True,
                         "source": "ss_upload.py 정본 CAT 11패턴(순서 유지·첫 매칭 우선) + 기본 리프 50004132"},
        }, "note": "인증·호출은 릴레이 경유(네이버 IP 게이트). 계정 축 = chezgoga/gocosmos."}

    def register(self, product_data: dict, account: str) -> dict:
        gate = self._canon_gate()
        if gate:
            return gate
        acct = str(account or "").strip().lower()
        if acct not in self.ACCOUNTS:
            # 쿠팡 계정명(고가네/우주대행)이 잘못 들어오는 사고 방지 — 축이 다르다.
            return {"success": False, "held": True,
                    "error": (f"스마트스토어 계정이 아닙니다: {account!r} — "
                              f"{'/'.join(self.ACCOUNTS)} 중에서 선택하세요(쿠팡 계정 축과 별개).")}
        from src.seller_console.views import _smartstore_account_dispatch
        return _smartstore_account_dispatch(product_data, acct)


class TalkStoreAdapter(MarketAdapter):
    """톡스토어(카카오) — **연동대행사 모델**. 정본 미확보로 `ready=False`.

    다른 마켓과 축이 하나 더 있다: 대행사 앱 Admin키(서버 비밀 1개) × 판매자별 API 인증키.
    그래서 판매자가 앱을 직접 만들지 않고 **우리 앱에 자기 스토어를 매핑**한다.

    **지금 여기서 아무것도 보내지 않는다.** 통과 이력 스크립트도, 문서 실측도 없다
    (컨테이너에서 카카오 문서 도메인이 차단돼 K0 실측을 못 했다 — HTTP 000).
    쿠팡이 6차 왕복을 태운 이유가 정확히 이것이라, 키가 들어와도 문서 확정이 먼저다.
    """

    market = "talkstore"
    market_ko = "톡스토어"

    def canon_status(self) -> dict:
        gap = "공개 문서 미실측(컨테이너 도메인 차단) + 대행사 등록 심사 전 — 통과 이력 정본 없음"
        return {"ready": False, "gaps": list(CANON_POINTS), "points": {
            p: {"ok": False, "gap": gap} for p in CANON_POINTS
        }, "note": ("연동대행사 모델 — 대행사 앱 Admin키(서버) + 판매자 API 인증키(판매자). "
                    "심사 통과·문서 실측 전까지 등록 비활성.")}

    def register(self, product_data: dict, account: str) -> dict:
        # `_canon_gate`가 ready=False를 보고 **전송 없이** 정직 차단한다(추측 페이로드 금지).
        return self._canon_gate() or {
            "success": False, "held": True,
            "error": "톡스토어 등록 경로가 아직 열리지 않았습니다.",
        }


_ADAPTERS = {a.market: a for a in (CoupangAdapter(), WooCommerceAdapter(), SmartStoreAdapter(),
                             TalkStoreAdapter())}


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
