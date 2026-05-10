from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


class BIEngine:
    def __init__(self) -> None:
        self._ttl = max(1, int(os.getenv("ANALYTICS_CACHE_TTL_SECONDS", "300")))
        self._fallback = Path(os.getenv("ANALYTICS_FALLBACK_PATH", "data/analytics_cache.jsonl"))
        self._fallback.parent.mkdir(parents=True, exist_ok=True)

    def build_dashboard(self, *, force_refresh: bool = False) -> dict:
        if not force_refresh:
            cached = self._read_cache()
            if cached:
                age = time.time() - float(cached.get("cached_at_ts", 0))
                if age <= self._ttl:
                    return cached["payload"]

        payload = self._compute()
        self._write_cache(payload)
        return payload

    def _compute(self) -> dict:
        orders = self._load_orders()
        products = self._load_products()
        cs_stats = self._load_cs_stats()

        now = datetime.now(timezone.utc)
        total_today = 0
        total_week = 0
        total_month = 0
        by_channel: dict[str, float] = {}
        sales_by_sku: dict[str, dict] = {}
        for row in orders:
            amount = float(row.get("sell_price_krw") or row.get("amount") or row.get("total") or 0)
            channel = str(row.get("channel") or "기타")
            sku = str(row.get("sku") or "unknown")
            dt = _parse_dt(row.get("order_date") or row.get("created_at"))
            if dt is None:
                continue
            by_channel[channel] = by_channel.get(channel, 0.0) + amount
            if dt.date() == now.date():
                total_today += amount
            if (now - dt).days < 7:
                total_week += amount
            if dt.year == now.year and dt.month == now.month:
                total_month += amount
            item = sales_by_sku.setdefault(sku, {"sku": sku, "qty": 0, "revenue": 0.0})
            item["qty"] += 1
            item["revenue"] += amount

        top20 = sorted(sales_by_sku.values(), key=lambda x: x["revenue"], reverse=True)[:20]
        low_stock = []
        over_stock = []
        for p in products:
            stock_qty = int(p.get("stock_qty") or 0)
            if stock_qty <= 5:
                low_stock.append(p)
            if stock_qty >= 100:
                over_stock.append(p)

        return {
            "sales_summary": {
                "today_krw": int(total_today),
                "week_krw": int(total_week),
                "month_krw": int(total_month),
                "channel_share": by_channel,
            },
            "top_products": top20,
            "inventory_alerts": {
                "low_stock": low_stock[:20],
                "over_stock": over_stock[:20],
            },
            "ad_roi": {"channels": [], "roas_threshold": 1.5},
            "quality": cs_stats,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _load_orders(self) -> list[dict]:
        try:
            from src.dashboard.order_status import OrderStatusTracker

            return OrderStatusTracker()._get_all_rows()
        except Exception:
            return []

    def _load_products(self) -> list[dict]:
        try:
            from src.dashboard.web_ui import _load_products

            return _load_products()
        except Exception:
            return []

    def _load_cs_stats(self) -> dict:
        try:
            from src.cs_bot.inbox_store import InboxStore

            stats = InboxStore().stats_24h()
            return {
                "unanswered_24h": int(stats.get("unanswered", 0)),
                "response_rate": float(stats.get("response_rate", 0.0)),
                "avg_response_minutes": float(stats.get("avg_response_minutes", 0.0)),
                "delayed_shipping": 0,
                "refund_rate": 0.0,
            }
        except Exception:
            return {
                "unanswered_24h": 0,
                "response_rate": 0.0,
                "avg_response_minutes": 0.0,
                "delayed_shipping": 0,
                "refund_rate": 0.0,
            }

    def _write_cache(self, payload: dict) -> None:
        row = {"cached_at_ts": time.time(), "payload": payload}
        tmp = self._fallback.with_suffix(f"{self._fallback.suffix}.tmp.{os.getpid()}")
        with tmp.open("w", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._fallback)

    def _read_cache(self) -> dict | None:
        if not self._fallback.exists():
            return None
        try:
            with self._fallback.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if raw:
                        return json.loads(raw)
        except Exception:
            return None
        return None


def _parse_dt(raw) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
