"""src/seller_console/orders/sync_service.py — 주문 동기화 서비스 (Phase 129)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# 택배사 **코드** 모양 — 영문/숫자로 시작하고 영문·숫자·`_`·`-`만. 한글·공백은 코드가 아니다.
_COURIER_CODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")

# 코드 관문을 거는 마켓. **쿠팡만이다** — 다른 마켓의 코드표를 아직 모르기 때문이고,
#   모르는 채로 막으면 그건 또 다른 발명이다. 코드표가 오면(F44) 그때 늘린다.
_CODE_GATED_MARKETS = {"coupang"}


def courier_code_hold(marketplace: str, courier: str) -> str:
    """전송을 **보류할 사유**(없으면 빈 문자열) — F45.

    실측(2026-09-21): 일괄 송장 화면의 **자유 입력 문자열이 쿠팡에 그대로** 갔다.
    셀러가 「CJ대한통운」이라고 치면 그 한글이 `courierCode`로 나갔다.

    > ★ **여기서 매핑하지 않는다.** 쿠팡 코드표가 아직 없으므로(F44, 오너 캡처 대기)
    > 「이름 → 코드」를 지어내면 그게 발명이다. **코드 모양이 아닌 값이 나가는 것만 막는다.**

    값은 **바꾸지 않는다** — 대소문자 보정조차 하지 않는다(조용한 변형 금지).
    """
    mkt = str(marketplace or "").strip().lower()
    val = str(courier or "").strip()
    if mkt not in _CODE_GATED_MARKETS:
        return ""
    if not val:
        return "택배사를 입력하세요"
    if _COURIER_CODE_RE.match(val):
        return ""
    return (f"쿠팡 코드표의 코드가 필요합니다 — 「{val}」은(는) 택배사 **이름**으로 보입니다. "
            "쿠팡 Wing의 택배사 코드(영문/숫자)를 넣어 주세요.")


def _market_tracking_result(raw) -> tuple:
    """어댑터 반환을 `(성공, 상세)`로 정규화 — F45.

    어댑터마다 반환이 다르다: 쿠팡은 **응답 원문까지** 담은 dict을 주고(F41 규율),
    나머지는 아직 bool이다. **관용 수용**하되, 화면에 나가는 모양은 하나다.
    """
    if isinstance(raw, dict):
        return bool(raw.get("ok")), raw
    return bool(raw), {}


class OrderSyncService:
    """모든 마켓 주문 동기화 + Sheets CRUD 통합 서비스."""

    def __init__(self):
        from .sheets_adapter import OrderSheetsAdapter
        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter

        self.sheets = OrderSheetsAdapter()
        self.adapters = {
            "coupang": CoupangAdapter(),
            "smartstore": SmartStoreAdapter(),
            "11st": ElevenAdapter(),
            # Phase 132: kohganemultishop → woocommerce (kohganemultishop.org 실연동)
            "woocommerce": WooCommerceAdapter(),
            # Phase 206: Shopify 주문수집·배송추적 (GraphQL + client_credentials)
            "shopify": ShopifyAdapter(),
        }

    def sync_all(self, since: datetime = None) -> dict:
        """모든 마켓 주문 동기화."""
        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        results = {}
        for name, adapter in self.adapters.items():
            try:
                orders = adapter.fetch_orders_unified(since=since)
                upserted = self.sheets.bulk_upsert(orders)
                results[name] = {"fetched": len(orders), "upserted": upserted, "status": "ok"}
                logger.info("동기화 완료 [%s]: %d건", name, len(orders))
            except Exception as exc:
                logger.warning("동기화 실패 [%s]: %s", name, exc)
                results[name] = {"error": str(exc), "status": "fail"}

        return results

    def sync_one(self, marketplace: str, since: datetime = None) -> dict:
        """특정 마켓 주문 동기화."""
        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        adapter = self.adapters.get(marketplace)
        if adapter is None:
            return {"status": "fail", "error": f"알 수 없는 마켓: {marketplace}"}

        try:
            orders = adapter.fetch_orders_unified(since=since)
            upserted = self.sheets.bulk_upsert(orders)
            logger.info("단일 마켓 동기화 완료 [%s]: %d건", marketplace, len(orders))
            return {"fetched": len(orders), "upserted": upserted, "status": "ok"}
        except Exception as exc:
            logger.warning("단일 마켓 동기화 실패 [%s]: %s", marketplace, exc)
            return {"error": str(exc), "status": "fail"}

    def update_tracking(
        self,
        order_id: str,
        marketplace: str,
        courier: str,
        tracking_no: str,
    ) -> dict:
        """운송장 업데이트 — **마켓 반영 여부가 정본**이다 (F45).

        ## 무엇이 잘못돼 있었나 (실측 2026-09-21)

        예전 반환은 **`sheets_ok or api_ok`**였다. 쿠팡이 `courierCode`를 거부해도
        **우리 DB 저장만 성공하면 화면은 「성공」**이라고 말했다.
        → **구매자에게 송장이 안 붙었는데 우리는 붙었다고 봤다.**

        > ★★★ **한 필드에 두 뜻을 담지 않는다.** 「우리 쪽에 적혔다」와
        > 「마켓에 반영됐다」는 다른 사실이고, 둘 다 화면에 따로 나가야 한다.

        ## 반환 (dict)

        | 키 | 뜻 |
        |---|---|
        | `ok` | **마켓에 반영됐나** — 이게 정본이다 |
        | `local_ok` | 우리 기록(대장)에 적혔나 |
        | `market_supported` | 이 마켓에 운송장 API 연동이 있나 |
        | `error` | 사람이 읽을 사유(없으면 빈 문자열) |
        | `error_body` | **마켓 응답 원문**(마스킹·300자, F41 규율) |
        | `http_status` | 마켓 응답 코드(있으면) |
        """
        import os

        result = {
            "ok": False, "local_ok": False, "market_supported": True,
            "error": "", "error_body": "", "http_status": None,
        }

        dry_run = os.getenv("ADAPTER_DRY_RUN", "0") == "1"
        if dry_run:
            logger.info("ADAPTER_DRY_RUN=1 — update_tracking 차단됨 (%s, %s)", marketplace, order_id)
            return {**result, "ok": True, "local_ok": True, "error": "ADAPTER_DRY_RUN=1 — 전송하지 않았습니다"}

        # ★ 택배사 코드 관문 — **모든 경로가 여기를 지난다**(단일/일괄 둘 다).
        #   마켓별 업로더마다 따로 막으면 한 곳을 빠뜨리고, 그 마켓으로 한국어가 나간다.
        hold = courier_code_hold(marketplace, courier)
        if hold:
            logger.warning("[운송장] %s 전송 보류 — %s", marketplace, hold)
            return {**result, "error": hold}

        adapter = self.adapters.get(marketplace)
        if adapter is None or not hasattr(adapter, "update_tracking"):
            # 연동 자체가 없다 — 「거부당함」과 **다른 사실**이므로 다른 문장으로 말한다.
            result["market_supported"] = False
            result["error"] = f"{marketplace}는 운송장 API 연동이 없습니다 — 우리 기록에만 남습니다"
        else:
            try:
                raw = adapter.update_tracking(order_id, courier=courier, tracking_no=tracking_no)
                ok, detail = _market_tracking_result(raw)
                result["ok"] = ok
                result["error_body"] = detail.get("body", "")
                result["http_status"] = detail.get("http_status")
                if not ok:
                    result["error"] = detail.get("error") or "마켓이 운송장 등록을 거부했습니다"
            except Exception as exc:
                logger.warning("마켓 API 운송장 등록 실패 [%s]: %s", marketplace, exc)
                result["error"] = f"마켓 호출 중 오류: {type(exc).__name__}"
                result["error_body"] = str(exc)[:300]

        # 우리 기록은 마켓 성패와 **무관하게** 남긴다(추적·재시도의 근거).
        #   단 이것이 `ok`를 만들지는 않는다 — 그게 이 트랙의 요지다.
        result["local_ok"] = bool(self.sheets.update_tracking(order_id, marketplace, courier, tracking_no))

        if not result["ok"]:
            logger.warning("운송장 마켓 미반영: %s/%s — %s (우리 기록=%s)",
                           marketplace, order_id, result["error"], result["local_ok"])
        return result

    def update_status(
        self,
        order_id: str,
        marketplace: str,
        next_status: str,
        *,
        reason: str = "",
    ) -> dict:
        """주문 상태 변경 (외부 연동 실패 시 로컬 상태 우선 반영 + 정직 표기)."""
        next_status = str(next_status or "").strip().lower()
        if not next_status:
            return {"ok": False, "error": "next_status가 필요합니다."}

        adapter = self.adapters.get(marketplace)
        adapter_result = {"applied": False, "simulated": True}

        if adapter and hasattr(adapter, "update_status"):
            try:
                result = adapter.update_status(order_id, next_status, reason=reason)  # type: ignore[attr-defined]
                if isinstance(result, dict):
                    adapter_result["applied"] = bool(result.get("ok") or result.get("applied"))
                    adapter_result["simulated"] = bool(result.get("simulated", not adapter_result["applied"]))
                else:
                    adapter_result["applied"] = bool(result)
                    adapter_result["simulated"] = not bool(result)
            except Exception as exc:
                logger.warning("마켓 API 상태 변경 실패 [%s/%s]: %s", marketplace, order_id, exc)

        note = f"status:{next_status}"
        if reason:
            note = f"{note} ({reason})"
        if adapter_result["simulated"]:
            note = f"{note} [simulation]"

        sheets_ok = self.sheets.update_status(order_id, marketplace, next_status, note=note)
        if not sheets_ok:
            return {"ok": False, "error": "주문 상태 저장에 실패했습니다."}

        return {
            "ok": True,
            "status": next_status,
            "adapter": adapter_result,
            "note": note,
        }

    def list_orders(self, filters: dict = None, limit: int = 50, offset: int = 0):
        """Sheets에서 통합 주문 조회."""
        try:
            return self.sheets.query(filters=filters or {}, limit=limit, offset=offset)
        except Exception as exc:
            logger.warning("list_orders 실패: %s", exc)
            return []

    def kpi_summary(self) -> dict:
        """KPI 요약."""
        try:
            return self.sheets.kpi_summary()
        except Exception as exc:
            logger.warning("kpi_summary 실패: %s", exc)
            return {
                "today_new": 0,
                "pending_ship": 0,
                "shipped": 0,
                "returned_exchanged": 0,
                "source": "error",
            }
