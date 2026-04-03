"""tests/test_users.py — Phase 47: 사용자 프로필 + 주소록 관리 테스트."""
import pytest


class TestUserManager:
    def setup_method(self):
        from src.users.user_manager import UserManager
        self.mgr = UserManager()

    def test_create_user(self):
        user = self.mgr.create({'name': '홍길동', 'email': 'hong@example.com', 'phone': '010-1234-5678'})
        assert user['name'] == '홍길동'
        assert user['email'] == 'hong@example.com'
        assert user['grade'] == 'bronze'

    def test_create_without_email_raises(self):
        with pytest.raises(ValueError):
            self.mgr.create({'name': '홍길동'})

    def test_get_user(self):
        user = self.mgr.create({'email': 'test@example.com'})
        found = self.mgr.get(user['id'])
        assert found['id'] == user['id']

    def test_get_by_email(self):
        self.mgr.create({'email': 'find@example.com'})
        found = self.mgr.get_by_email('find@example.com')
        assert found is not None

    def test_grade_bronze(self):
        user = self.mgr.create({'email': 'a@example.com'})
        assert user['grade'] == 'bronze'

    def test_grade_silver(self):
        user = self.mgr.create({'email': 'b@example.com'})
        self.mgr.add_purchase_amount(user['id'], 150000)
        updated = self.mgr.get(user['id'])
        assert updated['grade'] == 'silver'

    def test_grade_gold(self):
        user = self.mgr.create({'email': 'c@example.com'})
        self.mgr.add_purchase_amount(user['id'], 600000)
        assert self.mgr.get(user['id'])['grade'] == 'gold'

    def test_grade_vip(self):
        user = self.mgr.create({'email': 'd@example.com'})
        self.mgr.add_purchase_amount(user['id'], 3000000)
        assert self.mgr.get(user['id'])['grade'] == 'vip'

    def test_get_benefits_bronze(self):
        user = self.mgr.create({'email': 'e@example.com'})
        benefits = self.mgr.get_benefits(user['id'])
        assert benefits['discount_pct'] == 0

    def test_get_benefits_vip(self):
        user = self.mgr.create({'email': 'f@example.com'})
        self.mgr.add_purchase_amount(user['id'], 5000000)
        benefits = self.mgr.get_benefits(user['id'])
        assert benefits['discount_pct'] == 10

    def test_update_user(self):
        user = self.mgr.create({'email': 'g@example.com'})
        updated = self.mgr.update(user['id'], {'name': '업데이트'})
        assert updated['name'] == '업데이트'

    def test_deactivate(self):
        user = self.mgr.create({'email': 'h@example.com'})
        self.mgr.deactivate(user['id'])
        assert self.mgr.get(user['id'])['active'] is False

    def test_list_active_only(self):
        u1 = self.mgr.create({'email': 'i@example.com'})
        u2 = self.mgr.create({'email': 'j@example.com'})
        self.mgr.deactivate(u2['id'])
        active = self.mgr.list_all(active_only=True)
        ids = [u['id'] for u in active]
        assert u1['id'] in ids
        assert u2['id'] not in ids


class TestAddressBook:
    def setup_method(self):
        from src.users.address_book import AddressBook
        self.book = AddressBook()
        self.valid_address = {
            'recipient_name': '홍길동',
            'phone': '010-1234-5678',
            'address1': '서울시 강남구',
            'city': '서울',
            'postal_code': '06000',
            'country': 'KR',
        }

    def test_add_address(self):
        addr = self.book.add('u1', self.valid_address)
        assert addr['recipient_name'] == '홍길동'
        assert 'id' in addr

    def test_first_address_is_default(self):
        addr = self.book.add('u1', self.valid_address)
        default = self.book.get_default('u1')
        assert default['id'] == addr['id']

    def test_add_missing_required_field(self):
        invalid = dict(self.valid_address)
        del invalid['phone']
        with pytest.raises(ValueError):
            self.book.add('u1', invalid)

    def test_max_addresses(self):
        from src.users.address_book import MAX_ADDRESSES_PER_USER
        for i in range(MAX_ADDRESSES_PER_USER):
            addr = dict(self.valid_address)
            addr['recipient_name'] = f'User{i}'
            self.book.add('u1', addr)
        with pytest.raises(ValueError):
            self.book.add('u1', self.valid_address)

    def test_set_default(self):
        addr1 = self.book.add('u1', self.valid_address)
        addr2_data = dict(self.valid_address)
        addr2_data['recipient_name'] = '이순신'
        addr2 = self.book.add('u1', addr2_data)
        self.book.set_default('u1', addr2['id'])
        assert self.book.get_default('u1')['id'] == addr2['id']

    def test_delete_address(self):
        addr = self.book.add('u1', self.valid_address)
        assert self.book.delete(addr['id'])
        assert self.book.get(addr['id']) is None

    def test_delete_default_updates_default(self):
        addr1 = self.book.add('u1', self.valid_address)
        addr2_data = dict(self.valid_address)
        addr2_data['recipient_name'] = '이순신'
        addr2 = self.book.add('u1', addr2_data)
        self.book.delete(addr1['id'])
        assert self.book.get_default('u1')['id'] == addr2['id']

    def test_list_by_user(self):
        self.book.add('u1', self.valid_address)
        self.book.add('u2', self.valid_address)
        u1_addrs = self.book.list_by_user('u1')
        assert len(u1_addrs) == 1


class TestUserPreferences:
    def setup_method(self):
        from src.users.preferences import UserPreferences
        self.prefs = UserPreferences()

    def test_default_preferences(self):
        prefs = self.prefs.get('u1')
        assert prefs['language'] == 'ko'
        assert prefs['currency'] == 'KRW'

    def test_set_language(self):
        self.prefs.set_language('u1', 'en')
        assert self.prefs.get('u1')['language'] == 'en'

    def test_set_invalid_language(self):
        with pytest.raises(ValueError):
            self.prefs.set_language('u1', 'xx')

    def test_set_currency(self):
        self.prefs.set_currency('u1', 'usd')
        assert self.prefs.get('u1')['currency'] == 'USD'

    def test_set_notification_channels(self):
        self.prefs.set_notification_channels('u1', ['telegram', 'email'])
        prefs = self.prefs.get('u1')
        assert 'telegram' in prefs['notification_channels']

    def test_set_invalid_channel(self):
        with pytest.raises(ValueError):
            self.prefs.set_notification_channels('u1', ['invalid'])

    def test_update(self):
        self.prefs.update('u1', {'language': 'ja', 'currency': 'JPY'})
        prefs = self.prefs.get('u1')
        assert prefs['language'] == 'ja'
        assert prefs['currency'] == 'JPY'


class TestActivityLog:
    def setup_method(self):
        from src.users.activity_log import ActivityLog
        self.log = ActivityLog()

    def test_log_activity(self):
        record = self.log.log('u1', 'login')
        assert record['activity_type'] == 'login'
        assert record['user_id'] == 'u1'

    def test_log_unknown_type_becomes_other(self):
        record = self.log.log('u1', 'unknown_type')
        assert record['activity_type'] == 'other'

    def test_get_recent(self):
        for i in range(5):
            self.log.log('u1', 'product_view', {'product_id': f'P{i}'})
        recent = self.log.get_recent('u1', n=3)
        assert len(recent) == 3

    def test_get_by_type(self):
        self.log.log('u1', 'login')
        self.log.log('u1', 'order')
        self.log.log('u1', 'login')
        logins = self.log.get_by_type('u1', 'login')
        assert len(logins) == 2

    def test_get_all(self):
        self.log.log('u1', 'login')
        self.log.log('u1', 'search')
        assert len(self.log.get_all('u1')) == 2

    def test_max_records_respected(self):
        from src.users.activity_log import ActivityLog
        log = ActivityLog(max_records=5)
        for i in range(10):
            log.log('u1', 'login')
        assert len(log.get_all('u1')) == 5
