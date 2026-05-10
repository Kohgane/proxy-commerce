"""src/marketing/discount_campaign.py — Phase 142 할인 캠페인 자동화.

재고 과잉 SKU를 자동 추출하고 할인율을 추천한다.
마진 가드(Phase 140)를 통과하는 캠페인만 생성한다.

환경변수:
  DISCOUNT_CAMPAIGN_ENABLED=1          활성화 (기본: 0)
  DISCOUNT_CAMPAIGN_MAX_PCT=20         최대 할인율 (기본: 20%)
  DISCOUNT_CAMPAIGN_MARGIN_FLOOR_PCT=10 마진 하한선 (기본: 10%)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("DISCOUNT_CAMPAIGN_ENABLED", "0") == "1"
_MAX_DISCOUNT_PCT = int(os.getenv("DISCOUNT_CAMPAIGN_MAX_PCT", "20"))
_MARGIN_FLOOR_PCT = int(os.getenv("DISCOUNT_CAMPAIGN_MARGIN_FLOOR_PCT", "10"))

# 재고 과잉 기준: 판매 속도 대비 N일 이상의 재고
_OVERSTOCK_DAYS_THRESHOLD = int(os.getenv("DISCOUNT_CAMPAIGN_OVERSTOCK_DAYS", "60"))

# 할인율 계산 상수
# 30일 기준(TARGET_STOCK_DAYS)으로 할인율 결정:
# 재고일수가 TARGET_STOCK_DAYS보다 DISCOUNT_SCALING_FACTOR일 초과할 때마다 1% 추가 할인
_TARGET_STOCK_DAYS = 30          # 재고 회전 목표 일수
_DISCOUNT_SCALING_FACTOR = 10    # 재고일수 N일 초과당 1% 추가 할인
_MIN_SALES_VELOCITY = 0.01       # 판매 속도 최솟값 (0 나누기 방지)


@dataclass
class DiscountCampaign:
    """할인 캠페인."""

    sku: str
    title: str
    market: str           # "coupang" / "smartstore" / "global"
    original_price_krw: int
    discount_pct: float
    discounted_price_krw: int
    margin_pct_after: float
    current_stock: int
    campaign_type: str = "immediate"  # immediate / coupon
    status: str = "recommended"       # recommended / active / expired / rejected
    reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "title": self.title,
            "market": self.market,
            "original_price_krw": self.original_price_krw,
            "discount_pct": self.discount_pct,
            "discounted_price_krw": self.discounted_price_krw,
            "margin_pct_after": self.margin_pct_after,
            "current_stock": self.current_stock,
            "campaign_type": self.campaign_type,
            "status": self.status,
            "reason": self.reason,
            "created_at": self.created_at,
        }

    @property
    def margin_guard_passed(self) -> bool:
        return self.margin_pct_after >= _MARGIN_FLOOR_PCT


class DiscountCampaignEngine:
    """Phase 142 할인 캠페인 자동화 엔진."""

    def summary(self) -> dict:
        """진단 대시보드용 요약 정보."""
        enabled = os.getenv("DISCOUNT_CAMPAIGN_ENABLED", "0") == "1"
        recommended = self._get_recommendations()
        active = [c for c in recommended if c.status == "active"]
        overstocked = self._get_overstocked_skus()
        return {
            "enabled": enabled,
            "recommended_count": len(recommended),
            "active_count": len(active),
            "overstocked_skus": len(overstocked),
        }

    def get_recommendations(self) -> list[dict]:
        """추천 캠페인 목록 반환."""
        return [c.to_dict() for c in self._get_recommendations()]

    def get_active_campaigns(self) -> list[dict]:
        """활성 캠페인 목록 반환."""
        return [c.to_dict() for c in self._get_recommendations() if c.status == "active"]

    def approve_campaign(self, sku: str, market: str) -> dict:
        """캠페인 승인 및 마켓 적용 (마진 가드 통과 필요)."""
        campaigns = [c for c in self._get_recommendations() if c.sku == sku and c.market == market]
        if not campaigns:
            return {"ok": False, "error": "캠페인을 찾을 수 없습니다"}

        campaign = campaigns[0]
        if not campaign.margin_guard_passed:
            return {
                "ok": False,
                "error": f"마진 가드 실패: 할인 후 마진 {campaign.margin_pct_after:.1f}% < 최저 {_MARGIN_FLOOR_PCT}%",
            }

        campaign.status = "active"
        self._apply_to_market(campaign)
        logger.info("캠페인 승인: %s %s %.0f%% 할인", sku, market, campaign.discount_pct)
        return {"ok": True, "campaign": campaign.to_dict()}

    def _get_overstocked_skus(self) -> list[dict]:
        """재고 과잉 SKU 목록."""
        result = []
        try:
            from src.inventory.inventory_sync import InventorySync
            sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
            sync = InventorySync(sheet_id=sheet_id)
            rows = sync._get_active_rows() if hasattr(sync, "_get_active_rows") else []
            for row in rows:
                stock = int(row.get("stock") or row.get("quantity") or 0)
                velocity = float(row.get("sales_velocity") or _MIN_SALES_VELOCITY)
                days_left = stock / velocity if velocity > 0 else 9999
                if days_left > _OVERSTOCK_DAYS_THRESHOLD:
                    result.append({
                        "sku": str(row.get("sku") or ""),
                        "title": str(row.get("title") or row.get("name") or ""),
                        "stock": stock,
                        "days_of_stock": round(days_left, 1),
                        "sell_price_krw": int(row.get("sell_price_krw") or 0),
                        "margin_pct": float(row.get("margin_pct") or 0),
                        "buy_price_krw": int(row.get("buy_price_krw") or row.get("cost_krw") or 0),
                    })
        except Exception as exc:
            logger.debug("재고 과잉 SKU 조회 실패: %s", exc)
        return result

    def _get_recommendations(self) -> list[DiscountCampaign]:
        """추천 캠페인 목록 생성."""
        overstocked = self._get_overstocked_skus()
        campaigns = []
        for item in overstocked:
            sell_price = item.get("sell_price_krw", 0)
            buy_price = item.get("buy_price_krw", 0)
            current_margin = item.get("margin_pct", 0.0)

            if sell_price <= 0:
                continue

            # 최적 할인율: 재고 회전 목표(30일) 기준 산정
            days_of_stock = item.get("days_of_stock", 60)
            # 재고일수가 TARGET_STOCK_DAYS 초과할수록 더 많이 할인
            # (재고일수 - TARGET_STOCK_DAYS) / DISCOUNT_SCALING_FACTOR % 추가 할인
            # (최소 5%, 최대 MAX_PCT)
            suggested_pct = min(
                _MAX_DISCOUNT_PCT,
                max(5, round((days_of_stock - _TARGET_STOCK_DAYS) / _DISCOUNT_SCALING_FACTOR)),
            )

            discounted_price = int(sell_price * (1 - suggested_pct / 100))
            if buy_price > 0:
                margin_after = round((discounted_price - buy_price) / discounted_price * 100, 1)
            else:
                # 현재 마진에서 할인율의 절반만큼 차감 (근사, buy_price 미확인 시)
                margin_after = round(current_margin - suggested_pct * 0.5, 1)

            if margin_after < _MARGIN_FLOOR_PCT:
                # 마진 가드 통과하도록 할인율 조정
                if buy_price > 0:
                    max_discount_price = int(buy_price / (1 - _MARGIN_FLOOR_PCT / 100))
                    if max_discount_price >= sell_price:
                        continue  # 할인 불가
                    adjusted_pct = round((sell_price - max_discount_price) / sell_price * 100, 1)
                    if adjusted_pct < 3:
                        continue  # 의미 없는 할인
                    suggested_pct = adjusted_pct
                    discounted_price = int(sell_price * (1 - suggested_pct / 100))
                    margin_after = _MARGIN_FLOOR_PCT

            # 쿠팡 / 스마트스토어 캠페인 생성
            for market in ("coupang", "smartstore"):
                campaigns.append(DiscountCampaign(
                    sku=item["sku"],
                    title=item.get("title", item["sku"]),
                    market=market,
                    original_price_krw=sell_price,
                    discount_pct=suggested_pct,
                    discounted_price_krw=discounted_price,
                    margin_pct_after=margin_after,
                    current_stock=item.get("stock", 0),
                    campaign_type="coupon" if market == "coupang" else "immediate",
                    reason=f"재고 {days_of_stock:.0f}일 분량 ({_OVERSTOCK_DAYS_THRESHOLD}일 초과)",
                ))

        return campaigns

    def _apply_to_market(self, campaign: DiscountCampaign) -> None:
        """마켓에 할인가 적용 (어댑터 연동)."""
        try:
            module_map = {
                "coupang": "src.seller_console.market_adapters.coupang_adapter",
                "smartstore": "src.seller_console.market_adapters.smartstore_adapter",
            }
            cls_map = {
                "coupang": "CoupangAdapter",
                "smartstore": "SmartStoreAdapter",
            }
            import importlib
            mod = importlib.import_module(module_map[campaign.market])
            adapter = getattr(mod, cls_map[campaign.market])()
            if hasattr(adapter, "update_price"):
                adapter.update_price(campaign.sku, campaign.discounted_price_krw)
                logger.info("마켓 가격 업데이트: %s %s → ₩%d", campaign.sku, campaign.market, campaign.discounted_price_krw)
        except Exception as exc:
            logger.warning("마켓 가격 적용 실패 (%s %s): %s", campaign.sku, campaign.market, exc)
