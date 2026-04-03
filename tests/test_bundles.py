"""tests/test_bundles.py — Phase 44: 상품 번들/세트 관리 테스트."""
import pytest


class TestBundleManager:
    def setup_method(self):
        from src.bundles.bundle_manager import BundleManager
        self.mgr = BundleManager()

    def test_create_fixed_bundle(self):
        bundle = self.mgr.create({'name': '기본 세트', 'type': 'fixed'})
        assert bundle['type'] == 'fixed'
        assert bundle['status'] == 'draft'

    def test_create_pick_n_bundle(self):
        bundle = self.mgr.create({'name': '2개 선택', 'type': 'pick_n', 'pick_count': 2})
        assert bundle['type'] == 'pick_n'
        assert bundle['pick_count'] == 2

    def test_create_mix_match_bundle(self):
        bundle = self.mgr.create({'type': 'mix_match', 'min_items': 2, 'max_items': 5})
        assert bundle['type'] == 'mix_match'

    def test_create_invalid_type(self):
        with pytest.raises(ValueError):
            self.mgr.create({'type': 'invalid'})

    def test_get_bundle(self):
        bundle = self.mgr.create({'type': 'fixed'})
        found = self.mgr.get(bundle['id'])
        assert found['id'] == bundle['id']

    def test_list_all(self):
        self.mgr.create({'type': 'fixed', 'status': 'active'})
        self.mgr.create({'type': 'pick_n', 'status': 'draft'})
        assert len(self.mgr.list_all()) == 2

    def test_list_by_status(self):
        self.mgr.create({'type': 'fixed', 'status': 'active'})
        self.mgr.create({'type': 'fixed', 'status': 'draft'})
        active = self.mgr.list_all(status='active')
        assert len(active) == 1

    def test_add_item(self):
        bundle = self.mgr.create({'type': 'fixed'})
        updated = self.mgr.add_item(bundle['id'], 'P001', 2)
        assert len(updated['items']) == 1
        assert updated['items'][0]['product_id'] == 'P001'

    def test_add_item_duplicate(self):
        bundle = self.mgr.create({'type': 'fixed'})
        self.mgr.add_item(bundle['id'], 'P001', 1)
        updated = self.mgr.add_item(bundle['id'], 'P001', 2)
        assert len(updated['items']) == 1
        assert updated['items'][0]['quantity'] == 3

    def test_remove_item(self):
        bundle = self.mgr.create({'type': 'fixed'})
        self.mgr.add_item(bundle['id'], 'P001')
        updated = self.mgr.remove_item(bundle['id'], 'P001')
        assert len(updated['items']) == 0

    def test_activate_deactivate(self):
        bundle = self.mgr.create({'type': 'fixed'})
        self.mgr.activate(bundle['id'])
        assert self.mgr.get(bundle['id'])['status'] == 'active'
        self.mgr.deactivate(bundle['id'])
        assert self.mgr.get(bundle['id'])['status'] == 'inactive'

    def test_delete(self):
        bundle = self.mgr.create({'type': 'fixed'})
        assert self.mgr.delete(bundle['id'])
        assert self.mgr.get(bundle['id']) is None


class TestBundlePricing:
    def setup_method(self):
        from src.bundles.pricing import BundlePricing
        self.pricing = BundlePricing()
        self.items = [
            {'product_id': 'P001', 'quantity': 1, 'unit_price': 10000},
            {'product_id': 'P002', 'quantity': 2, 'unit_price': 5000},
        ]

    def test_sum_discount_strategy(self):
        result = self.pricing.calculate(self.items, strategy='sum_discount', discount_pct=10)
        assert result['original_price'] == 20000
        assert result['final_price'] == 18000
        assert result['discount_amount'] == 2000

    def test_fixed_price_strategy(self):
        result = self.pricing.calculate(self.items, strategy='fixed_price', fixed_price=15000)
        assert result['final_price'] == 15000

    def test_cheapest_free_strategy(self):
        result = self.pricing.calculate(self.items, strategy='cheapest_free')
        assert result['discount_amount'] == 5000
        assert result['final_price'] == 15000

    def test_invalid_strategy(self):
        with pytest.raises(ValueError):
            self.pricing.calculate(self.items, strategy='unknown')

    def test_fixed_price_without_price_raises(self):
        with pytest.raises(ValueError):
            self.pricing.calculate(self.items, strategy='fixed_price')

    def test_zero_discount(self):
        result = self.pricing.calculate(self.items, strategy='sum_discount', discount_pct=0)
        assert result['final_price'] == result['original_price']


class TestBundleAvailability:
    def setup_method(self):
        from src.bundles.availability import BundleAvailability
        self.avail = BundleAvailability()
        self.bundle = {
            'id': 'B001',
            'items': [
                {'product_id': 'P001', 'quantity': 2},
                {'product_id': 'P002', 'quantity': 1},
            ]
        }

    def test_all_available(self):
        stock = {'P001': 5, 'P002': 3}
        result = self.avail.check(self.bundle, stock)
        assert result['available'] is True
        assert result['unavailable_items'] == []

    def test_partially_unavailable(self):
        stock = {'P001': 1, 'P002': 5}
        result = self.avail.check(self.bundle, stock)
        assert result['available'] is False
        assert len(result['unavailable_items']) == 1

    def test_all_unavailable(self):
        stock = {}
        result = self.avail.check(self.bundle, stock)
        assert result['available'] is False

    def test_suggest_alternatives(self):
        catalog = [
            {'id': 'P001', 'category': '전자'},
            {'id': 'PA', 'category': '전자'},
            {'id': 'PB', 'category': '의류'},
        ]
        unavail = [{'product_id': 'P001', 'required': 2, 'in_stock': 0}]
        suggestions = self.avail.suggest_alternatives(unavail, catalog)
        assert len(suggestions) == 1
        assert suggestions[0]['original_product_id'] == 'P001'


class TestBundleSuggestion:
    def setup_method(self):
        from src.bundles.suggestions import BundleSuggestion
        self.sugg = BundleSuggestion()
        orders = [
            {'order_id': 'O1', 'items': ['P001', 'P002']},
            {'order_id': 'O2', 'items': ['P001', 'P002']},
            {'order_id': 'O3', 'items': ['P001', 'P003']},
            {'order_id': 'O4', 'items': ['P002', 'P003']},
        ]
        self.sugg.process_orders(orders)

    def test_suggest_bundles(self):
        suggestions = self.sugg.suggest_bundles(min_frequency=2)
        assert len(suggestions) > 0
        assert suggestions[0]['frequency'] >= 2

    def test_suggest_for_product(self):
        suggestions = self.sugg.suggest_for_product('P001')
        assert len(suggestions) > 0
        product_ids = [s['product_id'] for s in suggestions]
        assert 'P002' in product_ids

    def test_no_suggestions_below_frequency(self):
        suggestions = self.sugg.suggest_bundles(min_frequency=100)
        assert len(suggestions) == 0
