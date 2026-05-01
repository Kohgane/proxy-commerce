from __future__ import annotations

from app import publish as publish_app
from publisher.draft_publish import DraftPublisher, product_to_woo_payload
from publisher.woocommerce_client import WooCommerceClient
from schemas.product import Product


def _sample_product() -> Product:
    return Product(
        source="alo",
        source_product_id="123",
        source_url="https://example.com/p/123",
        brand="ALO",
        title="Sample Product",
        description="desc",
        currency="USD",
        cost_price=10,
        sell_price=20,
        images=["https://example.com/img.jpg"],
    )


class DummyPublisherClient:
    def __init__(self, existing=None):
        self.existing = existing
        self.created_payload = None
        self.updated_payload = None
        self.updated_id = None

    def find_product_by_idempotency(self, key):
        assert key == "alo:123"
        return self.existing

    def create_product(self, payload):
        self.created_payload = payload
        return {"id": 101, "action": "create"}

    def update_product(self, product_id, payload):
        self.updated_id = product_id
        self.updated_payload = payload
        return {"id": product_id, "action": "update"}


def test_product_to_woo_payload_contains_idempotency_metadata():
    payload = product_to_woo_payload(_sample_product())
    metadata = {item["key"]: item["value"] for item in payload["meta_data"]}
    assert metadata["_idempotency_key"] == "alo:123"
    assert metadata["_source"] == "alo"
    assert metadata["_source_product_id"] == "123"


def test_draft_publisher_creates_when_no_existing_product():
    client = DummyPublisherClient(existing=None)
    result = DraftPublisher(client=client).publish(_sample_product())
    assert result["action"] == "create"
    assert client.created_payload is not None
    assert client.updated_payload is None


def test_draft_publisher_updates_when_existing_product_found():
    client = DummyPublisherClient(existing={"id": 777})
    result = DraftPublisher(client=client).publish(_sample_product())
    assert result["action"] == "update"
    assert client.updated_id == 777
    assert client.updated_payload is not None
    assert client.created_payload is None


def test_draft_publisher_dry_run_returns_action_without_write():
    client = DummyPublisherClient(existing={"id": 777})
    result = DraftPublisher(client=client, dry_run=True).publish(_sample_product())
    assert result["dry_run"] is True
    assert result["action"] == "update"
    assert result["existing_id"] == 777
    assert client.created_payload is None
    assert client.updated_payload is None


class DummyLookupClient(WooCommerceClient):
    def __init__(self, pages):
        self.pages = pages
        self.max_lookup_pages = 100

    def list_products(self, **params):
        page = params["page"]
        return self.pages[page - 1] if page - 1 < len(self.pages) else []


def test_find_product_by_idempotency_finds_by_primary_and_fallback_metadata():
    by_primary = {"id": 1, "meta_data": [{"key": "_idempotency_key", "value": "alo:123"}]}
    by_fallback = {
        "id": 2,
        "meta_data": [
            {"key": "_source", "value": "alo"},
            {"key": "_source_product_id", "value": "123"},
        ],
    }

    client = DummyLookupClient([[{"id": 99, "meta_data": []}, by_primary]])
    assert client.find_product_by_idempotency("alo:123")["id"] == 1

    client = DummyLookupClient([[{"id": 99, "meta_data": []}], [by_fallback]])
    assert client.find_product_by_idempotency("alo:123")["id"] == 2


def test_publish_run_aggregates_create_update_counts(monkeypatch):
    product = _sample_product()

    class Pipeline:
        def run_batch(self, source_ids):
            assert source_ids
            return [product]

    class StubDraftPublisher:
        def __init__(self, dry_run=False):
            self.dry_run = dry_run

        def publish(self, _product):
            return {"action": "create", "id": 123}

    monkeypatch.setattr(publish_app, "PIPELINES", {"test": Pipeline()})
    monkeypatch.setattr(publish_app, "DraftPublisher", StubDraftPublisher)

    result = publish_app.run(source="test", dry_run=True)
    assert result["created"] == 1
    assert result["updated"] == 0
    assert result["failed"] == 0
    assert result["dry_run"] is True
