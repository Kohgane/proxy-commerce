"""tests/test_sourcing_pipeline.py — Phase 143: 소싱 파이프라인 테스트."""
from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def watch_store():
    from src.sourcing.pipeline import WatchStore
    return WatchStore()


@pytest.fixture
def candidate_queue():
    from src.sourcing.pipeline import CandidateQueue
    return CandidateQueue()


@pytest.fixture
def fresh_pipeline(monkeypatch):
    """격리된 파이프라인 인스턴스."""
    from src.sourcing import pipeline as p
    store = p.WatchStore()
    queue = p.CandidateQueue()
    monkeypatch.setattr(p, "_watch_store", store)
    monkeypatch.setattr(p, "_candidate_queue", queue)
    return store, queue


# ═══════════════════════════════════════════════════════════════════════════════
# SourcingWatch
# ═══════════════════════════════════════════════════════════════════════════════

class TestSourcingWatch:
    def test_to_dict_has_required_keys(self):
        from src.sourcing.pipeline import SourcingWatch
        from datetime import datetime, timezone
        w = SourcingWatch(
            watch_id="abc123",
            platform="rakuten",
            keyword="テスト",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        d = w.to_dict()
        for key in ("watch_id", "platform", "keyword", "category", "currency", "active"):
            assert key in d

    def test_defaults(self):
        from src.sourcing.pipeline import SourcingWatch
        from datetime import datetime, timezone
        w = SourcingWatch(watch_id="x", platform="rakuten", keyword="test", created_at=datetime.now(timezone.utc).isoformat())
        assert w.active is True
        assert w.currency == "JPY"
        assert w.min_price == 0.0
        assert w.max_price == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# WatchStore
# ═══════════════════════════════════════════════════════════════════════════════

class TestWatchStore:
    def test_add_returns_watch(self, watch_store):
        w = watch_store.add(platform="rakuten", keyword="ユニクロ")
        assert w.watch_id
        assert w.platform == "rakuten"
        assert w.keyword == "ユニクロ"

    def test_add_validates_platform(self, watch_store):
        with pytest.raises(ValueError):
            watch_store.add(platform="", keyword="test")

    def test_add_validates_keyword(self, watch_store):
        with pytest.raises(ValueError):
            watch_store.add(platform="rakuten", keyword="")

    def test_get_returns_watch(self, watch_store):
        w = watch_store.add(platform="amazon_jp", keyword="Anker")
        retrieved = watch_store.get(w.watch_id)
        assert retrieved is not None
        assert retrieved.keyword == "Anker"

    def test_get_unknown_returns_none(self, watch_store):
        assert watch_store.get("nonexistent") is None

    def test_list_all(self, watch_store):
        watch_store.add(platform="rakuten", keyword="A")
        watch_store.add(platform="rakuten", keyword="B")
        watches = watch_store.list_all()
        assert len(watches) >= 2

    def test_list_all_active_only(self, watch_store):
        w1 = watch_store.add(platform="rakuten", keyword="active")
        w2 = watch_store.add(platform="rakuten", keyword="inactive")
        watch_store.deactivate(w2.watch_id)
        active = watch_store.list_all(active_only=True)
        ids = [w.watch_id for w in active]
        assert w1.watch_id in ids
        assert w2.watch_id not in ids

    def test_deactivate(self, watch_store):
        w = watch_store.add(platform="rakuten", keyword="test")
        result = watch_store.deactivate(w.watch_id)
        assert result is True
        assert watch_store.get(w.watch_id).active is False

    def test_deactivate_unknown(self, watch_store):
        assert watch_store.deactivate("bogus") is False

    def test_delete(self, watch_store):
        w = watch_store.add(platform="rakuten", keyword="del")
        result = watch_store.delete(w.watch_id)
        assert result is True
        assert watch_store.get(w.watch_id) is None

    def test_delete_unknown(self, watch_store):
        assert watch_store.delete("bogus") is False

    def test_mark_checked(self, watch_store):
        w = watch_store.add(platform="rakuten", keyword="check")
        assert w.last_checked_at is None
        watch_store.mark_checked(w.watch_id)
        assert watch_store.get(w.watch_id).last_checked_at is not None

    def test_add_with_currency(self, watch_store):
        w = watch_store.add(platform="yahoo_shopping", keyword="test", currency="usd")
        assert w.currency == "USD"

    def test_add_with_price_range(self, watch_store):
        w = watch_store.add(platform="rakuten", keyword="test", min_price=1000.0, max_price=5000.0)
        assert w.min_price == 1000.0
        assert w.max_price == 5000.0


# ═══════════════════════════════════════════════════════════════════════════════
# Candidate
# ═══════════════════════════════════════════════════════════════════════════════

class TestCandidate:
    def _make_candidate(self, **kwargs):
        from src.sourcing.pipeline import Candidate
        from datetime import datetime, timezone
        defaults = dict(
            candidate_id="cid1",
            watch_id="wid1",
            platform="rakuten",
            product_name="テスト商品",
            product_url="https://example.com",
            source_price=5000.0,
            currency="JPY",
            source_price_krw=45000.0,
            estimated_selling_price_krw=90000.0,
            estimated_margin_pct=22.5,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        defaults.update(kwargs)
        return Candidate(**defaults)

    def test_to_dict(self):
        c = self._make_candidate()
        d = c.to_dict()
        for key in ("candidate_id", "platform", "product_name", "estimated_margin_pct", "status"):
            assert key in d

    def test_margin_rounded(self):
        c = self._make_candidate(estimated_margin_pct=22.5678)
        d = c.to_dict()
        assert d["estimated_margin_pct"] == 22.6


# ═══════════════════════════════════════════════════════════════════════════════
# MarginSim
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarginSim:
    def test_to_dict_keys(self):
        from src.sourcing.pipeline import MarginSim
        sim = MarginSim(
            candidate_id="c1",
            source_cost_krw=45000.0,
            fx_rate=9.0,
            platform_fee_krw=4500.0,
            shipping_cost_krw=5000.0,
            ad_cost_krw=4500.0,
            total_cost_krw=59000.0,
            selling_price_krw=90000.0,
            gross_profit_krw=31000.0,
            margin_pct=34.4,
            passes_threshold=True,
            min_margin_pct=15.0,
        )
        d = sim.to_dict()
        assert d["passes_threshold"] is True
        assert d["margin_pct"] == 34.4


# ═══════════════════════════════════════════════════════════════════════════════
# CandidateQueue
# ═══════════════════════════════════════════════════════════════════════════════

class TestCandidateQueue:
    def _make_candidate(self, cid="c1", status="pending"):
        from src.sourcing.pipeline import Candidate
        from datetime import datetime, timezone
        return Candidate(
            candidate_id=cid,
            watch_id="w1",
            platform="rakuten",
            product_name="商品",
            product_url="https://example.com",
            source_price=5000.0,
            currency="JPY",
            source_price_krw=45000.0,
            estimated_selling_price_krw=90000.0,
            estimated_margin_pct=25.0,
            status=status,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )

    def test_enqueue_and_get(self, candidate_queue):
        c = self._make_candidate("c1")
        candidate_queue.enqueue(c)
        assert candidate_queue.get("c1") is not None

    def test_list_all(self, candidate_queue):
        candidate_queue.enqueue(self._make_candidate("c1"))
        candidate_queue.enqueue(self._make_candidate("c2"))
        assert len(candidate_queue.list_all()) == 2

    def test_list_filtered_by_status(self, candidate_queue):
        candidate_queue.enqueue(self._make_candidate("c1", "pending"))
        candidate_queue.enqueue(self._make_candidate("c2", "approved"))
        pending = candidate_queue.list_all(status="pending")
        assert all(c.status == "pending" for c in pending)

    def test_approve(self, candidate_queue):
        c = self._make_candidate("c1")
        candidate_queue.enqueue(c)
        approved = candidate_queue.approve("c1")
        assert approved.status == "approved"
        assert approved.approved_at is not None

    def test_approve_unknown(self, candidate_queue):
        assert candidate_queue.approve("bogus") is None

    def test_reject(self, candidate_queue):
        c = self._make_candidate("c1")
        candidate_queue.enqueue(c)
        rejected = candidate_queue.reject("c1", reason="마진 부족")
        assert rejected.status == "rejected"
        assert rejected.metadata.get("reject_reason") == "마진 부족"

    def test_bulk_approve(self, candidate_queue):
        for cid in ("c1", "c2", "c3"):
            candidate_queue.enqueue(self._make_candidate(cid))
        approved = candidate_queue.bulk_approve(["c1", "c2", "bogus"])
        assert len(approved) == 2

    def test_mark_listed(self, candidate_queue):
        c = self._make_candidate("c1")
        candidate_queue.enqueue(c)
        listed = candidate_queue.mark_listed("c1")
        assert listed.status == "listed"
        assert listed.listed_at is not None

    def test_stats(self, candidate_queue):
        for cid in ("c1", "c2", "c3"):
            candidate_queue.enqueue(self._make_candidate(cid))
        candidate_queue.approve("c1")
        stats = candidate_queue.stats()
        assert stats["total"] == 3
        assert stats["approved"] == 1
        assert stats["pending"] == 2
        assert "avg_margin_pct" in stats


# ═══════════════════════════════════════════════════════════════════════════════
# simulate_margin
# ═══════════════════════════════════════════════════════════════════════════════

class TestSimulateMargin:
    def _make_candidate(self, price=5000.0, currency="JPY", platform="rakuten", selling_price=90000.0):
        from src.sourcing.pipeline import Candidate
        from datetime import datetime, timezone
        return Candidate(
            candidate_id="sim1",
            watch_id="w1",
            platform=platform,
            product_name="テスト",
            product_url="https://example.com",
            source_price=price,
            currency=currency,
            source_price_krw=price * 9,
            estimated_selling_price_krw=selling_price,
            estimated_margin_pct=0.0,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )

    def test_basic_simulation(self):
        from src.sourcing.pipeline import simulate_margin
        c = self._make_candidate()
        sim = simulate_margin(c)
        assert sim.candidate_id == "sim1"
        assert sim.source_cost_krw == pytest.approx(5000 * 9)
        assert sim.selling_price_krw == 90000.0
        assert sim.total_cost_krw > 0
        assert sim.margin_pct < 100

    def test_passes_threshold_high_margin(self):
        from src.sourcing.pipeline import simulate_margin
        c = self._make_candidate(price=1000.0, selling_price=90000.0)
        sim = simulate_margin(c)
        assert sim.passes_threshold is True

    def test_passes_threshold_low_margin(self):
        from src.sourcing.pipeline import simulate_margin
        # 비싼 소싱가, 낮은 판매가 → 마진 미달
        c = self._make_candidate(price=10000.0, selling_price=9000.0)
        sim = simulate_margin(c)
        assert sim.passes_threshold is False

    def test_to_dict(self):
        from src.sourcing.pipeline import simulate_margin
        c = self._make_candidate()
        sim = simulate_margin(c)
        d = sim.to_dict()
        for key in ("source_cost_krw", "margin_pct", "passes_threshold", "min_margin_pct"):
            assert key in d

    def test_amazon_jp_fee(self):
        from src.sourcing.pipeline import simulate_margin
        c = self._make_candidate(platform="amazon_jp")
        sim = simulate_margin(c)
        assert sim.platform_fee_krw == pytest.approx(5000 * 9 * 0.08, rel=0.01)


# ═══════════════════════════════════════════════════════════════════════════════
# discover_candidates
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscoverCandidates:
    def test_discover_returns_candidates(self, fresh_pipeline):
        store, queue = fresh_pipeline
        from src.sourcing.pipeline import discover_candidates
        w = store.add(platform="rakuten", keyword="テスト")
        candidates = discover_candidates(w.watch_id)
        assert isinstance(candidates, list)
        assert len(candidates) > 0

    def test_discover_sets_watch_checked(self, fresh_pipeline):
        store, queue = fresh_pipeline
        from src.sourcing.pipeline import discover_candidates
        w = store.add(platform="rakuten", keyword="テスト")
        assert w.last_checked_at is None
        discover_candidates(w.watch_id)
        assert store.get(w.watch_id).last_checked_at is not None

    def test_discover_unknown_watch_raises(self, fresh_pipeline):
        from src.sourcing.pipeline import discover_candidates
        with pytest.raises(ValueError, match="watch_id"):
            discover_candidates("nonexistent")

    def test_discover_inactive_watch_raises(self, fresh_pipeline):
        store, queue = fresh_pipeline
        from src.sourcing.pipeline import discover_candidates
        w = store.add(platform="rakuten", keyword="test")
        store.deactivate(w.watch_id)
        with pytest.raises(ValueError, match="비활성"):
            discover_candidates(w.watch_id)

    def test_discover_candidate_fields(self, fresh_pipeline):
        store, queue = fresh_pipeline
        from src.sourcing.pipeline import discover_candidates
        w = store.add(platform="rakuten", keyword="テスト")
        candidates = discover_candidates(w.watch_id)
        c = candidates[0]
        assert c.platform == "rakuten"
        assert c.watch_id == w.watch_id
        assert c.source_price > 0
        assert c.estimated_selling_price_krw > 0

    def test_discover_amazon_jp(self, fresh_pipeline):
        store, queue = fresh_pipeline
        from src.sourcing.pipeline import discover_candidates
        w = store.add(platform="amazon_jp", keyword="テスト")
        candidates = discover_candidates(w.watch_id)
        assert all(c.platform == "amazon_jp" for c in candidates)


# ═══════════════════════════════════════════════════════════════════════════════
# queue_candidate
# ═══════════════════════════════════════════════════════════════════════════════

class TestQueueCandidate:
    def _make_candidate(self, margin_pct=25.0, price=1000.0, selling_price=90000.0):
        from src.sourcing.pipeline import Candidate
        from datetime import datetime, timezone
        return Candidate(
            candidate_id="qc1",
            watch_id="w1",
            platform="rakuten",
            product_name="商品",
            product_url="https://example.com",
            source_price=price,
            currency="JPY",
            source_price_krw=price * 9,
            estimated_selling_price_krw=selling_price,
            estimated_margin_pct=margin_pct,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )

    def test_queue_high_margin_candidate(self, fresh_pipeline):
        from src.sourcing.pipeline import queue_candidate
        store, queue = fresh_pipeline
        c = self._make_candidate(price=1000.0, selling_price=90000.0)
        cid = queue_candidate(c)
        assert cid == c.candidate_id
        assert c.status == "pending"
        assert queue.get(cid) is not None

    def test_reject_low_margin_candidate(self, fresh_pipeline):
        from src.sourcing.pipeline import queue_candidate
        store, queue = fresh_pipeline
        # 매우 높은 소싱가, 낮은 판매가
        c = self._make_candidate(price=10000.0, selling_price=9000.0)
        cid = queue_candidate(c)
        assert c.status == "rejected"
        assert queue.get(cid) is None

    def test_queue_reason_set(self, fresh_pipeline):
        from src.sourcing.pipeline import queue_candidate
        store, queue = fresh_pipeline
        c = self._make_candidate(price=500.0, selling_price=90000.0)
        queue_candidate(c)
        if c.status == "pending":
            assert c.queue_reason != ""


# ═══════════════════════════════════════════════════════════════════════════════
# run_watch_cycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunWatchCycle:
    def test_cycle_returns_summary(self, fresh_pipeline):
        from src.sourcing.pipeline import run_watch_cycle
        store, queue = fresh_pipeline
        w = store.add(platform="rakuten", keyword="テスト")
        result = run_watch_cycle(w.watch_id)
        assert result["watch_id"] == w.watch_id
        assert "discovered" in result
        assert "queued" in result
        assert "skipped_low_margin" in result

    def test_cycle_total_consistency(self, fresh_pipeline):
        from src.sourcing.pipeline import run_watch_cycle
        store, queue = fresh_pipeline
        w = store.add(platform="rakuten", keyword="テスト")
        result = run_watch_cycle(w.watch_id)
        assert result["queued"] + result["skipped_low_margin"] == result["discovered"]


# ═══════════════════════════════════════════════════════════════════════════════
# pipeline_stats
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineStats:
    def test_stats_keys(self):
        from src.sourcing.pipeline import pipeline_stats
        stats = pipeline_stats()
        for key in ("active_watches", "candidates_24h", "pending_approval", "auto_listed", "avg_margin_pct"):
            assert key in stats

    def test_stats_after_watch_add(self, fresh_pipeline):
        store, queue = fresh_pipeline
        from src.sourcing.pipeline import pipeline_stats
        store.add(platform="rakuten", keyword="test1")
        store.add(platform="rakuten", keyword="test2")
        stats = pipeline_stats()
        assert stats["active_watches"] == 2
