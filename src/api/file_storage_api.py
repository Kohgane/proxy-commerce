"""src/api/file_storage_api.py — 파일 스토리지 API Blueprint (Phase 76)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

file_storage_bp = Blueprint("file_storage", __name__, url_prefix="/api/v1/files")


@file_storage_bp.get("/")
def list_files():
    """파일 목록 조회."""
    prefix = request.args.get("prefix", "")
    from ..file_storage import StorageManager
    mgr = StorageManager()
    files = mgr.list(prefix)
    return jsonify([f.to_dict() for f in files])


@file_storage_bp.post("/upload")
def upload_file():
    """파일 업로드."""
    body = request.get_json(silent=True) or {}
    key = body.get("key", "")
    filename = body.get("filename", "")
    content_type = body.get("content_type", "application/octet-stream")
    data_hex = body.get("data", "")
    owner_id = body.get("owner_id", "default")
    if not key or not filename:
        return jsonify({"error": "key, filename 필드가 필요합니다"}), 400
    try:
        data = bytes.fromhex(data_hex) if data_hex else b""
    except ValueError:
        data = data_hex.encode() if isinstance(data_hex, str) else b""
    from ..file_storage import StorageManager
    mgr = StorageManager()
    try:
        meta = mgr.upload(key, data, filename, content_type, owner_id)
        return jsonify(meta.to_dict()), 201
    except ValueError:
        return jsonify({"error": "파일 업로드에 실패했습니다. 스토리지 할당량을 확인하세요"}), 400


@file_storage_bp.get("/download/<path:key>")
def download_file(key: str):
    """파일 다운로드 (hex 인코딩 반환)."""
    from ..file_storage import StorageManager
    mgr = StorageManager()
    data = mgr.download(key)
    if data is None:
        return jsonify({"error": "파일 없음"}), 404
    return jsonify({"key": key, "data": data.hex(), "size": len(data)})


@file_storage_bp.delete("/<path:key>")
def delete_file(key: str):
    """파일 삭제."""
    owner_id = request.args.get("owner_id", "default")
    from ..file_storage import StorageManager
    mgr = StorageManager()
    mgr.delete(key, owner_id)
    return jsonify({"deleted": key})


@file_storage_bp.get("/quota/<owner_id>")
def get_quota(owner_id: str):
    """스토리지 사용량 조회."""
    from ..file_storage import StorageManager
    mgr = StorageManager()
    return jsonify(mgr.get_quota(owner_id))


@file_storage_bp.get("/metadata/<path:key>")
def get_metadata(key: str):
    """파일 메타데이터 조회."""
    from ..file_storage import StorageManager
    mgr = StorageManager()
    meta = mgr.get_metadata(key)
    if meta is None:
        return jsonify({"error": "파일 없음"}), 404
    return jsonify(meta.to_dict())
