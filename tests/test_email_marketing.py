"""tests/test_email_marketing.py — Phase 88: 자동 이메일 마케팅 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.email_marketing import (
    Campaign,
    CampaignManager,
    EmailTemplateRenderer,
    CampaignTrigger,
    ScheduleTrigger,
    EventTrigger,
    SegmentTrigger,
    CampaignAnalytics,
    UnsubscribeManager,
    ABTestCampaign,
)


class TestCampaignModel:
    def test_dataclass_fields(self):
        c = Campaign(
            campaign_id='c1',
            name='신년 이벤트',
            subject='새해 특가!',
            body_template='안녕하세요 {{name}}님',
        )
        assert c.campaign_id == 'c1'
        assert c.status == 'draft'
        assert c.sent_count == 0
        assert c.created_at


class TestCampaignManager:
    def test_create_draft(self):
        mgr = CampaignManager()
        c = mgr.create(name='테스트', subject='제목', body_template='내용')
        assert c.campaign_id
        assert c.status == 'draft'

    def test_create_scheduled(self):
        mgr = CampaignManager()
        c = mgr.create(name='테스트', subject='제목', body_template='내용', scheduled_at='2025-01-01T09:00:00')
        assert c.status == 'scheduled'

    def test_get(self):
        mgr = CampaignManager()
        c = mgr.create(name='테스트', subject='제목', body_template='내용')
        found = mgr.get(c.campaign_id)
        assert found is not None
        assert found.name == '테스트'

    def test_get_not_found(self):
        mgr = CampaignManager()
        assert mgr.get('nonexistent') is None

    def test_list(self):
        mgr = CampaignManager()
        mgr.create('캠페인1', '제목1', '내용1')
        mgr.create('캠페인2', '제목2', '내용2')
        camps = mgr.list()
        assert len(camps) == 2

    def test_list_by_status(self):
        mgr = CampaignManager()
        mgr.create('초안', '제목', '내용')
        mgr.create('예약', '제목', '내용', scheduled_at='2025-01-01')
        drafts = mgr.list(status='draft')
        assert len(drafts) == 1
        scheduled = mgr.list(status='scheduled')
        assert len(scheduled) == 1

    def test_update(self):
        mgr = CampaignManager()
        c = mgr.create('테스트', '제목', '내용')
        updated = mgr.update(c.campaign_id, name='업데이트됨')
        assert updated.name == '업데이트됨'

    def test_delete(self):
        mgr = CampaignManager()
        c = mgr.create('테스트', '제목', '내용')
        assert mgr.delete(c.campaign_id)
        assert mgr.get(c.campaign_id) is None

    def test_send(self):
        mgr = CampaignManager()
        c = mgr.create('테스트', '제목', '내용')
        result = mgr.send(c.campaign_id, recipient_count=100)
        assert result['success']
        assert result['sent_count'] == 100
        assert mgr.get(c.campaign_id).status == 'sent'

    def test_send_not_found(self):
        mgr = CampaignManager()
        result = mgr.send('nonexistent')
        assert not result['success']


class TestEmailTemplateRenderer:
    def test_render_variables(self):
        renderer = EmailTemplateRenderer()
        template = '안녕하세요 {{name}}님! {{discount}}% 할인 쿠폰을 드립니다.'
        result = renderer.render(template, {'name': '홍길동', 'discount': '20'})
        assert '홍길동' in result
        assert '20' in result
        assert '{{' not in result

    def test_render_no_variables(self):
        renderer = EmailTemplateRenderer()
        template = '안녕하세요'
        result = renderer.render(template, {})
        assert result == '안녕하세요'

    def test_render_missing_variable(self):
        renderer = EmailTemplateRenderer()
        template = '안녕하세요 {{name}}님'
        result = renderer.render(template, {})
        assert '{{name}}' not in result  # unreplaced placeholders removed


class TestScheduleTrigger:
    def test_should_trigger(self):
        trigger = ScheduleTrigger('2020-01-01T00:00:00')
        assert trigger.should_trigger({'now': '2025-01-01T00:00:00'})

    def test_should_not_trigger(self):
        trigger = ScheduleTrigger('2099-01-01T00:00:00')
        assert not trigger.should_trigger({'now': '2025-01-01T00:00:00'})

    def test_trigger_type(self):
        trigger = ScheduleTrigger('2020-01-01')
        assert trigger.trigger_type() == 'schedule'


class TestEventTrigger:
    def test_should_trigger(self):
        trigger = EventTrigger('order_placed')
        assert trigger.should_trigger({'event': 'order_placed'})

    def test_should_not_trigger(self):
        trigger = EventTrigger('order_placed')
        assert not trigger.should_trigger({'event': 'cart_abandoned'})

    def test_trigger_type(self):
        trigger = EventTrigger('welcome')
        assert trigger.trigger_type() == 'event'


class TestSegmentTrigger:
    def test_should_trigger(self):
        trigger = SegmentTrigger('vip_segment')
        assert trigger.should_trigger({'segments': ['vip_segment', 'other']})

    def test_should_not_trigger(self):
        trigger = SegmentTrigger('vip_segment')
        assert not trigger.should_trigger({'segments': ['other']})

    def test_trigger_type(self):
        trigger = SegmentTrigger('seg1')
        assert trigger.trigger_type() == 'segment'


class TestCampaignAnalytics:
    def test_stats_empty(self):
        c = Campaign(campaign_id='c1', name='t', subject='s', body_template='b')
        analytics = CampaignAnalytics()
        stats = analytics.stats(c)
        assert stats['open_rate'] == 0
        assert stats['click_rate'] == 0

    def test_stats_with_data(self):
        c = Campaign(campaign_id='c1', name='t', subject='s', body_template='b',
                     sent_count=100, open_count=30, click_count=10)
        analytics = CampaignAnalytics()
        stats = analytics.stats(c)
        assert stats['open_rate'] == 0.3
        assert stats['click_rate'] == 0.1

    def test_record_open(self):
        c = Campaign(campaign_id='c1', name='t', subject='s', body_template='b', sent_count=100)
        analytics = CampaignAnalytics()
        analytics.record_open(c)
        assert c.open_count == 1

    def test_record_click(self):
        c = Campaign(campaign_id='c1', name='t', subject='s', body_template='b', sent_count=100)
        analytics = CampaignAnalytics()
        analytics.record_click(c)
        assert c.click_count == 1


class TestUnsubscribeManager:
    def test_unsubscribe(self):
        mgr = UnsubscribeManager()
        result = mgr.unsubscribe('test@test.com', reason='spam')
        assert result['email'] == 'test@test.com'
        assert result['reason'] == 'spam'

    def test_is_unsubscribed(self):
        mgr = UnsubscribeManager()
        mgr.unsubscribe('test@test.com')
        assert mgr.is_unsubscribed('test@test.com')
        assert not mgr.is_unsubscribed('other@test.com')

    def test_list(self):
        mgr = UnsubscribeManager()
        mgr.unsubscribe('a@a.com')
        mgr.unsubscribe('b@b.com')
        result = mgr.list()
        assert len(result) == 2

    def test_resubscribe(self):
        mgr = UnsubscribeManager()
        mgr.unsubscribe('test@test.com')
        mgr.resubscribe('test@test.com')
        assert not mgr.is_unsubscribed('test@test.com')


class TestABTestCampaign:
    def test_create_test(self):
        ab = ABTestCampaign()
        test = ab.create_test(
            name='제목 A/B 테스트',
            variant_a={'subject': '제목 A'},
            variant_b={'subject': '제목 B'},
        )
        assert test['test_id']
        assert test['status'] == 'running'

    def test_record_result(self):
        ab = ABTestCampaign()
        test = ab.create_test('테스트', {'subject': 'A'}, {'subject': 'B'})
        ab.record_result(test['test_id'], 'a', 'sent')
        ab.record_result(test['test_id'], 'a', 'sent')
        ab.record_result(test['test_id'], 'a', 'open')
        ab.record_result(test['test_id'], 'b', 'sent')
        result = ab.winner(test['test_id'])
        assert result['winner'] in ('a', 'b')
        assert result['a_open_rate'] == 0.5

    def test_winner_no_data(self):
        ab = ABTestCampaign()
        test = ab.create_test('테스트', {'subject': 'A'}, {'subject': 'B'})
        result = ab.winner(test['test_id'])
        assert result['winner'] in ('a', 'b')  # defaults to 'a' when tie
