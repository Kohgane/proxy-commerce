"""tests/test_wishlist.py — Phase 43: 위시리스트/관심상품 관리 테스트."""
import pytest


class TestWishlistManager:
    def setup_method(self):
        from src.wishlist.wishlist_manager import WishlistManager
        self.mgr = WishlistManager()

    def test_create_wishlist(self):
        wl = self.mgr.create_wishlist('user1', '내 위시리스트')
        assert wl['user_id'] == 'user1'
        assert wl['name'] == '내 위시리스트'
        assert 'id' in wl

    def test_list_wishlists(self):
        self.mgr.create_wishlist('u1', 'A')
        self.mgr.create_wishlist('u1', 'B')
        self.mgr.create_wishlist('u2', 'C')
        assert len(self.mgr.list_wishlists('u1')) == 2
        assert len(self.mgr.list_wishlists('u2')) == 1

    def test_max_wishlists_per_user(self):
        from src.wishlist.wishlist_manager import MAX_WISHLISTS_PER_USER
        for i in range(MAX_WISHLISTS_PER_USER):
            self.mgr.create_wishlist('u1', f'WL{i}')
        with pytest.raises(ValueError):
            self.mgr.create_wishlist('u1', 'overflow')

    def test_rename_wishlist(self):
        wl = self.mgr.create_wishlist('u1', '원래')
        updated = self.mgr.rename_wishlist(wl['id'], '새이름')
        assert updated['name'] == '새이름'

    def test_delete_wishlist_removes_items(self):
        wl = self.mgr.create_wishlist('u1', '테스트')
        item = self.mgr.add_item(wl['id'], 'P001')
        self.mgr.delete_wishlist(wl['id'])
        assert self.mgr.get_wishlist(wl['id']) is None
        assert self.mgr.get_item(item['id']) is None

    def test_add_item(self):
        wl = self.mgr.create_wishlist('u1')
        item = self.mgr.add_item(wl['id'], 'P001', memo='메모', priority=2)
        assert item['product_id'] == 'P001'
        assert item['memo'] == '메모'
        assert item['priority'] == 2

    def test_add_item_invalid_priority(self):
        wl = self.mgr.create_wishlist('u1')
        with pytest.raises(ValueError):
            self.mgr.add_item(wl['id'], 'P001', priority=6)

    def test_add_item_invalid_wishlist(self):
        with pytest.raises(KeyError):
            self.mgr.add_item('nonexistent', 'P001')

    def test_max_items_per_wishlist(self):
        from src.wishlist.wishlist_manager import MAX_ITEMS_PER_WISHLIST
        wl = self.mgr.create_wishlist('u1')
        for i in range(MAX_ITEMS_PER_WISHLIST):
            self.mgr.add_item(wl['id'], f'P{i:03d}')
        with pytest.raises(ValueError):
            self.mgr.add_item(wl['id'], 'P999')

    def test_remove_item(self):
        wl = self.mgr.create_wishlist('u1')
        item = self.mgr.add_item(wl['id'], 'P001')
        assert self.mgr.remove_item(item['id'])
        assert self.mgr.get_item(item['id']) is None

    def test_list_items(self):
        wl = self.mgr.create_wishlist('u1')
        self.mgr.add_item(wl['id'], 'P001')
        self.mgr.add_item(wl['id'], 'P002')
        assert len(self.mgr.list_items(wl['id'])) == 2

    def test_move_item(self):
        wl1 = self.mgr.create_wishlist('u1', 'A')
        wl2 = self.mgr.create_wishlist('u1', 'B')
        item = self.mgr.add_item(wl1['id'], 'P001')
        moved = self.mgr.move_item(item['id'], wl2['id'])
        assert moved['wishlist_id'] == wl2['id']

    def test_update_item(self):
        wl = self.mgr.create_wishlist('u1')
        item = self.mgr.add_item(wl['id'], 'P001', priority=3)
        updated = self.mgr.update_item(item['id'], memo='새메모', priority=5)
        assert updated['memo'] == '새메모'
        assert updated['priority'] == 5


class TestPriceWatch:
    def setup_method(self):
        from src.wishlist.price_watch import PriceWatch
        self.pw = PriceWatch()

    def test_watch(self):
        watch = self.pw.watch('u1', 'P001', 10000)
        assert watch['user_id'] == 'u1'
        assert watch['target_price'] == 10000.0

    def test_unwatch(self):
        self.pw.watch('u1', 'P001', 10000)
        assert self.pw.unwatch('u1', 'P001')
        assert self.pw.get_watch('u1', 'P001') is None

    def test_record_price_triggers_alert(self):
        self.pw.watch('u1', 'P001', 10000)
        self.pw.record_price('P001', 9500)
        alerts = self.pw.get_alerts('u1')
        assert len(alerts) == 1
        assert alerts[0]['current_price'] == 9500

    def test_record_price_no_alert_above_target(self):
        self.pw.watch('u1', 'P001', 10000)
        self.pw.record_price('P001', 11000)
        alerts = self.pw.get_alerts('u1')
        assert len(alerts) == 0

    def test_price_history(self):
        self.pw.record_price('P001', 10000)
        self.pw.record_price('P001', 9800)
        history = self.pw.get_price_history('P001')
        assert len(history) == 2

    def test_list_watches(self):
        self.pw.watch('u1', 'P001', 10000)
        self.pw.watch('u1', 'P002', 5000)
        self.pw.watch('u2', 'P003', 3000)
        assert len(self.pw.list_watches('u1')) == 2


class TestWishlistShare:
    def setup_method(self):
        from src.wishlist.share import WishlistShare
        self.share = WishlistShare()

    def test_create_share(self):
        record = self.share.create_share('wl1')
        assert 'token' in record
        assert record['wishlist_id'] == 'wl1'
        assert record['active'] is True

    def test_is_valid(self):
        record = self.share.create_share('wl1')
        assert self.share.is_valid(record['token'])

    def test_revoke_share(self):
        record = self.share.create_share('wl1')
        self.share.revoke_share(record['token'])
        assert not self.share.is_valid(record['token'])

    def test_invalid_token(self):
        assert not self.share.is_valid('nonexistent_token')

    def test_expired_share(self):
        record = self.share.create_share('wl1', expires_at='2000-01-01T00:00:00+00:00')
        assert not self.share.is_valid(record['token'])

    def test_list_shares(self):
        self.share.create_share('wl1')
        self.share.create_share('wl1')
        self.share.create_share('wl2')
        assert len(self.share.list_shares('wl1')) == 2


class TestWishlistRecommender:
    def setup_method(self):
        from src.wishlist.recommendations import WishlistRecommender
        self.catalog = [
            {'id': 'P001', 'category': '전자제품', 'tags': ['노트북', '컴퓨터']},
            {'id': 'P002', 'category': '전자제품', 'tags': ['노트북', '게이밍']},
            {'id': 'P003', 'category': '의류', 'tags': ['티셔츠']},
            {'id': 'P004', 'category': '전자제품', 'tags': ['태블릿']},
        ]
        self.recommender = WishlistRecommender(self.catalog)

    def test_recommend_by_category(self):
        items = [{'product_id': 'P001'}]
        recs = self.recommender.recommend(items)
        rec_ids = [r['id'] for r in recs]
        assert 'P001' not in rec_ids
        assert 'P002' in rec_ids or 'P004' in rec_ids

    def test_recommend_empty_wishlist(self):
        recs = self.recommender.recommend([])
        assert recs == []

    def test_similar_products(self):
        similar = self.recommender.similar_products('P001')
        ids = [p['id'] for p in similar]
        assert 'P001' not in ids
        assert 'P002' in ids

    def test_similar_product_not_found(self):
        result = self.recommender.similar_products('NOTEXIST')
        assert result == []
