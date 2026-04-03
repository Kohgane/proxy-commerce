"""tests/test_cms.py — Phase 63: CMS 테스트."""
from __future__ import annotations

import pytest

from src.cms import (
    ContentType, ContentManager, ContentVersion,
    ContentPublisher, ContentRenderer, SEOMetadata,
)


class TestContentType:
    def test_enum_values(self):
        assert ContentType.page == "page"
        assert ContentType.blog == "blog"
        assert ContentType.faq == "faq"


class TestContentManager:
    def test_create_content(self):
        manager = ContentManager()
        item = manager.create("Test Title", "Body text", content_type="page")
        assert item["title"] == "Test Title"
        assert item["content_type"] == "page"
        assert "content_id" in item

    def test_get_content(self):
        manager = ContentManager()
        item = manager.create("Hello", "World")
        fetched = manager.get(item["content_id"])
        assert fetched["title"] == "Hello"

    def test_update_content(self):
        manager = ContentManager()
        item = manager.create("Old Title", "body")
        updated = manager.update(item["content_id"], title="New Title")
        assert updated["title"] == "New Title"

    def test_delete_content(self):
        manager = ContentManager()
        item = manager.create("To Delete", "body")
        manager.delete(item["content_id"])
        assert manager.get(item["content_id"]) is None

    def test_list_all(self):
        manager = ContentManager()
        manager.create("A", "body")
        manager.create("B", "body")
        items = manager.list_all()
        assert len(items) == 2

    def test_get_missing_returns_none(self):
        manager = ContentManager()
        assert manager.get("missing-id") is None

    def test_delete_missing_raises(self):
        manager = ContentManager()
        with pytest.raises(KeyError):
            manager.delete("nonexistent")


class TestContentVersion:
    def test_snapshot_and_get_history(self):
        versions = ContentVersion()
        content = {"title": "Hello", "body": "World"}
        entry = versions.snapshot("cid-1", content)
        assert entry["version"] == 1
        history = versions.get_history("cid-1")
        assert len(history) == 1

    def test_multiple_versions(self):
        versions = ContentVersion()
        versions.snapshot("cid-2", {"v": 1})
        versions.snapshot("cid-2", {"v": 2})
        history = versions.get_history("cid-2")
        assert len(history) == 2
        assert history[1]["version"] == 2


class TestContentPublisher:
    def test_publish(self):
        manager = ContentManager()
        item = manager.create("Test", "body")
        publisher = ContentPublisher(manager=manager)
        result = publisher.publish(item["content_id"])
        assert result["status"] == "published"

    def test_unpublish(self):
        manager = ContentManager()
        item = manager.create("Test", "body")
        publisher = ContentPublisher(manager=manager)
        publisher.publish(item["content_id"])
        result = publisher.unpublish(item["content_id"])
        assert result["status"] == "draft"


class TestContentRenderer:
    def test_bold(self):
        renderer = ContentRenderer()
        html = renderer.render("**bold text**")
        assert "<strong>bold text</strong>" in html

    def test_italic(self):
        renderer = ContentRenderer()
        html = renderer.render("*italic text*")
        assert "<em>italic text</em>" in html

    def test_heading(self):
        renderer = ContentRenderer()
        html = renderer.render("# Heading")
        assert "<h1>Heading</h1>" in html

    def test_h2(self):
        renderer = ContentRenderer()
        html = renderer.render("## Subheading")
        assert "<h2>Subheading</h2>" in html


class TestSEOMetadata:
    def test_set_and_get(self):
        seo = SEOMetadata()
        meta = seo.set("cid-1", title="SEO Title", description="Desc", keywords=["k1"])
        assert meta["title"] == "SEO Title"
        fetched = seo.get("cid-1")
        assert fetched["keywords"] == ["k1"]

    def test_get_missing_returns_none(self):
        seo = SEOMetadata()
        assert seo.get("missing") is None
