"""tests/test_storage.py — Phase 55: 파일 스토리지 테스트."""
from __future__ import annotations

import pytest
from src.storage.storage_backend import StorageBackend
from src.storage.local_storage import LocalStorageBackend
from src.storage.s3_storage import S3StorageBackend
from src.storage.file_metadata import FileMetadata
from src.storage.image_processor import ImageProcessor
from src.storage.storage_quota import StorageQuota


class TestLocalStorageBackend:
    def setup_method(self):
        self.backend = LocalStorageBackend()

    def test_upload_and_download(self):
        file_id = self.backend.upload("test.txt", b"hello world", "text/plain")
        assert file_id
        data = self.backend.download(file_id)
        assert data == b"hello world"

    def test_download_missing(self):
        assert self.backend.download("nonexistent") is None

    def test_delete(self):
        file_id = self.backend.upload("file.txt", b"data", "text/plain")
        assert self.backend.delete(file_id) is True
        assert self.backend.download(file_id) is None

    def test_delete_missing(self):
        assert self.backend.delete("nonexistent") is False

    def test_list_files(self):
        self.backend.upload("img/photo.jpg", b"jpg", "image/jpeg")
        self.backend.upload("img/banner.png", b"png", "image/png")
        self.backend.upload("doc/report.pdf", b"pdf", "application/pdf")
        files = self.backend.list_files("img/")
        assert len(files) == 2
        all_files = self.backend.list_files()
        assert len(all_files) == 3

    def test_is_storage_backend(self):
        assert isinstance(self.backend, StorageBackend)


class TestS3StorageBackend:
    def setup_method(self):
        self.backend = S3StorageBackend(bucket="test-bucket")

    def test_upload_returns_s3_url(self):
        file_id = self.backend.upload("data.csv", b"a,b,c", "text/csv")
        assert file_id.startswith("s3://test-bucket/")

    def test_download(self):
        file_id = self.backend.upload("data.csv", b"content", "text/csv")
        assert self.backend.download(file_id) == b"content"

    def test_delete(self):
        file_id = self.backend.upload("f.txt", b"x", "text/plain")
        assert self.backend.delete(file_id) is True
        assert self.backend.download(file_id) is None

    def test_list_files_with_prefix(self):
        self.backend.upload("img/a.jpg", b"1", "image/jpeg")
        self.backend.upload("img/b.jpg", b"2", "image/jpeg")
        self.backend.upload("doc/c.pdf", b"3", "application/pdf")
        imgs = self.backend.list_files("img/")
        assert len(imgs) == 2


class TestFileMetadata:
    def test_basic_creation(self):
        meta = FileMetadata(name="file.txt", size=100, content_type="text/plain", owner_id="u1")
        assert meta.id
        assert meta.uploaded_at

    def test_hash_computed_from_data(self):
        data = b"hello"
        meta = FileMetadata(name="f.txt", size=5, content_type="text/plain", owner_id="u1", data=data)
        import hashlib
        assert meta.hash == hashlib.md5(data).hexdigest()

    def test_to_dict(self):
        meta = FileMetadata(name="f.txt", size=5, content_type="text/plain", owner_id="u1")
        d = meta.to_dict()
        assert "id" in d
        assert "name" in d
        assert "owner_id" in d


class TestImageProcessor:
    def setup_method(self):
        self.processor = ImageProcessor()
        self.meta = FileMetadata(name="photo.jpg", size=50000, content_type="image/jpeg", owner_id="u1")

    def test_resize(self):
        result = self.processor.resize(self.meta, 800, 600)
        assert "800x600" in result.name
        assert result.content_type == "image/jpeg"

    def test_thumbnail(self):
        result = self.processor.thumbnail(self.meta, 128)
        assert "thumb_128" in result.name
        assert result.size <= self.meta.size


class TestStorageQuota:
    def setup_method(self):
        self.quota = StorageQuota()

    def test_default_quota(self):
        assert self.quota.get_quota("new_user") == StorageQuota.DEFAULT_QUOTA_BYTES

    def test_set_and_get_quota(self):
        self.quota.set_quota("u1", 500 * 1024 * 1024)
        assert self.quota.get_quota("u1") == 500 * 1024 * 1024

    def test_check_quota_allows_within_limit(self):
        self.quota.set_quota("u1", 1000)
        assert self.quota.check_quota("u1", 500) is True

    def test_check_quota_denies_over_limit(self):
        self.quota.set_quota("u1", 100)
        assert self.quota.check_quota("u1", 200) is False

    def test_record_upload_and_usage(self):
        self.quota.record_upload("u1", 1024)
        assert self.quota.get_usage("u1") == 1024

    def test_record_delete_reduces_usage(self):
        self.quota.record_upload("u1", 2048)
        self.quota.record_delete("u1", 1024)
        assert self.quota.get_usage("u1") == 1024

    def test_get_summary(self):
        self.quota.set_quota("u1", 1024 * 1024)
        self.quota.record_upload("u1", 512 * 1024)
        summary = self.quota.get_summary("u1")
        assert summary["owner_id"] == "u1"
        assert summary["usage_percent"] == 50.0
