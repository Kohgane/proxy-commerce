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
import re
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

def auth_failure_reason() -> str:
    """인증이 왜 실패했는지 **한 문장으로**. 토큰 값은 절대 싣지 않는다(마스킹도 안 한다).

    C-F6 실측(오너 단축어 v1): 응답이 「인증이 필요합니다. 토큰을 확인하세요.」 하나뿐이라
    **헤더 이름이 틀린 건지 토큰이 틀린 건지 알 수 없었다.** 오너 캡처의 헤더는
    `X-Intake-T…`였는데 서버가 읽는 건 `Authorization`이다 — 응답이 그걸 말해 줬어야 했다.

    값을 앞 4자라도 비추지 않는다: 로그·스크린샷·채팅으로 새는 경로가 그만큼 늘어난다.
    형식이 틀렸다는 것과 값이 틀렸다는 것만 말하면 유저는 고칠 수 있다.
    """
    raw = request.headers.get("Authorization")
    if raw is None:
        # 우리가 안 읽는 헤더로 보냈을 때가 여기다 — 그래서 **이름을 콕 집어** 말한다.
        return ("인증 헤더가 없습니다. 헤더 이름을 정확히 `Authorization`으로 넣어 주세요"
                "(다른 이름은 서버가 읽지 않습니다).")
    if not raw.strip():
        return "인증 헤더가 비어 있습니다. `Bearer ` 뒤에 토큰을 넣어 주세요."
    if not raw.startswith("Bearer "):
        return ("인증 헤더 값은 `Bearer ` 로 시작해야 합니다 — `Bearer`, 공백 한 칸, 그다음 토큰 순서입니다.")
    token = raw[7:]
    if not token.strip():
        return "`Bearer ` 뒤에 토큰이 없습니다."
    if token != token.strip() or any(c in token for c in "\r\n\t "):
        return ("토큰에 공백이나 줄바꿈이 섞여 있습니다 — 복사할 때 앞뒤가 딸려 온 경우입니다. "
                "토큰만 남기고 다시 넣어 주세요.")
    return ("토큰이 확인되지 않았습니다(만료·폐기·오타). "
            "셀러 콘솔 → 내 토큰에서 새로 발급해 단축어 헤더를 교체해 주세요.")


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


def _session_user() -> Optional[dict]:
    """v72 STEP1: Bearer 토큰이 없거나 무효(401)여도 **유효한 콘솔 로그인 세션 쿠키**면 통과(북마클릿 폴백).

    CSRF 방어: 커스텀 헤더 `X-KGP: 1`을 요구한다. 단순 HTML 폼은 커스텀 헤더를 붙일 수 없고, 커스텀 헤더가
    붙은 크로스사이트 fetch는 CORS preflight를 거쳐야 하므로(우리 CORS는 /api/v1/collect/* 만 자격 허용)
    임의 사이트의 폼 위조가 세션 인증을 악용하지 못한다.
    """
    try:
        if request.headers.get("X-KGP") != "1":
            return None
        from flask import session
        uid = str(session.get("user_id") or "").strip()
        email = str(session.get("user_email") or "").strip()
        if not uid and not email:
            return None
        return {"user_id": uid or email, "email": email,
                "scopes": ["collect.write", "catalog.read"], "auth": "session"}
    except Exception:
        return None


def _auth_user(scopes: list = None) -> Optional[dict]:
    """v72 STEP1: 인증 사다리 — Bearer 토큰 우선, 무효면 콘솔 세션 쿠키 폴백(X-KGP 헤더 필요)."""
    user = _require_token(scopes=scopes)
    if user:
        return user
    return _session_user()


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


def _bucket_filter(bucket, fallback) -> list:
    """v39-E2 #2: 이미지 버킷(갤러리/상세)을 무관 이미지 제거·중복 제거. 비었으면 fallback(이미 정제됨)."""
    try:
        from src.collectors.universal_scraper import filter_product_images
        out = filter_product_images(bucket) if isinstance(bucket, list) else []
    except Exception:
        out = [str(i).strip() for i in (bucket or []) if str(i or "").strip()]
    return out if out else list(fallback or [])


def _og_images_from_html(html: str) -> list:
    """v57 STEP4: 수신 HTML에서 og:image(들) 추출 — 제네릭 사이트 이미지 union 보강용.
    og:image / og:image:url / og:image:secure_url 다중 태그(순서 보존).
    """
    if not html or not isinstance(html, str):
        return []
    import re
    out, seen = [], set()
    for m in re.finditer(
        r'<meta[^>]+(?:property|name)=["\']og:image(?::(?:url|secure_url))?["\'][^>]*>', html, re.I):
        cm = re.search(r'content=["\']([^"\']+)["\']', m.group(0), re.I)
        if cm:
            u = cm.group(1).strip()
            if u and u not in seen:
                seen.add(u)
                out.append(u)
    return out


def _union_images(*sources) -> list:
    """v57 STEP4: 여러 이미지 소스(클라 + ld+json + og 등)를 **순서 보존 union + 중복 제거** →
    무관 이미지 제거. 첫 소스(클라/tier1)가 앞, 그 뒤로 미포함분만 append(제네릭 사이트 누락 0)."""
    merged, seen = [], set()
    for src in sources:
        if not isinstance(src, list):
            continue
        for u in src:
            u = str(u or "").strip()
            if u and u not in seen:
                seen.add(u)
                merged.append(u)
    try:
        from src.collectors.universal_scraper import filter_product_images
        return filter_product_images(merged)
    except Exception:
        return merged


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
        # v66 STEP4: 키가 있는데 호출 실패(fallback)면 실제 원인을 서버 로그에 남긴다(무음 금지·오귀인 금지).
        if tr.get("error"):
            out["translate_error"] = str(tr.get("error"))
            logger.warning("[collect 번역] 키 있음·호출 실패 → 원문 유지: %s", tr.get("error"))
    except Exception as exc:
        try:
            from src.seller_console.ai.translator import classify_translate_error
            out["translate_error"] = classify_translate_error(exc)
        except Exception:
            pass
        logger.warning("확장 수집 번역 실패(%s), 원문 유지: %s", out.get("translate_error", "원인 미상"), exc)
    # v39 D: 번역본에도 플레이스홀더 토큰이 남지 않도록 정리(가짜값 금지).
    try:
        from src.collectors.universal_scraper import strip_placeholder_tokens as _strip_ph
        out["title_ko"] = _strip_ph(out["title_ko"])
        out["description_ko"] = _strip_ph(out["description_ko"])
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------

def _field_empty(payload: dict, key: str) -> bool:
    """v52: 필드가 비었는지(스칼라 빈값/0, 배열 무내용)."""
    v = payload.get(key)
    if isinstance(v, list):
        return not any(str(i or "").strip() for i in v)
    return v is None or str(v).strip() in ("", "0", "0.0", "0.00")


# v86-F: 간이(제목·이미지만) 수집 모드 집합. 'core'=북마클릿 폴백(v81), 'simple'=목록 타일(v86-F),
#   C-T3 'share'=앱 공유 텍스트(제목·링크만 — 이미지도 없다).
#   셋 다 목록에서 '간이' 뱃지 + [다시 수집] 권유. **뱃지 조건은 여기 한 곳에서만 정의한다.**
SIMPLE_COLLECT_MODES = frozenset({"core", "simple", "share"})


def _resolve_collect_mode(payload: dict) -> str:
    """수집 모드를 **실체로 재검증**해 결정한다.

    v86-F 오너 지적: 아마존 목록 타일 수집이 `mode:'full'`로 저장돼, 제목·이미지뿐인 항목이
    상세페이지 수집분과 목록에서 구별되지 않았다(정직 표기 위반 — '간이' 뱃지가 안 뜬다).

    클라가 보낸 mode를 그대로 믿지 않는다. 확장이 낡았거나(구버전) 새 호출부가 mode를 빠뜨리면
    같은 사고가 조용히 재발하기 때문이다. 상세·옵션·스펙·갤러리가 **전부 비었으면** 간이로 강등한다.
    (가격은 목록 카드에도 실리므로 '상세를 받았다'의 근거가 못 된다 → 판정에서 제외.)
    반대로 올리진 않는다 — 클라가 간이라고 했으면 간이다(보수적).
    """
    mode = str(payload.get("mode") or "").strip().lower() or "full"
    if mode in SIMPLE_COLLECT_MODES:
        return mode
    substantive = ("description", "options", "detail_specs", "gallery_images", "detail_images", "reviews")
    if any(not _field_empty(payload, k) for k in substantive):
        return mode
    imgs = [i for i in (payload.get("images") or []) if str(i or "").strip()]
    if len(imgs) > 1:
        return mode
    return "simple"


def _nonempty_w4(v) -> bool:
    """v87-W4: 재수집 병합에서 '값이 실제로 왔는가' 판정(빈 문자열·빈 리스트·None=없음)."""
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    return bool(str(v).strip())


def _now_iso_w4() -> str:
    """v87-W4: 최근 갱신 시각(UTC ISO) — 최초수집(collected_at)과 분리 표시용."""
    return datetime.now(timezone.utc).isoformat()


def _merge_state_into_payload(payload: dict, sj: dict) -> dict:
    """v49 STEP4: 초기 상태 JSON 파싱 결과(sj)로 payload의 빈 필드를 보강(클라/사용자 값 우선).

    가격·통화는 payload가 비었거나 0일 때만. 배열(이미지/옵션/상세/리뷰)은 payload에 없을 때만 채움.
    """
    out = dict(payload)

    def _empty(v):
        return v is None or str(v).strip() in ("", "0", "0.0", "0.00")

    def _empty_list(v):
        return not (isinstance(v, list) and any(str(i or "").strip() for i in v))

    if _empty(out.get("price")) and sj.get("price"):
        out["price"] = str(sj["price"])
        if sj.get("currency"):
            out["currency"] = sj["currency"]
    if _empty(out.get("title")) and sj.get("title"):
        out["title"] = sj["title"]
    if _empty(out.get("description")) and sj.get("description"):
        out["description"] = sj["description"]
    if _empty_list(out.get("images")) and sj.get("images"):
        out["images"] = list(sj["images"])
    if _empty_list(out.get("gallery_images")) and sj.get("images"):
        out["gallery_images"] = list(sj["images"])
    if _empty_list(out.get("detail_images")) and sj.get("detail_images"):
        out["detail_images"] = list(sj["detail_images"])
    if not out.get("options") and sj.get("options"):
        out["options"] = sj["options"]
    if not out.get("skus") and sj.get("skus"):
        out["skus"] = sj["skus"]
    if not out.get("reviews") and sj.get("reviews"):
        out["reviews"] = sj["reviews"]
    if _empty(out.get("rating")) and sj.get("rating"):
        out["rating"] = sj["rating"]
    if _empty(out.get("review_count")) and sj.get("review_count"):
        out["review_count"] = sj["review_count"]
    return out


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

    # v39-E2 #2: 갤러리(대표) vs 상세(본문) 이미지 버킷 — 스크래퍼가 분리했으면 payload로 전달.
    try:
        rm = getattr(scraped, "raw_meta", None) or {}
        if not out.get("gallery_images") and rm.get("gallery_images"):
            out["gallery_images"] = list(rm["gallery_images"])
        if not out.get("detail_images") and rm.get("detail_images"):
            out["detail_images"] = list(rm["detail_images"])
    except Exception:
        pass

    return out


@extension_bp.get("/me")
def api_me():
    """v42 E-1: 토큰 연결 상태 확인 — 확장 옵션의 '연결됨 ✓ (계정)' 표시용.

    유효 토큰 → 200 {ok:true, email, name}. 무효·만료 → 401(재설정 유도).
    CORS는 /api/v1/collect/* 에 이미 열려 있어 확장(교차출처)에서 호출 가능.
    """
    user = _require_token()
    if not user:
        return jsonify({"ok": False, "error": "invalid_or_expired_token"}), 401
    uid = str(user.get("user_id") or "")
    email, name = "", ""
    try:
        from src.auth.user_store import get_store as _get_user_store
        u = _get_user_store().find_by_id(uid)
        if u is not None:
            email = getattr(u, "email", "") or ""
            name = getattr(u, "name", "") or getattr(u, "display_name", "") or ""
    except Exception:
        pass
    return jsonify({"ok": True, "email": email, "name": name, "user_id": uid})


@extension_bp.post("/exists")
def api_exists():
    """v42 E-3: 목록 카드 중 '이미 수집된' 상품 URL을 알려준다(호버 버튼 '수집됨 ✓' 선표시).

    Request: {"urls": ["...", ...]}  Response: {"ok": true, "collected": ["...이미 수집된 url..."]}
    정규화 키(1-3)로 셀러 스코프에서 판정. 미인증 401.
    """
    user = _require_token(scopes=["collect.write"])
    if not user:
        return jsonify({"ok": False, "error": "auth"}), 401
    data = request.get_json(force=True, silent=True) or {}
    urls = data.get("urls") if isinstance(data.get("urls"), list) else []
    urls = [str(u) for u in urls if str(u or "").strip()][:200]
    seller_id_val = str(user.get("user_id") or "")
    ids = {seller_id_val}
    try:
        from src.auth.user_store import get_store as _gs
        _u = _gs().find_by_id(seller_id_val)
        if _u is not None and getattr(_u, "email", ""):
            ids.add(str(_u.email))
    except Exception:
        pass
    collected = []
    try:
        from src.seller_console.collect_history_store import find_by_product_key as _find
        for u in urls:
            try:
                if _find(u, seller_ids=ids):
                    collected.append(u)
            except Exception:
                pass
    except Exception:
        pass
    return jsonify({"ok": True, "collected": collected})


@extension_bp.post("/link-diag")
def collect_link_diag():
    """C-F9-3: **서버가 이 링크를 어디까지 펴는지** 서버 자신이 재서 원문으로 돌려준다.

    F7-2(「Render 싱가포르에서 302 체인을 재라」)가 오너 Shell을 기다리며 열려 있었다.
    측정을 사람 손에 맡기면 **매번** 사람 손이 필요하다 — 앱 안에 재는 자리를 두면
    오너가 폰에서 한 번 누르고 끝난다.

    요청 `{url}` · 응답은 `link_diag.diagnose_link` 원문 그대로(홉·최종 URL·오류 클래스).
    **저장 0** — 진단 결과는 어디에도 쌓지 않는다(최종 URL에 세션성 값이 실려 온다).
    """
    user = _require_token(scopes=["collect.write"])
    if not user:
        return jsonify({"ok": False, "error": auth_failure_reason()}), 401

    body = request.get_json(force=True, silent=True) or {}
    raw = str(body.get("url") or body.get("share_text") or "").strip()
    if not raw:
        return jsonify({"ok": False, "error": "진단할 링크를 보내 주세요."}), 400

    # 공유 글을 통째로 붙여도 되게 — 파서가 링크를 골라낸다(입구마다 다른 규칙 금지).
    from src.collectors.share_text import parse_share_text
    url = parse_share_text(raw).get("url", "") or raw

    from src.collectors.link_diag import diagnose_link
    out = diagnose_link(url)
    out["asked"] = url                 # 무엇을 쟀는지 되비쳐 준다(오타·잘린 주소 확인용)
    # 링크를 못 열었다는 **진단은 성공한 진단**이다 → 항상 200. 실패는 `error`가 말한다.
    return jsonify(out), 200


@extension_bp.get("/enrich/pending")
def collect_enrich_pending():
    """C-T4': **보강 대기 목록** — 확장이 "무엇을 열어야 하는지" 묻는 곳.

    공유 텍스트로 담은 초안은 제목·링크뿐이고, 그 링크는 **로그인된 브라우저에서만** 열린다
    (실측 2026-09-11: 서버는 중국 IP도 해외 IP도 막힌다). 그래서 보강 주체가 확장이다 —
    퍼센티가 같은 구조인 이유다. 유저 체감은 "폰에서 담고 PC에서 마무리"다.

    응답 `{ok, items: [{item_id, url, title, uncollected}], total}`.
    비면 빈 배열이다 — 없는 일감을 만들지 않는다.
    """
    user = _require_token(scopes=["collect.write"])
    if not user:
        return jsonify({"ok": False, "error": auth_failure_reason()}), 401
    seller_id_val = str(user.get("user_id") or "")
    ids = {seller_id_val} if seller_id_val else set()
    try:
        from src.auth.user_store import get_store as _gs
        _u = _gs().find_by_id(seller_id_val)
        if _u is not None and getattr(_u, "email", ""):
            ids.add(str(_u.email))
    except Exception:
        pass

    import json as _json
    from src.seller_console.collect_history_store import list_items as _list
    try:
        limit = max(1, min(int(request.args.get("limit") or 50), 200))
    except Exception:
        limit = 50

    out = []
    for row in _list(seller_ids=ids or None, days=90, limit=500):
        try:
            ex = _json.loads(row.get("extra_json") or "{}") or {}
        except Exception:
            continue
        if str(ex.get("enrich_state") or "") != "pending":
            continue
        out.append({
            "item_id": row.get("id"),
            "url": row.get("url") or "",
            "title": row.get("title") or ex.get("title") or "",
            "uncollected": ex.get("uncollected") or [],
        })
        if len(out) >= limit:
            break
    logger.info("[enrich-pending] seller=%s 대기 %s건", seller_id_val or "?", len(out))
    return jsonify({"ok": True, "items": out, "total": len(out)})


@extension_bp.post("/enrich")
def collect_enrich():
    """v64 STEP1: 벌크 2단 수집 — 목록 데이터 저장 후 확장이 각 상품 상세 페이지에서 읽은
    상세 필드로 기존 항목을 '보강'한다. **fill-only**: 제목·가격은 기존 우선(상세 추출이 비면 유지),
    옵션·상세설명·상세이미지·리뷰·평점·갤러리는 비어 있을 때 채운다. 상태 배지 재계산(부분→성공).

    Request: {item_id, options?, description?, detail_images?, gallery?/images?, reviews?, rating?, review_count?}
    Response: {ok, item_id, changed:{field:count}, status, filled, total}
    서버측 아마존/테무 직접 크롤 없음 — 확장이 브라우저 컨텍스트에서 읽어 보낸 값만 병합(가짜 성공 0).
    """
    user = _require_token(scopes=["collect.write"])
    if not user:
        return jsonify({"ok": False, "error": "auth"}), 401
    data = request.get_json(force=True, silent=True) or {}
    item_id = str(data.get("item_id") or "").strip()
    if not item_id:
        return jsonify({"ok": False, "error": "item_id가 필요합니다."}), 400
    seller_id_val = str(user.get("user_id") or "")
    ids = {seller_id_val}
    try:
        from src.auth.user_store import get_store as _gs
        _u = _gs().find_by_id(seller_id_val)
        if _u is not None and getattr(_u, "email", ""):
            ids.add(str(_u.email))
    except Exception:
        pass
    import json as _json
    from src.seller_console.collect_history_store import get as _get, update as _update
    item = _get(item_id, seller_ids=ids)
    if not item:
        return jsonify({"ok": False, "error": "항목을 찾을 수 없습니다."}), 404
    try:
        extra = _json.loads(item.get("extra_json") or "{}")
    except Exception:
        extra = {}

    def _union(a, b):
        out, seen = [], set()
        for x in list(a or []) + list(b or []):
            if isinstance(x, str) and x and x not in seen:
                seen.add(x); out.append(x)
        return out

    changed: dict = {}
    # 옵션·리뷰: 리스트가 오고 기존이 비었으면 채움.
    for k in ("options", "reviews"):
        v = data.get(k)
        if isinstance(v, list) and v and not extra.get(k):
            extra[k] = v; changed[k] = len(v)
    # 상세설명: 20자↑ 실텍스트가 오고 기존이 빈약(<20자)하면 채움.
    _desc = str(data.get("description") or "").strip()
    if len(_desc) >= 20 and len(str(extra.get("description") or "").strip()) < 20:
        extra["description"] = _desc; changed["description"] = 1
    # 평점·리뷰수: 오고 기존 비었으면.
    for k in ("rating", "review_count"):
        if data.get(k) and not extra.get(k):
            extra[k] = data[k]; changed[k] = 1
    # C-T4': 가격·통화 — **기존이 비었을 때만** 채운다(fill-only 그대로).
    #   원래 가격은 보강 대상이 아니었다: 벌크 목록 수집엔 카드 가격이 이미 실려 있었으니까.
    #   공유 텍스트 초안은 **가격이 아예 없다** — 그래서 여기서 채우지 않으면 등록 게이트가 영영 안 열린다.
    #   기존 값이 있으면 손대지 않으므로 옛 경로의 '기존 우선' 규칙은 그대로다.
    _pin = str(data.get("price") or "").strip()
    if _pin and not str(extra.get("price") or "").strip():
        extra["price"] = _pin; changed["price"] = 1
        _cin = str(data.get("currency") or "").strip()
        if _cin and not str(extra.get("currency") or "").strip():
            extra["currency"] = _cin; changed["currency"] = 1
    # 상세이미지·갤러리: union(순서보존 dedup) — 늘어날 때만.
    di = data.get("detail_images")
    if isinstance(di, list) and di:
        merged = _union(extra.get("detail_images"), di)
        if len(merged) > len(extra.get("detail_images") or []):
            extra["detail_images"] = merged; changed["detail_images"] = len(merged)
    gi = data.get("gallery") or data.get("gallery_images") or data.get("images")
    rep = ""
    if isinstance(gi, list) and gi:
        # v66 STEP3: 상세 페이지 고해상 갤러리를 **대표로** — 검색결과 저해상 썸네일을 대표로 쓰지 않는다.
        #   보강 갤러리(hi-res)를 앞에 두어 union → 대표(images[0])가 고해상이 되게.
        merged = _union(gi, extra.get("images"))
        extra["images"] = merged; changed["images"] = len(merged)
        extra["gallery_images"] = _union(gi, extra.get("gallery_images"))
        rep = merged[0] if merged else ""
    extra["enriched"] = True
    # v86-F: 보강으로 상세가 실제로 채워졌으면 '간이'를 해제한다. 안 그러면 타일 수집분에 뱃지가
    #   영구히 남아 경고가 소음이 되고, 정작 진짜 간이 항목이 묻힌다. 단 **실제로 채워졌을 때만**
    #   (changed가 비면 그대로 간이 — 큐만 돌고 못 채운 것을 성공으로 위장하지 않는다).
    if changed and str(extra.get("mode") or "").lower() in SIMPLE_COLLECT_MODES:
        extra["mode"] = "full"
        changed["mode"] = 1
    # C-T3/T4': 등록 게이트 해제 — **가격이 실제로 들어왔을 때만**.
    #   상세·이미지만 채워지고 가격이 여전히 비면 마진을 못 낸다(그 상태로 열면 0 발명으로 돌아간다).
    if str(extra.get("enrich_state") or "") == "pending":
        _price_now = str(extra.get("price") or "").strip()
        if _price_now and _price_now not in ("0", "0.0", "0.00"):
            extra["enrich_state"] = "done"
            extra["uncollected"] = [f for f in (extra.get("uncollected") or []) if f != "price"]
            changed["enrich_state"] = 1
        else:
            logger.info("[enrich] item=%s 가격 미보강 — 등록 게이트 유지", item_id)
    # 상태 배지 재계산(부분→성공).
    try:
        from src.collectors.collect_status import compute_collect_status as _ccs
        extra["collect_status"] = _ccs(extra, title_fallback=item.get("title") or "")
    except Exception:
        pass
    _upd = {"extra_json": _json.dumps(extra, ensure_ascii=False)}
    if rep:
        _upd["image_url"] = rep     # 목록 대표 썸네일도 고해상으로 교체
    # C-T4': 가격을 채웠으면 **행 컬럼도** 갱신한다 — 목록·검수표는 extra가 아니라 행을 읽는다.
    #   여기 빠뜨리면 드로어엔 가격이 보이는데 목록은 '-'로 남아, 보강이 안 된 것처럼 보인다.
    if changed.get("price"):
        _upd["price"] = str(extra.get("price") or "")
        if extra.get("currency"):
            _upd["currency"] = str(extra.get("currency"))
        _upd["status"] = "ok"       # '보강 대기' 해제

    ok = _update(item_id, seller_ids=ids, **_upd)
    st = extra.get("collect_status") or {}
    # v66 STEP3: 보강 판정 회수 — 큐가 돌았는지/필드를 채웠는지 서버 로그로 특정(어느 쪽인지 PR 근거).
    logger.info("[enrich] item=%s changed=%s status=%s rep=%s", item_id, changed, st.get("status"), bool(rep))
    return jsonify({"ok": bool(ok), "item_id": item_id, "changed": changed,
                    "status": st.get("status"), "filled": st.get("filled"), "total": st.get("total")})


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
    # v72 STEP1: Bearer 우선, 무효(401)면 콘솔 로그인 세션 쿠키 폴백(X-KGP 헤더 필요) — 북마클릿 토큰 사망 대비.
    user = _auth_user(scopes=["collect.write"])
    if not user:
        logger.warning("[collect %s] 인증 실패(토큰 무효 + 세션 없음)", _corr)
        return jsonify({"ok": False, "error": "콘솔 로그인 후 다시 눌러 주세요.",
                        "login_required": True, "login_url": "/seller/dashboard",
                        "reissue_url": "/seller/bookmarklet"}), 401   # v72b STEP2: 토큰 재발급 페이지
    if user.get("auth") == "session":
        logger.info("[collect %s] 세션 폴백 인증(토큰 무효) user_id=%r", _corr, user.get("user_id"))

    payload = request.get_json(force=True, silent=True) or {}
    url = (payload.get("url") or "").strip()
    # 다시 수집(덮어쓰기): 중복이어도 새 항목을 만들지 않고 기존 항목의 가격·이미지를 갱신한다.
    _force = bool(payload.get("force") or payload.get("overwrite"))
    # P0 진단: 확장 버전·엔드포인트·수신 필드를 로깅(전면 실패 원인 1줄 규명용).
    _ext_ver = str(payload.get("ext_version") or "").strip()
    logger.info("[collect %s] 수신 ext_version=%s token_user_id=%r url=%s fields=%s",
                _corr, _ext_ver or "(없음/구버전)", user.get("user_id"), url[:80],
                sorted(k for k in payload.keys() if k != "html"))
    # v49 STEP4 포렌식: 수신 값 요약(토큰 제외) — 어느 필드가 비었는지 서버 로그로 즉시 규명.
    def _n(v):
        return len(v) if isinstance(v, (list, str)) else (0 if v is None else 1)
    logger.info("[collect %s] 수신요약 price=%r currency=%r images=%d desc=%d자 html=%d자 options=%d reviews=%d rating=%r",
                _corr, payload.get("price"), payload.get("currency"),
                _n(payload.get("images")), _n(payload.get("description")),
                _n(payload.get("html")), _n(payload.get("options")),
                _n(payload.get("reviews")), payload.get("rating"))
    if not url:
        # 구버전 확장이 url 없이 보내면 조용한 실패 대신 업데이트 안내(정직).
        _hint = " 확장을 최신 버전으로 업데이트해 주세요." if not _ext_ver else ""
        return jsonify({"ok": False, "error": "url 필드가 필요합니다." + _hint,
                        "corr": _corr, "update_extension": not bool(_ext_ver)}), 400

    # 봇 차단 사이트 대응: 확장이 보낸 페이지 HTML을 서버에서 파싱해 필드 보강 (네트워크 fetch 없음)
    page_html = payload.get("html")
    _srv_src: dict = {}   # v52: 서버가 채운 필드의 출처(ldjson/tier1/dom) — 수집 로그용
    _ld_images: list = []   # v57 STEP4: ld+json Product.image 배열(union 보강용)
    # ── v54 STEP3: 필드 병합 우선순위(명문화) = tier1 > ld+json > tier2 DOM > og ─────────────────
    #   tier1 = 확장이 클릭시점 API 캡처/DOM에서 읽어 **payload에 이미 담아 보낸 값**(자가진단 채택 포함).
    #   서버 보강(_merge_*)은 **빈 필드만** 채우므로 payload(tier1) 값이 항상 우선. 그 다음 ld+json(서버),
    #   그 다음 UniversalScraper(DOM=tier2 → og=tier3) 순. 출처 라벨도 이 순서로: compute_collect_status에
    #   {**_srv_src(ldjson), **client_field_sources(tier1/tier2)} 병합 → 클라(tier1/tier2)가 서버(ldjson)를 덮는다.
    if page_html and isinstance(page_html, str):
        # ld+json(서버 1차) — 대부분 쇼핑몰이 schema.org Product(offers.price 등)를 싣는다(북마클릿 가격 본체).
        #   tier1(payload)이 이미 채운 필드는 건드리지 않음(_field_empty 게이트).
        try:
            from src.collectors.state_json import parse_ldjson
            _ld = parse_ldjson(page_html)
            if _ld:
                if isinstance(_ld.get("images"), list):
                    _ld_images = list(_ld["images"])       # v57 STEP4: union 보강용(빈 필드 게이트와 무관)
                for _k in ("price", "images", "title", "description", "rating", "review_count", "reviews"):
                    if _ld.get(_k) and _field_empty(payload, _k):
                        _srv_src[_k if _k not in ("rating", "review_count") else "reviews"] = "ldjson"
                payload = _merge_state_into_payload(payload, _ld)
                logger.info("[collect %s] ld+json 파싱: price=%r %s images=%d rating=%r reviews=%d",
                            _corr, _ld.get("price"), _ld.get("currency"), len(_ld.get("images") or []),
                            _ld.get("rating"), len(_ld.get("reviews") or []))
        except Exception as exc:
            logger.warning("[collect %s] ld+json 파싱 실패: %s", _corr, exc)
        # v49 STEP4(근본): 수신 HTML의 **초기 상태 JSON**(window.rawData 등)을 서버가 직접 파싱 →
        #   sku 가격·갤러리 전체·옵션·상세 이미지·평점·리뷰 매핑(추가 API 호출 없음). 확장·북마클릿 공통.
        #   기존 값이 비었을 때만 보강(사용자/클라 값 우선). DOM/OG(UniversalScraper)는 그 다음 폴백.
        try:
            from src.collectors.state_json import parse_state_from_html
            _sj = parse_state_from_html(page_html, url)   # v51: 테무 URL은 파서 건너뜀(초기상태 없음)
            if _sj:
                _filled = payload = _merge_state_into_payload(payload, _sj)
                logger.info("[collect %s] 초기상태 JSON 파싱: price=%r images=%d options=%d detail=%d reviews=%d rating=%r",
                            _corr, _sj.get("price"), len(_sj.get("images") or []), len(_sj.get("options") or []),
                            len(_sj.get("detail_images") or []), len(_sj.get("reviews") or []), _sj.get("rating"))
        except Exception as exc:
            logger.warning("[collect %s] 초기상태 JSON 파싱 실패: %s", _corr, exc)
        try:
            from src.collectors.universal_scraper import UniversalScraper
            scraped = UniversalScraper().parse_html(page_html, url)
            payload = _merge_scraped_into_payload(payload, scraped)
        except Exception as exc:
            logger.warning("확장 HTML 서버 파싱 실패(클라이언트 값 유지): %s", exc)
        # v39-E2 #3: 상세설명 실추출(본문 텍스트 + 스펙 표). 설명이 비었거나 빈약하면 본문으로 채움.
        try:
            from src.collectors.universal_scraper import extract_detail_description
            det = extract_detail_description(page_html, url)
            cur = (payload.get("description") or "").strip()
            if det.get("text") and len(cur) < 30:
                payload["description"] = det["text"]
            if det.get("specs"):
                payload["detail_specs"] = [list(s) for s in det["specs"]]
        except Exception as exc:
            logger.debug("상세설명 추출 실패: %s", exc)

        # v57 STEP4: 제네릭 이미지 보강 — 클라(tier1/DOM) + ld+json image + og:image를 **순서 보존 union**
        #   (빈 필드만 채우는 _merge와 달리, 이미 이미지가 있어도 누락분을 뒤에 append). 제네릭 사이트 갤러리 누락 0.
        try:
            _og_imgs = _og_images_from_html(page_html)
            _client_g = payload.get("gallery_images") if isinstance(payload.get("gallery_images"), list) else []
            _client_i = payload.get("images") if isinstance(payload.get("images"), list) else []
            _union = _union_images(_client_g, _client_i, _ld_images, _og_imgs)
            if _union:
                # 클라 갤러리가 있었으면 그 순서를 앞에 유지(union이 이미 그 순서). images/gallery 동기.
                payload["images"] = _union
                payload["gallery_images"] = _union
                logger.info("[collect %s] 이미지 union: 클라 %d + ld %d + og %d → %d(중복제거)",
                            _corr, len(_client_g or _client_i), len(_ld_images), len(_og_imgs), len(_union))
        except Exception as exc:
            logger.debug("이미지 union 보강 실패: %s", exc)

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

    # v55 STEP2: 서버 단일 지점 sanity — 비상식/통화미상 가격은 **값 폐기**(9 KRW 저장 금지, needs_check),
    #   이미지는 도메인·중복·비상품 URL 필터. 모든 경로(확장·북마클릿) 공통 게이트.
    _price_before = payload.get("price")
    from src.collectors.collect_sanitize import sanitize_payload
    sanitize_payload(payload)
    if _price_before and not payload.get("price"):
        logger.warning("[collect %s] 가격 sanity 폐기: %r %s → 누락", _corr, _price_before, payload.get("currency"))

    payload.pop("html", None)  # 대용량 HTML은 이력에 저장하지 않음

    # v39 D: 소스 사이트가 미치환한 플레이스홀더 토큰({REGION_NAME...} 등)을 제목/상세에서 제거(가짜값 금지).
    try:
        from src.collectors.universal_scraper import strip_placeholder_tokens as _strip_ph
        payload["title"] = _strip_ph(payload.get("title") or "")
        payload["description"] = _strip_ph(payload.get("description") or "")
    except Exception:
        pass

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

    # v42 1-3: 중복 수집 방지 — 같은 상품(정규화 goods-id/ASIN 키)이 이미 있으면 새로 만들지 않고 안내.
    _dedup_ids = {seller_id_val}
    try:
        from src.auth.user_store import get_store as _get_user_store_d
        _du = _get_user_store_d().find_by_id(seller_id_val)
        if _du is not None and getattr(_du, "email", ""):
            _dedup_ids.add(str(_du.email))
    except Exception:
        pass
    try:
        from src.seller_console.collect_history_store import find_by_product_key as _find_dup
        _dup = _find_dup(url, seller_ids=_dedup_ids)
    except Exception:
        _dup = None
    if _dup and _dup.get("id"):
        _dup_id = _dup.get("id")
        if _force:
            # 다시 수집(덮어쓰기): 기존 항목의 가격·이미지·제목을 새 수집값으로 갱신(중복 행 안 만듦).
            try:
                import json as _json
                try:
                    _merged = _json.loads(_dup.get("extra_json") or "{}")
                except Exception:
                    _merged = {}
                _merged.update({
                    "title_ko": title_ko, "title_en": title, "title": title,
                    "price": payload.get("price", ""), "currency": payload.get("currency") or "",
                    "price_original": payload.get("price", ""),
                    "price_status": payload.get("price_status", ""),
                    "warnings": payload.get("warnings", []),
                    "images": images,
                    "gallery_images": _bucket_filter(payload.get("gallery_images"), images),
                    "detail_images": _bucket_filter(payload.get("detail_images"), []),
                    "options": payload.get("options", []),
                    "description": payload.get("description", ""),
                    "description_ko": tr.get("description_ko", ""),
                    "recollected": True,
                })
                # v87-W4: 재수집이 리뷰·평점(및 상세 스펙)을 **갱신**한다. 종전 _merged.update는 이 키들을
                #   빠뜨려, 최초수집(리뷰 없음) 행을 리뷰 담긴 새 수집으로 덮어써도 _merged엔 옛 빈 값이 남고
                #   그걸로 collect_status를 재계산 → '리뷰·평점 누락(4/5)' 고정이었다(오너 실기기 결함).
                #   정직 규칙: 새 수집이 값을 주면 그 값으로 갱신, 안 주면(빈값) 기존 값 보존(재수집 누락으로
                #   기존 리뷰를 지우지 않음 = 비파괴). 최근 갱신 시각도 남긴다(참고 칩: 최초/최근 분리 표시).
                def _fresh(_key, _new):
                    return _new if _nonempty_w4(_new) else _merged.get(_key)
                _merged["reviews"] = _fresh("reviews", payload.get("reviews", []))
                _merged["rating"] = _fresh("rating", payload.get("rating", ""))
                _merged["review_count"] = _fresh("review_count", payload.get("review_count", ""))
                _merged["detail_specs"] = _fresh("detail_specs", payload.get("detail_specs", []))
                _merged["recollected_at"] = _now_iso_w4()
                # v87-W6: 재수집=번역 재시도이기도 하다 — 번역 상태(성공/실패 사유)를 갱신(조용한 실패 고착 방지).
                _merged["translation_provider"] = tr.get("provider", "none")
                _merged["translated"] = (str(tr.get("provider") or "") in ("mymemory", "openai", "deepl")) and not tr.get("translate_error")
                _merged["translate_error"] = tr.get("translate_error", "")
                _merged["translate_requested"] = bool(translate)
                _merged["translation_attempts"] = tr.get("attempts") or []
                try:
                    from src.collectors.collect_status import compute_collect_status as _ccs
                    _cfs = payload.get("field_sources") if isinstance(payload.get("field_sources"), dict) else {}
                    _merged["collect_status"] = _ccs(_merged, title_fallback=title_ko, sources={**_srv_src, **_cfs})
                except Exception:
                    pass
                from src.seller_console.collect_history_store import update as _hist_update
                _ok = _hist_update(
                    _dup_id, seller_ids=_dedup_ids,
                    title=title_ko,
                    image_url=(images[0] if images else payload.get("image", "")),
                    price=payload.get("price", ""),
                    currency=payload.get("currency") or "",
                    extra_json=_json.dumps(_merged, ensure_ascii=False),
                )
                logger.info("[collect %s] 다시수집(덮어쓰기) id=%s ok=%s price=%s %s",
                            _corr, _dup_id, _ok, payload.get("price", ""), payload.get("currency") or "")
                if _ok:
                    return jsonify({
                        "ok": True, "updated": True, "item_id": _dup_id,
                        "preview_url": f"/seller/collect/preview/{_dup_id}",
                        "message": "다시 수집해 가격·이미지를 갱신했어요.",
                    })
            except Exception as _exc:
                logger.exception("[collect %s] 다시수집 갱신 실패: %s", _corr, _exc)
            # 갱신 실패 시 정직: 아래 일반 중복 응답(가짜 성공 금지)
        logger.info("[collect %s] 중복 수집 감지 → 기존 항목 안내: id=%s url=%s", _corr, _dup_id, url[:80])
        return jsonify({
            "ok": True, "duplicate": True, "item_id": _dup_id,
            "preview_url": f"/seller/collect/preview/{_dup_id}",
            "message": "이미 수집한 상품입니다.",
        })

    # v47 STEP2: 수집 필드 상태(성공/부분)를 단일 판정해 extra에 심는다 — 목록 상태 컬럼·드로어
    #   수집 로그·토스트가 같은 판정을 쓴다(가짜 성공·무음 실패 금지). field_sources는 확장이 보낸
    #   필드별 추출소스(json/dom/server)면 로그에 표기, 없으면 있음/없음.
    _extra = {
        "jsonld": payload.get("jsonld", []),
        "title": title,
        "title_en": title,
        "title_ko": title_ko,
        "description": payload.get("description", ""),
        "description_ko": tr.get("description_ko", ""),
        "images": images,
        "gallery_images": _bucket_filter(payload.get("gallery_images"), images),
        "detail_images": _bucket_filter(payload.get("detail_images"), []),
        "detail_fold": bool(payload.get("detail_fold")),      # v57 STEP3: 상세 '더보기' 접힘 잔존(정직 표기)
        "price": payload.get("price", ""),
        "price_original": payload.get("price", ""),
        "currency": payload.get("currency") or "",   # v42 1-1: USD 기본값 금지
        "brand": payload.get("brand", ""),
        "options": payload.get("options", []),
        "reviews": payload.get("reviews", []),
        "detail_specs": payload.get("detail_specs", []),
        "price_status": payload.get("price_status", ""),
        "warnings": payload.get("warnings", []),
        "source": payload.get("source", ""),
        "rating": payload.get("rating", ""),
        "review_count": payload.get("review_count", ""),
        "translation_provider": tr.get("provider", "none"),
        # v87-W6 item1·2 + v87-W7: 레코드 단위 번역 상태 — 사용자 선택(안 함) vs 실패를 구분해 정직 표시.
        #   translated=실제 번역됨(mymemory/openai/deepl, 폴백·stub·none 제외). translate_error=실패 사유.
        #   translate_requested=수집 시 토글 값(안 함이면 '원문 유지'는 사용자 선택). translation_attempts=체인 시도 이력.
        "translated": (str(tr.get("provider") or "") in ("mymemory", "openai", "deepl")) and not tr.get("translate_error"),
        "translate_error": tr.get("translate_error", ""),
        "translate_requested": bool(translate),
        "translation_attempts": tr.get("attempts") or [],
        "tier1_source": payload.get("tier1_source", ""),      # v55: 자가발견 채택 API URL
        "tier1_diag": payload.get("tier1_diag") or {},        # v56 STEP4: Tier1 최종 판정(used·원인) 저장
        "mode": _resolve_collect_mode(payload),   # v81 'core'(북마클릿) / v86-F 'simple'(목록 타일) / 'full'
    }
    _field_status = {}
    try:
        from src.collectors.collect_status import compute_collect_status
        _cfs = payload.get("field_sources") if isinstance(payload.get("field_sources"), dict) else {}
        _fs = {**_srv_src, **_cfs}   # v52: 서버 ld+json 출처 + 클라(확장 tier) 출처(클라 우선)
        _field_status = compute_collect_status(_extra, title_fallback=title_ko, sources=_fs)
        _extra["collect_status"] = _field_status
    except Exception as exc:
        logger.warning("[collect %s] 수집 상태 판정 실패: %s", _corr, exc)

    # v62 STEP4: 키워드는 **서버 생성**(클라 추출 폐지) — 제목·카테고리·옵션·상세 빈출어 + 오염어 필터.
    try:
        from src.seller_console.keyword_gen import generate_keywords, refine_keywords
        _kw = generate_keywords(
            title=(title_ko or title),
            category=(_extra.get("category_code") or payload.get("category_code") or ""),
            options=_extra.get("options") or [],
            desc_text=_extra.get("description") or "",
            brand=_extra.get("brand") or "",
        )
        _kw = refine_keywords(title_ko or title, _kw)   # OPENAI 가용 시 정제(미가용=그대로)
        _extra["keywords"] = _kw
        _extra["tags"] = _kw
    except Exception as exc:
        logger.warning("[collect %s] 키워드 서버 생성 실패: %s", _corr, exc)

    # v87-W1 유입 봉인: 저장 시점에 비상품 판별기를 통과시킨다. 후보면 사유를 extra에 남기고
    #   응답에 경고를 실어 준다 — 저장 자체는 허용(오탐으로 실상품을 거부하지 않는다).
    _hygiene = {"is_candidate": False, "score": 0, "reasons": []}
    try:
        from src.seller_console.collect_hygiene import classify_row as _classify_hygiene
        _hygiene = _classify_hygiene({
            "url": url, "price": payload.get("price", ""),
            "image_url": images[0] if images else payload.get("image", ""),
            "extra": _extra,
        })
        if _hygiene.get("is_candidate"):
            _extra["hygiene"] = _hygiene
    except Exception as _he:
        logger.warning("[collect %s] 유입 봉인 판별 실패: %s", _corr, _he)

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
            currency=payload.get("currency") or "",   # v42 1-1: USD 기본값 금지(통화 미상은 빈 값)
            status="ok",
            extra=_extra,
            seller_id=seller_id_val,
        )
        # return_durable=True면 (item_id, durable) 튜플. 단, 일부 테스트가 append를 단일값으로
        # 모킹하므로 두 형태 모두 허용(모킹은 영속으로 간주).
        if isinstance(_ret, tuple) and len(_ret) == 2:
            item_id, durable = _ret
        else:
            item_id, durable = _ret, True
        logger.info("[collect %s] 저장 시도 seller_id=%r item_id=%s", _corr, seller_id_val, item_id)
        # v41 STEP 1-0: '수집 완료 = 재조회로 목록에 실제 보임'까지. 브라우저 목록은 관용 식별자
        #   (user_id+email)로 조회하므로, 자기검증도 같은 식별자 집합으로 재읽기해 '보이는지' 확인.
        #   (토큰 seller_id와 세션 email이 어긋나면 저장은 됐는데 목록에 안 뜨던 스코프 불일치 방지.)
        verify_ids = {seller_id_val}
        try:
            from src.auth.user_store import get_store as _get_user_store
            _u = _get_user_store().find_by_id(seller_id_val)
            if _u is not None and getattr(_u, "email", ""):
                verify_ids.add(str(_u.email))
        except Exception:
            pass
        saved = False
        try:
            from src.seller_console.collect_history_store import existing_ids as _existing_ids
            saved = str(item_id) in _existing_ids([item_id], seller_ids=verify_ids)
        except Exception:
            saved = False
        if not saved:
            # 폴백: 정확 seller_id 재조회(existing_ids는 관용집합의 상위집합이라 실사용선 동치;
            #        여기 폴백은 append/get을 모킹한 테스트 등 특수 경로 호환).
            try:
                saved = history_get(item_id, seller_id=seller_id_val) is not None
            except Exception:
                saved = bool(item_id)
        logger.info("[collect %s] 저장 자기검증(목록 스코프 재읽기) saved=%s durable=%s ids=%r",
                    _corr, saved, durable, sorted(verify_ids))
    except Exception as exc:
        # P0 진단: 전체 예외 스택을 남긴다(PG 예외·컬럼 불일치 등 원인 규명). corr-id로 grep.
        logger.exception("[collect %s] 수집 이력 기록 실패(스택): %s", _corr, exc)

    if not item_id or not saved or not durable:
        # 가짜 성공 금지(v4/v38 P0): 실제 저장 안 됐거나(saved=False) 영속 저장(PG 커밋)에 못 들어가면
        # 정직한 실패로 토스트가 사유·corr-id를 표시하고 재시도하게 한다(가짜 성공 절대 금지).
        logger.warning("[collect %s] 저장 검증 실패 → 502: url=%s seller_id=%r saved=%s durable=%s",
                       _corr, url[:80], seller_id_val, saved, durable)
        return jsonify({"ok": False,
                        "error": "수집 항목을 저장하지 못했습니다. 잠시 후 다시 시도하세요.",
                        "corr": _corr}), 502

    preview_url = f"/seller/collect/preview/{item_id}"

    # 텔레그램 알림
    msg = f"🛒 [확장] {title or url} 수집됨 (by {user.get('user_id', '?')})"
    _notify_telegram(msg)

    logger.info("확장 수집 완료: url=%s user=%s id=%s", url[:80], seller_id_val, item_id)

    # v47 STEP2: 필드 상태(성공/부분 + 누락 필드)를 응답에 담는다 → 토스트가 '수집 완료(N/7)' 또는
    #   '부분 수집 — 이미지·리뷰 누락'으로 정직 표기(가짜 성공처럼 안 보이게).
    #   partial은 하위호환(경량 북마클릿용): 핵심(가격·이미지) 둘 다 없을 때만 True(coarse).
    _partial = (not str(payload.get("price") or "").strip()) and not images
    return jsonify({
        "ok": True,
        "item_id": item_id,
        "product_id": product_id,
        "preview_url": preview_url,
        "title": title,
        "title_ko": title_ko,
        "partial": _partial,
        "field_status": _field_status,   # {status,filled,total,missing,...}
        # v87-W6: 폴백(openai-fallback/deepl-fallback)은 **실패=번역 안 됨**이다(원문 유지). 종전엔 fallback을
        #   translated=True로 보고해 '됐다는데 원문'인 체감 불일치를 만들었다 → 실제 번역된 경우만 True.
        "translated": str(tr.get("provider") or "none") in ("mymemory", "openai", "deepl") and not tr.get("translate_error"),
        "translate_error": tr.get("translate_error", ""),
        "translation_provider": tr.get("provider", "none"),
        # v87-W1: 비상품 의심 경고(저장은 됨) — 확장/토스트가 '상품이 아닌 페이지 같아요' 안내.
        "hygiene_warning": (_hygiene if _hygiene.get("is_candidate") else None),
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


@extension_bp.post("/one")
def collect_one():
    """★ M1-1 — **모바일 단건 수집 엔드포인트**(iOS 단축어 · 텔레그램용).

    기존 진입점이 못 채우던 자리를 메운다(실측):
      · `/seller/collect/quick`·`/collect/share` = **로그인 세션** 필요 → 단축어·봇은 세션이 없다
      · `/api/v1/collect/bulk` = 토큰은 되지만 **비동기**(job_id 폴링) → 단축어는 한 번의 답을 원한다
      · `/api/v1/collect/extension` = 확장이 만든 페이로드(제목·이미지·HTML) 전제
    그래서 여기는 **토큰 + 동기 + 단건**이다. 수집 자체는 벌크와 **같은 코어**(`collect_one_url`).

    입력: `url`(JSON body · form · 쿼리 어느 쪽이든 — 단축어가 만들기 쉬운 형태를 다 받는다)
    인증: `Authorization: Bearer <token>` (scope `collect.write`)
    """
    user = _require_token(scopes=["collect.write"])
    if not user:
        return jsonify({"ok": False, "error": auth_failure_reason()}), 401

    body = request.get_json(force=True, silent=True) or {}
    # C-F4: 단축어 가이드가 쓰라고 한 필드 이름을 **서버가 실제로 읽어야** 한다.
    #   `share_text`는 가이드의 정본 이름이다(공유 시트 입력 그대로). 나머지는 하위호환.
    raw = (body.get("share_text") or body.get("url") or request.form.get("share_text")
           or request.form.get("url") or request.args.get("url")
           or request.args.get("u") or "").strip()
    if not raw:
        raw = str(body.get("text") or body.get("title")
                  or request.form.get("text") or request.args.get("text") or "")
    # C-T1: `url` 칸에 **공유 텍스트 통째**가 오는 게 정상이다(타오바오 앱 공유 시트가 그 형태로만 준다).
    #   입력구마다 제 정규식을 두지 않는다 — 파서는 `share_text` 한 곳이다.
    # C-T2'': 폰 단축어가 「URL 확장」으로 이미 편 최종 URL을 함께 보낼 수 있다(중국망일 때만 성공).
    #   오면 id·가격까지 건지고, 안 오면 단축 링크와 제목만으로 간다 — 두 갈래 다 정직 표기.
    final_url = str(body.get("final_url") or body.get("expanded_url")
                    or request.form.get("final_url") or request.args.get("final_url") or "").strip()
    from src.collectors.share_text import parse_share_text
    share = parse_share_text(raw, final_url=final_url)
    url = share.get("url", "")
    if not url:
        from src.collectors.share_text import link_failure_reason
        return jsonify({"ok": False, "error": link_failure_reason(raw, final_url)}), 400

    seller_id = str(user.get("user_id") or "")
    # 중복 수집 방지 — 기존 정규화 키(v42 1-3)를 그대로 쓴다(새 규칙 만들지 않는다).
    try:
        from src.seller_console.collect_history_store import find_by_product_key
        dup = find_by_product_key(url, seller_ids={seller_id} if seller_id else None)
        if not dup and final_url:
            # C-F7: 폰이 편 링크로 왔을 때, **같은 상품의 단축 링크 초안**이 이미 있는지 본다.
            #   편 링크가 `short_name`에 단축 토큰을 싣고 오므로 그 키로 한 번 더 조회한다 —
            #   안 그러면 같은 상품이 `tbshare:…`와 `taobao:item:…` 두 행으로 쌓인다(실측).
            _sn = parse_share_text("", final_url=final_url).get("short_name", "")
            _tk2 = parse_share_text("", final_url=final_url).get("tk", "")
            if _sn:
                _alt = f"https://e.tb.cn/{_sn}" + (f"?tk={_tk2}" if _tk2 else "")
                dup = find_by_product_key(_alt, seller_ids={seller_id} if seller_id else None)
        if dup:
            return jsonify({"ok": True, "duplicate": True, "item_id": dup.get("id"),
                            "title": dup.get("title", ""),
                            "message": "이미 수집한 상품입니다."})
    except Exception as exc:                       # 중복 조회 실패가 수집을 막지 않게
        logger.warning("단건 수집 중복 조회 실패: %s", exc)

    # C-F1: 갈래 판단은 **한 곳**(`collect_input`)에서만 — 입구마다 제 나름대로 하면 갈라진다.
    from src.collectors.share_collect import collect_input
    res = collect_input(raw, seller_id=seller_id, source="mobile", final_url=final_url)
    if res.get("ok"):
        _partial = res.get("kind") == "share_draft"
        out = {"ok": True, "duplicate": False, "item_id": res.get("item_id"),
               "url": res.get("url", ""),
               "title": res.get("title_ko") or res.get("title") or "",
               "message": "수집됐습니다."}
        if _partial:
            # C-F9-1: 문구는 `gap_message` 한 곳에서만 만든다. 서버는 **자기가 본 것만** 말한다 —
            #   최종 URL이 왔는지·상품번호가 있었는지·가격이 있었는지. VPN 상태는 서버가 모른다
            #   (오너 실측: VPN 꺼진 채로 같은 결과 → 「전체 모드면…」 단정이 그대로 오진이 됐다).
            out.update({
                "partial": True, "price": res.get("price", ""), "currency": res.get("currency", ""),
                "item_id_taobao": res.get("item_id_taobao", ""),
                "uncollected": res.get("uncollected", []),
                "enrich_state": res.get("enrich_state", ""),
                "resolve_gap": res.get("resolve_gap", ""),
                "message": res.get("message") or "수집됐습니다.",
            })
            # 문구가 「링크 진단」을 가리키면 **거기로 가는 길도 준다** — 폰에서는 사이드바를 못 쓴다.
            #   가리키기만 하고 길이 없으면 그 문장은 안내가 아니라 막다른 골목이다.
            if res.get("resolve_gap") in ("no_final_url", "final_url_without_id"):
                out["diag_url"] = request.url_root.rstrip("/") + "/seller/collect/link-diag"
        if _wants_review():
            out["review"] = _review_verdict(res.get("url", ""))
        return jsonify(out)
    # 정직 실패 — 무엇이 왜 안 됐는지 그대로 올린다(가짜 성공 0).
    #   초안 폴백은 `collect_input` 안에 있다 — 여기서 또 하면 그게 두 벌째다.
    return jsonify({"ok": False, "duplicate": False, "url": res.get("url", ""),
                    "error": res.get("error") or "수집 실패",
                    "message": "수집하지 못했습니다. 봇 차단 사이트는 PC 확장을 권합니다."}), 502


def _wants_review() -> bool:
    """`review=1`(body·form·쿼리) — 수집만 할지, 검수 판정까지 받을지."""
    body = request.get_json(force=True, silent=True) or {}
    raw = (body.get("review") if isinstance(body, dict) else None)
    if raw is None:
        raw = request.form.get("review") or request.args.get("review")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _review_verdict(url: str) -> dict:
    """★ M1-2 — 수집한 URL을 **등록 파이프 검수표에 그대로 통과**시켜 판정만 뽑아 온다.

    폰에서 소싱할 때 필요한 건 '수집됨'이 아니라 **취급 가능한가 · 얼마에 팔리나**다.
    판정 로직은 콘솔 화면과 **같은 배선**(`build_review_for_urls`) — 여기서 새로 만들지 않는다.
    실패·취급제외도 사유와 함께 그대로 올린다(조용한 탈락 금지).
    """
    try:
        from src.seller_console.views import build_review_for_urls
        rv = build_review_for_urls([url], cap=1)
    except Exception as exc:
        logger.warning("모바일 검수 판정 실패(%s): %s", url[:60], exc)
        return {"ok": False, "error": f"검수 판정 실패: {str(exc)[:120]}"}

    if rv.get("failed"):
        return {"ok": False, "verdict": "수집 실패", "reason": rv["failed"][0].get("reason", "")}
    rows = (rv.get("review_pass") or []) + (rv.get("excluded") or [])
    if not rows:
        return {"ok": False, "error": "검수 행이 만들어지지 않았습니다."}
    r = rows[0]
    fd = r.get("forbidden_detail") or {}
    return {
        "ok": True,
        "verdict": "취급 제외" if r.get("excluded") else "검수 통과",
        "excluded": bool(r.get("excluded")),
        "reason": (f"{fd.get('kind_ko', '')} '{fd.get('term', '')}'".strip()
                   if r.get("excluded") else ""),
        "title_ko": r.get("title_ko", ""),
        "cost_krw": r.get("cost_krw"), "sale_krw": r.get("sale_krw"),
        "margin_pct": r.get("margin_pct"), "net_krw": r.get("net_krw"),
        "ship_status": r.get("ship_status", ""), "ship_reason": r.get("ship_reason", ""),
        "warnings": [w.get("label", "") for w in (r.get("warnings") or [])],
    }


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


def _dispatcher_collect():
    """URL → 수집 결과. 디스패처 우선, 없으면 범용 스크래퍼(기존 폴백 그대로)."""
    try:
        from src.collectors.dispatcher import collect as fn
        return fn
    except ImportError:
        from src.collectors.universal_scraper import UniversalScraper
        return UniversalScraper().fetch


def collect_one_url(url: str, *, seller_id: str = "", source: str = "bulk") -> dict:
    """URL 1건 수집 → 이력 저장. **벌크와 단건(M1-1)이 공유하는 단일 코어**.

    반환 {url, ok, item_id?, title?, error?}. 영속 저장(durable)이 확인될 때만 ok=True —
    가짜 성공 금지(v38 P0). 이 함수를 두 번 만들지 않는다: 벌크 안에 갇혀 있던 내부 함수를
    끌어올린 것이고, 모바일 단건 엔드포인트가 같은 것을 부른다(이중 구현 금지).
    """
    # C-F8: 코어에서 멈춘다(호출부마다 두면 입구가 늘 때마다 샌다 — 실측 6곳 중 2곳만 서 있었다).
    from src.collectors.share_text import is_short_link as _is_short
    from src.collectors.share_text import is_taobao_family as _is_tb
    if _is_tb(url):
        # C-F11: **단축 링크는 예외다 — 서버가 펼 수 있다**(오너 실측 2026-09-12).
        #   맨 단축 URL만 온 경우(확장 벌크·텔레그램)도 초안이 서게 같은 자리로 보낸다.
        #   상세 페이지(item/m.intl)는 여전히 로그인 벽이라 가드가 그대로 막는다.
        if _is_short(url):
            from src.collectors.share_collect import collect_from_share_text
            r = collect_from_share_text(url, seller_id=seller_id, source=source)
            if r.get("ok"):
                return {"url": r.get("url", url), "ok": True, "item_id": r.get("item_id"),
                        "title": r.get("title_ko") or r.get("title", ""),
                        "partial": True, "message": r.get("message", "")}
            return {"url": url, "ok": False, "error": r.get("error") or "수집 실패"}
        logger.info("수집 코어: 타오바오 상세는 서버에서 못 읽는다 — 요청 생략 (%s)", url[:80])
        return {"url": url, "ok": False,
                "error": ("타오바오 상품 페이지는 서버에서 열 수 없어요(로그인 벽). "
                          "앱 공유 글을 통째로 보내시면 제목으로 초안을 만듭니다.")}

    try:
        result = _dispatcher_collect()(url)
        title = getattr(result, "title", "") or ""
        images = list(getattr(result, "images", []) or [])
        price = str(getattr(result, "price", "") or "")
        currency = getattr(result, "currency", "USD")
        # C-F1 회귀 수리: **정본 가격 단일 소스(v72b)를 여기서 건다.**
        #   전엔 벌크 라우트만 `_canon_price`를 불렀다 — 단건·모바일·텔레그램은 안 걸렸다는 뜻이다.
        #   네 입구를 이 코어로 합치면서 벌크가 그걸 잃을 뻔했고(계약이 잡았다), 되살리는 김에
        #   **코어에 둔다** — 그래야 네 입구가 다 같은 보증을 받는다(한 곳에 두는 이유가 이거다).
        try:
            from src.collectors.collect_sanitize import canonical_price as _cp
            price = _cp(price, str(getattr(result, "price_original", "") or "")) or price
        except Exception as _pexc:
            logger.debug("정본 가격 정규화 스킵: %s", _pexc)
        _upsert_catalog(
            {"url": url, "title": title, "price": price, "currency": currency,
             "image": images[0] if images else ""},
            source=f"{source}_collect",
        )
        # v38 P0: 이력에 실제 저장(이전엔 catalog만 써서 수집품목에 안 보였음).
        from src.seller_console.collect_history_store import append as history_append
        _ret = history_append(
            return_durable=True, source=source, url=url, title=title,
            image=images[0] if images else "", price=price, currency=currency,
            status="ok", seller_id=str(seller_id or ""),
            extra={"title": title, "title_ko": title, "images": images,
                   "price": price, "currency": currency},
        )
        item_id, durable = _ret if (isinstance(_ret, tuple) and len(_ret) == 2) else (_ret, True)
        if not item_id or not durable:
            return {"url": url, "ok": False, "error": "저장 영속화 실패(재시도 필요)"}
        return {"url": url, "ok": True, "item_id": item_id, "title": title}
    except Exception as exc:
        logger.warning("URL 수집 실패(%s): %s — %s", source, url[:60], exc)
        return {"url": url, "ok": False, "error": str(exc)[:100]}


def _run_bulk_job(job_id: str, urls: list) -> None:
    """벌크 수집 백그라운드 실행 (스레드 풀)."""
    job = _bulk_jobs.get(job_id)
    if not job:
        return

    seller_id_val = str(job.get("user_id") or "")

    def process_url(url: str) -> dict:
        return collect_one_url(url, seller_id=seller_id_val, source="bulk")

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
