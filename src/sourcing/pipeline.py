"""src/sourcing/pipeline.py — 소싱 파이프라인 자동화 (Phase 143).

라쿠텐/아마존JP/Yahoo Shopping 키워드/카테고리 watch 기반 신상품·할인 자동 발견,
마진 시뮬레이션 통과 시 후보 큐 적재, 운영자 승인 후 본 등록.

환경변수:
  SOURCING_WATCH_INTERVAL_MINUTES=60    감시 주기 (분, 기본 60)
  SOURCING_AUTO_QUEUE_MIN_MARGIN_PCT=15 자동 큐 최소 마진율 (기본 15%)
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_WATCH_INTERVAL_MINUTES = int(os.getenv("SOURCING_WATCH_INTERVAL_MINUTES", "60"))
_MIN_MARGIN_PCT = float(os.getenv("SOURCING_AUTO_QUEUE_MIN_MARGIN_PCT", "15"))

# 플랫폼별 환율 대략치 (실제 운영 시 FX API 연동)
_FX_RATES: Dict[str, float] = {
    "JPY": 9.0,    # ¥1 ≈ ₩9
    "CNY": 185.0,  # ¥1 ≈ ₩185 (위안)
    "USD": 1330.0,
}

# 플랫폼별 수수료율
_PLATFORM_FEE_RATES: Dict[str, float] = {
    "rakuten": 0.10,
    "amazon_jp": 0.08,
    "yahoo_shopping": 0.08,
    "taobao": 0.05,
    "1688": 0.04,
    "alibaba": 0.05,
    "default": 0.08,
}

# 배송비 (원)
_SHIPPING_COST_KRW: int = 5_000

# 광고비 추정율
_AD_COST_RATE: float = 0.05


# ---------------------------------------------------------------------------
# 도메인 모델
# ---------------------------------------------------------------------------

@dataclass
class SourcingWatch:
    """등록된 watch 항목 — 키워드/카테고리 기반 모니터링."""

    watch_id: str
    platform: str           # rakuten / amazon_jp / yahoo_shopping
    keyword: str
    category: str = ""
    currency: str = "JPY"
    min_price: float = 0.0
    max_price: float = 0.0  # 0 = 상한 없음
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_checked_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "watch_id": self.watch_id,
            "platform": self.platform,
            "keyword": self.keyword,
            "category": self.category,
            "currency": self.currency,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "active": self.active,
            "created_at": self.created_at,
            "last_checked_at": self.last_checked_at,
            "metadata": self.metadata,
        }


@dataclass
class Candidate:
    """소싱 후보 상품."""

    candidate_id: str
    watch_id: str
    platform: str
    product_name: str
    product_url: str
    source_price: float
    currency: str
    source_price_krw: float
    estimated_selling_price_krw: float
    estimated_margin_pct: float
    image_urls: List[str] = field(default_factory=list)
    category: str = ""
    status: str = "pending"        # pending / approved / rejected / listed
    is_new: bool = True            # 신상품 여부
    is_discounted: bool = False    # 할인 감지
    discount_pct: float = 0.0
    queue_reason: str = ""
    approved_at: Optional[str] = None
    listed_at: Optional[str] = None
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "watch_id": self.watch_id,
            "platform": self.platform,
            "product_name": self.product_name,
            "product_url": self.product_url,
            "source_price": self.source_price,
            "currency": self.currency,
            "source_price_krw": self.source_price_krw,
            "estimated_selling_price_krw": self.estimated_selling_price_krw,
            "estimated_margin_pct": round(self.estimated_margin_pct, 1),
            "image_urls": self.image_urls,
            "category": self.category,
            "status": self.status,
            "is_new": self.is_new,
            "is_discounted": self.is_discounted,
            "discount_pct": self.discount_pct,
            "queue_reason": self.queue_reason,
            "approved_at": self.approved_at,
            "listed_at": self.listed_at,
            "discovered_at": self.discovered_at,
            "metadata": self.metadata,
        }


@dataclass
class MarginSim:
    """마진 시뮬레이션 결과."""

    candidate_id: str
    source_cost_krw: float
    fx_rate: float
    platform_fee_krw: float
    shipping_cost_krw: float
    ad_cost_krw: float
    total_cost_krw: float
    selling_price_krw: float
    gross_profit_krw: float
    margin_pct: float
    passes_threshold: bool
    min_margin_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_cost_krw": round(self.source_cost_krw),
            "fx_rate": self.fx_rate,
            "platform_fee_krw": round(self.platform_fee_krw),
            "shipping_cost_krw": self.shipping_cost_krw,
            "ad_cost_krw": round(self.ad_cost_krw),
            "total_cost_krw": round(self.total_cost_krw),
            "selling_price_krw": round(self.selling_price_krw),
            "gross_profit_krw": round(self.gross_profit_krw),
            "margin_pct": round(self.margin_pct, 1),
            "passes_threshold": self.passes_threshold,
            "min_margin_pct": self.min_margin_pct,
        }


# ---------------------------------------------------------------------------
# WatchStore — watch CRUD (메모리 + 향후 Sheets 연동)
# ---------------------------------------------------------------------------

class WatchStore:
    """소싱 watch CRUD 저장소."""

    def __init__(self) -> None:
        self._watches: Dict[str, SourcingWatch] = {}

    # ── 내부 Sheets 연동 (graceful) ───────────────────────────────────────

    def _try_load_sheets(self) -> None:
        """Sheets에서 watch 목록 로드 (실패해도 무시)."""
        try:
            from src.utils.sheets import get_worksheet
            ws = get_worksheet("sourcing_watches", headers=[
                "watch_id", "platform", "keyword", "category", "currency",
                "min_price", "max_price", "active", "created_at", "last_checked_at",
            ])
            rows = ws.get_all_records()
            for row in rows:
                wid = row.get("watch_id", "")
                if wid and wid not in self._watches:
                    self._watches[wid] = SourcingWatch(
                        watch_id=wid,
                        platform=row.get("platform", ""),
                        keyword=row.get("keyword", ""),
                        category=row.get("category", ""),
                        currency=row.get("currency", "JPY"),
                        min_price=float(row.get("min_price", 0) or 0),
                        max_price=float(row.get("max_price", 0) or 0),
                        active=str(row.get("active", "1")) == "1",
                        created_at=row.get("created_at", datetime.now(timezone.utc).isoformat()),
                        last_checked_at=row.get("last_checked_at") or None,
                    )
        except Exception as exc:
            logger.debug("WatchStore Sheets 로드 스킵: %s", exc)

    def _try_append_sheets(self, watch: SourcingWatch) -> None:
        try:
            from src.utils.sheets import get_worksheet
            ws = get_worksheet("sourcing_watches", headers=[
                "watch_id", "platform", "keyword", "category", "currency",
                "min_price", "max_price", "active", "created_at", "last_checked_at",
            ])
            ws.append_row([
                watch.watch_id, watch.platform, watch.keyword, watch.category,
                watch.currency, watch.min_price, watch.max_price,
                "1" if watch.active else "0",
                watch.created_at, watch.last_checked_at or "",
            ])
        except Exception as exc:
            logger.debug("WatchStore Sheets append 스킵: %s", exc)

    # ── 공개 API ─────────────────────────────────────────────────────────

    def add(
        self,
        platform: str,
        keyword: str,
        category: str = "",
        currency: str = "JPY",
        min_price: float = 0.0,
        max_price: float = 0.0,
    ) -> SourcingWatch:
        """watch 등록."""
        if not platform or not keyword:
            raise ValueError("platform과 keyword는 필수입니다.")
        watch = SourcingWatch(
            watch_id=str(uuid.uuid4())[:12],
            platform=platform.lower(),
            keyword=keyword,
            category=category,
            currency=currency.upper(),
            min_price=min_price,
            max_price=max_price,
        )
        self._watches[watch.watch_id] = watch
        self._try_append_sheets(watch)
        logger.info("WatchStore.add: %s / %s / %s", watch.watch_id, platform, keyword)
        return watch

    def get(self, watch_id: str) -> Optional[SourcingWatch]:
        return self._watches.get(watch_id)

    def list_all(self, active_only: bool = False) -> List[SourcingWatch]:
        self._try_load_sheets()
        watches = list(self._watches.values())
        if active_only:
            watches = [w for w in watches if w.active]
        return sorted(watches, key=lambda w: w.created_at, reverse=True)

    def deactivate(self, watch_id: str) -> bool:
        watch = self._watches.get(watch_id)
        if watch is None:
            return False
        watch.active = False
        return True

    def delete(self, watch_id: str) -> bool:
        if watch_id in self._watches:
            del self._watches[watch_id]
            return True
        return False

    def mark_checked(self, watch_id: str) -> None:
        watch = self._watches.get(watch_id)
        if watch:
            watch.last_checked_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CandidateQueue — 후보 큐 저장소
# ---------------------------------------------------------------------------

class CandidateQueue:
    """소싱 후보 큐."""

    def __init__(self) -> None:
        self._candidates: Dict[str, Candidate] = {}

    def enqueue(self, candidate: Candidate) -> None:
        self._candidates[candidate.candidate_id] = candidate

    def get(self, candidate_id: str) -> Optional[Candidate]:
        return self._candidates.get(candidate_id)

    def list_all(self, status: Optional[str] = None) -> List[Candidate]:
        items = list(self._candidates.values())
        if status:
            items = [c for c in items if c.status == status]
        return sorted(items, key=lambda c: c.discovered_at, reverse=True)

    def approve(self, candidate_id: str) -> Optional[Candidate]:
        c = self._candidates.get(candidate_id)
        if c is None:
            return None
        c.status = "approved"
        c.approved_at = datetime.now(timezone.utc).isoformat()
        return c

    def reject(self, candidate_id: str, reason: str = "") -> Optional[Candidate]:
        c = self._candidates.get(candidate_id)
        if c is None:
            return None
        c.status = "rejected"
        c.metadata["reject_reason"] = reason
        return c

    def bulk_approve(self, candidate_ids: List[str]) -> List[Candidate]:
        return [c for cid in candidate_ids if (c := self.approve(cid)) is not None]

    def mark_listed(self, candidate_id: str) -> Optional[Candidate]:
        c = self._candidates.get(candidate_id)
        if c is None:
            return None
        c.status = "listed"
        c.listed_at = datetime.now(timezone.utc).isoformat()
        return c

    def stats(self) -> Dict[str, Any]:
        all_c = list(self._candidates.values())
        now = datetime.now(timezone.utc)
        last_24h = [
            c for c in all_c
            if (now - datetime.fromisoformat(c.discovered_at.replace("Z", "+00:00"))).total_seconds() < 86400
        ]
        margins = [c.estimated_margin_pct for c in all_c if c.estimated_margin_pct > 0]
        return {
            "total": len(all_c),
            "pending": sum(1 for c in all_c if c.status == "pending"),
            "approved": sum(1 for c in all_c if c.status == "approved"),
            "rejected": sum(1 for c in all_c if c.status == "rejected"),
            "listed": sum(1 for c in all_c if c.status == "listed"),
            "last_24h": len(last_24h),
            "avg_margin_pct": round(sum(margins) / len(margins), 1) if margins else 0.0,
        }


# ---------------------------------------------------------------------------
# 파이프라인 함수 — 공개 API
# ---------------------------------------------------------------------------

_watch_store = WatchStore()
_candidate_queue = CandidateQueue()


def get_watch_store() -> WatchStore:
    return _watch_store


def get_candidate_queue() -> CandidateQueue:
    return _candidate_queue


# 샘플 상품 데이터 (stub — 실제 운영 시 Rakuten/Amazon API 연동)
_STUB_PRODUCTS: Dict[str, List[Dict[str, Any]]] = {
    "rakuten": [
        {"name": "ユニクロ ウルトラライトダウン", "price": 5990, "currency": "JPY", "url": "https://item.rakuten.co.jp/dummy/1", "is_new": True, "is_discounted": False, "category": "패션", "images": ["https://example.com/img1.jpg"]},
        {"name": "キヤノン EOS R50 ミラーレス", "price": 89000, "currency": "JPY", "url": "https://item.rakuten.co.jp/dummy/2", "is_new": False, "is_discounted": True, "discount_pct": 15.0, "category": "전자기기", "images": []},
        {"name": "資生堂 エッセンス 50ml", "price": 3200, "currency": "JPY", "url": "https://item.rakuten.co.jp/dummy/3", "is_new": True, "is_discounted": False, "category": "뷰티", "images": []},
    ],
    "amazon_jp": [
        {"name": "Anker PowerCore 10000", "price": 3299, "currency": "JPY", "url": "https://www.amazon.co.jp/dp/dummy1", "is_new": True, "is_discounted": False, "category": "전자기기", "images": []},
        {"name": "TORRAS iPhone ケース", "price": 1580, "currency": "JPY", "url": "https://www.amazon.co.jp/dp/dummy2", "is_new": False, "is_discounted": True, "discount_pct": 20.0, "category": "전자기기", "images": []},
    ],
    "yahoo_shopping": [
        {"name": "ムーミン 保温マグカップ", "price": 2800, "currency": "JPY", "url": "https://store.shopping.yahoo.co.jp/dummy/1", "is_new": True, "is_discounted": False, "category": "주방용품", "images": []},
    ],
}


def discover_candidates(watch_id: str) -> List[Candidate]:
    """등록된 watch 기준 신규·할인 상품 발견.

    실제 운영 시 Rakuten Product API / Amazon PA-API / Yahoo Shopping API 연동.
    현재는 stub 데이터 반환.
    """
    watch = _watch_store.get(watch_id)
    if watch is None:
        raise ValueError(f"watch_id를 찾을 수 없습니다: {watch_id}")
    if not watch.active:
        raise ValueError(f"비활성 watch입니다: {watch_id}")

    platform = watch.platform
    stub_items = _STUB_PRODUCTS.get(platform, _STUB_PRODUCTS["rakuten"])

    # 키워드 필터 (대소문자 무시)
    keyword_lower = watch.keyword.lower()
    filtered = [
        item for item in stub_items
        if keyword_lower in item["name"].lower() or not keyword_lower
    ] or stub_items  # 키워드 미매칭 시 전체 반환 (stub)

    # 가격 필터
    if watch.max_price > 0:
        filtered = [i for i in filtered if i["price"] <= watch.max_price]
    if watch.min_price > 0:
        filtered = [i for i in filtered if i["price"] >= watch.min_price]

    candidates: List[Candidate] = []
    fx = _FX_RATES.get(watch.currency, _FX_RATES["JPY"])

    for item in filtered:
        source_price = item["price"]
        source_krw = source_price * fx
        selling_price = source_krw * 2.5  # 마크업 2.5x (stub)

        platform_fee_rate = _PLATFORM_FEE_RATES.get(platform, _PLATFORM_FEE_RATES["default"])
        total_cost = source_krw * (1 + platform_fee_rate) + _SHIPPING_COST_KRW + selling_price * _AD_COST_RATE
        margin = (selling_price - total_cost) / selling_price * 100 if selling_price > 0 else 0.0

        cid = str(uuid.uuid4())[:12]
        c = Candidate(
            candidate_id=cid,
            watch_id=watch_id,
            platform=platform,
            product_name=item["name"],
            product_url=item["url"],
            source_price=source_price,
            currency=item.get("currency", watch.currency),
            source_price_krw=round(source_krw, 0),
            estimated_selling_price_krw=round(selling_price, 0),
            estimated_margin_pct=round(margin, 1),
            image_urls=item.get("images", []),
            category=item.get("category", watch.category),
            is_new=item.get("is_new", True),
            is_discounted=item.get("is_discounted", False),
            discount_pct=item.get("discount_pct", 0.0),
        )
        candidates.append(c)

    _watch_store.mark_checked(watch_id)
    logger.info(
        "discover_candidates: watch=%s platform=%s keyword=%s → %d건",
        watch_id, platform, watch.keyword, len(candidates),
    )
    return candidates


def simulate_margin(candidate: Candidate) -> MarginSim:
    """소싱가 + FX + 수수료 + 배송비 + 광고비 추정 → 예상 마진."""
    fx = _FX_RATES.get(candidate.currency, _FX_RATES["JPY"])
    source_krw = candidate.source_price * fx
    fee_rate = _PLATFORM_FEE_RATES.get(candidate.platform, _PLATFORM_FEE_RATES["default"])
    platform_fee_krw = source_krw * fee_rate
    selling_price = candidate.estimated_selling_price_krw or source_krw * 2.5
    ad_cost_krw = selling_price * _AD_COST_RATE
    total_cost = source_krw + platform_fee_krw + _SHIPPING_COST_KRW + ad_cost_krw
    gross_profit = selling_price - total_cost
    margin_pct = gross_profit / selling_price * 100 if selling_price > 0 else 0.0

    return MarginSim(
        candidate_id=candidate.candidate_id,
        source_cost_krw=source_krw,
        fx_rate=fx,
        platform_fee_krw=platform_fee_krw,
        shipping_cost_krw=float(_SHIPPING_COST_KRW),
        ad_cost_krw=ad_cost_krw,
        total_cost_krw=total_cost,
        selling_price_krw=selling_price,
        gross_profit_krw=gross_profit,
        margin_pct=margin_pct,
        passes_threshold=margin_pct >= _MIN_MARGIN_PCT,
        min_margin_pct=_MIN_MARGIN_PCT,
    )


def queue_candidate(candidate: Candidate) -> str:
    """후보 큐에 적재. 운영자 승인 대기.

    Returns:
        candidate_id
    """
    sim = simulate_margin(candidate)
    if not sim.passes_threshold:
        logger.info(
            "queue_candidate 스킵 (마진 미달): %s %.1f%% < %.1f%%",
            candidate.candidate_id, sim.margin_pct, _MIN_MARGIN_PCT,
        )
        candidate.status = "rejected"
        candidate.metadata["reject_reason"] = f"마진 미달: {sim.margin_pct:.1f}% < {_MIN_MARGIN_PCT}%"
    else:
        candidate.queue_reason = f"마진 {sim.margin_pct:.1f}% ≥ {_MIN_MARGIN_PCT}% 기준 통과"
        candidate.status = "pending"
        _candidate_queue.enqueue(candidate)
        logger.info("queue_candidate: %s → 큐 적재", candidate.candidate_id)

    return candidate.candidate_id


def run_watch_cycle(watch_id: str) -> Dict[str, Any]:
    """단일 watch 전체 사이클 실행: 발견 → 시뮬레이션 → 큐 적재."""
    candidates = discover_candidates(watch_id)
    queued: List[str] = []
    skipped: List[str] = []
    for c in candidates:
        cid = queue_candidate(c)
        if c.status == "pending":
            queued.append(cid)
        else:
            skipped.append(cid)
    return {
        "watch_id": watch_id,
        "discovered": len(candidates),
        "queued": len(queued),
        "skipped_low_margin": len(skipped),
        "queued_ids": queued,
    }


def pipeline_stats() -> Dict[str, Any]:
    """파이프라인 전체 통계 (diagnostics 카드용)."""
    watches = _watch_store.list_all()
    active_watches = [w for w in watches if w.active]
    queue_stats = _candidate_queue.stats()
    return {
        "active_watches": len(active_watches),
        "total_watches": len(watches),
        "candidates_24h": queue_stats.get("last_24h", 0),
        "pending_approval": queue_stats.get("pending", 0),
        "auto_listed": queue_stats.get("listed", 0),
        "avg_margin_pct": queue_stats.get("avg_margin_pct", 0.0),
        "watch_interval_minutes": _WATCH_INTERVAL_MINUTES,
        "min_margin_pct": _MIN_MARGIN_PCT,
    }
