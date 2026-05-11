"""tests/test_web_push.py — Web Push 모듈 테스트 (Phase 147)."""
import os
import pytest
import tempfile


def test_vapid_not_configured_by_default():
    """기본 환경에서는 VAPID 키가 설정되지 않아야 한다."""
    from src.notifications.web_push import vapid_configured
    # 환경변수 없으면 False
    old = os.environ.pop("WEB_PUSH_VAPID_PUBLIC", None)
    old2 = os.environ.pop("WEB_PUSH_VAPID_PRIVATE", None)
    assert vapid_configured() is False
    if old:
        os.environ["WEB_PUSH_VAPID_PUBLIC"] = old
    if old2:
        os.environ["WEB_PUSH_VAPID_PRIVATE"] = old2


def test_vapid_configured_with_env(monkeypatch):
    """VAPID 키 환경변수 설정 시 vapid_configured()가 True를 반환해야 한다."""
    monkeypatch.setenv("WEB_PUSH_VAPID_PUBLIC", "test_pub_key")
    monkeypatch.setenv("WEB_PUSH_VAPID_PRIVATE", "test_priv_key")
    from src.notifications.web_push import vapid_configured
    assert vapid_configured() is True


def test_generate_vapid_keys_returns_dict():
    """generate_vapid_keys()가 dict를 반환해야 한다."""
    from src.notifications.web_push import generate_vapid_keys
    result = generate_vapid_keys()
    assert isinstance(result, dict)
    assert "public" in result
    assert "private" in result


def test_push_subscription_store_subscribe_unsubscribe():
    """구독 추가 및 해제가 정상 동작해야 한다."""
    from src.notifications.web_push import PushSubscription, PushSubscriptionStore
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        store = PushSubscriptionStore(path=path)
        sub = PushSubscription(
            user_id="user1",
            endpoint="https://push.example.com/sub1",
            p256dh="p256dh_key",
            auth="auth_key",
        )
        store.subscribe(sub)
        assert store.count() == 1

        # 중복 endpoint는 upsert
        store.subscribe(sub)
        assert store.count() == 1

        # 해제
        ok = store.unsubscribe("https://push.example.com/sub1")
        assert ok is True
        assert store.count() == 0

        # 없는 endpoint 해제는 False
        ok2 = store.unsubscribe("https://nonexistent.example.com/")
        assert ok2 is False
    finally:
        os.unlink(path)


def test_push_subscription_store_list_for_user():
    """list_for_user()가 해당 사용자 구독만 반환해야 한다."""
    from src.notifications.web_push import PushSubscription, PushSubscriptionStore
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        store = PushSubscriptionStore(path=path)
        sub1 = PushSubscription(user_id="userA", endpoint="https://ep1", p256dh="k1", auth="a1")
        sub2 = PushSubscription(user_id="userB", endpoint="https://ep2", p256dh="k2", auth="a2")
        store.subscribe(sub1)
        store.subscribe(sub2)
        userA_subs = store.list_for_user("userA")
        assert len(userA_subs) == 1
        assert userA_subs[0].user_id == "userA"
    finally:
        os.unlink(path)


def test_send_push_stub_without_vapid():
    """VAPID 미설정 시 stub 모드로 True 반환해야 한다."""
    from src.notifications.web_push import PushSubscription, send_push
    sub = PushSubscription(
        user_id="user1",
        endpoint="https://push.example.com/sub1",
        p256dh="p256dh_key",
        auth="auth_key",
    )
    old_pub = os.environ.pop("WEB_PUSH_VAPID_PUBLIC", None)
    old_priv = os.environ.pop("WEB_PUSH_VAPID_PRIVATE", None)
    try:
        result = send_push(sub, title="Test", body="Hello")
        assert result is True
    finally:
        if old_pub:
            os.environ["WEB_PUSH_VAPID_PUBLIC"] = old_pub
        if old_priv:
            os.environ["WEB_PUSH_VAPID_PRIVATE"] = old_priv


def test_broadcast_push_no_subscribers():
    """구독자 없을 때 broadcast_push가 0/0을 반환해야 한다."""
    from src.notifications.web_push import broadcast_push
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        os.environ["PUSH_SUBSCRIPTIONS_PATH"] = path
        result = broadcast_push(title="T", body="B", category="order")
        assert result["sent"] == 0
        assert result["failed"] == 0
    finally:
        os.environ.pop("PUSH_SUBSCRIPTIONS_PATH", None)
        os.unlink(path)


def test_push_status_returns_dict():
    """push_status()가 예상 키를 가진 dict를 반환해야 한다."""
    from src.notifications.web_push import push_status
    status = push_status()
    assert "vapid_configured" in status
    assert "subscriber_count" in status
    assert "vapid_public_hint" in status


def test_notify_helpers_dont_raise():
    """트리거 함수들이 예외를 발생시키지 않아야 한다 (stub 모드)."""
    from src.notifications.web_push import (
        notify_new_order, notify_cs_urgent, notify_shipping_delay, notify_roas_change
    )
    old_pub = os.environ.pop("WEB_PUSH_VAPID_PUBLIC", None)
    old_priv = os.environ.pop("WEB_PUSH_VAPID_PRIVATE", None)
    try:
        notify_new_order("ORD-001", 50000)
        notify_cs_urgent("MSG-001", "빨리 답변해 주세요")
        notify_shipping_delay("ORD-002")
        notify_roas_change("coupang", 3.5, 2.0)
    finally:
        if old_pub:
            os.environ["WEB_PUSH_VAPID_PUBLIC"] = old_pub
        if old_priv:
            os.environ["WEB_PUSH_VAPID_PRIVATE"] = old_priv
