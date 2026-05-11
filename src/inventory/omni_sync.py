"""src/inventory/omni_sync.py — 옴니채널 재고 동기화 (Phase 147).

모드:
  common_pool  — 채널 공통 재고 풀 (한 채널 판매 → 전체 차감)
  per_channel  — 채널별 독립 재고 (각 채널 재고 별도 관리)

환경변수:
  INVENTORY_OMNI_SYNC_MODE           — common_pool | per_channel (기본: common_pool)
  INVENTORY_OMNI_SYNC_INTERVAL_SEC   — 동기화 주기(초) (기본: 60)
  INVENTORY_OMNI_SYNC_ENABLED        — 1 이면 활성 (기본: 0)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)

SYNC_MODE = Literal["common_pool", "per_channel"]

_OMNI_LOG_PATH = os.getenv("OMNI_SYNC_LOG_PATH", "data/omni_sync_log.jsonl")

# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class ChannelStock:
    """단일 채널 재고 정보."""

    channel: str          # coupang | smartstore | 11st | woocommerce | ...
    sku: str
    stock: int
    last_synced_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sync_status: str = "ok"   # ok | delayed | failed
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OmniSyncEvent:
    """재고 동기화 이벤트 로그."""

    event_type: str   # sold | manual_adjust | sync_complete | sync_fail
    channel: str
    sku: str
    delta: int        # 변화량 (음수 = 차감)
    new_stock: int
    mode: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 채널 어댑터 인터페이스
# ---------------------------------------------------------------------------

class ChannelStockAdapter:
    """채널별 재고 조회/업데이트 기본 인터페이스."""

    channel: str = "mock"

    def get_stock(self, sku: str) -> int:
        return 0

    def set_stock(self, sku: str, stock: int) -> bool:
        return True

    def is_configured(self) -> bool:
        return False


class CoupangStockAdapter(ChannelStockAdapter):
    channel = "coupang"

    def is_configured(self) -> bool:
        return bool(os.getenv("COUPANG_VENDOR_ID") and os.getenv("COUPANG_ACCESS_KEY"))

    def get_stock(self, sku: str) -> int:
        try:
            from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter  # type: ignore
            adapter = CoupangAdapter()
            result = adapter.get_inventory(sku)
            return int(result.get("quantity", 0))
        except Exception as exc:
            logger.debug("Coupang 재고 조회 실패 (%s): %s", sku, exc)
            return 0

    def set_stock(self, sku: str, stock: int) -> bool:
        try:
            from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter  # type: ignore
            adapter = CoupangAdapter()
            return adapter.update_inventory(sku, stock)
        except Exception as exc:
            logger.warning("Coupang 재고 업데이트 실패 (%s): %s", sku, exc)
            return False


class SmartstoreStockAdapter(ChannelStockAdapter):
    channel = "smartstore"

    def is_configured(self) -> bool:
        return bool(os.getenv("NAVER_COMMERCE_CLIENT_ID"))

    def get_stock(self, sku: str) -> int:
        try:
            from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter  # type: ignore
            adapter = SmartStoreAdapter()
            result = adapter.get_inventory(sku)
            return int(result.get("quantity", 0))
        except Exception as exc:
            logger.debug("SmartStore 재고 조회 실패 (%s): %s", sku, exc)
            return 0

    def set_stock(self, sku: str, stock: int) -> bool:
        try:
            from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter  # type: ignore
            adapter = SmartStoreAdapter()
            return adapter.update_inventory(sku, stock)
        except Exception as exc:
            logger.warning("SmartStore 재고 업데이트 실패 (%s): %s", sku, exc)
            return False


class ElevenStockAdapter(ChannelStockAdapter):
    channel = "11st"

    def is_configured(self) -> bool:
        return bool(os.getenv("ELEVENST_API_KEY"))

    def get_stock(self, sku: str) -> int:
        return 0  # 11번가 재고 API 추후 연동

    def set_stock(self, sku: str, stock: int) -> bool:
        return False  # 11번가 재고 API 추후 연동


def _build_adapters() -> list[ChannelStockAdapter]:
    return [
        CoupangStockAdapter(),
        SmartstoreStockAdapter(),
        ElevenStockAdapter(),
    ]


# ---------------------------------------------------------------------------
# 동기화 로그 저장소
# ---------------------------------------------------------------------------

class OmniSyncLog:
    def __init__(self, path: str = _OMNI_LOG_PATH):
        self._path = path
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)

    def append(self, event: OmniSyncEvent) -> None:
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("omni_sync 로그 기록 실패: %s", exc)

    def recent(self, limit: int = 100) -> list[dict]:
        if not os.path.exists(self._path):
            return []
        lines = []
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            lines.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except OSError:
            pass
        return lines[-limit:]

    def failure_count_24h(self) -> int:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        return sum(
            1 for r in self.recent(10000)
            if r.get("event_type") == "sync_fail" and r.get("timestamp", "") >= cutoff
        )


# ---------------------------------------------------------------------------
# 옴니채널 동기화 엔진
# ---------------------------------------------------------------------------

class OmniInventorySyncer:
    """옴니채널 재고 동기화 메인 엔진."""

    def __init__(self):
        self._mode: SYNC_MODE = os.getenv("INVENTORY_OMNI_SYNC_MODE", "common_pool")  # type: ignore
        self._enabled = os.getenv("INVENTORY_OMNI_SYNC_ENABLED", "0") == "1"
        self._adapters = _build_adapters()
        self._log = OmniSyncLog()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def enabled(self) -> bool:
        return self._enabled

    def configured_channels(self) -> list[str]:
        return [a.channel for a in self._adapters if a.is_configured()]

    def channel_stocks(self, sku: str) -> list[ChannelStock]:
        """SKU별 각 채널 재고 조회."""
        result = []
        for adapter in self._adapters:
            try:
                qty = adapter.get_stock(sku)
                result.append(ChannelStock(
                    channel=adapter.channel,
                    sku=sku,
                    stock=qty,
                    sync_status="ok" if adapter.is_configured() else "not_configured",
                ))
            except Exception as exc:
                result.append(ChannelStock(
                    channel=adapter.channel,
                    sku=sku,
                    stock=0,
                    sync_status="failed",
                    error=str(exc)[:100],
                ))
        return result

    def on_sale(self, sku: str, sold_qty: int, source_channel: str) -> dict[str, bool]:
        """한 채널에서 판매 발생 → 다른 채널 재고 차감 (이벤트 기반).

        common_pool 모드에서만 동작.
        """
        results: dict[str, bool] = {}
        if not self._enabled:
            logger.debug("옴니 동기화 비활성 (INVENTORY_OMNI_SYNC_ENABLED=0)")
            return results

        if self._mode != "common_pool":
            return results

        for adapter in self._adapters:
            if adapter.channel == source_channel:
                continue
            try:
                current = adapter.get_stock(sku)
                new_stock = max(0, current - sold_qty)
                ok = adapter.set_stock(sku, new_stock)
                results[adapter.channel] = ok
                self._log.append(OmniSyncEvent(
                    event_type="sold",
                    channel=adapter.channel,
                    sku=sku,
                    delta=-sold_qty,
                    new_stock=new_stock,
                    mode=self._mode,
                ))
            except Exception as exc:
                logger.warning("채널 %s 재고 차감 실패 (%s): %s", adapter.channel, sku, exc)
                results[adapter.channel] = False
                self._log.append(OmniSyncEvent(
                    event_type="sync_fail",
                    channel=adapter.channel,
                    sku=sku,
                    delta=-sold_qty,
                    new_stock=-1,
                    mode=self._mode,
                ))
        return results

    def manual_sync(self, sku: str) -> dict[str, int]:
        """수동 동기화 트리거 — 모든 채널 재고 조회 후 공통 풀 기준 통일.

        common_pool: 최대 재고값을 공통 풀로 사용
        per_channel: 각 채널 독립 유지 (조회만)
        """
        stocks = self.channel_stocks(sku)
        channel_qty = {s.channel: s.stock for s in stocks}

        if self._mode == "common_pool":
            max_stock = max(channel_qty.values()) if channel_qty else 0
            for adapter in self._adapters:
                if adapter.is_configured():
                    try:
                        adapter.set_stock(sku, max_stock)
                        self._log.append(OmniSyncEvent(
                            event_type="sync_complete",
                            channel=adapter.channel,
                            sku=sku,
                            delta=0,
                            new_stock=max_stock,
                            mode=self._mode,
                        ))
                    except Exception as exc:
                        logger.warning("수동 동기화 실패 (%s/%s): %s", sku, adapter.channel, exc)

        return channel_qty

    def summary(self) -> dict:
        """진단 카드용 상태 요약."""
        configured = self.configured_channels()
        failure_24h = self._log.failure_count_24h()
        recent_logs = self._log.recent(20)
        return {
            "enabled": self._enabled,
            "mode": self._mode,
            "configured_channels": configured,
            "channel_count": len(configured),
            "failure_24h": failure_24h,
            "recent_log_count": len(recent_logs),
            "sync_interval_sec": int(os.getenv("INVENTORY_OMNI_SYNC_INTERVAL_SEC", "60")),
        }
