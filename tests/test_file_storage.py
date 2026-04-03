"""tests/test_file_storage.py — Phase 76: 파일 스토리지 추상화 테스트."""
from __future__ import annotations

import pytest

from src.file_storage import (
    FileMetadata, StorageBackend, LocalStorage, S3Storage, GCSStorage,
    FileOrganizer, FileQuota, FileUploader, StorageManager
)


class TestFileMetadata:
    def test_creation(self):
        meta = FileMetadata(
            key="test/file.txt",
            filename="file.txt",
            content_type="text/plain",
            size=100,
        )
        assert meta.key == "test/file.txt"
        assert meta.size == 100
        assert "metadata_id" in meta.to_dict()

    def test_compute_checksum(self):
        data = b"hello world"
        checksum = FileMetadata.compute_checksum(data)
        assert len(checksum) == 64  # SHA-256 hex
        assert checksum == FileMetadata.compute_checksum(data)

    def test_to_dict(self):
        meta = FileMetadata("k", "f", "t", 50)
        d = meta.to_dict()
        assert all(k in d for k in ["key", "filename", "content_type", "size", "checksum"])


class TestLocalStorage:
    def setup_method(self):
        self.storage = LocalStorage()

    def test_put_and_get(self):
        data = b"test content"
        meta = FileMetadata("key1", "test.txt", "text/plain", len(data))
        self.storage.put("key1", data, meta)
        retrieved = self.storage.get("key1")
        assert retrieved == data

    def test_exists(self):
        assert self.storage.exists("nonexistent") is False
        meta = FileMetadata("key2", "f", "t", 1)
        self.storage.put("key2", b"x", meta)
        assert self.storage.exists("key2") is True

    def test_delete(self):
        meta = FileMetadata("key3", "f", "t", 1)
        self.storage.put("key3", b"data", meta)
        self.storage.delete("key3")
        assert self.storage.exists("key3") is False

    def test_list(self):
        m1 = FileMetadata("images/a.jpg", "a.jpg", "image/jpeg", 100)
        m2 = FileMetadata("images/b.jpg", "b.jpg", "image/jpeg", 200)
        m3 = FileMetadata("docs/c.pdf", "c.pdf", "application/pdf", 300)
        self.storage.put("images/a.jpg", b"", m1)
        self.storage.put("images/b.jpg", b"", m2)
        self.storage.put("docs/c.pdf", b"", m3)
        images = self.storage.list("images/")
        assert len(images) == 2

    def test_checksum_stored(self):
        data = b"checksum test"
        meta = FileMetadata("ck_key", "f", "t", len(data))
        stored_meta = self.storage.put("ck_key", data, meta)
        assert stored_meta.checksum == FileMetadata.compute_checksum(data)


class TestS3Storage:
    def test_put_and_get(self):
        storage = S3Storage(bucket="test-bucket")
        data = b"s3 data"
        meta = FileMetadata("s3key", "f.txt", "text/plain", len(data))
        storage.put("s3key", data, meta)
        assert storage.get("s3key") == data
        assert storage.get_metadata("s3key").tags["s3_bucket"] == "test-bucket"

    def test_get_s3_url(self):
        storage = S3Storage(bucket="my-bucket")
        url = storage.get_s3_url("path/to/file.txt")
        assert url == "s3://my-bucket/path/to/file.txt"


class TestGCSStorage:
    def test_put_and_get(self):
        storage = GCSStorage(bucket="test-gcs-bucket")
        data = b"gcs data"
        meta = FileMetadata("gcs_key", "f.txt", "text/plain", len(data))
        storage.put("gcs_key", data, meta)
        assert storage.get("gcs_key") == data

    def test_get_gcs_url(self):
        storage = GCSStorage(bucket="my-gcs")
        url = storage.get_gcs_url("path/file.txt")
        assert url == "gs://my-gcs/path/file.txt"


class TestFileOrganizer:
    def setup_method(self):
        self.organizer = FileOrganizer()

    def test_generate_key_with_image(self):
        key = self.organizer.generate_key("photo.jpg", "image/jpeg", "uploads")
        assert "images" in key
        assert "photo.jpg" in key
        assert "uploads" in key

    def test_generate_key_with_pdf(self):
        key = self.organizer.generate_key("doc.pdf", "application/pdf")
        assert "documents" in key

    def test_organize_by_date(self):
        keys = ["2024/01/15/a.jpg", "2024/01/15/b.jpg", "2024/02/01/c.jpg"]
        result = self.organizer.organize_by_date(keys)
        assert "2024/01/15" in result
        assert len(result["2024/01/15"]) == 2

    def test_organize_by_type(self):
        keys = ["images/a.jpg", "images/b.jpg", "docs/c.pdf"]
        result = self.organizer.organize_by_type(keys)
        assert "images" in result
        assert len(result["images"]) == 2


class TestFileQuota:
    def setup_method(self):
        self.quota = FileQuota()

    def test_default_quota(self):
        assert self.quota.get_quota("user1") == FileQuota.DEFAULT_QUOTA_BYTES

    def test_set_and_get_quota(self):
        self.quota.set_quota("user1", 500 * 1024 * 1024)
        assert self.quota.get_quota("user1") == 500 * 1024 * 1024

    def test_add_and_get_usage(self):
        self.quota.add_usage("user1", 100)
        self.quota.add_usage("user1", 200)
        assert self.quota.get_usage("user1") == 300

    def test_subtract_usage(self):
        self.quota.add_usage("user1", 500)
        self.quota.subtract_usage("user1", 200)
        assert self.quota.get_usage("user1") == 300

    def test_check_quota_within(self):
        self.quota.set_quota("user1", 1000)
        assert self.quota.check_quota("user1", 500) is True

    def test_check_quota_exceeded(self):
        self.quota.set_quota("user1", 100)
        self.quota.add_usage("user1", 50)
        assert self.quota.check_quota("user1", 100) is False

    def test_get_summary(self):
        self.quota.set_quota("u1", 1000)
        self.quota.add_usage("u1", 400)
        summary = self.quota.get_summary("u1")
        assert summary["used_bytes"] == 400
        assert summary["available_bytes"] == 600
        assert summary["usage_pct"] == 40.0


class TestFileUploader:
    def setup_method(self):
        self.backend = LocalStorage()
        self.uploader = FileUploader(self.backend)

    def test_upload_file(self):
        data = b"hello"
        meta = self.uploader.upload("test.txt", data, "test.txt", "text/plain")
        assert meta.key == "test.txt"
        assert meta.size == len(data)

    def test_upload_deduplication(self):
        data = b"same content"
        meta1 = self.uploader.upload("dup.txt", data, "dup.txt")
        meta2 = self.uploader.upload("dup.txt", data, "dup.txt", check_duplicate=True)
        assert meta1.checksum == meta2.checksum

    def test_chunked_upload(self):
        upload_id = self.uploader.start_chunked_upload(
            key="chunked.bin",
            filename="chunked.bin",
            content_type="application/octet-stream",
            total_size=6,
        )
        self.uploader.upload_chunk(upload_id, 0, b"hel")
        progress = self.uploader.upload_chunk(upload_id, 1, b"lo!")
        assert progress["progress_pct"] == 100.0
        meta = self.uploader.complete_chunked_upload(upload_id)
        assert meta.size == 6
        assert self.backend.get("chunked.bin") == b"hello!"

    def test_get_progress(self):
        upload_id = self.uploader.start_chunked_upload(
            key="p.bin", filename="p.bin",
            content_type="application/octet-stream", total_size=100
        )
        self.uploader.upload_chunk(upload_id, 0, b"x" * 50)
        progress = self.uploader.get_progress(upload_id)
        assert progress["progress_pct"] == 50.0


class TestStorageManager:
    def setup_method(self):
        self.mgr = StorageManager()

    def test_upload_and_download(self):
        data = b"test data"
        self.mgr.upload("myfile.txt", data, "myfile.txt")
        downloaded = self.mgr.download("myfile.txt")
        assert downloaded == data

    def test_quota_enforced(self):
        self.mgr.set_quota("user1", 10)  # 10 bytes only
        with pytest.raises(ValueError):
            self.mgr.upload("bigfile.txt", b"x" * 100, "bigfile.txt",
                            owner_id="user1")

    def test_delete_reduces_quota(self):
        self.mgr.set_quota("u1", 1000)
        data = b"x" * 100
        self.mgr.upload("f.txt", data, "f.txt", owner_id="u1")
        summary = self.mgr.get_quota("u1")
        assert summary["used_bytes"] == 100
        self.mgr.delete("f.txt", "u1")
        summary = self.mgr.get_quota("u1")
        assert summary["used_bytes"] == 0

    def test_list_files(self):
        self.mgr.upload("a.txt", b"a", "a.txt")
        self.mgr.upload("b.txt", b"b", "b.txt")
        files = self.mgr.list()
        assert len(files) >= 2

    def test_get_metadata(self):
        self.mgr.upload("meta_test.txt", b"data", "meta_test.txt")
        meta = self.mgr.get_metadata("meta_test.txt")
        assert meta is not None
        assert meta.filename == "meta_test.txt"

    def test_generate_key(self):
        key = self.mgr.generate_key("photo.jpg", "image/jpeg", "user1")
        assert "photo.jpg" in key
        assert "user1" in key
