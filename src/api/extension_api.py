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
import secrets
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


def _translate_payload(payload: dict) -> dict:
    """수집 페이로드 제목/설명을 한국어로 번역 (Phase 202).

    OPENAI/DEEPL 키 미설정·ADAPTER_DRY_RUN·실패 시 원문 유지(목업 없음).
    """
    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    out = {"title_ko": title, "description_ko": description, "provider": "none"}
    if not title and not description:
        return out
    try:
        from src.seller_console.ai.translator import AITranslator

        tr = AITranslator().translate_product({"title": title, "description": description})
        out["title_ko"] = (tr.get("title_ko") or "").strip() or title
        out["description_ko"] = (tr.get("description_ko") or "").strip() or description
        out["provider"] = tr.get("provider", "stub")
    except Exception as exc:
        logger.warning("확장 수집 번역 실패, 원문 유지: %s", exc)
    return out


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------

def _merge_scraped_into_payload(payload: dict, scraped) -> dict:
    """확장이 보낸 페이지 HTML을 서버 파싱한 결과로 payload의 빈 필드를 보강.

    봇 차단 사이트도 브라우저 DOM 기반으로 수집되도록, 클라이언트가 못 채운 값을
    범용 스크래퍼 추출값으로 채운다. 기존에 값이 있으면 사용자 값 우선(가격 0/빈 값만 보강).
    """
    out = dict(payload)

    def _is_empty(v):
        return v is None or str(v).strip() in ("", "0", "0.0")

    if _is_empty(out.get("title")) and scraped.title:
        out["title"] = scraped.title
    # v16 P0: 클라이언트가 보낸 description이 사이트 공통 마케팅 필러면 버리고(상품 설명 아님),
    # 스크래퍼가 찾은 실제 설명으로 대체. 둘 다 없으면 빈 값(정직 — 가짜 필러 저장 금지).
    try:
        from src.collectors.universal_scraper import is_filler_description as _is_filler
    except Exception:
        _is_filler = lambda *a, **k: False
    if _is_filler(out.get("description"), out.get("url", "")):
        out["description"] = ""
    if _is_empty(out.get("description")) and scraped.description and not _is_filler(scraped.description):
        out["description"] = scraped.description
    if _is_empty(out.get("brand")) and getattr(scraped, "brand", None):
        out["brand"] = scraped.brand

    # 가격: payload 가격이 비었거나 0이면 스크래퍼 추출값으로 보강 (가격 0 문제 해결)
    if _is_empty(out.get("price")) and scraped.price is not None:
        out["price"] = str(scraped.price)
        if scraped.currency:
            out["currency"] = scraped.currency

    # 이미지: payload에 없으면 스크래퍼 이미지 사용
    p_imgs = out.get("images")
    if not (isinstance(p_imgs, list) and any(str(i or "").strip() for i in p_imgs)):
        if scraped.images:
            out["images"] = list(scraped.images)
            if _is_empty(out.get("image")) and scraped.images:
                out["image"] = scraped.images[0]

    # 옵션: payload에 없으면 스크래퍼 옵션 사용
    if not out.get("options") and getattr(scraped, "options", None):
        out["options"] = scraped.options

    return out


@extension_bp.post("/extension")
def collect_from_extension():
    """크롬 확장 / 북마클릿에서 상품 메타 수신 + 카탈로그 저장.

    Request body:
        {url, title, image, price, currency, description, jsonld, html, ...}
        html(선택): 브라우저 페이지 HTML — 봇 차단(403) 사이트도 서버 파싱으로 수집.
    Response:
        {ok: true, preview_url: "/seller/collect/preview/<id>"}
    """
    # v9 P0 — 수집 1건 끝까지 추적(상관관계 ID). 어느 홉에서 사라지는지 로그로 본다.
    _corr = secrets.token_hex(4)
    user = _require_token(scopes=["collect.write"])
    if not user:
        logger.warning("[collect %s] 인증 실패(토큰 없음/무효)", _corr)
        return jsonify({"ok": False, "error": "인증이 필요합니다. Personal Access Token을 설정해주세요."}), 401

    payload = request.get_json(force=True, silent=True) or {}
    url = (payload.get("url") or "").strip()
    logger.info("[collect %s] 수신 token_user_id=%r url=%s", _corr, user.get("user_id"), url[:80])
    if not url:
        return jsonify({"ok": False, "error": "url 필드가 필요합니다."}), 400

    # 봇 차단 사이트 대응: 확장이 보낸 페이지 HTML을 서버에서 파싱해 필드 보강 (네트워크 fetch 없음)
    page_html = payload.get("html")
    if page_html and isinstance(page_html, str):
        try:
            from src.collectors.universal_scraper import UniversalScraper
            scraped = UniversalScraper().parse_html(page_html, url)
            payload = _merge_scraped_into_payload(payload, scraped)
        except Exception as exc:
            logger.warning("확장 HTML 서버 파싱 실패(클라이언트 값 유지): %s", exc)

    # v16 P0: 사이트 공통 마케팅 필러는 상품 설명으로 저장하지 않는다(html 없어도 적용).
    # 리뷰(해당 제품)는 best-effort 추출(없으면 빈 리스트 — 가짜 리뷰 금지).
    try:
        from src.collectors.universal_scraper import is_filler_description, extract_reviews
        if is_filler_description(payload.get("description"), url):
            payload["description"] = ""
        if not payload.get("reviews") and isinstance(page_html, str) and page_html:
            _revs = extract_reviews(page_html)
            if _revs:
                payload["reviews"] = _revs
    except Exception as exc:
        logger.warning("[collect %s] 필러/리뷰 처리 실패: %s", _corr, exc)

    # v16 P0: 가격이 비었거나 0이면 가짜 0원 대신 '확인 필요'로 정직 표기.
    def _price_empty(v):
        return v is None or str(v).strip() in ("", "0", "0.0", "0.00")
    if _price_empty(payload.get("price")):
        payload["price_status"] = "needs_check"

    payload.pop("html", None)  # 대용량 HTML은 이력에 저장하지 않음

    title = payload.get("title") or ""
    source = "extension"

    # 수집 시 한국어 번역 (키 없으면 원문 유지)
    translate = payload.get("translate", True) is not False
    tr = _translate_payload(payload) if translate else {
        "title_ko": title, "description_ko": payload.get("description", ""), "provider": "none",
    }
    title_ko = tr.get("title_ko") or title

    product_id = _upsert_catalog(payload, source=source)

    # 이미지 목록 정규화 + 무관 이미지 제거 (편집 페이지에서 바로 쓰도록)
    # v11 P0: 어떤 소스(확장/서버파싱)든 최종 단계에서 플래그·태그·픽셀·문서 등 무관 이미지 제거.
    images = payload.get("images")
    if not isinstance(images, list):
        images = [payload.get("image")] if payload.get("image") else []
    try:
        from src.collectors.universal_scraper import filter_product_images
        images = filter_product_images(images)
    except Exception:
        images = [str(i).strip() for i in images if str(i or "").strip()]

    # 수집 이력 기록 (편집 페이지가 바로 프리필되도록 상세 필드 보관)
    # v4 P0: 저장 자기검증 — append 직후 같은 seller_id로 재조회해 실제 저장됐을 때만 성공.
    #        저장 실패면 가짜 성공(낙관적 토스트) 대신 정직한 실패를 반환한다.
    seller_id_val = str(user.get("user_id") or "")
    item_id = None
    saved = False
    durable = True
    try:
        from src.seller_console.collect_history_store import append as history_append, get as history_get
        _ret = history_append(
            return_durable=True,
            source=source,
            url=url,
            title=title_ko,
            image=images[0] if images else payload.get("image", ""),
            price=payload.get("price", ""),
            currency=payload.get("currency", "USD"),
            status="ok",
            extra={
                "jsonld": payload.get("jsonld", []),
                "title": title,
                "title_en": title,
                "title_ko": title_ko,
                "description": payload.get("description", ""),
                "description_ko": tr.get("description_ko", ""),
                "images": images,
                "price": payload.get("price", ""),
                "price_original": payload.get("price", ""),
                "currency": payload.get("currency", "USD"),
                "brand": payload.get("brand", ""),
                "options": payload.get("options", []),
                "reviews": payload.get("reviews", []),
                "price_status": payload.get("price_status", ""),
                "translation_provider": tr.get("provider", "none"),
            },
            seller_id=seller_id_val,
        )
        # return_durable=True면 (item_id, durable) 튜플. 단, 일부 테스트가 append를 단일값으로
        # 모킹하므로 두 형태 모두 허용(모킹은 영속으로 간주).
        if isinstance(_ret, tuple) and len(_ret) == 2:
            item_id, durable = _ret
        else:
            item_id, durable = _ret, True
        logger.info("[collect %s] 저장 시도 seller_id=%r item_id=%s", _corr, seller_id_val, item_id)
        try:
            saved = history_get(item_id, seller_id=seller_id_val) is not None
        except Exception:
            saved = bool(item_id)
        logger.info("[collect %s] 저장 자기검증 saved=%s durable=%s (같은 seller_id=%r로 재조회)",
                    _corr, saved, durable, seller_id_val)
    except Exception as exc:
        logger.warning("[collect %s] 수집 이력 기록 실패: %s", _corr, exc)

    if not item_id or not saved or not durable:
        # 가짜 성공 금지(v4/v38 P0): 실제 저장 안 됐거나(saved=False) 영속 저장소(시트)에 못 들어가
        # 인메모리로만 폴백(durable=False)된 경우 — 멀티워커/새로고침엔 안 보임 → 정직한 실패로
        # 토스트가 사유를 표시하고 재시도하게 한다(가짜 성공 절대 금지).
        logger.warning("[collect %s] 저장 검증 실패 → 502 정직 실패: url=%s seller_id=%r saved=%s durable=%s",
                       _corr, url[:80], seller_id_val, saved, durable)
        return jsonify({"ok": False, "error": "수집 항목을 저장하지 못했습니다. 잠시 후 다시 시도하세요."}), 502

    preview_url = f"/seller/collect/preview/{item_id}"

    # 텔레그램 알림
    msg = f"🛒 [확장] {title or url} 수집됨 (by {user.get('user_id', '?')})"
    _notify_telegram(msg)

    logger.info("확장 수집 완료: url=%s user=%s id=%s", url[:80], seller_id_val, item_id)

    return jsonify({
        "ok": True,
        "item_id": item_id,
        "product_id": product_id,
        "preview_url": preview_url,
        "title": title,
        "title_ko": title_ko,
        "translated": tr.get("provider", "none") not in ("none", "stub"),
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

    # URL 최대 1000개 제한
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()][:1000]
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

    seller_id_val = str(job.get("user_id") or "")

    def process_url(url: str) -> dict:
        try:
            result = dispatcher_collect(url)
            title = getattr(result, "title", "") or ""
            images = list(getattr(result, "images", []) or [])
            price = str(getattr(result, "price", "") or "")
            currency = getattr(result, "currency", "USD")
            _upsert_catalog(
                {"url": url, "title": title, "price": price, "currency": currency,
                 "image": images[0] if images else ""},
                source="bulk_collect",
            )
            # v38 P0: 벌크도 '수집 이력'에 실제 저장(이전엔 catalog만 써서 수집품목에 안 보였음).
            #         영속 저장(durable) 확인된 경우에만 성공 처리(가짜 성공 금지).
            from src.seller_console.collect_history_store import append as history_append
            _ret = history_append(
                return_durable=True, source="bulk", url=url, title=title,
                image=images[0] if images else "", price=price, currency=currency,
                status="ok", seller_id=seller_id_val,
                extra={"title": title, "title_ko": title, "images": images,
                       "price": price, "currency": currency},
            )
            item_id, durable = _ret if (isinstance(_ret, tuple) and len(_ret) == 2) else (_ret, True)
            if not item_id or not durable:
                return {"url": url, "ok": False, "error": "저장 영속화 실패(재시도 필요)"}
            return {"url": url, "ok": True, "item_id": item_id}
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
