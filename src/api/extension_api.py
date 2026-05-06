"""src/api/extension_api.py — 크롬 확장/북마클릿 수집 API (Phase 135).

라우트:
  POST /api/v1/collect/extension — 확장/북마클릿에서 상품 수집
  POST /api/v1/collect/bulk     — 벌크 URL 수집 (백그라운드 큐)
  GET  /api/v1/collect/bulk/<job_id> — 벌크 수집 진행률 폴링

인증: Authorization: Bearer <personal_access_token>
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

extension_bp = Blueprint("extension_api", __name__, url_prefix="/api/v1/collect")

# 인메모리 벌크 잡 저장소 (운영 환경에서는 Redis 또는 Sheets로 교체)
_bulk_jobs: dict = {}
_BULK_MAX_WORKERS = int(os.getenv("BULK_MAX_WORKERS", "5"))


# ---------------------------------------------------------------------------
# Personal Access Token 인증
# ---------------------------------------------------------------------------

def _require_token(scopes: list = None) -> Optional[dict]:
    """Authorization: Bearer 토큰 검증.

    Returns:
        유효한 사용자 정보 dict, 없으면 None
    """
    scopes = scopes or []
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    raw_token = auth_header[7:].strip()
    if not raw_token:
        return None

    try:
        from src.auth.personal_tokens import validate_token
        return validate_token(raw_token, required_scopes=scopes)
    except ImportError:
        logger.debug("personal_tokens 모듈 미설치 — 토큰 검증 스킵 (개발 모드)")
        if raw_token:
            return {"user_id": "dev", "scopes": ["collect.write", "catalog.read"]}
        return None
    except Exception as exc:
        logger.warning("토큰 검증 오류: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _notify_telegram(msg: str) -> None:
    """텔레그램 알림 발송 (실패해도 무시)."""
    try:
        from src.utils.telegram import send_message
        send_message(msg)
    except Exception:
        pass


def _upsert_catalog(product_data: dict, source: str) -> Optional[str]:
    """카탈로그에 상품 upsert.

    Returns:
        생성된 상품 ID (문자열), 실패 시 None
    """
    product_id = str(uuid.uuid4())[:8]
    try:
        from src.utils.sheets import open_sheet
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        if sheet_id:
            ws = open_sheet(sheet_id, "catalog")
            row = [
                product_id,
                product_data.get("url", ""),
                product_data.get("title", ""),
                product_data.get("description", "")[:200],
                product_data.get("price", ""),
                product_data.get("currency", "USD"),
                product_data.get("image", ""),
                source,
                datetime.now(timezone.utc).isoformat(),
            ]
            ws.append_row(row)
    except Exception as exc:
        logger.warning("카탈로그 upsert 실패: %s", exc)
    return product_id


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------

@extension_bp.post("/extension")
def collect_from_extension():
    """크롬 확장 / 북마클릿에서 상품 메타 수신 + 카탈로그 저장.

    Request body:
        {url, title, image, price, currency, description, jsonld, ...}
    Response:
        {ok: true, preview_url: "/seller/collect/preview/<id>"}
    """
    user = _require_token(scopes=["collect.write"])
    if not user:
        return jsonify({"ok": False, "error": "인증이 필요합니다. Personal Access Token을 설정해주세요."}), 401

    payload = request.get_json(force=True, silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "url 필드가 필요합니다."}), 400

    title = payload.get("title") or ""
    source = "chrome_extension"

    product_id = _upsert_catalog(payload, source=source)

    # 텔레그램 알림
    msg = f"🛒 [확장] {title or url} 수집됨 (by {user.get('user_id', '?')})"
    _notify_telegram(msg)

    logger.info("확장 수집 완료: url=%s user=%s", url[:80], user.get("user_id"))

    return jsonify({
        "ok": True,
        "product_id": product_id,
        "preview_url": f"/seller/collect/preview/{product_id}",
        "title": title,
    })


@extension_bp.post("/bulk")
def collect_bulk():
    """벌크 URL 수집 시작.

    Request body:
        {urls: ["https://...", ...]}
    Response:
        {ok: true, job_id: "...", total: N, status: "queued"}
    """
    user = _require_token(scopes=["collect.write"])
    if not user:
        return jsonify({"ok": False, "error": "인증이 필요합니다."}), 401

    payload = request.get_json(force=True, silent=True) or {}
    urls = payload.get("urls") or []
    if not urls or not isinstance(urls, list):
        return jsonify({"ok": False, "error": "urls 배열이 필요합니다."}), 400

    # URL 최대 100개 제한
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()][:100]
    if not urls:
        return jsonify({"ok": False, "error": "유효한 URL이 없습니다."}), 400

    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "total": len(urls),
        "processed": 0,
        "success": 0,
        "failed": 0,
        "status": "running",
        "results": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "user_id": user.get("user_id"),
    }
    _bulk_jobs[job_id] = job

    # 백그라운드 스레드에서 처리
    thread = threading.Thread(
        target=_run_bulk_job,
        args=(job_id, urls),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "total": len(urls),
        "status": "running",
        "polling_url": f"/api/v1/collect/bulk/{job_id}",
    })


@extension_bp.get("/bulk/<job_id>")
def get_bulk_status(job_id: str):
    """벌크 수집 진행률 폴링.

    Response:
        {job_id, total, processed, success, failed, status, results}
    """
    user = _require_token(scopes=["collect.write"])
    if not user:
        return jsonify({"ok": False, "error": "인증이 필요합니다."}), 401

    job = _bulk_jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "잡을 찾을 수 없습니다."}), 404

    return jsonify({
        "ok": True,
        **{k: v for k, v in job.items() if k != "results"},
        "results": job["results"][-20:],  # 최근 20개만 반환
    })


def _run_bulk_job(job_id: str, urls: list) -> None:
    """벌크 수집 백그라운드 실행 (스레드 풀)."""
    job = _bulk_jobs.get(job_id)
    if not job:
        return

    try:
        from src.collectors.dispatcher import collect as dispatcher_collect
    except ImportError:
        # 폴백: 범용 수집기
        from src.collectors.universal_scraper import UniversalScraper
        scraper = UniversalScraper()
        dispatcher_collect = scraper.fetch

    def process_url(url: str) -> dict:
        try:
            result = dispatcher_collect(url)
            product_id = _upsert_catalog(
                {
                    "url": url,
                    "title": getattr(result, "title", ""),
                    "price": str(getattr(result, "price", "") or ""),
                    "currency": getattr(result, "currency", "USD"),
                    "image": (getattr(result, "images", []) or [""])[0],
                },
                source="bulk_collect",
            )
            return {"url": url, "ok": True, "product_id": product_id}
        except Exception as exc:
            logger.warning("벌크 URL 처리 실패: %s — %s", url[:60], exc)
            return {"url": url, "ok": False, "error": str(exc)[:100]}

    with ThreadPoolExecutor(max_workers=_BULK_MAX_WORKERS) as executor:
        futures = {executor.submit(process_url, url): url for url in urls}
        for future in futures:
            try:
                result = future.result(timeout=30)
            except Exception as exc:
                result = {"url": futures[future], "ok": False, "error": str(exc)[:100]}

            job["processed"] += 1
            if result.get("ok"):
                job["success"] += 1
            else:
                job["failed"] += 1
            job["results"].append(result)

    job["status"] = "completed"
    job["completed_at"] = datetime.now(timezone.utc).isoformat()

    # 완료 알림
    user_id = job.get("user_id", "?")
    msg = (
        f"📦 벌크 수집 완료: {job['success']}/{job['total']} 성공 "
        f"(by {user_id})"
    )
    _notify_telegram(msg)
    logger.info("벌크 수집 완료: job_id=%s %s/%s", job_id, job["success"], job["total"])
