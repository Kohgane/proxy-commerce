"""판매 채널 레지스트리."""
from .percenty import PercentyExporter
from .shopify_global import ShopifyGlobalChannel
from .woo_domestic import WooDomesticChannel

CHANNEL_REGISTRY = {
    'percenty': PercentyExporter,
    'shopify': ShopifyGlobalChannel,
    'woocommerce': WooDomesticChannel,
}


def get_channel(channel_name: str):
    """채널 이름으로 채널 인스턴스를 반환한다."""
    cls = CHANNEL_REGISTRY.get(channel_name.lower())
    if cls is None:
        raise ValueError(f"Unknown channel: {channel_name}")
    return cls()
