"""tests/test_inventory_omni_sync.py — 옴니채널 재고 동기화 테스트 (Phase 147)."""
import os
import pytest
import tempfile


def test_omni_syncer_summary_disabled_by_default():
    """기본적으로 옴니 동기화가 비활성이어야 한다."""
    old = os.environ.pop("INVENTORY_OMNI_SYNC_ENABLED", None)
    try:
        from src.inventory.omni_sync import OmniInventorySyncer
        syncer = OmniInventorySyncer()
        assert syncer.enabled is False
    finally:
        if old is not None:
            os.environ["INVENTORY_OMNI_SYNC_ENABLED"] = old


def test_omni_syncer_mode_default_common_pool():
    """기본 모드가 common_pool이어야 한다."""
    from src.inventory.omni_sync import OmniInventorySyncer
    syncer = OmniInventorySyncer()
    assert syncer.mode == "common_pool"


def test_omni_syncer_mode_env(monkeypatch):
    """INVENTORY_OMNI_SYNC_MODE 환경변수로 모드를 설정할 수 있어야 한다."""
    monkeypatch.setenv("INVENTORY_OMNI_SYNC_MODE", "per_channel")
    from src.inventory.omni_sync import OmniInventorySyncer
    syncer = OmniInventorySyncer()
    assert syncer.mode == "per_channel"


def test_omni_syncer_channel_stocks_returns_list():
    """channel_stocks()가 리스트를 반환해야 한다."""
    from src.inventory.omni_sync import OmniInventorySyncer
    syncer = OmniInventorySyncer()
    stocks = syncer.channel_stocks("TEST-SKU-001")
    assert isinstance(stocks, list)
    assert len(stocks) > 0
    for cs in stocks:
        assert hasattr(cs, "channel")
        assert hasattr(cs, "sku")
        assert hasattr(cs, "stock")


def test_omni_syncer_on_sale_disabled_returns_empty():
    """동기화 비활성 시 on_sale()이 빈 dict를 반환해야 한다."""
    old = os.environ.pop("INVENTORY_OMNI_SYNC_ENABLED", None)
    try:
        from src.inventory.omni_sync import OmniInventorySyncer
        syncer = OmniInventorySyncer()
        result = syncer.on_sale("SKU-001", sold_qty=1, source_channel="coupang")
        assert result == {}
    finally:
        if old is not None:
            os.environ["INVENTORY_OMNI_SYNC_ENABLED"] = old


def test_omni_syncer_manual_sync_returns_dict():
    """manual_sync()가 채널별 재고 dict를 반환해야 한다."""
    from src.inventory.omni_sync import OmniInventorySyncer
    syncer = OmniInventorySyncer()
    result = syncer.manual_sync("SKU-001")
    assert isinstance(result, dict)
    # 채널이 키로 존재해야 함
    for channel in result:
        assert isinstance(result[channel], int)


def test_omni_syncer_summary_keys():
    """summary()가 필요한 키를 모두 포함해야 한다."""
    from src.inventory.omni_sync import OmniInventorySyncer
    syncer = OmniInventorySyncer()
    s = syncer.summary()
    for key in ("enabled", "mode", "configured_channels", "channel_count", "failure_24h", "sync_interval_sec"):
        assert key in s, f"summary에서 '{key}' 키 누락"


def test_omni_sync_log_append_and_recent():
    """OmniSyncLog.append() + recent()가 정상 동작해야 한다."""
    from src.inventory.omni_sync import OmniSyncLog, OmniSyncEvent
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        log = OmniSyncLog(path=path)
        event = OmniSyncEvent(
            event_type="sold",
            channel="coupang",
            sku="SKU-001",
            delta=-1,
            new_stock=9,
            mode="common_pool",
        )
        log.append(event)
        recent = log.recent(10)
        assert len(recent) == 1
        assert recent[0]["event_type"] == "sold"
        assert recent[0]["sku"] == "SKU-001"
    finally:
        os.unlink(path)


def test_channel_stock_to_dict():
    """ChannelStock.to_dict()가 dict를 반환해야 한다."""
    from src.inventory.omni_sync import ChannelStock
    cs = ChannelStock(channel="coupang", sku="SKU-001", stock=10)
    d = cs.to_dict()
    assert d["channel"] == "coupang"
    assert d["sku"] == "SKU-001"
    assert d["stock"] == 10


def test_configured_channels_no_env():
    """환경변수 미설정 시 configured_channels()가 빈 리스트를 반환해야 한다."""
    for key in ["COUPANG_VENDOR_ID", "COUPANG_ACCESS_KEY", "NAVER_COMMERCE_CLIENT_ID", "ELEVENST_API_KEY"]:
        os.environ.pop(key, None)
    from src.inventory.omni_sync import OmniInventorySyncer
    syncer = OmniInventorySyncer()
    assert syncer.configured_channels() == []
