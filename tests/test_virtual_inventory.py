"""tests/test_virtual_inventory.py — Phase 113: 가상 재고 관리 테스트 (89개+)."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════════════════════════════
# 공통 픽스처
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def pool():
    from src.virtual_inventory.virtual_stock import VirtualStockPool, SourceStock
    p = VirtualStockPool()
    src1 = SourceStock(
        source_id='src1', source_name='Amazon US', platform='amazon_us',
        available_qty=50, price=10000, currency='USD',
        lead_time_days=5, reliability_score=0.9, is_active=True,
        last_checked_at=datetime.now(timezone.utc),
    )
    src2 = SourceStock(
        source_id='src2', source_name='Taobao', platform='taobao',
        available_qty=30, price=5000, currency='CNY',
        lead_time_days=10, reliability_score=0.75, is_active=True,
        last_checked_at=datetime.now(timezone.utc),
    )
    src3 = SourceStock(
        source_id='src3', source_name='1688', platform='1688',
        available_qty=20, price=4000, currency='CNY',
        lead_time_days=12, reliability_score=0.65, is_active=False,
        last_checked_at=datetime.now(timezone.utc),
    )
    p.add_source_stock('prod1', src1)
    p.add_source_stock('prod1', src2)
    p.add_source_stock('prod1', src3)
    p.add_source_stock('prod2', src1)
    return p


@pytest.fixture
def alert_service(pool):
    from src.virtual_inventory.stock_alerts import VirtualStockAlertService
    svc = VirtualStockAlertService()
    svc.set_stock_pool(pool)
    return svc


@pytest.fixture
def analytics(pool):
    from src.virtual_inventory.stock_analytics import VirtualStockAnalytics
    a = VirtualStockAnalytics()
    a.set_stock_pool(pool)
    return a


@pytest.fixture
def sync_bridge(pool):
    from src.virtual_inventory.inventory_sync_bridge import InventorySyncBridge
    b = InventorySyncBridge()
    b.set_stock_pool(pool)
    return b


@pytest.fixture
def allocator(pool):
    from src.virtual_inventory.source_allocator import SourceAllocator
    a = SourceAllocator()
    a.set_stock_pool(pool)
    return a


@pytest.fixture
def dashboard(pool, alert_service, analytics, sync_bridge, allocator):
    from src.virtual_inventory.virtual_inventory_dashboard import VirtualInventoryDashboard
    d = VirtualInventoryDashboard()
    d.set_components(pool, alert_service, analytics, sync_bridge, allocator)
    return d


@pytest.fixture
def flask_app():
    import importlib, sys
    # Reset lazy-init globals so each test starts fresh
    api_mod_name = 'src.api.virtual_inventory_api'
    if api_mod_name in sys.modules:
        mod = sys.modules[api_mod_name]
        for attr in ('_stock_pool', '_aggregation_engine', '_allocator',
                     '_sync_bridge', '_alert_service', '_analytics', '_dashboard'):
            setattr(mod, attr, None)

    from flask import Flask
    from src.api.virtual_inventory_api import virtual_inventory_bp
    app = Flask(__name__)
    app.register_blueprint(virtual_inventory_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


# ═══════════════════════════════════════════════════════════════════════════════
# VirtualStockPool
# ═══════════════════════════════════════════════════════════════════════════════

class TestVirtualStockPool:

    def test_add_source_stock_registers(self, pool):
        """1. add_source_stock registers source."""
        sources = pool.get_source_stocks('prod1')
        assert len(sources) == 3

    def test_get_virtual_stock_aggregates(self, pool):
        """2. get_virtual_stock returns aggregated data."""
        vs = pool.get_virtual_stock('prod1')
        assert vs is not None
        # active: src1(50) + src2(30) = 80
        assert vs.total_available == 80
        assert vs.product_id == 'prod1'

    def test_get_source_stocks_returns_details(self, pool):
        """3. get_source_stocks returns per-source details."""
        sources = pool.get_source_stocks('prod1')
        ids = {s.source_id for s in sources}
        assert 'src1' in ids and 'src2' in ids and 'src3' in ids

    def test_update_source_stock(self, pool):
        """4. update_source_stock updates fields."""
        ok = pool.update_source_stock('prod1', 'src1', {'available_qty': 99})
        assert ok is True
        vs = pool.get_virtual_stock('prod1')
        # src1 now 99, src2 30 → total 129
        assert vs.total_available == 129

    def test_remove_source_stock(self, pool):
        """5. remove_source_stock removes source."""
        ok = pool.remove_source_stock('prod1', 'src3')
        assert ok is True
        sources = pool.get_source_stocks('prod1')
        assert len(sources) == 2

    def test_remove_nonexistent_returns_false(self, pool):
        ok = pool.remove_source_stock('prod1', 'nonexistent')
        assert ok is False

    def test_reserve_stock_creates_reservation(self, pool):
        """6. reserve_stock creates reservation."""
        reservation = pool.reserve_stock('prod1', 10)
        assert reservation.reservation_id is not None
        assert reservation.quantity == 10
        assert reservation.status.value == 'pending'

    def test_reserve_stock_fails_insufficient(self, pool):
        """7. reserve_stock fails when insufficient stock."""
        with pytest.raises(ValueError):
            pool.reserve_stock('prod1', 9999)

    def test_release_reservation(self, pool):
        """8. release_reservation changes status to released."""
        r = pool.reserve_stock('prod1', 5)
        ok = pool.release_reservation(r.reservation_id)
        assert ok is True
        reservations = pool.get_reservations()
        matched = next(x for x in reservations if x.reservation_id == r.reservation_id)
        assert matched.status.value == 'released'

    def test_confirm_reservation(self, pool):
        """9. confirm_reservation changes status to confirmed."""
        r = pool.reserve_stock('prod1', 5)
        ok = pool.confirm_reservation(r.reservation_id)
        assert ok is True
        reservations = pool.get_reservations()
        matched = next(x for x in reservations if x.reservation_id == r.reservation_id)
        assert matched.status.value == 'confirmed'

    def test_get_reservations_returns_list(self, pool):
        """10. get_reservations returns list."""
        pool.reserve_stock('prod1', 1)
        pool.reserve_stock('prod1', 2)
        assert len(pool.get_reservations()) >= 2

    def test_get_reservations_filtered_by_product_id(self, pool):
        """11. get_reservations filtered by product_id."""
        pool.reserve_stock('prod1', 1)
        pool.reserve_stock('prod2', 1)
        p1_res = pool.get_reservations(product_id='prod1')
        assert all(r.product_id == 'prod1' for r in p1_res)

    def test_get_all_virtual_stocks(self, pool):
        """12. get_all_virtual_stocks returns all products."""
        stocks = pool.get_all_virtual_stocks()
        pids = {vs.product_id for vs in stocks}
        assert 'prod1' in pids and 'prod2' in pids

    def test_virtual_stock_sellable_decreases_on_reservation(self, pool):
        """sellable decreases when pending reservation exists."""
        vs_before = pool.get_virtual_stock('prod1')
        sellable_before = vs_before.sellable
        pool.reserve_stock('prod1', 10)
        vs_after = pool.get_virtual_stock('prod1')
        assert vs_after.sellable == sellable_before - 10

    def test_get_virtual_stock_none_for_unknown(self, pool):
        assert pool.get_virtual_stock('unknown_prod') is None


# ═══════════════════════════════════════════════════════════════════════════════
# StockAggregationEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestStockAggregationEngine:

    @pytest.fixture
    def engine(self):
        from src.virtual_inventory.aggregation import StockAggregationEngine
        return StockAggregationEngine()

    @pytest.fixture
    def sources(self):
        from src.virtual_inventory.virtual_stock import SourceStock
        return [
            SourceStock('s1', 'A', 'p1', 50, 10000, 'USD', 5, 0.9, True, datetime.now(timezone.utc)),
            SourceStock('s2', 'B', 'p2', 30, 5000, 'CNY', 10, 0.75, True, datetime.now(timezone.utc)),
            SourceStock('s3', 'C', 'p3', 20, 4000, 'CNY', 12, 0.65, False, datetime.now(timezone.utc)),
        ]

    def test_sum_all_includes_inactive(self, engine, sources):
        """13. sum_all includes inactive sources."""
        from src.virtual_inventory.aggregation import AggregationStrategy
        result = engine.aggregate(sources, AggregationStrategy.sum_all)
        assert result == 100  # 50+30+20

    def test_sum_active_excludes_inactive(self, engine, sources):
        """14. sum_active excludes inactive sources."""
        from src.virtual_inventory.aggregation import AggregationStrategy
        result = engine.aggregate(sources, AggregationStrategy.sum_active)
        assert result == 80  # 50+30

    def test_max_single_returns_max(self, engine, sources):
        """15. max_single returns max of all sources."""
        from src.virtual_inventory.aggregation import AggregationStrategy
        result = engine.aggregate(sources, AggregationStrategy.max_single)
        assert result == 50

    def test_weighted_uses_reliability(self, engine, sources):
        """16. weighted uses reliability score."""
        from src.virtual_inventory.aggregation import AggregationStrategy
        result = engine.aggregate(sources, AggregationStrategy.weighted)
        expected = int(50 * 0.9 + 30 * 0.75)  # only active
        assert result == expected

    def test_conservative_subtracts_safety(self, engine, sources):
        """17. conservative subtracts safety stock."""
        from src.virtual_inventory.aggregation import AggregationStrategy
        result = engine.aggregate(sources, AggregationStrategy.conservative)
        sum_active = 80
        safety = max(3, int(sum_active * 0.1))
        assert result == max(0, sum_active - safety)

    def test_calculate_safety_stock(self, engine, sources):
        """18. calculate_safety_stock returns reasonable value."""
        safety = engine.calculate_safety_stock('prod1', sources)
        assert safety >= 3

    def test_get_sellable_quantity(self, engine, pool):
        """19. get_sellable_quantity uses pool data."""
        qty = engine.get_sellable_quantity('prod1', pool)
        assert qty >= 0

    def test_aggregate_empty_returns_zero(self, engine):
        """20. aggregate with empty sources returns 0."""
        from src.virtual_inventory.aggregation import AggregationStrategy
        assert engine.aggregate([], AggregationStrategy.sum_all) == 0
        assert engine.aggregate([], AggregationStrategy.sum_active) == 0
        assert engine.aggregate([], AggregationStrategy.max_single) == 0
        assert engine.aggregate([], AggregationStrategy.weighted) == 0
        assert engine.aggregate([], AggregationStrategy.conservative) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SourceAllocator
# ═══════════════════════════════════════════════════════════════════════════════

class TestSourceAllocator:

    def test_cheapest_first(self, allocator):
        """21. cheapest_first allocates from cheapest."""
        from src.virtual_inventory.source_allocator import AllocationStrategy
        result = allocator.allocate('prod1', 10, AllocationStrategy.cheapest_first)
        # cheapest is src2 (price=5000)
        assert result.allocated_sources[0].source_id == 'src2'

    def test_fastest_first(self, allocator):
        """22. fastest_first allocates from fastest."""
        from src.virtual_inventory.source_allocator import AllocationStrategy
        result = allocator.allocate('prod1', 10, AllocationStrategy.fastest_first)
        # fastest is src1 (lead_time_days=5)
        assert result.allocated_sources[0].source_id == 'src1'

    def test_single_source_picks_most_stock(self, allocator):
        """23. single_source picks single source."""
        from src.virtual_inventory.source_allocator import AllocationStrategy
        result = allocator.allocate('prod1', 10, AllocationStrategy.single_source)
        # picks source with most stock = src1 (50)
        assert len(result.allocated_sources) == 1
        assert result.allocated_sources[0].source_id == 'src1'

    def test_balanced_allocates_composite(self, allocator):
        """24. balanced allocates with composite score."""
        from src.virtual_inventory.source_allocator import AllocationStrategy
        result = allocator.allocate('prod1', 10, AllocationStrategy.balanced)
        assert result is not None
        assert result.quantity == 10

    def test_reliability_first(self, allocator):
        """25. reliability_first picks most reliable."""
        from src.virtual_inventory.source_allocator import AllocationStrategy
        result = allocator.allocate('prod1', 10, AllocationStrategy.reliability_first)
        # most reliable is src1 (0.9)
        assert result.allocated_sources[0].source_id == 'src1'

    def test_partial_allocation_when_insufficient(self, allocator):
        """26. partial allocation when stock insufficient."""
        from src.virtual_inventory.source_allocator import AllocationStrategy
        result = allocator.allocate('prod1', 9999, AllocationStrategy.cheapest_first)
        allocated_total = sum(a.allocated_qty for a in result.allocated_sources)
        # Only gets available (active: 50+30=80)
        assert allocated_total == 80

    def test_get_allocation(self, allocator):
        """27. get_allocation returns result."""
        result = allocator.allocate('prod1', 5)
        fetched = allocator.get_allocation(result.allocation_id)
        assert fetched is not None
        assert fetched.allocation_id == result.allocation_id

    def test_get_allocation_history_filtered(self, allocator):
        """28. get_allocation_history filtered."""
        allocator.allocate('prod1', 5)
        allocator.allocate('prod2', 5)
        hist = allocator.get_allocation_history(product_id='prod1')
        assert all(a.product_id == 'prod1' for a in hist)

    def test_cancel_allocation(self, allocator):
        """29. cancel_allocation sets status."""
        result = allocator.allocate('prod1', 5)
        ok = allocator.cancel_allocation(result.allocation_id)
        assert ok is True
        fetched = allocator.get_allocation(result.allocation_id)
        assert fetched.status == 'cancelled'

    def test_cancel_nonexistent_returns_false(self, allocator):
        ok = allocator.cancel_allocation('nonexistent')
        assert ok is False


# ═══════════════════════════════════════════════════════════════════════════════
# InventorySyncBridge
# ═══════════════════════════════════════════════════════════════════════════════

class TestInventorySyncBridge:

    def test_sync_to_channels_stores_stocks(self, sync_bridge):
        """30. sync_to_channels stores channel stocks."""
        result = sync_bridge.sync_to_channels()
        assert result['synced'] == 2  # prod1, prod2

    def test_get_channel_stock_map(self, sync_bridge):
        """31. get_channel_stock_map returns channels."""
        sync_bridge.sync_to_channels()
        channel_map = sync_bridge.get_channel_stock_map('prod1')
        assert 'coupang' in channel_map
        assert 'naver' in channel_map
        assert 'internal' in channel_map

    def test_calculate_channel_stock_deductions(self, sync_bridge):
        """32. calculate_channel_stock applies channel deductions."""
        vs = sync_bridge._stock_pool.get_virtual_stock('prod1')
        sellable = vs.sellable

        coupang = sync_bridge.calculate_channel_stock('prod1', 'coupang')
        naver = sync_bridge.calculate_channel_stock('prod1', 'naver')
        internal = sync_bridge.calculate_channel_stock('prod1', 'internal')
        default = sync_bridge.calculate_channel_stock('prod1', 'other')

        assert coupang == max(0, int(sellable * 0.9))
        assert naver == max(0, int(sellable * 0.95))
        assert internal == sellable
        assert default == max(0, int(sellable * 0.85))

    def test_get_sync_status(self, sync_bridge):
        """33. get_sync_status returns status dict."""
        status = sync_bridge.get_sync_status()
        assert 'last_synced_at' in status
        assert 'total_products' in status
        assert 'synced_products' in status
        assert 'discrepancy_count' in status

    def test_get_stock_discrepancies(self, sync_bridge):
        """34. get_stock_discrepancies returns list."""
        sync_bridge.sync_to_channels()
        discrepancies = sync_bridge.get_stock_discrepancies()
        # channel stocks are reduced from sellable → discrepancies for coupang/naver/default
        assert isinstance(discrepancies, list)
        for d in discrepancies:
            assert d['difference'] != 0


# ═══════════════════════════════════════════════════════════════════════════════
# VirtualStockAlertService
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def pool_with_out_of_stock():
    """Pool with a product that has 0 sellable stock."""
    from src.virtual_inventory.virtual_stock import VirtualStockPool, SourceStock
    p = VirtualStockPool()
    src = SourceStock(
        source_id='s_out', source_name='Empty', platform='p',
        available_qty=0, price=1000, currency='KRW',
        lead_time_days=3, reliability_score=0.8, is_active=True,
        last_checked_at=datetime.now(timezone.utc),
    )
    p.add_source_stock('prod_out', src)
    return p


@pytest.fixture
def pool_with_overstock():
    """Pool with a product that has very high stock."""
    from src.virtual_inventory.virtual_stock import VirtualStockPool, SourceStock
    p = VirtualStockPool()
    src = SourceStock(
        source_id='s_over', source_name='Full', platform='p',
        available_qty=1000, price=1000, currency='KRW',
        lead_time_days=3, reliability_score=0.8, is_active=True,
        last_checked_at=datetime.now(timezone.utc),
    )
    p.add_source_stock('prod_over', src)
    return p


class TestVirtualStockAlertService:

    def test_out_of_stock_alert_created(self, pool_with_out_of_stock):
        """35. out_of_stock alert created."""
        from src.virtual_inventory.stock_alerts import VirtualStockAlertService
        svc = VirtualStockAlertService()
        svc.set_stock_pool(pool_with_out_of_stock)
        alerts = svc.check_alerts()
        types = [a.alert_type.value for a in alerts]
        assert 'out_of_stock' in types

    def test_low_stock_alert_created(self):
        """36. low_stock alert created."""
        from src.virtual_inventory.virtual_stock import VirtualStockPool, SourceStock
        from src.virtual_inventory.stock_alerts import VirtualStockAlertService
        p = VirtualStockPool()
        src = SourceStock('s', 'N', 'pl', 2, 1000, 'KRW', 3, 0.8, True, datetime.now(timezone.utc))
        p.add_source_stock('prod_low', src)
        svc = VirtualStockAlertService()
        svc.set_stock_pool(p)
        alerts = svc.check_alerts()
        types = [a.alert_type.value for a in alerts]
        assert 'low_stock' in types

    def test_overstock_alert_created(self, pool_with_overstock):
        """37. overstock alert created."""
        from src.virtual_inventory.stock_alerts import VirtualStockAlertService
        svc = VirtualStockAlertService()
        svc.set_stock_pool(pool_with_overstock)
        alerts = svc.check_alerts()
        types = [a.alert_type.value for a in alerts]
        assert 'overstock' in types

    def test_single_source_risk_alert(self):
        """38. single_source_risk alert created."""
        from src.virtual_inventory.virtual_stock import VirtualStockPool, SourceStock
        from src.virtual_inventory.stock_alerts import VirtualStockAlertService
        p = VirtualStockPool()
        src = SourceStock('s1', 'N', 'pl', 50, 1000, 'KRW', 3, 0.8, True, datetime.now(timezone.utc))
        p.add_source_stock('prod_single', src)
        svc = VirtualStockAlertService()
        svc.set_stock_pool(p)
        alerts = svc.check_alerts()
        types = [a.alert_type.value for a in alerts]
        assert 'single_source_risk' in types

    def test_source_depleted_alert(self, pool):
        """39. source_depleted alert created (src3 has qty=0 but inactive)."""
        # Update src2 to have 0 qty
        pool.update_source_stock('prod1', 'src2', {'available_qty': 0})
        from src.virtual_inventory.stock_alerts import VirtualStockAlertService
        svc = VirtualStockAlertService()
        svc.set_stock_pool(pool)
        alerts = svc.check_alerts(product_id='prod1')
        types = [a.alert_type.value for a in alerts]
        assert 'source_depleted' in types

    def test_acknowledge_alert(self, alert_service):
        """40. acknowledge_alert marks alert."""
        alerts = alert_service.check_alerts()
        if not alerts:
            pytest.skip('No alerts generated')
        alert = alerts[0]
        ok = alert_service.acknowledge_alert(alert.alert_id)
        assert ok is True
        fetched = alert_service.get_alerts(acknowledged=True)
        ids = [a.alert_id for a in fetched]
        assert alert.alert_id in ids

    def test_get_alert_summary(self, alert_service):
        """41. get_alert_summary returns summary."""
        alert_service.check_alerts()
        summary = alert_service.get_alert_summary()
        assert 'total' in summary
        assert 'by_severity' in summary
        assert 'by_type' in summary
        assert 'unacknowledged' in summary

    def test_get_alerts_filtered_by_severity(self, alert_service):
        """42. get_alerts filtered by severity."""
        alert_service.check_alerts()
        all_alerts = alert_service.get_alerts()
        if not all_alerts:
            pytest.skip('No alerts generated')
        sev = all_alerts[0].severity.value
        filtered = alert_service.get_alerts(severity=sev)
        assert all(a.severity.value == sev for a in filtered)

    def test_get_alerts_filtered_by_type(self, alert_service):
        """43. get_alerts filtered by type."""
        alert_service.check_alerts()
        all_alerts = alert_service.get_alerts()
        if not all_alerts:
            pytest.skip('No alerts generated')
        atype = all_alerts[0].alert_type.value
        filtered = alert_service.get_alerts(alert_type=atype)
        assert all(a.alert_type.value == atype for a in filtered)

    def test_get_alerts_filtered_by_acknowledged(self, alert_service):
        """44. get_alerts filtered by acknowledged."""
        alerts = alert_service.check_alerts()
        if not alerts:
            pytest.skip('No alerts generated')
        alert_service.acknowledge_alert(alerts[0].alert_id)
        acked = alert_service.get_alerts(acknowledged=True)
        unacked = alert_service.get_alerts(acknowledged=False)
        assert all(a.acknowledged for a in acked)
        assert all(not a.acknowledged for a in unacked)


# ═══════════════════════════════════════════════════════════════════════════════
# VirtualStockAnalytics
# ═══════════════════════════════════════════════════════════════════════════════

class TestVirtualStockAnalytics:

    def test_get_stock_summary(self, analytics):
        """45. get_stock_summary returns stats."""
        summary = analytics.get_stock_summary()
        assert 'total_skus' in summary
        assert summary['total_skus'] == 2
        assert 'total_virtual_stock' in summary
        assert 'avg_sources_per_sku' in summary

    def test_get_source_distribution(self, analytics):
        """46. get_source_distribution returns distribution."""
        dist = analytics.get_source_distribution()
        assert isinstance(dist, dict)
        assert 'src1' in dist
        assert dist['src1']['product_count'] == 2  # src1 used in both prod1 and prod2

    def test_get_stock_health(self, analytics):
        """47. get_stock_health returns percentages."""
        health = analytics.get_stock_health()
        assert 'healthy_pct' in health
        assert 'low_stock_pct' in health
        assert 'out_of_stock_pct' in health
        assert 'overstock_pct' in health

    def test_get_turnover_analysis(self, analytics):
        """48. get_turnover_analysis returns ratios."""
        result = analytics.get_turnover_analysis()
        assert 'prod1' in result
        assert 'turnover_rate' in result['prod1']

    def test_get_turnover_single_product(self, analytics):
        """get_turnover_analysis for single product."""
        result = analytics.get_turnover_analysis(product_id='prod1')
        assert 'prod1' in result

    def test_get_single_source_products(self, analytics):
        """49. get_single_source_products returns list."""
        result = analytics.get_single_source_products()
        assert isinstance(result, list)
        # prod2 has only src1 (active)
        assert 'prod2' in result

    def test_get_stock_value(self, analytics):
        """50. get_stock_value returns value."""
        result = analytics.get_stock_value()
        assert 'total_value' in result
        assert 'by_product' in result
        assert result['total_value'] >= 0

    def test_get_stock_value_single_product(self, analytics):
        result = analytics.get_stock_value(product_id='prod1')
        assert 'prod1' in result['by_product']


# ═══════════════════════════════════════════════════════════════════════════════
# VirtualInventoryDashboard
# ═══════════════════════════════════════════════════════════════════════════════

class TestVirtualInventoryDashboard:

    def test_get_dashboard_data(self, dashboard):
        """51. get_dashboard_data returns full dashboard."""
        data = dashboard.get_dashboard_data()
        assert 'stock_health' in data
        assert 'source_distribution' in data
        assert 'low_stock_products' in data
        assert 'single_source_risks' in data
        assert 'recent_activity' in data
        assert 'alerts' in data
        assert 'reservations' in data
        assert 'sync_status' in data

    def test_dashboard_low_stock_products_ordered(self, dashboard):
        """low_stock_products should have product data."""
        data = dashboard.get_dashboard_data()
        for item in data['low_stock_products']:
            assert 'product_id' in item
            assert 'sellable' in item

    def test_dashboard_reservations_count(self, dashboard):
        """Dashboard reservations count is correct."""
        data = dashboard.get_dashboard_data()
        reservations = data['reservations']
        assert 'pending_count' in reservations
        assert 'total_count' in reservations


# ═══════════════════════════════════════════════════════════════════════════════
# API Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestVirtualInventoryAPI:

    def _add_source(self, client, product_id: str, source_id: str = 'api_src1',
                    qty: int = 100, price: float = 5000.0) -> None:
        client.post(
            f'/api/v1/virtual-inventory/stock/{product_id}/sources',
            json={
                'source_id': source_id,
                'source_name': 'Test Source',
                'platform': 'test',
                'available_qty': qty,
                'price': price,
                'currency': 'KRW',
                'lead_time_days': 5,
                'reliability_score': 0.9,
                'is_active': True,
            },
        )

    def test_get_stock_list(self, client):
        """52. GET /stock returns list."""
        resp = client.get('/api/v1/virtual-inventory/stock')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_get_stock_single(self, client):
        """53. GET /stock/<id> returns single."""
        self._add_source(client, 'api_prod1')
        resp = client.get('/api/v1/virtual-inventory/stock/api_prod1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['product_id'] == 'api_prod1'

    def test_get_stock_not_found(self, client):
        resp = client.get('/api/v1/virtual-inventory/stock/nonexistent_xyz')
        assert resp.status_code == 404

    def test_post_stock_sources(self, client):
        """54. POST /stock/<id>/sources adds source."""
        resp = client.post(
            '/api/v1/virtual-inventory/stock/api_prod2/sources',
            json={
                'source_id': 'src_new',
                'source_name': 'New',
                'platform': 'test',
                'available_qty': 50,
                'price': 3000,
                'currency': 'KRW',
                'lead_time_days': 7,
                'reliability_score': 0.8,
                'is_active': True,
            },
        )
        assert resp.status_code == 201

    def test_get_stock_sources(self, client):
        """55. GET /stock/<id>/sources returns sources."""
        self._add_source(client, 'api_prod3')
        resp = client.get('/api/v1/virtual-inventory/stock/api_prod3/sources')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_post_reserve(self, client):
        """56. POST /stock/<id>/reserve creates reservation."""
        self._add_source(client, 'api_prod4')
        resp = client.post(
            '/api/v1/virtual-inventory/stock/api_prod4/reserve',
            json={'quantity': 5},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'reservation_id' in data

    def test_post_reserve_insufficient(self, client):
        self._add_source(client, 'api_prod5', qty=10)
        resp = client.post(
            '/api/v1/virtual-inventory/stock/api_prod5/reserve',
            json={'quantity': 9999},
        )
        assert resp.status_code == 400

    def test_get_reservations(self, client):
        """57. GET /reservations returns list."""
        resp = client.get('/api/v1/virtual-inventory/reservations')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_post_allocate(self, client):
        """58. POST /allocate creates allocation."""
        self._add_source(client, 'api_prod6')
        resp = client.post(
            '/api/v1/virtual-inventory/allocate',
            json={'product_id': 'api_prod6', 'quantity': 10, 'strategy': 'cheapest_first'},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'allocation_id' in data

    def test_get_analytics_summary(self, client):
        """59. GET /analytics/summary returns stats."""
        resp = client.get('/api/v1/virtual-inventory/analytics/summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_skus' in data

    def test_get_dashboard(self, client):
        """60. GET /dashboard returns dashboard."""
        resp = client.get('/api/v1/virtual-inventory/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'stock_health' in data

    def test_sync_endpoint(self, client):
        resp = client.post('/api/v1/virtual-inventory/sync', json={})
        assert resp.status_code == 200

    def test_sync_status(self, client):
        resp = client.get('/api/v1/virtual-inventory/sync/status')
        assert resp.status_code == 200

    def test_alerts_check(self, client):
        resp = client.post('/api/v1/virtual-inventory/alerts/check', json={})
        assert resp.status_code == 200

    def test_alerts_list(self, client):
        resp = client.get('/api/v1/virtual-inventory/alerts')
        assert resp.status_code == 200

    def test_alerts_summary(self, client):
        resp = client.get('/api/v1/virtual-inventory/alerts/summary')
        assert resp.status_code == 200

    def test_analytics_health(self, client):
        resp = client.get('/api/v1/virtual-inventory/analytics/health')
        assert resp.status_code == 200

    def test_analytics_source_distribution(self, client):
        resp = client.get('/api/v1/virtual-inventory/analytics/source-distribution')
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# Bot Command Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestBotCommands:

    def test_cmd_vstock_returns_output(self):
        """61. cmd_vstock returns formatted output."""
        from src.bot.virtual_inventory_commands import cmd_vstock
        result = cmd_vstock('test_sku')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_vstock_empty_sku(self):
        from src.bot.virtual_inventory_commands import cmd_vstock
        result = cmd_vstock('')
        assert 'SKU' in result or 'error' in result.lower() or '⚠' in result or '오류' in result or 'vstock' in result.lower()

    def test_cmd_vstock_all(self):
        """62. cmd_vstock_all returns summary."""
        from src.bot.virtual_inventory_commands import cmd_vstock_all
        result = cmd_vstock_all()
        assert isinstance(result, str)

    def test_cmd_vstock_health(self):
        """63. cmd_vstock_health returns health info."""
        from src.bot.virtual_inventory_commands import cmd_vstock_health
        result = cmd_vstock_health()
        assert isinstance(result, str)

    def test_cmd_vstock_alerts(self):
        """64. cmd_vstock_alerts returns alerts."""
        from src.bot.virtual_inventory_commands import cmd_vstock_alerts
        result = cmd_vstock_alerts()
        assert isinstance(result, str)

    def test_cmd_vstock_dashboard(self):
        """65. cmd_vstock_dashboard returns dashboard."""
        from src.bot.virtual_inventory_commands import cmd_vstock_dashboard
        result = cmd_vstock_dashboard()
        assert isinstance(result, str)

    def test_cmd_vstock_low(self):
        from src.bot.virtual_inventory_commands import cmd_vstock_low
        result = cmd_vstock_low()
        assert isinstance(result, str)

    def test_cmd_vstock_out(self):
        from src.bot.virtual_inventory_commands import cmd_vstock_out
        result = cmd_vstock_out()
        assert isinstance(result, str)

    def test_cmd_vstock_sync(self):
        from src.bot.virtual_inventory_commands import cmd_vstock_sync
        result = cmd_vstock_sync()
        assert isinstance(result, str)

    def test_cmd_vstock_risk(self):
        from src.bot.virtual_inventory_commands import cmd_vstock_risk
        result = cmd_vstock_risk()
        assert isinstance(result, str)

    def test_cmd_vstock_reserve_bad_qty(self):
        from src.bot.virtual_inventory_commands import cmd_vstock_reserve
        result = cmd_vstock_reserve('prod1', 'not_a_number')
        assert isinstance(result, str)

    def test_cmd_vstock_allocate(self):
        from src.bot.virtual_inventory_commands import cmd_vstock_allocate
        result = cmd_vstock_allocate('test_sku', '5')
        assert isinstance(result, str)
