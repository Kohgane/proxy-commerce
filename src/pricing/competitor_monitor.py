"""src/pricing/competitor_monitor.py — Phase 140 경쟁사 가격 모니터링."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_WORKSHEET = "competitor_prices"
_HEADERS = [
    "id",
    "competitor_id",
    "product_id",
    "url",
    "site",
    "price_krw",
    "stock_status",
    "shipping_fee_krw",
    "captured_at",
]
_SUPPORTED_SITES = {
    "coupang": "쿠팡",
    "smartstore": "스마트스토어",
    "11st": "11번가",
    "gmarket": "G마켓",
    "auction": "옥션",
    "amazon": "Amazon JP",
    "rakuten": "라쿠텐",
    "yahoo": "Yahoo Shopping",
}


@dataclass
class CompetitorTarget:
    competitor_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    product_id: str = ""
    name: str = ""
    url: str = ""
    enabled: bool = True
    site: str = "unknown"
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "competitor_id": self.competitor_id,
            "product_id": self.product_id,
            "name": self.name,
            "url": self.url,
            "enabled": self.enabled,
            "site": self.site,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CompetitorTarget":
        return cls(
            competitor_id=str(d.get("competitor_id") or str(uuid.uuid4())),
            product_id=str(d.get("product_id") or ""),
            name=str(d.get("name") or ""),
            url=str(d.get("url") or ""),
            enabled=str(d.get("enabled", "True")).strip().lower() in {"1", "true", "yes"},
            site=str(d.get("site") or "unknown"),
            created_at=str(d.get("created_at") or datetime.now(tz=timezone.utc).isoformat()),
        )


class CompetitorMonitor:
    _LOCK = threading.RLock()

    def __init__(self) -> None:
        fallback_path = Path(os.getenv("COMPETITOR_SCRAPE_FALLBACK_PATH", "data/competitor_prices.jsonl"))
        self._history_path = fallback_path
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        self._targets_path = fallback_path.with_name("competitor_targets.jsonl")
        self._price_alert_threshold = Decimal(os.getenv("PRICING_NOTIFY_THRESHOLD_PCT", "5"))

    # ── Target CRUD ─────────────────────────────────────────────────────

    def list_targets(self, product_id: Optional[str] = None) -> List[CompetitorTarget]:
        rows = self._read_jsonl(self._targets_path)
        out = [CompetitorTarget.from_dict(row) for row in rows]
        if product_id:
            out = [x for x in out if x.product_id == product_id]
        return out

    def create_target(self, payload: dict) -> CompetitorTarget:
        target = CompetitorTarget.from_dict(
            {
                **payload,
                "site": self.detect_site(str(payload.get("url") or "")),
            }
        )
        with self._LOCK:
            rows = self._read_jsonl(self._targets_path)
            rows.append(target.to_dict())
            self._write_jsonl(self._targets_path, rows)
        return target

    def update_target(self, competitor_id: str, payload: dict) -> Optional[CompetitorTarget]:
        with self._LOCK:
            rows = self._read_jsonl(self._targets_path)
            updated: Optional[CompetitorTarget] = None
            for i, row in enumerate(rows):
                if str(row.get("competitor_id")) != competitor_id:
                    continue
                merged = {**row, **payload}
                if "url" in payload:
                    merged["site"] = self.detect_site(str(payload.get("url") or ""))
                updated = CompetitorTarget.from_dict(merged)
                rows[i] = updated.to_dict()
                break
            if updated is None:
                return None
            self._write_jsonl(self._targets_path, rows)
            return updated

    def delete_target(self, competitor_id: str) -> bool:
        with self._LOCK:
            rows = self._read_jsonl(self._targets_path)
            filtered = [r for r in rows if str(r.get("competitor_id")) != competitor_id]
            if len(filtered) == len(rows):
                return False
            self._write_jsonl(self._targets_path, filtered)
            return True

    # ── Monitoring ──────────────────────────────────────────────────────

    def monitor_now(self, competitor_id: Optional[str] = None) -> dict:
        targets = [t for t in self.list_targets() if t.enabled]
        if competitor_id:
            targets = [t for t in targets if t.competitor_id == competitor_id]

        captured = 0
        alerts = 0
        skipped = 0
        for target in targets:
            snapshot = self._capture_target(target)
            if not snapshot:
                skipped += 1
                continue
            captured += 1
            if snapshot.get("alerted"):
                alerts += 1

        return {
            "ok": True,
            "targets": len(targets),
            "captured": captured,
            "alerts": alerts,
            "skipped": skipped,
        }

    def _capture_target(self, target: CompetitorTarget) -> Optional[dict]:
        html = self._fetch_html(target.url)
        if not html:
            return None

        parsed = self._parse_snapshot(target.url, html)
        price = parsed.get("price_krw")
        if price is None:
            return None

        history = self.get_history(target.competitor_id, limit=1)
        prev_price = None
        if history:
            try:
                prev_price = Decimal(str(history[0].get("price_krw")))
            except Exception:
                prev_price = None

        change_pct = Decimal("0")
        alerted = False
        if prev_price and prev_price != 0:
            change_pct = (Decimal(str(price)) - prev_price) / prev_price * Decimal("100")
            if abs(change_pct) >= self._price_alert_threshold:
                alerted = self._send_price_alert(target, prev_price, Decimal(str(price)), change_pct)

        row = {
            "id": str(uuid.uuid4()),
            "competitor_id": target.competitor_id,
            "product_id": target.product_id,
            "url": target.url,
            "site": target.site,
            "price_krw": int(price),
            "stock_status": parsed.get("stock_status", "unknown"),
            "shipping_fee_krw": int(parsed.get("shipping_fee_krw") or 0),
            "captured_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._append_history(row)
        row["change_pct"] = float(round(change_pct, 4))
        row["alerted"] = alerted
        return row

    def get_history(self, competitor_id: Optional[str] = None, limit: int = 200) -> List[dict]:
        rows = self._read_history_from_sheet() or self._read_jsonl(self._history_path)
        if competitor_id:
            rows = [r for r in rows if str(r.get("competitor_id")) == competitor_id]
        rows.sort(key=lambda x: str(x.get("captured_at", "")), reverse=True)
        return rows[:limit]

    def get_price_trend(self, competitor_id: str, points: int = 30) -> List[dict]:
        rows = self.get_history(competitor_id=competitor_id, limit=max(points, 1))
        out = []
        for row in reversed(rows):
            out.append({
                "captured_at": row.get("captured_at"),
                "price_krw": int(float(row.get("price_krw") or 0)),
                "shipping_fee_krw": int(float(row.get("shipping_fee_krw") or 0)),
                "stock_status": str(row.get("stock_status") or "unknown"),
            })
        return out

    def summary_24h(self) -> dict:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        rows = self.get_history(limit=5000)
        recent = []
        for row in rows:
            ts = str(row.get("captured_at") or "")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt >= cutoff:
                    recent.append(row)
            except Exception:
                continue
        competitor_ids = {str(r.get("competitor_id") or "") for r in recent if r.get("competitor_id")}
        return {
            "recent_changes": len(recent),
            "monitored": len(self.list_targets()),
            "active_monitored": len([t for t in self.list_targets() if t.enabled]),
            "recent_competitors": len(competitor_ids),
        }

    def get_lowest_price(self, product_id: str) -> Optional[Decimal]:
        target_ids = {t.competitor_id for t in self.list_targets(product_id=product_id) if t.enabled}
        if not target_ids:
            return None
        rows = self.get_history(limit=3000)
        prices: List[Decimal] = []
        for row in rows:
            if str(row.get("competitor_id")) not in target_ids:
                continue
            try:
                prices.append(Decimal(str(row.get("price_krw"))))
            except Exception:
                continue
        return min(prices) if prices else None

    # ── Scraping ───────────────────────────────────────────────────────

    def detect_site(self, url: str) -> str:
        normalized = (url or "").lower()
        if "coupang" in normalized:
            return "coupang"
        if "smartstore.naver" in normalized:
            return "smartstore"
        if "11st" in normalized:
            return "11st"
        if "gmarket" in normalized:
            return "gmarket"
        if "auction" in normalized:
            return "auction"
        if "amazon.co.jp" in normalized:
            return "amazon"
        if "rakuten" in normalized:
            return "rakuten"
        if "shopping.yahoo" in normalized:
            return "yahoo"
        return "unknown"

    def _fetch_html(self, url: str) -> str:
        try:
            from src.ai.budget import BudgetGuard

            if not BudgetGuard().can_spend(Decimal("0.0001")):
                logger.warning("BudgetGuard 제한으로 스크랩 건너뜀: %s", url)
                return ""
        except Exception:
            pass

        if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
            return ""
        try:
            import requests

            res = requests.get(
                url,
                timeout=10,
                headers={
                    "User-Agent": os.getenv(
                        "SCRAPER_USER_AGENT",
                        "Mozilla/5.0 (compatible; proxy-commerce/1.0)",
                    )
                },
            )
            if res.status_code != 200:
                return ""
            return res.text
        except Exception as exc:
            logger.debug("경쟁사 스크랩 실패 %s: %s", url, exc)
            return ""

    def _parse_snapshot(self, url: str, html: str) -> dict:
        price = self._extract_price(html)
        shipping = self._extract_shipping_fee(html)
        stock = self._extract_stock_status(html)
        return {
            "site": self.detect_site(url),
            "price_krw": price,
            "shipping_fee_krw": shipping,
            "stock_status": stock,
        }

    @staticmethod
    def _extract_price(html: str) -> Optional[int]:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for selector in (
                'meta[property="product:price:amount"]',
                'meta[itemprop="price"]',
                'meta[name="price"]',
            ):
                node = soup.select_one(selector)
                if node and node.get("content"):
                    val = CompetitorMonitor._to_int(node.get("content"))
                    if val is not None:
                        return val
            for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
                text = script.get_text("", strip=True)
                if "price" not in text:
                    continue
                val = CompetitorMonitor._to_int(text)
                if val is not None:
                    return val
        except Exception:
            pass

        return CompetitorMonitor._to_int(html)

    @staticmethod
    def _extract_stock_status(html: str) -> str:
        lower = html.lower()
        if any(x in lower for x in ["품절", "out of stock", "sold out"]):
            return "out"
        if any(x in lower for x in ["재고", "in stock", "available"]):
            return "in"
        return "unknown"

    @staticmethod
    def _extract_shipping_fee(html: str) -> int:
        m = re.search(r"배송비\s*[:：]?\s*([0-9,]{1,12})\s*원", html)
        if m:
            return int(m.group(1).replace(",", ""))
        m2 = re.search(r"shipping\s*[:]?\s*\$?([0-9,.]{1,12})", html, re.IGNORECASE)
        if m2:
            try:
                return int(float(m2.group(1).replace(",", "")))
            except Exception:
                return 0
        return 0

    @staticmethod
    def _to_int(raw: Optional[str]) -> Optional[int]:
        if raw is None:
            return None
        txt = str(raw)
        candidates = re.findall(r"(?<!\d)(\d{2,3}(?:,\d{3})+|\d{3,12})(?!\d)", txt)
        for cand in candidates:
            try:
                num = int(cand.replace(",", ""))
            except Exception:
                continue
            if num >= 100:
                return num
        return None

    # ── Persistence ─────────────────────────────────────────────────────

    def _append_history(self, row: dict) -> None:
        ws = self._open_ws()
        if ws is not None:
            try:
                ws.append_row([row.get(h, "") for h in _HEADERS])
            except Exception as exc:
                logger.debug("competitor_prices 시트 기록 실패(JSONL 폴백): %s", exc)

        with self._LOCK:
            rows = self._read_jsonl(self._history_path)
            rows.append(row)
            self._write_jsonl(self._history_path, rows)

    def _read_history_from_sheet(self) -> List[dict]:
        ws = self._open_ws()
        if ws is None:
            return []
        try:
            return ws.get_all_records()
        except Exception:
            return []

    def _open_ws(self):
        try:
            from src.utils.sheets import get_worksheet

            return get_worksheet(_WORKSHEET, headers=_HEADERS)
        except Exception:
            return None

    def _read_jsonl(self, path: Path) -> List[dict]:
        if not path.exists():
            return []
        out: List[dict] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        out.append(json.loads(raw))
                    except Exception:
                        continue
        except Exception:
            return []
        return out

    def _write_jsonl(self, path: Path, rows: List[dict]) -> None:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(path)

    @staticmethod
    def _send_price_alert(
        target: CompetitorTarget,
        old_price: Decimal,
        new_price: Decimal,
        change_pct: Decimal,
    ) -> bool:
        direction = "상승" if change_pct > 0 else "하락"
        msg = (
            "⚠️ 경쟁사 가격 급변\n"
            f"- 사이트: {_SUPPORTED_SITES.get(target.site, target.site)}\n"
            f"- 대상: {target.name or target.product_id or target.competitor_id}\n"
            f"- 변동: {int(old_price):,}원 → {int(new_price):,}원 ({float(change_pct):+.1f}%, {direction})"
        )
        try:
            from src.notifications.telegram import send_telegram

            return bool(send_telegram(msg, urgency="warning"))
        except Exception:
            return False
