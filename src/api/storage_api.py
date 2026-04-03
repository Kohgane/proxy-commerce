"""src/api/storage_api.py — 파일 스토리지 API Blueprint (Phase 55)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

storage_bp = Blueprint("storage", __name__, url_prefix="/api/v1/storage")

_backend = None
_quota = None
_metadata_store: dict = {}


def _get_services():
    global _backend, _quota
    if _backend is None:
        from ..storage.local_storage import LocalStorageBackend
        from ..storage.storage_quota import StorageQuota
        _backend = LocalStorageBackend()
        _quota = StorageQuota()
    return _backend, _quota


@storage_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "storage"})


@storage_bp.post("/upload")
def upload():
    backend, quota = _get_services()
    data = request.get_json(force=True) or {}
    owner_id = data.get("owner_id", "anonymous")
    filename = data.get("filename", "file.bin")
    content_type = data.get("content_type", "application/octet-stream")
    content = data.get("content", "").encode()

    if not quota.check_quota(owner_id, len(content)):
        return jsonify({"error": "스토리지 할당량 초과"}), 400

    from ..storage.file_metadata import FileMetadata
    file_id = backend.upload(filename, content, content_type)
    meta = FileMetadata(
        name=filename,
        size=len(content),
        content_type=content_type,
        owner_id=owner_id,
        data=content,
        id=file_id,
    )
    _metadata_store[file_id] = meta
    quota.record_upload(owner_id, len(content))
    return jsonify(meta.to_dict()), 201


@storage_bp.get("/download/<file_id>")
def download(file_id: str):
    backend, _ = _get_services()
    data = backend.download(file_id)
    if data is None:
        return jsonify({"error": "파일 없음"}), 404
    return jsonify({"file_id": file_id, "size": len(data), "data": data.decode(errors="replace")})


@storage_bp.get("/list")
def list_files():
    backend, _ = _get_services()
    prefix = request.args.get("prefix", "")
    files = backend.list_files(prefix)
    return jsonify({"files": files, "count": len(files)})


@storage_bp.delete("/delete/<file_id>")
def delete_file(file_id: str):
    backend, quota = _get_services()
    meta = _metadata_store.get(file_id)
    success = backend.delete(file_id)
    if not success:
        return jsonify({"error": "파일 없음"}), 404
    if meta:
        quota.record_delete(meta.owner_id, meta.size)
        del _metadata_store[file_id]
    return jsonify({"deleted": file_id})


@storage_bp.get("/quota")
def get_quota():
    _, quota = _get_services()
    owner_id = request.args.get("owner_id", "anonymous")
    return jsonify(quota.get_summary(owner_id))
