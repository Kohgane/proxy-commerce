"""tests/test_china_marketplace.py — Phase 104: 타오바오/1688 자동 구매 규격 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── ChinaPurchaseStatus / ChinaPurchaseOrder ────────────────────────────────

class TestChinaPurchaseStatus:
    def test_all_statuses_exist(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        assert ChinaPurchaseStatus.created == 'created'
        assert ChinaPurchaseStatus.agent_assigned == 'agent_assigned'
        assert ChinaPurchaseStatus.searching == 'searching'
        assert ChinaPurchaseStatus.seller_verified == 'seller_verified'
        assert ChinaPurchaseStatus.ordering == 'ordering'
        assert ChinaPurchaseStatus.paid == 'paid'
        assert ChinaPurchaseStatus.shipped == 'shipped'
        assert ChinaPurchaseStatus.warehouse_received == 'warehouse_received'
        assert ChinaPurchaseStatus.completed == 'completed'
        assert ChinaPurchaseStatus.cancelled == 'cancelled'
        assert ChinaPurchaseStatus.failed == 'failed'

    def test_status_is_str(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        assert isinstance(ChinaPurchaseStatus.created, str)


class TestChinaPurchaseOrder:
    def test_default_status_is_created(self):
        from src.china_marketplace.engine import ChinaPurchaseOrder, ChinaPurchaseStatus
        order = ChinaPurchaseOrder(order_id='test_001', marketplace='taobao', product_url='https://example.com')
        assert order.status == ChinaPurchaseStatus.created

    def test_created_at_set_on_init(self):
        from src.china_marketplace.engine import ChinaPurchaseOrder
        order = ChinaPurchaseOrder(order_id='test_002', marketplace='taobao', product_url='https://example.com')
        assert 'created_at' in order.timestamps

    def test_update_status(self):
        from src.china_marketplace.engine import ChinaPurchaseOrder, ChinaPurchaseStatus
        order = ChinaPurchaseOrder(order_id='test_003', marketplace='taobao', product_url='https://example.com')
        order.update_status(ChinaPurchaseStatus.searching)
        assert order.status == ChinaPurchaseStatus.searching
        assert 'searching_at' in order.timestamps

    def test_to_dict(self):
        from src.china_marketplace.engine import ChinaPurchaseOrder
        order = ChinaPurchaseOrder(order_id='test_004', marketplace='taobao', product_url='https://example.com', quantity=3)
        d = order.to_dict()
        assert d['order_id'] == 'test_004'
        assert d['marketplace'] == 'taobao'
        assert d['quantity'] == 3

    def test_default_quantity(self):
        from src.china_marketplace.engine import ChinaPurchaseOrder
        order = ChinaPurchaseOrder(order_id='x', marketplace='taobao', product_url='u')
        assert order.quantity == 1

    def test_agent_defaults_none(self):
        from src.china_marketplace.engine import ChinaPurchaseOrder
        order = ChinaPurchaseOrder(order_id='x', marketplace='taobao', product_url='u')
        assert order.agent is None


# ─── ChinaMarketplaceEngine ──────────────────────────────────────────────────

class TestChinaMarketplaceEngine:
    def _make_engine(self):
        from src.china_marketplace.engine import ChinaMarketplaceEngine
        return ChinaMarketplaceEngine()

    def test_create_order_returns_order(self):
        engine = self._make_engine()
        order = engine.create_order(marketplace='taobao', product_url='https://example.com')
        assert order.order_id.startswith('cn_')
        assert order.marketplace == 'taobao'

    def test_create_order_with_quantity(self):
        engine = self._make_engine()
        order = engine.create_order(marketplace='1688', product_url='https://1688.com/x', quantity=50)
        assert order.quantity == 50

    def test_get_order(self):
        engine = self._make_engine()
        order = engine.create_order(marketplace='taobao', product_url='u')
        fetched = engine.get_order(order.order_id)
        assert fetched is not None
        assert fetched.order_id == order.order_id

    def test_get_order_not_found(self):
        engine = self._make_engine()
        assert engine.get_order('nonexistent') is None

    def test_list_orders(self):
        engine = self._make_engine()
        engine.create_order('taobao', 'u1')
        engine.create_order('1688', 'u2')
        orders = engine.list_orders()
        assert len(orders) == 2

    def test_list_orders_filter_by_marketplace(self):
        engine = self._make_engine()
        engine.create_order('taobao', 'u1')
        engine.create_order('1688', 'u2')
        tb = engine.list_orders(marketplace='taobao')
        assert len(tb) == 1
        assert tb[0].marketplace == 'taobao'

    def test_list_orders_filter_by_status(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        engine = self._make_engine()
        o1 = engine.create_order('taobao', 'u1')
        engine.create_order('taobao', 'u2')
        engine.start_searching(o1.order_id)
        searching = engine.list_orders(status=ChinaPurchaseStatus.searching)
        assert len(searching) == 1

    def test_assign_agent(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        engine = self._make_engine()
        order = engine.create_order('taobao', 'u')
        engine.assign_agent(order.order_id, 'agent_x')
        updated = engine.get_order(order.order_id)
        assert updated.agent == 'agent_x'
        assert updated.status == ChinaPurchaseStatus.agent_assigned

    def test_start_searching(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        engine = self._make_engine()
        order = engine.create_order('taobao', 'u')
        engine.start_searching(order.order_id)
        assert engine.get_order(order.order_id).status == ChinaPurchaseStatus.searching

    def test_mark_seller_verified(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        engine = self._make_engine()
        order = engine.create_order('taobao', 'u')
        engine.mark_seller_verified(order.order_id, {'seller_id': 's1', 'name': '테스트셀러'})
        updated = engine.get_order(order.order_id)
        assert updated.status == ChinaPurchaseStatus.seller_verified
        assert updated.seller_info['seller_id'] == 's1'

    def test_start_ordering(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        engine = self._make_engine()
        order = engine.create_order('taobao', 'u')
        engine.start_ordering(order.order_id, {'price_cny': 50.0})
        updated = engine.get_order(order.order_id)
        assert updated.status == ChinaPurchaseStatus.ordering

    def test_mark_paid(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        engine = self._make_engine()
        order = engine.create_order('taobao', 'u')
        engine.mark_paid(order.order_id, {'payment_id': 'p1', 'amount_cny': 50.0})
        updated = engine.get_order(order.order_id)
        assert updated.status == ChinaPurchaseStatus.paid
        assert updated.payment_info['payment_id'] == 'p1'

    def test_mark_shipped(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        engine = self._make_engine()
        order = engine.create_order('taobao', 'u')
        engine.mark_shipped(order.order_id, {'tracking_number': 'SF123'})
        updated = engine.get_order(order.order_id)
        assert updated.status == ChinaPurchaseStatus.shipped

    def test_complete_order(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        engine = self._make_engine()
        order = engine.create_order('taobao', 'u')
        engine.complete_order(order.order_id)
        assert engine.get_order(order.order_id).status == ChinaPurchaseStatus.completed

    def test_cancel_order(self):
        from src.china_marketplace.engine import ChinaPurchaseStatus
        engine = self._make_engine()
        order = engine.create_order('taobao', 'u')
        engine.cancel_order(order.order_id, '고객 요청')
        updated = engine.get_order(order.order_id)
        assert updated.status == ChinaPurchaseStatus.cancelled
        assert updated.notes == '고객 요청'

    def test_get_stats(self):
        engine = self._make_engine()
        engine.create_order('taobao', 'u1')
        engine.create_order('1688', 'u2')
        stats = engine.get_stats()
        assert stats['total'] == 2
        assert 'by_status' in stats
        assert 'by_marketplace' in stats

    def test_get_order_not_found_raises(self):
        engine = self._make_engine()
        with pytest.raises(KeyError):
            engine._get_or_raise('nonexistent_order')


# ─── TaobaoAgent ─────────────────────────────────────────────────────────────

class TestTaobaoAgent:
    def _make_agent(self):
        from src.china_marketplace.taobao_agent import TaobaoAgent
        return TaobaoAgent()

    def test_search_returns_products(self):
        agent = self._make_agent()
        results = agent.search('운동화', max_results=3)
        assert len(results) > 0
        assert len(results) <= 3

    def test_search_product_has_required_fields(self):
        agent = self._make_agent()
        results = agent.search('의류')
        assert len(results) > 0
        p = results[0]
        assert p.product_id.startswith('tb_')
        assert p.price_cny > 0
        assert p.seller_id
        assert p.url

    def test_search_by_url(self):
        agent = self._make_agent()
        product = agent.search_by_url('https://item.taobao.com/item.htm?id=123456')
        assert product is not None
        assert product.price_cny > 0

    def test_get_detail(self):
        agent = self._make_agent()
        detail = agent.get_detail('tb_test001')
        assert 'product_id' in detail
        assert 'price_cny' in detail
        assert 'seller' in detail

    def test_evaluate_seller(self):
        agent = self._make_agent()
        result = agent.evaluate_seller('seller_001')
        assert 'trust_score' in result
        assert 0 <= result['trust_score'] <= 100

    def test_place_order(self):
        agent = self._make_agent()
        order = agent.place_order('tb_001', quantity=2, unit_price_cny=50.0)
        assert order.taobao_order_id.startswith('TB')
        assert order.quantity == 2
        assert order.unit_price_cny == 50.0

    def test_place_order_uses_default_address(self):
        from src.china_marketplace.taobao_agent import TaobaoAgent
        agent = self._make_agent()
        order = agent.place_order('tb_001', quantity=1, unit_price_cny=10.0)
        assert order.shipping_address == TaobaoAgent.DEFAULT_WAREHOUSE_ADDRESS

    def test_place_order_custom_address(self):
        agent = self._make_agent()
        order = agent.place_order('tb_001', quantity=1, unit_price_cny=10.0, shipping_address='Custom Address')
        assert order.shipping_address == 'Custom Address'

    def test_place_order_stores_in_orders(self):
        agent = self._make_agent()
        order = agent.place_order('tb_001', quantity=1, unit_price_cny=20.0)
        fetched = agent.get_order(order.taobao_order_id)
        assert fetched is not None

    def test_track_order(self):
        agent = self._make_agent()
        result = agent.track_order('TB_TEST001')
        assert 'status' in result
        assert 'tracking_number' in result

    def test_negotiate_price(self):
        agent = self._make_agent()
        result = agent.negotiate_price('tb_001', target_price_cny=80.0)
        assert 'accepted' in result
        assert 'final_price' in result
        assert result['final_price'] > 0

    def test_apply_coupon(self):
        agent = self._make_agent()
        result = agent.apply_coupon('order_001', 'COUPON10')
        assert result['applied'] is True
        assert result['discount_cny'] >= 0

    def test_list_orders(self):
        agent = self._make_agent()
        agent.place_order('p1', 1, 10.0)
        agent.place_order('p2', 2, 20.0)
        orders = agent.list_orders()
        assert len(orders) == 2

    def test_to_dict(self):
        agent = self._make_agent()
        order = agent.place_order('p1', 1, 10.0)
        d = order.to_dict()
        assert 'taobao_order_id' in d
        assert 'product_id' in d


# ─── Alibaba1688Agent ────────────────────────────────────────────────────────

class TestAlibaba1688Agent:
    def _make_agent(self):
        from src.china_marketplace.alibaba_agent import Alibaba1688Agent
        return Alibaba1688Agent()

    def test_search_returns_products(self):
        agent = self._make_agent()
        results = agent.search('전자부품', max_results=3)
        assert len(results) > 0
        assert len(results) <= 3

    def test_search_product_has_required_fields(self):
        agent = self._make_agent()
        results = agent.search('의류')
        p = results[0]
        assert p.product_id.startswith('ali_')
        assert p.moq > 0
        assert len(p.price_tiers) > 0
        assert p.supplier_type in ('factory', 'wholesaler')

    def test_search_by_url(self):
        agent = self._make_agent()
        product = agent.search_by_url('https://detail.1688.com/offer/12345.html')
        assert product is not None
        assert product.moq > 0

    def test_get_price_for_qty(self):
        from src.china_marketplace.alibaba_agent import Alibaba1688Product
        product = Alibaba1688Product(
            product_id='test',
            title='test',
            moq=10,
            price_tiers=[
                {'min_qty': 10, 'price_cny': 10.0},
                {'min_qty': 100, 'price_cny': 8.0},
                {'min_qty': 500, 'price_cny': 5.0},
            ],
            supplier_type='factory',
            supplier_id='s1',
            supplier_name='test',
            stock=1000,
            rating=4.5,
            url='https://test.com',
        )
        assert product.get_price_for_qty(50) == 10.0
        assert product.get_price_for_qty(100) == 8.0
        assert product.get_price_for_qty(500) == 5.0

    def test_check_moq(self):
        agent = self._make_agent()
        result = agent.check_moq('ali_001', quantity=100)
        assert 'moq' in result
        assert 'meets_moq' in result

    def test_get_supplier_detail(self):
        agent = self._make_agent()
        detail = agent.get_supplier_detail('sup_001')
        assert 'supplier_type' in detail
        assert detail['supplier_type'] in ('factory', 'wholesaler')

    def test_place_sample_order(self):
        agent = self._make_agent()
        order = agent.place_sample_order('ali_001', 'sup_001', sample_price_cny=50.0)
        assert 'SAMPLE' in order.order_id
        assert order.is_sample is True
        assert order.quantity == 1

    def test_place_bulk_order(self):
        agent = self._make_agent()
        order = agent.place_bulk_order('ali_001', 'sup_001', quantity=1000, unit_price_cny=10.0)
        assert order.quantity == 1000
        assert order.total_price_cny > 0

    def test_bulk_order_discount_rate(self):
        agent = self._make_agent()
        order = agent.place_bulk_order('ali_001', 'sup_001', quantity=1000, unit_price_cny=10.0, negotiate_discount=True)
        # 500개 이상이면 할인 가능
        assert order.bulk_discount_rate >= 0.0

    def test_check_certifications(self):
        agent = self._make_agent()
        result = agent.check_certifications('sup_001')
        assert 'certifications' in result
        assert 'verified' in result

    def test_negotiate_bulk_discount(self):
        agent = self._make_agent()
        result = agent.negotiate_bulk_discount('ali_001', 500, 8.0)
        assert 'accepted' in result
        assert 'offered_price' in result

    def test_list_orders(self):
        agent = self._make_agent()
        agent.place_sample_order('p1', 's1', 50.0)
        agent.place_bulk_order('p2', 's2', 100, 10.0)
        orders = agent.list_orders()
        assert len(orders) == 2

    def test_to_dict(self):
        agent = self._make_agent()
        order = agent.place_bulk_order('p1', 's1', 100, 10.0)
        d = order.to_dict()
        assert 'order_id' in d
        assert 'is_sample' in d
        assert d['is_sample'] is False


# ─── AgentManager ────────────────────────────────────────────────────────────

class TestAgentManager:
    def _make_manager(self):
        from src.china_marketplace.agent_manager import AgentManager
        return AgentManager()

    def test_default_agents_registered(self):
        mgr = self._make_manager()
        agents = mgr.list_agents()
        assert len(agents) > 0

    def test_register_agent(self):
        mgr = self._make_manager()
        agent = mgr.register_agent('테스트 에이전트', 'taobao', specialties=['clothing'])
        assert agent.name == '테스트 에이전트'
        assert agent.marketplace == 'taobao'
        assert 'clothing' in agent.specialties

    def test_get_agent(self):
        mgr = self._make_manager()
        agent = mgr.register_agent('에이전트 X', 'taobao')
        fetched = mgr.get_agent(agent.agent_id)
        assert fetched is not None
        assert fetched.name == '에이전트 X'

    def test_get_agent_not_found(self):
        mgr = self._make_manager()
        assert mgr.get_agent('nonexistent') is None

    def test_list_agents_filter_by_marketplace(self):
        mgr = self._make_manager()
        tb_agents = mgr.list_agents(marketplace='taobao')
        for a in tb_agents:
            assert a.marketplace in ('taobao', 'all')

    def test_deactivate_agent(self):
        mgr = self._make_manager()
        agent = mgr.register_agent('비활성 에이전트', 'taobao')
        mgr.deactivate_agent(agent.agent_id)
        fetched = mgr.get_agent(agent.agent_id)
        assert fetched.is_active is False

    def test_assign_best_agent(self):
        mgr = self._make_manager()
        agent = mgr.assign_best_agent('order_001', 'taobao')
        assert agent is not None

    def test_assign_best_agent_with_category(self):
        mgr = self._make_manager()
        agent = mgr.assign_best_agent('order_002', 'taobao', category='clothing')
        assert agent is not None

    def test_assign_agent_specific(self):
        mgr = self._make_manager()
        new_agent = mgr.register_agent('특정 에이전트', 'taobao')
        assigned = mgr.assign_agent('order_003', new_agent.agent_id)
        assert assigned.agent_id == new_agent.agent_id

    def test_assign_agent_not_found_raises(self):
        mgr = self._make_manager()
        with pytest.raises(KeyError):
            mgr.assign_agent('order_004', 'nonexistent_agent')

    def test_get_assignment(self):
        mgr = self._make_manager()
        agent = mgr.assign_best_agent('order_005', 'taobao')
        assignment = mgr.get_assignment('order_005')
        assert assignment == agent.agent_id

    def test_record_completion(self):
        mgr = self._make_manager()
        agent = mgr.register_agent('성과 테스트', 'taobao')
        mgr.assign_agent('order_006', agent.agent_id)
        mgr.record_completion('order_006', success=True, processing_hours=12.0)
        updated = mgr.get_agent(agent.agent_id)
        assert updated.orders_processed == 1
        assert updated.success_count == 1

    def test_success_rate(self):
        mgr = self._make_manager()
        agent = mgr.register_agent('성공률 테스트', 'taobao')
        mgr.assign_agent('o1', agent.agent_id)
        mgr.assign_agent('o2', agent.agent_id)
        mgr.record_completion('o1', success=True, processing_hours=10.0)
        mgr.record_completion('o2', success=False, processing_hours=20.0)
        updated = mgr.get_agent(agent.agent_id)
        assert updated.success_rate == 0.5

    def test_overall_score(self):
        mgr = self._make_manager()
        agent = mgr.register_agent('점수 테스트', 'taobao')
        assert 0.0 <= agent.overall_score <= 1.0

    def test_get_performance_stats(self):
        mgr = self._make_manager()
        stats = mgr.get_performance_stats()
        assert 'total' in stats
        assert 'active' in stats
        assert 'agents' in stats

    def test_to_dict(self):
        mgr = self._make_manager()
        agent = mgr.register_agent('딕셔너리 테스트', 'taobao')
        d = agent.to_dict()
        assert 'agent_id' in d
        assert 'name' in d
        assert 'overall_score' in d


# ─── RPAController ───────────────────────────────────────────────────────────

class TestRPAController:
    def _make_controller(self):
        from src.china_marketplace.rpa_controller import RPAController
        return RPAController()

    def test_create_task(self):
        from src.china_marketplace.rpa_controller import RPATaskType
        ctrl = self._make_controller()
        task = ctrl.create_task(RPATaskType.search_product)
        assert task.task_id.startswith('rpa_')
        assert task.task_type == RPATaskType.search_product

    def test_execute_task_returns_task(self):
        from src.china_marketplace.rpa_controller import RPATaskType, RPATaskStatus
        ctrl = self._make_controller()
        task = ctrl.create_task(RPATaskType.search_product)
        result = ctrl.execute_task(task.task_id)
        assert result.task_id == task.task_id
        assert result.status in (RPATaskStatus.completed, RPATaskStatus.failed, RPATaskStatus.manual_required)

    def test_execute_task_sets_timestamps(self):
        from src.china_marketplace.rpa_controller import RPATaskType, RPATaskStatus
        ctrl = self._make_controller()
        task = ctrl.create_task(RPATaskType.place_order)
        result = ctrl.execute_task(task.task_id)
        assert result.completed_at is not None

    def test_get_task(self):
        from src.china_marketplace.rpa_controller import RPATaskType
        ctrl = self._make_controller()
        task = ctrl.create_task(RPATaskType.check_status)
        fetched = ctrl.get_task(task.task_id)
        assert fetched is not None

    def test_get_task_not_found(self):
        ctrl = self._make_controller()
        assert ctrl.get_task('nonexistent') is None

    def test_list_tasks(self):
        from src.china_marketplace.rpa_controller import RPATaskType
        ctrl = self._make_controller()
        ctrl.create_task(RPATaskType.search_product)
        ctrl.create_task(RPATaskType.place_order)
        tasks = ctrl.list_tasks()
        assert len(tasks) == 2

    def test_execute_not_found_raises(self):
        ctrl = self._make_controller()
        with pytest.raises(KeyError):
            ctrl.execute_task('nonexistent_task')

    def test_task_steps_built(self):
        from src.china_marketplace.rpa_controller import RPATaskType, RPATaskStatus
        ctrl = self._make_controller()
        task = ctrl.create_task(RPATaskType.search_product)
        result = ctrl.execute_task(task.task_id)
        assert len(result.steps) > 0

    def test_to_dict(self):
        from src.china_marketplace.rpa_controller import RPATaskType
        ctrl = self._make_controller()
        task = ctrl.create_task(RPATaskType.apply_coupon)
        ctrl.execute_task(task.task_id)
        d = task.to_dict()
        assert 'task_id' in d
        assert 'task_type' in d
        assert 'status' in d
        assert 'steps' in d

    def test_get_stats(self):
        from src.china_marketplace.rpa_controller import RPATaskType
        ctrl = self._make_controller()
        ctrl.create_task(RPATaskType.search_product)
        stats = ctrl.get_stats()
        assert 'total' in stats
        assert 'by_status' in stats
        assert 'by_type' in stats


# ─── SellerVerificationService ───────────────────────────────────────────────

class TestSellerVerificationService:
    def _make_service(self):
        from src.china_marketplace.seller_verification import SellerVerificationService
        return SellerVerificationService()

    def test_register_seller(self):
        svc = self._make_service()
        profile = svc.register_seller(
            seller_id='s001', name='우수판매자', marketplace='taobao',
            rating=4.8, sales_count=5000, years_active=3.0,
        )
        assert profile.seller_id == 's001'
        assert profile.name == '우수판매자'

    def test_get_seller(self):
        svc = self._make_service()
        svc.register_seller('s002', '판매자2', 'taobao', 4.5, 1000, 2.0)
        p = svc.get_seller('s002')
        assert p is not None

    def test_get_seller_not_found(self):
        svc = self._make_service()
        assert svc.get_seller('nonexistent') is None

    def test_verify_seller_returns_score(self):
        svc = self._make_service()
        svc.register_seller('s003', '검증셀러', 'taobao', 4.9, 10000, 5.0)
        score = svc.verify_seller('s003')
        assert score.seller_id == 's003'
        assert 0 <= score.overall <= 100
        assert score.recommendation in ('approved', 'caution', 'rejected')

    def test_verify_unregistered_seller(self):
        svc = self._make_service()
        score = svc.verify_seller('unknown_seller')
        assert score.seller_id == 'unknown_seller'
        assert score.overall >= 0

    def test_blacklisted_seller_gets_zero_score(self):
        svc = self._make_service()
        svc.add_to_blacklist('s_bad', '사기 셀러')
        score = svc.verify_seller('s_bad')
        assert score.overall == 0.0
        assert score.recommendation == 'rejected'

    def test_add_to_blacklist(self):
        svc = self._make_service()
        svc.add_to_blacklist('s_evil', '사기')
        assert svc.is_blacklisted('s_evil') is True
        assert 's_evil' in svc.get_blacklist()

    def test_remove_from_blacklist(self):
        svc = self._make_service()
        svc.add_to_blacklist('s_temp')
        svc.remove_from_blacklist('s_temp')
        assert svc.is_blacklisted('s_temp') is False

    def test_add_to_whitelist(self):
        svc = self._make_service()
        svc.add_to_whitelist('s_good')
        assert svc.is_whitelisted('s_good') is True
        assert 's_good' in svc.get_whitelist()

    def test_remove_from_whitelist(self):
        svc = self._make_service()
        svc.add_to_whitelist('s_good')
        svc.remove_from_whitelist('s_good')
        assert svc.is_whitelisted('s_good') is False

    def test_get_stats(self):
        svc = self._make_service()
        svc.register_seller('s1', 'seller1', 'taobao', 4.5, 1000, 2.0)
        svc.add_to_blacklist('bl_seller')
        svc.add_to_whitelist('wl_seller')
        stats = svc.get_stats()
        assert stats['blacklisted'] == 1
        assert stats['whitelisted'] == 1

    def test_seller_profile_to_dict(self):
        svc = self._make_service()
        p = svc.register_seller('s4', 'seller4', 'taobao', 4.0, 500, 1.5)
        d = p.to_dict()
        assert 'seller_id' in d
        assert 'verification_status' in d

    def test_seller_score_to_dict(self):
        svc = self._make_service()
        score = svc.verify_seller('any_seller')
        d = score.to_dict()
        assert 'reliability' in d
        assert 'overall' in d
        assert 'recommendation' in d


# ─── ChinaPaymentService ─────────────────────────────────────────────────────

class TestChinaPaymentService:
    def _make_service(self):
        from src.china_marketplace.payment import ChinaPaymentService
        return ChinaPaymentService(cny_krw_rate=188.0)

    def test_convert_cny_to_krw(self):
        svc = self._make_service()
        krw = svc.convert_cny_to_krw(100.0)
        assert krw == 18800.0

    def test_convert_krw_to_cny(self):
        svc = self._make_service()
        cny = svc.convert_krw_to_cny(18800.0)
        assert abs(cny - 100.0) < 0.01

    def test_update_exchange_rate(self):
        svc = self._make_service()
        svc.update_exchange_rate(190.0)
        assert svc.get_exchange_rate()['cny_krw'] == 190.0

    def test_get_exchange_rate(self):
        svc = self._make_service()
        rate = svc.get_exchange_rate()
        assert 'cny_krw' in rate
        assert 'krw_cny' in rate

    def test_pay_alipay_success(self):
        svc = self._make_service()
        record = svc.pay('order_001', 100.0, provider='alipay')
        assert record.provider == 'alipay'
        assert record.amount_cny == 100.0
        assert record.amount_krw == 18800.0

    def test_pay_wechatpay(self):
        svc = self._make_service()
        record = svc.pay('order_002', 50.0, provider='wechatpay')
        assert record.provider == 'wechatpay'

    def test_pay_over_limit_fails(self):
        from src.china_marketplace.payment import ChinaPaymentService
        svc = ChinaPaymentService()
        record = svc.pay('order_003', 60000.0, provider='alipay')
        assert record.status == 'failed'

    def test_pay_stores_record(self):
        svc = self._make_service()
        record = svc.pay('order_004', 100.0)
        fetched = svc.get_record(record.payment_id)
        assert fetched is not None

    def test_refund(self):
        svc = self._make_service()
        record = svc.pay('order_005', 100.0, provider='alipay')
        if record.status == 'completed':
            result = svc.refund(record.payment_id)
            assert result['success'] is True
            updated = svc.get_record(record.payment_id)
            assert updated.status == 'refunded'

    def test_refund_not_found(self):
        svc = self._make_service()
        result = svc.refund('nonexistent_payment')
        assert result['success'] is False

    def test_list_records(self):
        svc = self._make_service()
        svc.pay('o1', 10.0)
        svc.pay('o2', 20.0)
        records = svc.list_records()
        assert len(records) == 2

    def test_list_records_filter_by_order(self):
        svc = self._make_service()
        svc.pay('o1', 10.0)
        svc.pay('o2', 20.0)
        records = svc.list_records(order_id='o1')
        assert len(records) == 1
        assert records[0].order_id == 'o1'

    def test_get_limit_status(self):
        svc = self._make_service()
        limits = svc.get_limit_status()
        assert 'alipay' in limits
        assert 'wechatpay' in limits

    def test_get_stats(self):
        svc = self._make_service()
        svc.pay('o1', 50.0)
        stats = svc.get_stats()
        assert 'total_records' in stats
        assert 'by_provider' in stats

    def test_payment_record_to_dict(self):
        svc = self._make_service()
        record = svc.pay('o_dict', 10.0)
        d = record.to_dict()
        assert 'payment_id' in d
        assert 'amount_cny' in d
        assert 'exchange_rate' in d


class TestAlipayProvider:
    def test_pay_success(self):
        from src.china_marketplace.payment import AlipayProvider
        provider = AlipayProvider()
        result = provider.pay('order_001', 100.0)
        assert result['success'] is True
        assert result['payment_id'].startswith('ALI_')

    def test_pay_over_single_limit(self):
        from src.china_marketplace.payment import AlipayProvider
        provider = AlipayProvider()
        result = provider.pay('order_002', 60000.0)
        assert result['success'] is False
        assert '한도' in result['error']

    def test_daily_limit(self):
        from src.china_marketplace.payment import AlipayProvider
        provider = AlipayProvider()
        provider._daily_used_cny = 190000.0
        result = provider.pay('order_003', 20000.0)
        assert result['success'] is False

    def test_reset_daily_limit(self):
        from src.china_marketplace.payment import AlipayProvider
        provider = AlipayProvider()
        provider._daily_used_cny = 50000.0
        provider.reset_daily_limit()
        assert provider._daily_used_cny == 0.0

    def test_get_limit_status(self):
        from src.china_marketplace.payment import AlipayProvider
        provider = AlipayProvider()
        status = provider.get_limit_status()
        assert status['provider'] == 'alipay'
        assert 'daily_limit_cny' in status


class TestWechatPayProvider:
    def test_pay_success(self):
        from src.china_marketplace.payment import WechatPayProvider
        provider = WechatPayProvider()
        result = provider.pay('order_001', 100.0)
        assert result['success'] is True
        assert result['payment_id'].startswith('WX_')

    def test_pay_over_single_limit(self):
        from src.china_marketplace.payment import WechatPayProvider
        provider = WechatPayProvider()
        result = provider.pay('order_002', 25000.0)
        assert result['success'] is False


# ─── ChinaPurchaseDashboard ──────────────────────────────────────────────────

class TestChinaPurchaseDashboard:
    def _make_dashboard(self):
        from src.china_marketplace.engine import ChinaMarketplaceEngine
        from src.china_marketplace.agent_manager import AgentManager
        from src.china_marketplace.seller_verification import SellerVerificationService
        from src.china_marketplace.payment import ChinaPaymentService
        from src.china_marketplace.rpa_controller import RPAController
        from src.china_marketplace.dashboard import ChinaPurchaseDashboard
        return ChinaPurchaseDashboard(
            engine=ChinaMarketplaceEngine(),
            agent_manager=AgentManager(),
            seller_service=SellerVerificationService(),
            payment_service=ChinaPaymentService(),
            rpa_controller=RPAController(),
        )

    def test_get_summary(self):
        dashboard = self._make_dashboard()
        summary = dashboard.get_summary()
        assert 'orders' in summary
        assert 'agents' in summary
        assert 'sellers' in summary
        assert 'payments' in summary
        assert 'rpa' in summary

    def test_get_order_status_chart(self):
        dashboard = self._make_dashboard()
        chart = dashboard.get_order_status_chart()
        assert 'taobao' in chart
        assert '1688' in chart

    def test_get_agent_performance(self):
        dashboard = self._make_dashboard()
        perf = dashboard.get_agent_performance()
        assert 'total' in perf

    def test_get_seller_distribution(self):
        dashboard = self._make_dashboard()
        dist = dashboard.get_seller_distribution()
        assert 'total' in dist

    def test_get_payment_stats(self):
        dashboard = self._make_dashboard()
        stats = dashboard.get_payment_stats()
        assert 'payment_stats' in stats
        assert 'exchange_rate' in stats

    def test_get_rpa_stats(self):
        dashboard = self._make_dashboard()
        stats = dashboard.get_rpa_stats()
        assert 'total' in stats


# ─── API Blueprint ───────────────────────────────────────────────────────────

class TestChinaMarketplaceAPI:
    def _make_client(self):
        from flask import Flask
        from src.api.china_marketplace_api import china_marketplace_bp
        app = Flask(__name__)
        app.register_blueprint(china_marketplace_bp)
        return app.test_client()

    def test_search_taobao(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/search', json={'keyword': '운동화', 'marketplace': 'taobao'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['marketplace'] == 'taobao'
        assert 'results' in data

    def test_search_1688(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/search', json={'keyword': '전자부품', 'marketplace': '1688'})
        assert resp.status_code == 200

    def test_search_missing_keyword(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/search', json={})
        assert resp.status_code == 400

    def test_search_invalid_marketplace(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/search', json={'keyword': 'test', 'marketplace': 'amazon'})
        assert resp.status_code == 400

    def test_get_product(self):
        client = self._make_client()
        resp = client.get('/api/v1/china-marketplace/product/https://item.taobao.com/item.htm?id=123')
        assert resp.status_code == 200

    def test_create_order(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/orders', json={
            'marketplace': 'taobao',
            'product_url': 'https://item.taobao.com/item.htm?id=123',
            'quantity': 2,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'order_id' in data

    def test_create_order_missing_url(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/orders', json={'marketplace': 'taobao'})
        assert resp.status_code == 400

    def test_list_orders(self):
        client = self._make_client()
        resp = client.get('/api/v1/china-marketplace/orders')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'orders' in data

    def test_get_order_not_found(self):
        client = self._make_client()
        resp = client.get('/api/v1/china-marketplace/orders/nonexistent')
        assert resp.status_code == 404

    def test_cancel_order_not_found(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/orders/nonexistent/cancel', json={})
        assert resp.status_code == 404

    def test_get_tracking(self):
        client = self._make_client()
        # Create order first
        create_resp = client.post('/api/v1/china-marketplace/orders', json={
            'marketplace': 'taobao',
            'product_url': 'https://item.taobao.com/item.htm?id=999',
            'quantity': 1,
        })
        order_id = create_resp.get_json()['order_id']
        resp = client.get(f'/api/v1/china-marketplace/orders/{order_id}/tracking')
        assert resp.status_code == 200

    def test_verify_seller(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/seller/verify', json={'seller_id': 'seller_001'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'recommendation' in data

    def test_verify_seller_missing_id(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/seller/verify', json={})
        assert resp.status_code == 400

    def test_get_seller_not_found(self):
        client = self._make_client()
        resp = client.get('/api/v1/china-marketplace/seller/nonexistent')
        assert resp.status_code == 404

    def test_get_blacklist(self):
        client = self._make_client()
        resp = client.get('/api/v1/china-marketplace/sellers/blacklist')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'blacklist' in data

    def test_add_to_blacklist(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/sellers/blacklist', json={'seller_id': 'bad_seller', 'reason': '사기'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['blacklisted'] is True

    def test_add_to_blacklist_missing_id(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/sellers/blacklist', json={})
        assert resp.status_code == 400

    def test_list_agents(self):
        client = self._make_client()
        resp = client.get('/api/v1/china-marketplace/agents')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'agents' in data
        assert len(data['agents']) > 0

    def test_assign_agent_not_found_order(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/agents/nonexistent/assign', json={'order_id': 'o1'})
        assert resp.status_code == 404

    def test_assign_agent_missing_order_id(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/agents/a1/assign', json={})
        assert resp.status_code == 400

    def test_create_rpa_task(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/rpa/task', json={
            'task_type': 'search_product',
            'auto_execute': True,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'task_id' in data

    def test_create_rpa_task_invalid_type(self):
        client = self._make_client()
        resp = client.post('/api/v1/china-marketplace/rpa/task', json={'task_type': 'invalid_type'})
        assert resp.status_code == 400

    def test_list_rpa_tasks(self):
        client = self._make_client()
        resp = client.get('/api/v1/china-marketplace/rpa/tasks')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'tasks' in data

    def test_get_dashboard(self):
        client = self._make_client()
        resp = client.get('/api/v1/china-marketplace/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'orders' in data


# ─── 봇 커맨드 ──────────────────────────────────────────────────────────────

class TestChinaMarketplaceCommands:
    def test_cmd_china_search(self):
        from src.bot.commands import cmd_china_search
        result = cmd_china_search('운동화')
        assert isinstance(result, str)
        assert '운동화' in result or '검색' in result

    def test_cmd_china_search_empty(self):
        from src.bot.commands import cmd_china_search
        result = cmd_china_search('')
        assert '사용법' in result

    def test_cmd_china_buy(self):
        from src.bot.commands import cmd_china_buy
        result = cmd_china_buy('https://item.taobao.com/item.htm?id=123', 2)
        assert isinstance(result, str)
        assert '주문' in result or '생성' in result

    def test_cmd_china_buy_empty(self):
        from src.bot.commands import cmd_china_buy
        result = cmd_china_buy('')
        assert '사용법' in result

    def test_cmd_china_status_empty(self):
        from src.bot.commands import cmd_china_status
        result = cmd_china_status('')
        assert '사용법' in result

    def test_cmd_china_status_not_found(self):
        from src.bot.commands import cmd_china_status
        result = cmd_china_status('nonexistent_order')
        assert isinstance(result, str)

    def test_cmd_seller_check(self):
        from src.bot.commands import cmd_seller_check
        result = cmd_seller_check('seller_001')
        assert isinstance(result, str)
        assert '셀러' in result or '검증' in result

    def test_cmd_seller_check_empty(self):
        from src.bot.commands import cmd_seller_check
        result = cmd_seller_check('')
        assert '사용법' in result

    def test_cmd_china_dashboard(self):
        from src.bot.commands import cmd_china_dashboard
        result = cmd_china_dashboard()
        assert isinstance(result, str)
        assert '대시보드' in result or '중국' in result


# ─── 포매터 ──────────────────────────────────────────────────────────────────

class TestChinaMarketplaceFormatters:
    def test_format_china_order(self):
        from src.bot.formatters import format_message
        data = {
            'order_id': 'cn_test001',
            'marketplace': 'taobao',
            'quantity': 2,
            'status': 'created',
            'agent': 'agent_001',
        }
        result = format_message('china_order', data)
        assert 'cn_test001' in result
        assert 'taobao' in result

    def test_format_china_search(self):
        from src.bot.formatters import format_message
        data = {
            'marketplace': 'taobao',
            'keyword': '운동화',
            'results': [
                {'title': '나이키 운동화', 'price_cny': 150.0},
            ],
        }
        result = format_message('china_search', data)
        assert '운동화' in result

    def test_format_china_seller_score(self):
        from src.bot.formatters import format_message
        data = {
            'seller_id': 's001',
            'reliability': 85.0,
            'quality': 90.0,
            'shipping_speed': 80.0,
            'communication': 88.0,
            'overall': 86.0,
            'recommendation': 'approved',
        }
        result = format_message('china_seller_score', data)
        assert 's001' in result or '셀러' in result

    def test_format_china_dashboard(self):
        from src.bot.formatters import format_message
        data = {
            'orders': {'total': 10},
            'payments': {'total_amount_cny': 5000.0},
            'rpa': {'total_tasks': 5, 'success_rate': 0.9},
        }
        result = format_message('china_dashboard', data)
        assert '10' in result or '대시보드' in result

    def test_format_rpa_task(self):
        from src.bot.formatters import format_message
        data = {
            'task_id': 'rpa_test001',
            'task_type': 'search_product',
            'status': 'completed',
            'steps': [{'step_id': 'step_001', 'action': 'navigate', 'target': 'https://taobao.com', 'value': '', 'screenshot_url': None, 'executed_at': None, 'success': True}],
        }
        result = format_message('rpa_task', data)
        assert 'rpa_test001' in result or 'RPA' in result
