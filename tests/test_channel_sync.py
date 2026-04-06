"""tests/test_channel_sync.py — Phase 109: 판매채널 자동 연동 테스트 (40개+)."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── Publishers: base ────────────────────────────────────────────────────────

class TestListingState:
    def test_values(self):
        from src.channel_sync.publishers.base import ListingState
        assert ListingState.draft == 'draft'
        assert ListingState.pending_review == 'pending_review'
        assert ListingState.active == 'active'
        assert ListingState.paused == 'paused'
        assert ListingState.inactive == 'inactive'
        assert ListingState.deleted == 'deleted'
        assert ListingState.error == 'error'

    def test_is_str(self):
        from src.channel_sync.publishers.base import ListingState
        assert isinstance(ListingState.active, str)


class TestPublishResult:
    def test_success(self):
        from src.channel_sync.publishers.base import PublishResult
        r = PublishResult(success=True, listing_id='lid-1', channel='coupang', message='ok')
        assert r.success is True
        assert r.listing_id == 'lid-1'
        assert r.executed_at != ''

    def test_failure(self):
        from src.channel_sync.publishers.base import PublishResult
        r = PublishResult(success=False, channel='naver', error='not found')
        assert r.success is False
        assert r.error == 'not found'

    def test_to_dict(self):
        from src.channel_sync.publishers.base import PublishResult
        r = PublishResult(success=True, listing_id='lid-1', channel='coupang')
        d = r.to_dict()
        assert d['success'] is True
        assert d['listing_id'] == 'lid-1'
        assert 'executed_at' in d


class TestListingStatus:
    def test_creation(self):
        from src.channel_sync.publishers.base import ListingStatus, ListingState
        ls = ListingStatus(listing_id='l1', channel='coupang', product_id='p1')
        assert ls.listing_id == 'l1'
        assert ls.state == ListingState.draft

    def test_to_dict(self):
        from src.channel_sync.publishers.base import ListingStatus
        ls = ListingStatus(listing_id='l1', channel='coupang', product_id='p1', price=10000.0)
        d = ls.to_dict()
        assert d['listing_id'] == 'l1'
        assert d['price'] == 10000.0
        assert isinstance(d['state'], str)


# ─── Publishers: CoupangPublisher ────────────────────────────────────────────

class TestCoupangPublisher:
    def _make(self):
        from src.channel_sync.publishers.coupang import CoupangPublisher
        return CoupangPublisher()

    def test_channel_name(self):
        pub = self._make()
        assert pub.channel_name == 'coupang'

    def test_publish(self):
        pub = self._make()
        result = pub.publish({'product_id': 'p1', 'title': '테스트', 'price': 10000, 'stock': 5})
        assert result.success is True
        assert result.listing_id is not None

    def test_publish_creates_listing(self):
        pub = self._make()
        result = pub.publish({'product_id': 'p1', 'price': 10000})
        assert pub.get_status(result.listing_id) is not None

    def test_update(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 10000})
        result = pub.update(r.listing_id, {'price': 12000, 'stock': 3})
        assert result.success is True

    def test_update_not_found(self):
        pub = self._make()
        result = pub.update('nonexistent', {'price': 1000})
        assert result.success is False
        assert result.error == 'listing not found'

    def test_deactivate(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 10000})
        result = pub.deactivate(r.listing_id, '품절')
        assert result.success is True
        from src.channel_sync.publishers.base import ListingState
        assert pub.get_status(r.listing_id).state == ListingState.paused

    def test_activate(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 10000})
        pub.deactivate(r.listing_id, '품절')
        result = pub.activate(r.listing_id)
        assert result.success is True
        from src.channel_sync.publishers.base import ListingState
        assert pub.get_status(r.listing_id).state == ListingState.active

    def test_delete(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 10000})
        result = pub.delete(r.listing_id)
        assert result.success is True
        from src.channel_sync.publishers.base import ListingState
        assert pub.get_status(r.listing_id).state == ListingState.deleted

    def test_health_check(self):
        pub = self._make()
        assert pub.health_check() is True

    def test_fee_applied(self):
        pub = self._make()
        result = pub.publish({'product_id': 'p1', 'price': 10000, 'category': 'electronics'})
        listing = pub.get_status(result.listing_id)
        # 10% 수수료 적용 후 가격이 더 높아야 함
        assert listing.price > 10000


# ─── Publishers: NaverPublisher ──────────────────────────────────────────────

class TestNaverPublisher:
    def _make(self):
        from src.channel_sync.publishers.naver import NaverPublisher
        return NaverPublisher()

    def test_channel_name(self):
        pub = self._make()
        assert pub.channel_name == 'naver'

    def test_publish(self):
        pub = self._make()
        result = pub.publish({'product_id': 'p1', 'title': '네이버 상품', 'price': 15000, 'stock': 10})
        assert result.success is True
        assert result.listing_id is not None

    def test_update(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 15000})
        result = pub.update(r.listing_id, {'price': 17000})
        assert result.success is True

    def test_deactivate(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 15000})
        result = pub.deactivate(r.listing_id, '소싱처 품절')
        assert result.success is True

    def test_activate(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 15000})
        pub.deactivate(r.listing_id, '소싱처 품절')
        result = pub.activate(r.listing_id)
        assert result.success is True

    def test_delete(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 15000})
        result = pub.delete(r.listing_id)
        assert result.success is True

    def test_health_check(self):
        pub = self._make()
        assert pub.health_check() is True

    def test_tags_generated_from_title(self):
        pub = self._make()
        result = pub.publish({'product_id': 'p1', 'title': '블루투스 이어폰 무선', 'price': 15000})
        listing = pub.get_status(result.listing_id)
        assert 'tags' in listing.metadata


# ─── Publishers: InternalPublisher ───────────────────────────────────────────

class TestInternalPublisher:
    def _make(self):
        from src.channel_sync.publishers.internal import InternalPublisher
        return InternalPublisher()

    def test_channel_name(self):
        pub = self._make()
        assert pub.channel_name == 'internal'

    def test_publish(self):
        pub = self._make()
        result = pub.publish({'product_id': 'p1', 'title': '자체몰 상품', 'price': 20000})
        assert result.success is True

    def test_update(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 20000})
        result = pub.update(r.listing_id, {'price': 22000, 'description': '새 설명'})
        assert result.success is True
        listing = pub.get_status(r.listing_id)
        assert listing.metadata['description'] == '새 설명'

    def test_deactivate_activate(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 20000})
        pub.deactivate(r.listing_id, '재고 없음')
        result = pub.activate(r.listing_id)
        assert result.success is True

    def test_delete(self):
        pub = self._make()
        r = pub.publish({'product_id': 'p1', 'price': 20000})
        result = pub.delete(r.listing_id)
        assert result.success is True

    def test_health_check(self):
        pub = self._make()
        assert pub.health_check() is True


# ─── ProductMapper ────────────────────────────────────────────────────────────

class TestProductMapper:
    def _make(self):
        from src.channel_sync.product_mapper import ProductMapper
        return ProductMapper()

    def _source_product(self, **kwargs):
        base = {
            'product_id': 'p-001',
            'source_product_id': 'sp-001',
            'title': '블루투스 이어폰',
            'price': 10000.0,
            'currency': 'KRW',
            'category': '전자제품',
            'stock': 5,
            'description': '고품질 이어폰',
            'images': ['https://example.com/img.jpg'],
            'options': [{'name': '색상', 'values': ['검정', '흰색']}],
        }
        base.update(kwargs)
        return base

    def test_map_product_coupang(self):
        mapper = self._make()
        result = mapper.map_product(self._source_product(), 'coupang')
        assert result['channel'] == 'coupang'
        assert result['product_id'] == 'p-001'
        assert result['currency'] == 'KRW'
        assert result['category'] == 'electronics'

    def test_map_product_naver(self):
        mapper = self._make()
        result = mapper.map_product(self._source_product(), 'naver')
        assert result['channel'] == 'naver'

    def test_map_product_internal(self):
        mapper = self._make()
        result = mapper.map_product(self._source_product(), 'internal')
        assert result['channel'] == 'internal'

    def test_price_conversion_margin(self):
        mapper = self._make()
        result = mapper.map_product(self._source_product(price=10000), 'coupang')
        # 마진 30% 적용: 10000 * 1.30 = 13000
        assert result['price'] > 10000

    def test_price_conversion_fx(self):
        mapper = self._make()
        # CNY 가격
        result = mapper.map_product(self._source_product(price=100, currency='CNY'), 'coupang')
        # CNY → KRW (약 190배) + 마진
        assert result['original_price'] > 100

    def test_category_mapping(self):
        mapper = self._make()
        result = mapper.map_product(self._source_product(category='beauty'), 'coupang')
        assert result['category'] == 'beauty'

    def test_category_unknown(self):
        mapper = self._make()
        result = mapper.map_product(self._source_product(category='unknown'), 'coupang')
        assert result['category'] == 'default'

    def test_title_length_limit(self):
        mapper = self._make()
        long_title = 'A' * 200
        result = mapper.map_product(self._source_product(title=long_title), 'coupang')
        assert len(result['title']) <= 100

    def test_images_passthrough(self):
        mapper = self._make()
        result = mapper.map_product(self._source_product(), 'coupang')
        assert 'https://example.com/img.jpg' in result['images']

    def test_options_mapping(self):
        mapper = self._make()
        result = mapper.map_product(self._source_product(), 'coupang')
        assert len(result['options']) == 1
        assert result['options'][0]['name'] == '색상'

    def test_update_margin_rate(self):
        mapper = self._make()
        mapper.update_margin_rate('coupang', 0.50)
        result = mapper.map_product(self._source_product(price=10000), 'coupang')
        assert result['price'] == 15000

    def test_update_fx_rate(self):
        mapper = self._make()
        mapper.update_fx_rate('USD', 1000.0)
        result = mapper.map_product(self._source_product(price=10, currency='USD'), 'internal')
        assert result['original_price'] == 10000


# ─── ListingStatusManager ────────────────────────────────────────────────────

class TestListingStatusManager:
    def _make(self):
        from src.channel_sync.listing_manager import ListingStatusManager
        return ListingStatusManager()

    def _make_listing(self, **kwargs):
        from src.channel_sync.publishers.base import ListingStatus
        import uuid
        defaults = dict(
            listing_id=str(uuid.uuid4()),
            channel='coupang',
            product_id='p-001',
            title='테스트 상품',
            price=10000.0,
            stock=5,
        )
        defaults.update(kwargs)
        return ListingStatus(**defaults)

    def test_register_listing(self):
        manager = self._make()
        listing = self._make_listing()
        result = manager.register_listing(listing)
        assert manager.get_listing(listing.listing_id) is not None

    def test_get_listings_by_product(self):
        manager = self._make()
        l1 = self._make_listing(product_id='p-001', channel='coupang')
        l2 = self._make_listing(product_id='p-001', channel='naver')
        l3 = self._make_listing(product_id='p-002', channel='coupang')
        manager.register_listing(l1)
        manager.register_listing(l2)
        manager.register_listing(l3)
        listings = manager.get_listings(product_id='p-001')
        assert len(listings) == 2

    def test_pause_listing(self):
        manager = self._make()
        listing = self._make_listing()
        manager.register_listing(listing)
        result = manager.pause_listing(listing.listing_id, '품절')
        from src.channel_sync.publishers.base import ListingState
        assert result.state == ListingState.paused
        assert result.error_message == '품절'

    def test_resume_listing(self):
        manager = self._make()
        listing = self._make_listing()
        manager.register_listing(listing)
        manager.pause_listing(listing.listing_id, '품절')
        result = manager.resume_listing(listing.listing_id)
        from src.channel_sync.publishers.base import ListingState
        assert result.state == ListingState.active

    def test_deactivate_listing(self):
        manager = self._make()
        listing = self._make_listing()
        manager.register_listing(listing)
        result = manager.deactivate_listing(listing.listing_id, '소싱처 삭제')
        from src.channel_sync.publishers.base import ListingState
        assert result.state == ListingState.inactive

    def test_delete_listing(self):
        manager = self._make()
        listing = self._make_listing()
        manager.register_listing(listing)
        result = manager.delete_listing(listing.listing_id)
        from src.channel_sync.publishers.base import ListingState
        assert result.state == ListingState.deleted

    def test_bulk_pause(self):
        manager = self._make()
        l1 = self._make_listing(product_id='p-001', channel='coupang')
        l2 = self._make_listing(product_id='p-001', channel='naver')
        manager.register_listing(l1)
        manager.register_listing(l2)
        paused = manager.bulk_pause(['p-001'], '일괄 중지')
        assert len(paused) == 2

    def test_bulk_resume(self):
        manager = self._make()
        l1 = self._make_listing(product_id='p-001', channel='coupang')
        l2 = self._make_listing(product_id='p-001', channel='naver')
        manager.register_listing(l1)
        manager.register_listing(l2)
        manager.bulk_pause(['p-001'], '일괄 중지')
        resumed = manager.bulk_resume(['p-001'])
        assert len(resumed) == 2

    def test_history_tracking(self):
        manager = self._make()
        listing = self._make_listing()
        manager.register_listing(listing)
        manager.pause_listing(listing.listing_id, '품절')
        manager.resume_listing(listing.listing_id)
        history = manager.get_history(listing_id=listing.listing_id)
        assert len(history) >= 2

    def test_stats(self):
        manager = self._make()
        l1 = self._make_listing(channel='coupang')
        l2 = self._make_listing(channel='naver')
        manager.register_listing(l1)
        manager.register_listing(l2)
        stats = manager.get_stats()
        assert stats['total'] == 2
        assert 'coupang' in stats['by_channel']

    def test_pause_not_found(self):
        manager = self._make()
        result = manager.pause_listing('nonexistent', '이유')
        assert result is None


# ─── SyncConflictResolver ────────────────────────────────────────────────────

class TestSyncConflictResolver:
    def _make(self):
        from src.channel_sync.conflict_resolver import SyncConflictResolver
        return SyncConflictResolver()

    def test_detect_conflicts(self):
        resolver = self._make()
        source = {'price': 10000, 'title': '소싱처 제목'}
        channel = {'price': 12000, 'title': '채널 제목'}
        conflicts = resolver.detect_conflicts('p-001', source, channel, 'coupang')
        assert len(conflicts) >= 1

    def test_resolve_source_priority(self):
        from src.channel_sync.conflict_resolver import SyncConflictResolver, ConflictStrategy
        resolver = SyncConflictResolver()
        source = {'price': 10000, 'title': '소싱처'}
        channel = {'price': 12000, 'title': '채널'}
        result = resolver.resolve(source, channel, ConflictStrategy.source_priority)
        assert result['price'] == 10000
        assert result['title'] == '소싱처'

    def test_resolve_channel_priority(self):
        from src.channel_sync.conflict_resolver import SyncConflictResolver, ConflictStrategy
        resolver = SyncConflictResolver()
        source = {'price': 10000, 'title': '소싱처'}
        channel = {'price': 12000, 'title': '채널'}
        result = resolver.resolve(source, channel, ConflictStrategy.channel_priority)
        assert result['price'] == 12000
        assert result['title'] == '채널'

    def test_resolve_latest_wins(self):
        from src.channel_sync.conflict_resolver import SyncConflictResolver, ConflictStrategy
        resolver = SyncConflictResolver()
        source = {'price': 10000, 'updated_at': '2024-01-02T00:00:00Z'}
        channel = {'price': 12000, 'updated_at': '2024-01-01T00:00:00Z'}
        result = resolver.resolve(source, channel, ConflictStrategy.latest_wins)
        assert result['price'] == 10000

    def test_resolve_manual_strategy(self):
        from src.channel_sync.conflict_resolver import SyncConflictResolver, ConflictStrategy
        resolver = SyncConflictResolver()
        source = {'price': 10000}
        channel = {'price': 12000}
        result = resolver.resolve(source, channel, ConflictStrategy.manual)
        assert result.get('_manual_review_required') is True

    def test_resolve_conflict_manual(self):
        resolver = self._make()
        source = {'price': 10000}
        channel = {'price': 12000}
        conflicts = resolver.detect_conflicts('p-001', source, channel, 'coupang')
        if conflicts:
            conflict = resolver.resolve_conflict(conflicts[0].conflict_id, 10000, '소싱처 가격 채택')
            assert conflict is not None
            from src.channel_sync.conflict_resolver import ConflictStatus
            assert conflict.status == ConflictStatus.resolved

    def test_get_unresolved_conflicts(self):
        resolver = self._make()
        source = {'price': 10000}
        channel = {'price': 12000}
        resolver.detect_conflicts('p-001', source, channel, 'coupang')
        unresolved = resolver.get_unresolved_conflicts()
        assert len(unresolved) >= 1

    def test_stats(self):
        resolver = self._make()
        source = {'price': 10000}
        channel = {'price': 12000}
        resolver.detect_conflicts('p-001', source, channel, 'coupang')
        stats = resolver.get_stats()
        assert stats['total'] >= 1
        assert 'unresolved' in stats


# ─── ChannelSyncEngine ───────────────────────────────────────────────────────

class TestChannelSyncEngine:
    def _make(self):
        from src.channel_sync.sync_engine import ChannelSyncEngine
        return ChannelSyncEngine()

    def test_sync_product_single_channel(self):
        engine = self._make()
        result = engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 10000, 'title': '테스트'})
        assert 'coupang' in result['results']
        assert result['results']['coupang']['success'] is True

    def test_sync_product_multiple_channels(self):
        engine = self._make()
        result = engine.sync_product('p-001', channels=['coupang', 'naver'], product_data={'product_id': 'p-001', 'price': 10000})
        assert result['results']['coupang']['success'] is True
        assert result['results']['naver']['success'] is True

    def test_sync_product_creates_listing(self):
        engine = self._make()
        engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 10000})
        assert 'coupang' in engine._product_listings.get('p-001', {})

    def test_sync_product_update_existing(self):
        engine = self._make()
        # 첫 번째 동기화 (등록)
        engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 10000})
        # 두 번째 동기화 (업데이트)
        result = engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 12000})
        assert result['results']['coupang']['success'] is True

    def test_sync_all(self):
        engine = self._make()
        engine.sync_product('p-001', product_data={'product_id': 'p-001', 'price': 10000})
        result = engine.sync_all()
        assert 'synced' in result
        assert 'failed' in result

    def test_sync_all_specific_channel(self):
        engine = self._make()
        engine.sync_product('p-001', product_data={'product_id': 'p-001', 'price': 10000})
        result = engine.sync_all(channel='coupang')
        assert result['channels'] == ['coupang']

    def test_handle_price_change_event(self):
        engine = self._make()
        engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 10000})
        result = engine.handle_source_change({
            'change_type': 'price_increase',
            'my_product_id': 'p-001',
            'new_value': 15000,
            'channels': ['coupang'],
        })
        assert result['event_type'] == 'price_increase'
        assert 'coupang' in result['results']

    def test_handle_out_of_stock_event(self):
        engine = self._make()
        engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 10000})
        result = engine.handle_source_change({
            'change_type': 'out_of_stock',
            'my_product_id': 'p-001',
            'channels': ['coupang'],
        })
        assert result['event_type'] == 'out_of_stock'

    def test_handle_listing_removed_event(self):
        engine = self._make()
        engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 10000})
        result = engine.handle_source_change({
            'change_type': 'listing_removed',
            'my_product_id': 'p-001',
            'channels': ['coupang'],
        })
        assert result['event_type'] == 'listing_removed'

    def test_handle_back_in_stock_event(self):
        engine = self._make()
        engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 10000})
        engine.handle_source_change({'change_type': 'out_of_stock', 'my_product_id': 'p-001', 'channels': ['coupang']})
        result = engine.handle_source_change({
            'change_type': 'back_in_stock',
            'my_product_id': 'p-001',
            'channels': ['coupang'],
        })
        assert result['event_type'] == 'back_in_stock'

    def test_get_sync_status(self):
        engine = self._make()
        status = engine.get_sync_status()
        assert 'total_products' in status

    def test_get_sync_status_product(self):
        engine = self._make()
        engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 10000})
        status = engine.get_sync_status(product_id='p-001')
        assert status['product_id'] == 'p-001'

    def test_get_sync_history(self):
        engine = self._make()
        engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 10000})
        history = engine.get_sync_history(product_id='p-001')
        assert len(history) >= 1

    def test_get_sync_stats(self):
        engine = self._make()
        engine.sync_product('p-001', channels=['coupang'], product_data={'product_id': 'p-001', 'price': 10000})
        stats = engine.get_sync_stats()
        assert stats['total'] >= 1
        assert 'success' in stats
        assert 'failed' in stats

    def test_enqueue(self):
        engine = self._make()
        item = engine.enqueue('p-001', ['coupang'], 'update', {'price': 10000})
        assert item.item_id is not None
        assert item.product_id == 'p-001'

    def test_get_queue_status(self):
        engine = self._make()
        engine.enqueue('p-001', ['coupang'], 'update', {'price': 10000})
        queue = engine.get_queue_status()
        assert queue['total'] >= 1

    def test_channel_health(self):
        engine = self._make()
        health = engine.get_channel_health()
        assert 'coupang' in health
        assert 'naver' in health
        assert 'internal' in health

    def test_channel_health_specific(self):
        engine = self._make()
        health = engine.get_channel_health(channel='coupang')
        assert 'coupang' in health
        assert health['coupang']['healthy'] is True


# ─── ChannelSyncScheduler ────────────────────────────────────────────────────

class TestChannelSyncScheduler:
    def _make(self):
        from src.channel_sync.sync_scheduler import ChannelSyncScheduler
        return ChannelSyncScheduler()

    def test_schedule_event_sync(self):
        scheduler = self._make()
        job = scheduler.schedule_event_sync('p-001', ['coupang'], '가격 변동')
        assert job.job_id is not None
        assert job.product_id == 'p-001'
        from src.channel_sync.sync_scheduler import SyncPriority
        assert job.priority == SyncPriority.EVENT

    def test_schedule_full_sync(self):
        scheduler = self._make()
        job = scheduler.schedule_full_sync()
        from src.channel_sync.sync_scheduler import SyncPriority
        assert job.priority == SyncPriority.FULL

    def test_schedule_quick_sync(self):
        scheduler = self._make()
        jobs = scheduler.schedule_quick_sync(['p-001', 'p-002'])
        assert len(jobs) == 2
        from src.channel_sync.sync_scheduler import SyncPriority
        assert all(j.priority == SyncPriority.QUICK for j in jobs)

    def test_get_pending_jobs_ordered(self):
        scheduler = self._make()
        scheduler.schedule_full_sync()
        scheduler.schedule_event_sync('p-001', ['coupang'], 'event')
        pending = scheduler.get_pending_jobs()
        assert pending[0].priority <= pending[-1].priority

    def test_mark_completed(self):
        scheduler = self._make()
        job = scheduler.schedule_full_sync()
        scheduler.mark_completed(job.job_id)
        assert scheduler.get_job(job.job_id).completed is True

    def test_is_full_sync_due_initial(self):
        scheduler = self._make()
        assert scheduler.is_full_sync_due() is True

    def test_stats(self):
        scheduler = self._make()
        scheduler.schedule_full_sync()
        stats = scheduler.get_stats()
        assert stats['total_jobs'] >= 1


# ─── ChannelSyncDashboard ────────────────────────────────────────────────────

class TestChannelSyncDashboard:
    def _make(self):
        from src.channel_sync.sync_engine import ChannelSyncEngine
        from src.channel_sync.listing_manager import ListingStatusManager
        from src.channel_sync.conflict_resolver import SyncConflictResolver
        from src.channel_sync.sync_scheduler import ChannelSyncScheduler
        from src.channel_sync.dashboard import ChannelSyncDashboard
        engine = ChannelSyncEngine()
        return ChannelSyncDashboard(
            engine=engine,
            listing_manager=ListingStatusManager(),
            conflict_resolver=SyncConflictResolver(),
            scheduler=ChannelSyncScheduler(),
        )

    def test_get_dashboard(self):
        dashboard = self._make()
        data = dashboard.get_dashboard()
        assert 'sync_stats' in data
        assert 'listing_stats' in data
        assert 'channel_health' in data
        assert 'conflict_stats' in data
        assert 'scheduler_stats' in data

    def test_get_channel_summary(self):
        dashboard = self._make()
        summary = dashboard.get_channel_summary()
        assert isinstance(summary, dict)

    def test_get_pending_conflicts(self):
        dashboard = self._make()
        conflicts = dashboard.get_pending_conflicts()
        assert isinstance(conflicts, list)

    def test_get_recent_sync_feed(self):
        dashboard = self._make()
        feed = dashboard.get_recent_sync_feed()
        assert isinstance(feed, list)


# ─── API 테스트 ───────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from flask import Flask
    from src.api.channel_sync_api import channel_sync_bp
    app = Flask(__name__)
    app.register_blueprint(channel_sync_bp)
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestChannelSyncAPI:
    def test_get_status(self, client):
        resp = client.get('/api/v1/channel-sync/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True

    def test_get_stats(self, client):
        resp = client.get('/api/v1/channel-sync/stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True

    def test_get_history(self, client):
        resp = client.get('/api/v1/channel-sync/history')
        assert resp.status_code == 200

    def test_post_sync_all(self, client):
        resp = client.post('/api/v1/channel-sync/sync', json={})
        assert resp.status_code == 200

    def test_post_sync_product(self, client):
        resp = client.post(
            '/api/v1/channel-sync/sync/p-001',
            json={'product_data': {'product_id': 'p-001', 'price': 10000}},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True

    def test_post_handle_change(self, client):
        resp = client.post('/api/v1/channel-sync/handle-change', json={
            'change_type': 'price_increase',
            'my_product_id': 'p-001',
            'new_value': 15000,
        })
        assert resp.status_code == 200

    def test_post_handle_change_missing_type(self, client):
        resp = client.post('/api/v1/channel-sync/handle-change', json={})
        assert resp.status_code == 400

    def test_get_listings(self, client):
        resp = client.get('/api/v1/channel-sync/listings')
        assert resp.status_code == 200

    def test_get_channels(self, client):
        resp = client.get('/api/v1/channel-sync/channels')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True
        assert 'coupang' in data.get('channels', {})

    def test_get_channel_health(self, client):
        resp = client.get('/api/v1/channel-sync/channels/coupang/health')
        assert resp.status_code == 200

    def test_get_channel_health_unknown(self, client):
        resp = client.get('/api/v1/channel-sync/channels/unknown_channel/health')
        assert resp.status_code == 404

    def test_get_dashboard(self, client):
        resp = client.get('/api/v1/channel-sync/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True

    def test_get_conflicts(self, client):
        resp = client.get('/api/v1/channel-sync/conflicts')
        assert resp.status_code == 200

    def test_pause_listing_not_found(self, client):
        resp = client.post('/api/v1/channel-sync/listings/nonexistent/pause', json={'reason': '테스트'})
        assert resp.status_code == 404

    def test_resume_listing_not_found(self, client):
        resp = client.post('/api/v1/channel-sync/listings/nonexistent/resume')
        assert resp.status_code == 404

    def test_delete_listing_not_found(self, client):
        resp = client.delete('/api/v1/channel-sync/listings/nonexistent')
        assert resp.status_code == 404


# ─── 봇 커맨드 테스트 ─────────────────────────────────────────────────────────

class TestChannelSyncBotCommands:
    def test_cmd_sync_status(self):
        from src.bot.channel_sync_commands import cmd_sync_status
        result = cmd_sync_status()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_sync_channel_valid(self):
        from src.bot.channel_sync_commands import cmd_sync_channel
        result = cmd_sync_channel('coupang')
        assert isinstance(result, str)
        assert 'coupang' in result.lower() or '동기화' in result or '실패' in result

    def test_cmd_sync_channel_invalid(self):
        from src.bot.channel_sync_commands import cmd_sync_channel
        result = cmd_sync_channel('invalid_channel')
        assert '유효하지 않은' in result or 'invalid' in result.lower()

    def test_cmd_sync_product(self):
        from src.bot.channel_sync_commands import cmd_sync_product
        result = cmd_sync_product('p-001')
        assert isinstance(result, str)

    def test_cmd_sync_product_empty(self):
        from src.bot.channel_sync_commands import cmd_sync_product
        result = cmd_sync_product('')
        assert '입력' in result or 'ID' in result

    def test_cmd_sync_force(self):
        from src.bot.channel_sync_commands import cmd_sync_force
        result = cmd_sync_force()
        assert isinstance(result, str)

    def test_cmd_listing_status(self):
        from src.bot.channel_sync_commands import cmd_listing_status
        result = cmd_listing_status()
        assert isinstance(result, str)

    def test_cmd_listing_pause_empty(self):
        from src.bot.channel_sync_commands import cmd_listing_pause
        result = cmd_listing_pause('')
        assert '입력' in result or 'ID' in result

    def test_cmd_listing_pause_not_found(self):
        from src.bot.channel_sync_commands import cmd_listing_pause
        result = cmd_listing_pause('nonexistent', '테스트')
        assert '찾을 수 없습니다' in result or '실패' in result

    def test_cmd_listing_resume_empty(self):
        from src.bot.channel_sync_commands import cmd_listing_resume
        result = cmd_listing_resume('')
        assert '입력' in result or 'ID' in result

    def test_cmd_listing_resume_not_found(self):
        from src.bot.channel_sync_commands import cmd_listing_resume
        result = cmd_listing_resume('nonexistent')
        assert '찾을 수 없습니다' in result or '실패' in result

    def test_cmd_channel_health(self):
        from src.bot.channel_sync_commands import cmd_channel_health
        result = cmd_channel_health()
        assert isinstance(result, str)
        assert '채널' in result or 'channel' in result.lower()

    def test_cmd_sync_dashboard(self):
        from src.bot.channel_sync_commands import cmd_sync_dashboard
        result = cmd_sync_dashboard()
        assert isinstance(result, str)

    def test_cmd_sync_conflicts(self):
        from src.bot.channel_sync_commands import cmd_sync_conflicts
        result = cmd_sync_conflicts()
        assert isinstance(result, str)
