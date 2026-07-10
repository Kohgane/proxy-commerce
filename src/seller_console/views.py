"""src/seller_console/views.py — 셀러 콘솔 Flask Blueprint (Phase 127).

라우트:
  GET  /seller/              → 메인 대시보드
  GET  /seller/dashboard     → 메인 대시보드
  GET  /seller/collect       → 수동 수집기 페이지
  POST /seller/collect/preview → URL → 메타데이터 추출 결과 (JSON)
  POST /seller/collect/upload  → 마켓 업로드 트리거 (JSON)
  GET  /seller/pricing       → 마진 계산기
  POST /seller/pricing/calc  → 단일 마켓 마진 계산 (JSON)
  POST /seller/pricing/compare → 여러 마켓 비교 계산 (JSON)
  GET  /seller/market-status → 마켓 현황 (기존, 리다이렉트)
  GET  /seller/markets       → 마켓 현황 상세 페이지 (Phase 127)
  GET  /seller/markets/status → JSON: 모든 마켓 상태 (Phase 127)
  POST /seller/markets/sync  → 라이브 동기화 트리거 (Phase 127)
  GET  /seller/health        → 셀러 콘솔 헬스체크
  POST /api/v1/pricing/calculate → 공개 API (인증 stub)

인증: 현재 stub 미들웨어만 (다음 PR에서 Phase 24 OAuth 연결 예정).
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
import hashlib
from typing import Any, Dict, Optional
from difflib import SequenceMatcher

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from urllib.parse import quote_plus

from flask import Blueprint, abort, jsonify, redirect, render_template, render_template_string, request, session, url_for, Response
from src.utils.branding import get_brand_name, get_brand_name_ko

logger = logging.getLogger(__name__)
_CS_FAQ_SUPPORTED_LOCALES = {"ko", "ja", "en", "zh"}

# Blueprint 정의
bp = Blueprint(
    "seller_console",
    __name__,
    url_prefix="/seller",
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)

# ---------------------------------------------------------------------------
# 인증 stub — Phase 24 OAuth 연결 전까지 환경변수로 제어
# ---------------------------------------------------------------------------
# 기본 ON — 소비자별 로그인/개인화(수집·마켓·소싱처 격리). 끄려면 SELLER_CONSOLE_AUTH=0.
_AUTH_ENABLED = os.getenv("SELLER_CONSOLE_AUTH", "1") == "1"
_ONBOARDING_DISMISS_COOKIE = "seller_onboarding_dismissed"
_ONBOARDING_DISMISS_COOKIE_MAX_AGE = 60 * 60 * 24 * 180


@bp.app_context_processor
def inject_seller_template_flags():
    # v15 i18n: kgp_lang 쿠키(ko|en) 기반 현지화. t('key')로 템플릿에서 사용(영어 1급).
    from .i18n import normalize_lang, t as _t
    try:
        _lang = normalize_lang(request.cookies.get("kgp_lang"))
    except Exception:
        _lang = "ko"
    # v34: 개인화 헤더용 내 플랜(로그인 시에만, 경량 — 인메모리/시트 1회 조회)
    _plan = None
    try:
        if session.get("user_id") or session.get("user_email"):
            from . import billing_store
            _plan = (billing_store.get_account(_seller_id()) or {}).get("plan", "free")
    except Exception:
        _plan = None
    return {
        "diagnostic_reveal_enabled": os.getenv("DIAGNOSTIC_REVEAL", "0") == "1",
        "sidebar_grouped": os.getenv("SIDEBAR_GROUPED", "1") == "1",
        "brand_name": get_brand_name(),
        "brand_name_ko": get_brand_name_ko(),
        "current_lang": _lang,
        "t": (lambda key, lang=_lang: _t(key, lang)),
        "account_plan": _plan,
        "_auth_enabled": _AUTH_ENABLED,
        # True when the full console sidebar should be rendered:
        # • always when auth is OFF (dev/test mode — matches pre-existing behaviour)
        # • when auth is ON and a user session exists
        "_show_console_nav": (not _AUTH_ENABLED) or bool(
            session.get("user_id") or session.get("user_email")
        ),
    }


def _render_seller_page(title: str, body: str, page: str = "dashboard") -> str:
    from markupsafe import Markup

    return render_template_string(
        """
{% extends "_base.html" %}
{% block title %}{{ title }}{% endblock %}
{% block content %}{{ body }}{% endblock %}
        """,
        title=title,
        body=Markup(body),
        page=page,
    )


def _check_auth() -> bool:
    """인증 확인. SELLER_CONSOLE_AUTH=1 이면 실제 로그인 세션을 요구한다.

    로그인 시스템(src.auth)이 세션에 user_id/user_email 을 채운다.
    미설정(기본)일 때는 단일 테넌트(오너) 모드로 항상 통과한다.
    """
    if not _AUTH_ENABLED:
        return True
    try:
        return bool(session.get("user_id") or session.get("user_email"))
    except Exception:
        return False


def _current_user_id() -> str | None:
    """현재 세션의 user_id(또는 user_email)를 반환한다. 없으면 None.

    _check_auth() 통과 후에 호출할 것 — 인증 게이트가 먼저 실행되므로
    이 함수가 반환하는 None은 실제로 인증되지 않은 요청에서만 발생한다.
    """
    try:
        return session.get("user_id") or session.get("user_email") or None
    except Exception:
        return None


def _cs_role_allowed() -> bool:
    role = (session.get("user_role") or "").strip().lower()
    if role and role not in {"admin", "seller"}:
        return False
    if not _AUTH_ENABLED:
        return True
    return role in {"admin", "seller"}


def _infer_customer_identity(msg) -> dict[str, str]:
    if not msg:
        return {}
    raw = f"{msg.customer_id or ''} {msg.body or ''}"[:1000]
    email_match = re.search(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}", raw)
    phone_match = re.search(r"\+?\d[\d\-\s]{7,20}\d", raw)
    return {
        "name": msg.customer_name or "",
        "email": email_match.group(0) if email_match else "",
        "phone": re.sub(r"[\s\-]", "", phone_match.group(0)) if phone_match else "",
    }


def _find_cross_channel_messages(messages: list, identity: dict[str, str]) -> list:
    if not identity:
        return []
    out = []
    for row in messages:
        if not row:
            continue
        if identity.get("name") and row.customer_name == identity["name"]:
            out.append(row.channel)
            continue
        raw = f"{row.customer_id or ''} {row.body or ''}"
        if identity.get("email") and identity["email"] in raw:
            out.append(row.channel)
            continue
        if identity.get("phone") and identity["phone"] in re.sub(r"[\s\-]", "", raw):
            out.append(row.channel)
    uniq = []
    for ch in out:
        if ch not in uniq:
            uniq.append(ch)
    return uniq


# ---------------------------------------------------------------------------
# 헬퍼 — graceful import
# ---------------------------------------------------------------------------

def _get_widgets(seller_id=None, seller_ids=None) -> list:
    """위젯 데이터 목록 조회 (graceful import). seller_id/식별자집합으로 KPI 셀러 격리."""
    try:
        from .widgets import build_all_widgets
        return build_all_widgets(seller_id, seller_ids)
    except Exception as exc:
        logger.warning("위젯 로드 실패: %s", exc)
        return []


def _draft_is_meaningful(draft: Optional[dict]) -> bool:
    """수집 결과가 실데이터로 쓸 만한지 판단.

    제목·가격·이미지 중 하나라도 실제로 있으면 True (목업 폴백 방지용).
    """
    if not draft:
        return False
    title = (draft.get("title") or draft.get("title_en") or draft.get("title_ko") or "")
    if title and str(title).strip():
        return True
    if draft.get("price") or draft.get("price_original"):
        return True
    if draft.get("images"):
        return True
    return False


def _scraped_to_draft(scraped) -> dict:
    """UniversalScraper.ScrapedProduct → collect_preview draft 형식으로 변환."""
    options = []
    for opt in (getattr(scraped, "options", None) or []):
        if not isinstance(opt, dict):
            continue
        name = (opt.get("name") or "").strip()
        if not name:
            continue
        if isinstance(opt.get("values"), list):
            values = [str(v) for v in opt["values"] if v]
        elif opt.get("value"):
            values = [str(opt["value"])]
        else:
            values = []
        options.append({"name": name, "values": values})

    title = scraped.title or ""
    method = scraped.extraction_method or "heuristic"
    return {
        "url": scraped.source_url,
        "source": f"universal_{method}",
        "title": title,
        "title_en": title,
        "title_ko": title,
        "description": scraped.description or "",
        "images": list(scraped.images or []),
        "price": str(scraped.price) if scraped.price is not None else None,
        "price_original": float(scraped.price) if scraped.price is not None else 0.0,
        "currency": scraped.currency or "USD",
        "brand": scraped.brand or "",
        "sku": scraped.sku or "",
        "category": "",
        "options": options,
        "in_stock": scraped.in_stock,
        "confidence": scraped.confidence,
        "extraction_method": method,
        "is_mock": False,
        "adapter_used": "universal_scraper",
    }


def _translate_draft(draft: dict) -> dict:
    """수집 draft에 한국어 번역(title_ko/description_ko)·마켓 카피를 채운다.

    번역 키(OPENAI/DEEPL) 미설정·실패 시 원문 유지(목업 생성 안 함).
    """
    title = (draft.get("title") or draft.get("title_en") or "").strip()
    description = (draft.get("description") or "").strip()
    if not title and not description:
        return draft
    try:
        from .ai.translator import AITranslator

        tr = AITranslator().translate_product({"title": title, "description": description})
        provider = tr.get("provider", "stub")
        draft["title_ko"] = (tr.get("title_ko") or "").strip() or title
        draft["description_ko"] = (tr.get("description_ko") or "").strip() or description
        draft["translation_provider"] = provider
        # 실 번역기일 때만 마켓 카피 노출 (stub/fallback의 더미 카피는 숨김)
        if provider not in ("stub", "openai-fallback", "deepl-fallback"):
            draft["marketplace_copy"] = {
                "coupang": tr.get("copy_coupang"),
                "smartstore": tr.get("copy_smartstore"),
                "11st": tr.get("copy_11st"),
            }
    except Exception as exc:
        logger.warning("번역 실패, 원문 유지: %s", exc)
        draft.setdefault("title_ko", title)
        draft.setdefault("translation_provider", "none")
    return draft


def _collect_real_draft(url: str, translate: bool = True) -> Optional[dict]:
    """실 수집 파이프라인 (Phase 200 — 목업 제거).

    1) 도메인별 dispatcher (Amazon/Rakuten/Alo/Lululemon/OG·JSON-LD)
    2) 범용 스크래퍼 (JSON-LD/OG/Microdata/Heuristic + 옵션·색상)
    3) (옵션) 한국어 번역

    실데이터를 못 얻으면 None 반환 — 호출부에서 정직한 에러로 처리(목업 금지).
    """
    draft: Optional[dict] = None
    source: Optional[str] = None
    warnings: list = []

    # 1) 도메인 dispatcher
    try:
        from src.seller_console.collectors.dispatcher import collect as dispatcher_collect

        result = dispatcher_collect(url)
        if result.success:
            cand = result.to_dict()
            cand.update({
                "title_en": result.title or "",
                "title_ko": result.title or "",
                "price_original": float(result.price) if result.price else 0.0,
                "is_mock": False,
                "adapter_used": result.source,
            })
            if _draft_is_meaningful(cand):
                draft = cand
                source = result.source
                warnings = list(result.warnings or [])
    except Exception as exc:
        logger.debug("dispatcher 수집 실패: %s", exc)

    # 2) 범용 스크래퍼 폴백
    if draft is None:
        try:
            from src.collectors.universal_scraper import UniversalScraper

            scraped = UniversalScraper().fetch(url)
            cand = _scraped_to_draft(scraped)
            if _draft_is_meaningful(cand):
                draft = cand
                source = cand["source"]
                if scraped.confidence < 0.5:
                    warnings.append("자동 추출 신뢰도가 낮습니다. 제목·가격·이미지를 확인·수정하세요.")
        except Exception as exc:
            logger.debug("universal_scraper 수집 실패: %s", exc)

    if draft is None:
        return None

    draft["source"] = source or draft.get("source") or "unknown"
    draft["warnings"] = warnings
    draft.setdefault("title_ko", draft.get("title") or draft.get("title_en") or "")
    if translate:
        draft = _translate_draft(draft)
    # v39 D: 소스 미치환 플레이스홀더 토큰({REGION_NAME...} 등)을 사용자 노출 필드에서 제거(가짜값 금지).
    try:
        from src.collectors.universal_scraper import strip_placeholder_tokens as _strip_ph
        for _k in ("title", "title_en", "title_ko", "description", "description_ko"):
            if draft.get(_k):
                draft[_k] = _strip_ph(draft[_k])
    except Exception:
        pass
    return draft


def _get_upload_dispatcher():
    """UploadDispatcher 인스턴스 반환 (graceful import)."""
    try:
        from .upload_dispatcher import UploadDispatcher
        return UploadDispatcher()
    except Exception as exc:
        logger.warning("UploadDispatcher 로드 실패: %s", exc)
        return None


_KEYWORD_PERIOD_FACTORS: dict[str, float] = {
    "realtime": 1 / 720,  # 30일 기준 월간검색량을 시간 단위로 환산
    "day": 1 / 30,
    "week": 7 / 30,
    "month": 1.0,
    "year": 12.0,
}
_KEYWORD_PERIOD_LABELS: dict[str, str] = {
    "realtime": "실시간",
    "day": "일",
    "week": "주",
    "month": "월",
    "year": "년",
}


def _is_admin_user() -> bool:
    try:
        from src.auth.admin_resolver import is_admin_session
        admin_ok, _ = is_admin_session(session)
        return bool(admin_ok)
    except Exception:
        return (session.get("user_role") or "").strip().lower() == "admin"


def _normalize_keyword_period(raw_period: str | None) -> str:
    period = (raw_period or "day").strip().lower()
    return period if period in _KEYWORD_PERIOD_FACTORS else "day"


def _parse_keywords(raw: str | None) -> list[str]:
    keywords = []
    for chunk in (raw or "").replace("\n", ",").split(","):
        kw = chunk.strip()
        if kw and kw not in keywords:
            keywords.append(kw)
    return keywords[:10]


def _stable_ratio(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _build_trend_series(seed: str, base_value: int) -> list[int]:
    points = []
    current = max(base_value, 1)
    for idx in range(8):
        ratio = _stable_ratio(f"{seed}:{idx}")
        drift = (ratio - 0.5) * 0.18
        current = max(1, int(round(current * (1 + drift))))
        points.append(current)
    if points:
        points[-1] = max(base_value, 1)
    return points


def _scale_volume_for_period(monthly_search: int, period: str) -> int:
    factor = _KEYWORD_PERIOD_FACTORS.get(period, _KEYWORD_PERIOD_FACTORS["day"])
    return max(1, int(round(max(monthly_search, 1) * factor)))


def _build_keyword_trend_context(query_keywords: list[str], period: str) -> dict[str, Any]:
    from src.ads.keyword_optimizer import get_keyword_metrics, keyword_optimizer_stats

    default_keywords = ["해외직구", "일본직구", "유니클로", "에코백", "플리스 자켓"]
    keywords = query_keywords or default_keywords
    period = _normalize_keyword_period(period)
    metrics = get_keyword_metrics(keywords)
    stats = keyword_optimizer_stats()

    rows: list[dict[str, Any]] = []
    for metric in metrics:
        base_volume = _scale_volume_for_period(metric.monthly_search, period)
        trend_seed = f"{metric.keyword}:{period}"
        drift = (_stable_ratio(trend_seed) - 0.5) * 0.32
        prev_volume = max(1, int(round(base_volume / (1 + drift))))
        trend_pct = ((base_volume - prev_volume) / prev_volume) * 100 if prev_volume else 0.0
        product_count = max(1, int(round(base_volume * (1.6 + metric.competition * 1.8))))
        rows.append(
            {
                "keyword": metric.keyword,
                "search_volume": base_volume,
                "competition": round(metric.competition, 2),
                "product_count": product_count,
                "avg_cpc_krw": int(round(metric.avg_cpc_krw)),
                "trend_pct": round(trend_pct, 1),
                "trend_direction": "up" if trend_pct > 0 else ("down" if trend_pct < 0 else "flat"),
                "series": _build_trend_series(trend_seed, base_volume),
            }
        )

    rows.sort(key=lambda x: x["search_volume"], reverse=True)
    risers = sorted(rows, key=lambda x: x["trend_pct"], reverse=True)[:5]
    top_keywords = [row["keyword"] for row in rows]

    related_keywords: list[str] = []
    for kw in top_keywords[:4]:
        related_keywords.extend(
            [
                f"{kw} 추천",
                f"{kw} 인기",
                f"{kw} 후기",
            ]
        )
    related_keywords = [kw for kw in related_keywords if kw not in top_keywords][:8]

    long_tail_keywords: list[str] = []
    for kw in top_keywords[:4]:
        long_tail_keywords.extend(
            [
                f"{kw} 가성비",
                f"{kw} 직구 방법",
                f"{kw} 정품 비교",
            ]
        )
    long_tail_keywords = [kw for kw in long_tail_keywords if kw not in top_keywords][:8]

    provider = (stats.get("provider") or "mock").lower()
    naver_key = (os.getenv("NAVER_SEARCHAD_API_KEY") or "").strip()
    naver_secret = (
        os.getenv("NAVER_SEARCHAD_API_SECRET")
        or os.getenv("NAVER_SEARCHAD_SECRET")
        or ""
    ).strip()
    mock_timeseries_active = (
        provider == "mock"
        or provider == "coupang_ads"
        or (provider == "naver_searchad" and (not naver_key or not naver_secret))
    )
    return {
        "period": period,
        "period_label": _KEYWORD_PERIOD_LABELS.get(period, "일"),
        "period_options": _KEYWORD_PERIOD_LABELS,
        "query_keywords": keywords,
        "query_text": ", ".join(keywords),
        "rows": rows,
        "risers": risers,
        "related_keywords": related_keywords,
        "long_tail_keywords": long_tail_keywords,
        "provider": provider,
        "fallback_active": mock_timeseries_active,
    }


def _sourcing_search_links(query: str) -> "list[dict[str, str]]":
    """국내 상품명/키워드를 소싱처(타오바오/1688/알리/테무/아마존)에서 바로 검색하는 딥링크.

    실제 검색 URL로 연결한다(가짜 상품 카드 날조 금지). 사용자가 그 사이트에서
    크롬 확장 '고가수집기'로 바로 수집할 수 있다.
    """
    q = quote_plus((query or "").strip())
    if not q:
        return []
    # v34: 단일 버튼 마켓만(아마존은 국가 선택이라 템플릿 드롭다운). 이모지 0.
    return [
        {"name": "타오바오", "url": f"https://s.taobao.com/search?q={q}"},
        {"name": "1688", "url": f"https://s.1688.com/selloffer/offer_search.htm?keywords={q}"},
        {"name": "알리익스프레스", "url": f"https://www.aliexpress.com/wholesale?SearchText={q}"},
        {"name": "테무", "url": f"https://www.temu.com/search_result.html?search_key={q}"},
    ]


# v34 P1: 아마존 국가별 검색 도메인(주요국부터) — 소싱 카드 '아마존에서 검색' 드롭다운.
_AMAZON_SEARCH_COUNTRIES = [
    {"name": "미국", "tld": "com", "currency": "USD"},
    {"name": "일본", "tld": "co.jp", "currency": "JPY"},
    {"name": "영국", "tld": "co.uk", "currency": "GBP"},
    {"name": "독일", "tld": "de", "currency": "EUR"},
    {"name": "프랑스", "tld": "fr", "currency": "EUR"},
    {"name": "캐나다", "tld": "ca", "currency": "CAD"},
    {"name": "호주", "tld": "com.au", "currency": "AUD"},
    {"name": "싱가포르", "tld": "sg", "currency": "SGD"},
    {"name": "멕시코", "tld": "com.mx", "currency": "MXN"},
    {"name": "인도", "tld": "in", "currency": "INR"},
]


def _build_sourcing_analysis(domestic_products: "list[dict[str, Any]]",
                             keyword_context: "dict[str, Any] | None",
                             keyword: str,
                             domestic_total: "int | None" = None) -> "dict[str, Any]":
    """소싱 분석 패널 — 계산 가능한 것만 실데이터, 불가하면 None('데이터 없음').

    날조 금지: 해외직구 비율·리뷰 지수 등 우리가 계산 못 하는 지표는 None으로 두고
    템플릿이 '데이터 없음'으로 표시한다. domestic_total = 네이버 '검색' API 전국 결과 수(실데이터).
    """
    metrics: "list[dict[str, Any]]" = []
    products = domestic_products or []
    prices = [p["price"] for p in products if isinstance(p.get("price"), int) and p["price"] > 0]

    # 전국 검색 결과 수(네이버 쇼핑 '검색' API total — 시장 규모/노출량 실데이터)
    metrics.append({"label": "국내 검색 결과 수",
                    "value": (f"{domestic_total:,}개" if isinstance(domestic_total, int) and domestic_total > 0 else None),
                    "note": "네이버 쇼핑 전국 검색"})
    # 국내 판매 상품 수(이번 조회 표본)
    metrics.append({"label": "국내 판매 상품 수", "value": (f"{len(products)}개" if products else None),
                    "note": "네이버 쇼핑 검색 결과"})
    # 최저가 / 평균가(실데이터 계산)
    metrics.append({"label": "국내 최저가", "value": (f"₩{min(prices):,}" if prices else None), "note": "검색 결과 기준"})
    metrics.append({"label": "국내 평균가", "value": (f"₩{round(sum(prices) / len(prices)):,}" if prices else None), "note": "검색 결과 기준"})
    # 판매처(쇼핑몰) 수 — 검색 결과의 고유 몰 수 = 경쟁 강도 실데이터 신호
    _malls = {(p.get("mall") or "").strip() for p in products if (p.get("mall") or "").strip()}
    metrics.append({"label": "판매처(쇼핑몰) 수", "value": (f"{len(_malls)}곳" if _malls else None),
                    "note": "검색 결과 기준"})

    # 검색 관심도·경쟁도(네이버 검색광고 실데이터 — 있을 때만)
    kw_lower = (keyword or "").strip().lower()
    riser = None
    for row in ((keyword_context or {}).get("risers") or []):
        if kw_lower and str(row.get("keyword", "")).strip().lower() == kw_lower:
            riser = row
            break
    if riser is None:
        risers = (keyword_context or {}).get("risers") or []
        riser = risers[0] if risers else None
    metrics.append({"label": "검색 관심도(검색량)",
                    "value": (f"{riser['search_volume']:,}" if riser and riser.get("search_volume") is not None else None),
                    "note": "네이버 검색광고"})
    metrics.append({"label": "경쟁도",
                    "value": (f"{riser['competition']:.2f}" if riser and riser.get("competition") is not None else None),
                    "note": "0=낮음·1=높음"})

    # 우리가 계산 못 하는 지표(날조 금지 → 데이터 없음)
    for label in ("해외직구 비율", "리뷰 지수", "실구매 리뷰"):
        metrics.append({"label": label, "value": None, "note": "데이터 연동 전"})

    return {"metrics": metrics, "has_any": any(m["value"] is not None for m in metrics)}


def _build_sourcing_recommendations(
    *,
    keyword: str,
    keyword_context: "dict[str, Any] | None" = None,
    discovery_candidates: "list[dict[str, Any]] | None" = None,
    queue_candidates: "list[Any] | None" = None,
) -> list[dict[str, Any]]:
    keyword_context = keyword_context or {}
    discovery_candidates = discovery_candidates or []
    queue_candidates = queue_candidates or []
    recommendations: list[dict[str, Any]] = []
    keyword_lower = (keyword or "").strip().lower()

    for row in keyword_context.get("risers", [])[:3]:
        kw = row["keyword"]
        recommendations.append(
            {
                "title": kw,
                "source": "키워드 트렌드",
                "reason": f"{keyword_context.get('period_label')} 기준 검색량 {row['search_volume']:,} · 추세 {row['trend_pct']:+.1f}%",
                "margin_hint": f"예상 CPC {row['avg_cpc_krw']:,}원 · 경쟁도 {row['competition']:.2f}",
                "cta_href": f"/seller/sourcing/watches?keyword={quote_plus(kw)}",
                "cta_label": "이 키워드로 소싱",
                "secondary_href": f"/seller/keywords?q={quote_plus(kw)}&period={keyword_context.get('period', 'day')}",
                "secondary_label": "트렌드 보기",
            }
        )

    for item in queue_candidates[:5]:
        name = str(getattr(item, "product_name", "") or "")
        if keyword_lower and keyword_lower not in name.lower():
            continue
        margin = float(getattr(item, "estimated_margin_pct", 0.0) or 0.0)
        recommendations.append(
            {
                "title": name or "후보 상품",
                "source": "후보 큐",
                "reason": f"기존 소싱 후보({getattr(item, 'status', 'pending')})로 즉시 승인/등록 가능",
                "margin_hint": f"예상 마진 {margin:.1f}% · 출처 {getattr(item, 'platform', '-')}",
                "cta_href": f"/seller/sourcing/candidates?status={quote_plus(str(getattr(item, 'status', 'pending')))}",
                "cta_label": "후보 큐에서 처리",
                "secondary_href": getattr(item, "product_url", "") or "/seller/sourcing/candidates",
                "secondary_label": "원본 보기",
            }
        )

    for cand in discovery_candidates[:6]:
        domain = (cand.get("domain") or "").strip()
        if not domain:
            continue
        if keyword_lower and keyword_lower not in (cand.get("keyword", "") or "").lower():
            continue
        status = (cand.get("status") or "pending").strip()
        recommendations.append(
            {
                "title": domain,
                "source": "Discovery",
                "reason": f"신규 도메인 후보({status}) · 키워드: {cand.get('keyword') or '-'}",
                "margin_hint": "마진 계산기와 후보 큐에서 후속 검토 권장",
                "cta_href": f"/seller/collect?url={quote_plus(f'https://{domain}')}",
                "cta_label": "원클릭 수집",
                "secondary_href": "/seller/discovery",
                "secondary_label": "Discovery 관리",
            }
        )

    # 중복 제거(제목 기준) + 최대 12개
    unique: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for rec in recommendations:
        title = rec.get("title") or ""
        if title in seen_titles:
            continue
        seen_titles.add(title)
        unique.append(rec)
        if len(unique) >= 12:
            break
    return unique


def _register_discovery_candidate_from_collection(url: str, keyword_hint: str = "") -> None:
    try:
        from src.discovery.scout import register_collected_domain_candidate
        register_collected_domain_candidate(
            url,
            keyword=keyword_hint,
            source="manual_collect",
        )
    except Exception as exc:
        logger.debug("Discovery 자동 후보 등록 스킵: %s", exc)


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------

def _build_dashboard_home_context(widgets: list[dict[str, Any]], dismissed: bool = False) -> dict[str, Any]:
    """통합 대시보드 홈 렌더링에 필요한 안전한 컨텍스트를 구성한다."""
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _to_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _trend(delta: Any) -> dict[str, str]:
        amount = _to_float(delta)
        if amount is None:
            return {"label": "전일 대비 데이터 없음", "direction": "neutral", "icon": "bi-dash"}
        if amount > 0:
            return {"label": f"전일 대비 +{amount:g}", "direction": "up", "icon": "bi-arrow-up-right"}
        if amount < 0:
            return {"label": f"전일 대비 {amount:g}", "direction": "down", "icon": "bi-arrow-down-right"}
        return {"label": "전일 대비 변동 없음", "direction": "neutral", "icon": "bi-arrow-left-right"}

    kpi_data = {}
    queue_data = {}
    market_data = {}
    fx_data = {}
    orders_data = {}
    alerts_data = {}
    for widget in widgets or []:
        widget_type = widget.get("type")
        data = widget.get("data") or {}
        if widget_type == "kpi":
            kpi_data = data
        elif widget_type == "queue":
            queue_data = data
        elif widget_type == "market_status":
            market_data = data
        elif widget_type == "fx":
            fx_data = data
        elif widget_type == "orders_kpi":
            orders_data = data
        elif widget_type == "alerts":
            alerts_data = data

    market_rows = market_data.get("markets") or []
    market_by_key: dict[str, dict[str, Any]] = {}
    for row in market_rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("market") or row.get("id") or row.get("code") or "").strip().lower()
        if key:
            market_by_key[key] = row

    market_name_map = {
        "coupang": "쿠팡",
        "smartstore": "스마트스토어",
        "woocommerce": "WooCommerce",
        "selfmall": "자체몰",
        "naver": "네이버",
    }
    preferred_market_keys = list(market_name_map.keys())
    extra_market_keys = [k for k in market_by_key.keys() if k not in preferred_market_keys]
    market_keys = preferred_market_keys + extra_market_keys

    low_stock = 0
    for row in market_by_key.values():
        try:
            low_stock += int(row.get("out_of_stock") or 0)
        except (TypeError, ValueError):
            continue

    recent_orders = orders_data.get("today_orders")
    if recent_orders is None:
        recent_orders = kpi_data.get("order_count", 0)

    summary_cards = [
        {
            "icon": "bi-bag-plus",
            "label": "오늘 수집 건수",
            "value": kpi_data.get("new_products_collected", 0),
            "trend": _trend(kpi_data.get("new_products_collected_delta")),
            "accent": "primary",
            "href": "/seller/collect-history",
        },
        {
            "icon": "bi-hourglass-split",
            "label": "등록 대기",
            "value": queue_data.get("pending", 0),
            "trend": _trend(queue_data.get("pending_delta")),
            "accent": "warning",
            "href": "/seller/catalog",
        },
        {
            "icon": "bi-exclamation-triangle",
            "label": "재고 부족",
            "value": low_stock,
            "trend": _trend(market_data.get("out_of_stock_delta")),
            "accent": "danger",
            "href": "/seller/catalog?stock=low",
        },
        {
            "icon": "bi-cart-check",
            "label": "오늘 주문 수",
            "value": recent_orders if recent_orders is not None else "—",
            "trend": _trend(orders_data.get("today_orders_delta")),
            "accent": "success",
            "href": "/seller/orders",
        },
    ]
    quick_actions = [
        {"label": "상품 수집하기", "href": "/seller/collect", "icon": "bi-search"},
        {"label": "마진 계산", "href": "/seller/pricing", "icon": "bi-calculator"},
        {"label": "마켓 동기화", "href": "/seller/markets", "icon": "bi-arrow-repeat"},
    ]

    market_connection_badges = []
    connected_count = 0
    for market_key in market_keys:
        row = market_by_key.get(market_key) or {}
        connected = bool(
            row.get("connected")
            or _to_int(row.get("total")) > 0
            or _to_int(row.get("active")) > 0
            or _to_int(row.get("total_registered")) > 0
        )
        if connected:
            connected_count += 1
        market_connection_badges.append(
            {
                "label": market_name_map.get(market_key) or str(row.get("label") or market_key.upper()),
                "connected": connected,
            }
        )
    disconnected_count = max(0, len(market_connection_badges) - connected_count)
    connection_banner = {
        "title": "마켓 연동 상태",
        "description": (
            f"{connected_count}개 연결됨 · {disconnected_count}개 미연결"
            if market_connection_badges
            else "연동 정보가 아직 없습니다."
        ),
        "tone": "success" if disconnected_count == 0 else "warning",
        "cta_label": "연동 관리" if disconnected_count == 0 else "지금 연동하기",
        "cta_href": "/seller/markets",
        "badges": market_connection_badges,
    }

    market_grid_rows = []
    for market_key in market_keys:
        row = market_by_key.get(market_key) or {}
        market_grid_rows.append(
            {
                "market": market_name_map.get(market_key) or str(row.get("label") or market_key.upper()),
                "today_registered": _to_int(
                    row.get("today_registered") or row.get("today_uploaded") or row.get("uploaded_today")
                ),
                "today_synced": _to_int(row.get("today_synced") or row.get("synced_today")),
                "total_registered": _to_int(row.get("total_registered") or row.get("total") or row.get("active")),
                "total_synced": _to_int(row.get("total_synced") or row.get("active")),
                "stock_alerts": _to_int(row.get("out_of_stock")) + _to_int(row.get("error")),
            }
        )

    source_count = 0
    try:
        from src.seller_console.my_sources_store import list_sources
        source_count = len(list_sources())
    except Exception as exc:
        logger.debug("온보딩 소싱처 수 조회 스킵: %s", exc)

    product_count = sum(max(0, _to_int(row.get("total_registered"))) for row in market_grid_rows)
    # v25 P1: 활성화 퍼널 첫 단계 = 상품 수집(실데이터). 본인 스코프로 집계.
    collected_count = 0
    try:
        from src.seller_console import collect_history_store as _chs
        collected_count = _to_int(_chs.summary(seller_ids=_seller_identities()).get("total"))
    except Exception as exc:
        logger.debug("온보딩 수집 수 조회 스킵: %s", exc)
    try:
        from src.seller_console.onboarding import compute_onboarding_state
        onboarding = compute_onboarding_state(
            connected_markets=connected_count,
            source_count=source_count,
            product_count=product_count,
            collected_count=collected_count,
            dismissed=dismissed,
        )
    except Exception as exc:
        logger.debug("온보딩 상태 계산 실패: %s", exc)
        onboarding = {
            "steps": [],
            "completed_steps": 0,
            "total_steps": 3,
            "progress_percent": 0,
            "is_completed": False,
            "dismissed": bool(dismissed),
            "visible": not dismissed,
            "show_completion_notice": False,
        }

    def _fx_change_pct(code: str) -> float | None:
        changes = fx_data.get("changes")
        if isinstance(changes, dict):
            value = _to_float(changes.get(code))
            if value is not None:
                return value
        return _to_float(fx_data.get(f"{code}_change_pct"))

    fx_meta = {
        "updated_at": fx_data.get("updated_at"),
        "source": fx_data.get("source") or "default",
        "is_mock": bool(fx_data.get("is_mock", True)),
    }
    fx_cards = []
    for code, label, icon in [
        ("USD", "미국 달러", "bi-currency-dollar"),
        ("JPY", "일본 엔", "bi-currency-yen"),
        ("CNY", "중국 위안", "bi-currency-exchange"),
        ("EUR", "유로", "bi-currency-euro"),
    ]:
        rate = _to_float(fx_data.get(code))
        change = _fx_change_pct(code)
        if change is None:
            trend = {"direction": "neutral", "label": "전일 대비 데이터 없음"}
        elif change > 0:
            trend = {"direction": "up", "label": f"+{change:.2f}%"}
        elif change < 0:
            trend = {"direction": "down", "label": f"{change:.2f}%"}
        else:
            trend = {"direction": "neutral", "label": "0.00%"}
        fx_cards.append(
            {
                "code": code,
                "label": label,
                "icon": icon,
                "rate": rate,
                "trend": trend,
            }
        )

    recent_activities = []
    for alert in (alerts_data.get("alerts") or [])[:5]:
        if not isinstance(alert, dict):
            continue
        severity = (alert.get("severity") or "info").lower()
        type_key = (alert.get("type") or "activity").lower()
        icon_map = {
            "price_change": "bi-graph-up-arrow",
            "out_of_stock": "bi-box-seam",
            "new_product": "bi-stars",
            "activity": "bi-clock-history",
        }
        severity_label_map = {
            "error": "긴급",
            "warning": "주의",
            "info": "안내",
        }
        recent_activities.append(
            {
                "title": alert.get("label") or "활동",
                "detail": alert.get("product") or "최근 활동 데이터가 없습니다.",
                "severity": severity,
                "severity_label": severity_label_map.get(severity, "안내"),
                "icon": icon_map.get(type_key, "bi-clock-history"),
                "timestamp": alert.get("timestamp") or "방금 전",
            }
        )

    recent_products = []
    for alert in (alerts_data.get("alerts") or [])[:5]:
        if not isinstance(alert, dict):
            continue
        product_name = alert.get("product")
        if not product_name:
            continue
        recent_products.append(
            {
                "title": product_name,
                "status": alert.get("label") or "활동",
                "href": "/seller/catalog",
            }
        )
        if len(recent_products) >= 5:
            break

    if not recent_products and queue_data.get("pending"):
        recent_products.append(
            {
                "title": f"등록 대기 상품 {queue_data.get('pending')}건",
                "status": "등록 대기",
                "href": "/seller/catalog",
            }
        )

    try:
        from src.version import get_version_string
        dashboard_version = get_version_string()
    except Exception:
        dashboard_version = "서비스 버전 확인 불가"

    return {
        "summary_cards": summary_cards,
        "quick_actions": quick_actions,
        "connection_banner": connection_banner,
        "onboarding": onboarding,
        "market_grid_rows": market_grid_rows,
        "market_grid_is_placeholder": not any(
            row.get("today_registered")
            or row.get("today_synced")
            or row.get("total_registered")
            or row.get("total_synced")
            for row in market_grid_rows
        ),
        "fx_cards": fx_cards,
        "fx_meta": fx_meta,
        "info_cards": [
            {
                "title": "시스템/연동 요약",
                "icon": "bi-diagram-3",
                "items": [
                    f"연동된 마켓 {connected_count}개",
                    f"등록 대기 {queue_data.get('pending', 0)}건",
                    f"재고 경고 {low_stock}건",
                ],
                "link_label": "연동/현황 보기",
                "link_href": "/seller/markets",
            },
            {
                "title": "공지 / 릴리스 노트",
                "icon": "bi-megaphone",
                "items": [
                    "대시보드 홈 레이아웃과 정보 밀도를 개선했습니다.",
                    "환율/마켓 현황 위젯은 데이터 미연동 시 안전한 0값으로 표시됩니다.",
                    "신규 기능 없이 시각 품질과 사용성을 중심으로 리파인했습니다.",
                ],
                "link_label": "로드맵 보기",
                "link_href": "/admin/diagnostics",
            },
            {
                "title": "도움말 / 가이드",
                "icon": "bi-question-circle",
                "items": [
                    "상품 수집 → 등록: 수집기에서 시작하세요.",
                    "마진 계산: 환율/수수료를 반영해 판매가를 산출합니다.",
                    "마켓 동기화: 연동 후 상태 표를 확인하세요.",
                ],
                "link_label": "도움말 바로가기",
                "link_href": "/seller/cs/messaging",
            },
        ],
        "recent_activities": recent_activities,
        "recent_products": recent_products,
        "dashboard_footer": {
            "service_name": get_brand_name(),
            "version": dashboard_version,
            "policy_links": [
                {"label": "이용약관", "href": "/terms"},
                {"label": "개인정보처리방침", "href": "/privacy"},
                {"label": "도움말", "href": "/seller/cs/messaging"},
            ],
        },
    }


def _render_dashboard_home():
    widgets = _get_widgets(_seller_id(), _seller_identities())
    dismissed = request.cookies.get(_ONBOARDING_DISMISS_COOKIE) == "1"
    context = _build_dashboard_home_context(widgets, dismissed=dismissed)
    context["onboarding"]["dismiss_href"] = url_for("seller_console.dismiss_onboarding", next=request.path)
    return render_template("dashboard.html", widgets=widgets, page="dashboard", **context)


@bp.get("/")
def index():
    """통합 셀러 대시보드 홈."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    return _render_dashboard_home()


@bp.get("/dashboard")
def dashboard():
    """메인 셀러 대시보드."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    return _render_dashboard_home()


@bp.get("/onboarding/dismiss")
def dismiss_onboarding():
    """대시보드 온보딩 가이드 닫기."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    next_url = (request.args.get("next") or url_for("seller_console.dashboard")).strip()
    if not next_url.startswith("/seller"):
        next_url = url_for("seller_console.dashboard")

    response = redirect(next_url)
    response.set_cookie(
        _ONBOARDING_DISMISS_COOKIE,
        "1",
        max_age=_ONBOARDING_DISMISS_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )
    return response


@bp.get("/analytics")
def analytics_dashboard():
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    force_refresh = request.args.get("force_refresh", "0") == "1"
    try:
        from src.analytics.bi_engine import BIEngine

        data = BIEngine().build_dashboard(force_refresh=force_refresh)
    except Exception as exc:
        logger.warning("BI 대시보드 로드 실패: %s", exc)
        data = {
            "sales_summary": {"today_krw": 0, "week_krw": 0, "month_krw": 0, "channel_share": {}},
            "top_products": [],
            "inventory_alerts": {"low_stock": [], "over_stock": []},
            "ad_roi": {"channels": [], "roas_threshold": 1.5},
            "quality": {"unanswered_24h": 0, "delayed_shipping": 0, "refund_rate": 0.0},
        }
    return render_template("analytics.html", page="analytics", data=data)


@bp.get("/collect")
def collect():
    """수동 수집기 페이지 (Phase 128: API 상태 포함)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from src.utils.env_catalog import get_api_status
        _api_data = get_api_status()
        api_status = _api_data.get("apis", []) if isinstance(_api_data, dict) else _api_data
    except Exception as exc:
        logger.warning("API 상태 로드 실패: %s", exc)
        api_status = []

    marketplace_cards = [
        {"code": "coupang", **_marketplace_meta("coupang")},
        {"code": "smartstore", **_marketplace_meta("smartstore")},
        {"code": "elevenst", **_marketplace_meta("11st")},
        {"code": "woocommerce", **_marketplace_meta("woocommerce")},
        {"code": "amazon", **_marketplace_meta("amazon")},
        {"code": "ebay", **_marketplace_meta("ebay")},
        {"code": "shopify", **_marketplace_meta("shopify")},
        {"code": "shopee", **_marketplace_meta("shopee")},
    ]
    locale_options = []
    seen_locales: set[str] = set()
    for card in marketplace_cards:
        locale = str(card.get("locale") or "").strip()
        if locale and locale not in seen_locales:
            seen_locales.add(locale)
            locale_options.append(locale)
    locale_options = sorted(locale_options)

    try:
        from .localization_service import LocalizationService

        localization_configured = LocalizationService().is_configured()
    except Exception:
        localization_configured = False

    # 원클릭 수집 지원 마켓 — 상품 페이지에서 크롬확장 🛒'수집' 버튼으로 수집
    # 기본 소싱처 = 대형 크로스보더 마켓만(v13 P1: 요시다카반 등 니치는 제외 — 확장 '소싱처 관리'에서 직접 추가).
    # 각 항목에 domain을 넣어 사이트 로고(파비콘) 아이콘으로 표시.
    oneclick_markets = [
        {"name": "타오바오", "url": "https://www.taobao.com", "domain": "taobao.com"},
        {"name": "T몰", "url": "https://www.tmall.com", "domain": "tmall.com"},
        {"name": "1688", "url": "https://www.1688.com", "domain": "1688.com"},
        {"name": "테무", "url": "https://www.temu.com", "domain": "temu.com"},
        {"name": "알리익스프레스", "url": "https://www.aliexpress.com", "domain": "aliexpress.com"},
        # v15: 대형 크로스보더 마켓 디폴트 확장(도메인 검증된 것만).
        {"name": "아이허브", "url": "https://www.iherb.com", "domain": "iherb.com"},
        {"name": "DHgate", "url": "https://www.dhgate.com", "domain": "dhgate.com"},
        {"name": "큐텐", "url": "https://www.qoo10.com", "domain": "qoo10.com"},
        {"name": "메루카리", "url": "https://jp.mercari.com", "domain": "mercari.com"},
        {"name": "라쿠텐", "url": "https://www.rakuten.co.jp", "domain": "rakuten.co.jp"},
        # 아마존은 국가별 사이트가 달라 드롭다운으로 선택(v25 P1: 주요국 확장 + 통화 표기)
        {"name": "아마존", "domain": "amazon.com", "countries": [
            {"name": "미국 (.com)", "url": "https://www.amazon.com", "currency": "USD"},
            {"name": "일본 (.co.jp)", "url": "https://www.amazon.co.jp", "currency": "JPY"},
            {"name": "영국 (.co.uk)", "url": "https://www.amazon.co.uk", "currency": "GBP"},
            {"name": "독일 (.de)", "url": "https://www.amazon.de", "currency": "EUR"},
            {"name": "프랑스 (.fr)", "url": "https://www.amazon.fr", "currency": "EUR"},
            {"name": "이탈리아 (.it)", "url": "https://www.amazon.it", "currency": "EUR"},
            {"name": "스페인 (.es)", "url": "https://www.amazon.es", "currency": "EUR"},
            {"name": "캐나다 (.ca)", "url": "https://www.amazon.ca", "currency": "CAD"},
            {"name": "호주 (.com.au)", "url": "https://www.amazon.com.au", "currency": "AUD"},
            {"name": "싱가포르 (.sg)", "url": "https://www.amazon.sg", "currency": "SGD"},
            {"name": "멕시코 (.com.mx)", "url": "https://www.amazon.com.mx", "currency": "MXN"},
            {"name": "인도 (.in)", "url": "https://www.amazon.in", "currency": "INR"},
            {"name": "UAE (.ae)", "url": "https://www.amazon.ae", "currency": "AED"},
            {"name": "브라질 (.com.br)", "url": "https://www.amazon.com.br", "currency": "BRL"},
        ]},
    ]

    # v17 P1: 유저가 등록한 소싱처(My Sources)를 수집 페이지 '원클릭 마켓' 줄에 칩으로 표시.
    my_sources = []
    try:
        from src.seller_console.my_sources_store import list_sources as _list_my_sources
        for s in _list_my_sources():
            dom = (s.get("domain") or "").strip()
            if dom:
                my_sources.append({"name": s.get("label") or dom, "domain": dom,
                                   "url": "https://" + dom})
    except Exception as exc:
        logger.debug("My Sources 칩 로드 실패: %s", exc)

    return render_template(
        "manual_collect.html",
        page="collect",
        api_status=api_status,
        marketplace_cards=marketplace_cards,
        locale_options=locale_options,
        localization_configured=localization_configured,
        oneclick_markets=oneclick_markets,
        my_sources=my_sources,
    )


@bp.get("/manual-collect")
def manual_collect_alias():
    """수동 수집기 별칭 경로 (Phase 145)."""
    return redirect(url_for("seller_console.collect"))


@bp.post("/collect/preview")
def collect_preview():
    """URL → 메타데이터 추출 결과 (JSON).

    Phase 200: 실 스크래핑(도메인 dispatcher → 범용 스크래퍼)으로 상세설명·이미지·
    가격·색상/옵션을 추출하고 한국어 번역을 채운다. 목업 폴백 제거 — 자동 추출
    실패 시 정직한 에러를 반환하고 수동 입력을 안내한다.

    Request body: {"url": "https://...", "keyword": "...", "translate": true}
    Response: {"ok": true, "draft": {...}, "source": "...", "warnings": [...]}
    """
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    keyword_hint = (data.get("keyword") or "").strip()
    translate = data.get("translate", True) is not False
    save = bool(data.get("save"))

    if not url:
        return jsonify({"ok": False, "error": "URL이 필요합니다."}), 400

    try:
        draft = _collect_real_draft(url, translate=translate)
    except Exception as exc:
        logger.warning("수집 파이프라인 오류: %s", exc)
        return jsonify({"ok": False, "error": "추출 중 오류가 발생했습니다."}), 500

    if draft is None:
        # 목업 대신 정직한 안내 (로그인/봇 차단·비표준 페이지 등)
        return jsonify({
            "ok": False,
            "manual_entry": True,
            "error": (
                "이 URL에서 상품 정보를 자동으로 추출하지 못했습니다. "
                "페이지가 로그인·봇 차단이거나 표준 상품 메타(JSON-LD/OpenGraph)가 "
                "없을 수 있습니다. 제목·가격·이미지를 직접 입력해 진행하세요."
            ),
        }), 200

    _register_discovery_candidate_from_collection(url, keyword_hint=keyword_hint)

    response = {
        "ok": True,
        "draft": draft,
        "trust": None,
        "source": draft.get("source"),
        "warnings": draft.get("warnings", []),
    }

    # Phase 215: save=true 면 수집 이력에 저장해 결과 위치(편집/이력)를 돌려준다.
    # (소싱 허브 '즉시 수집'이 결과를 어디서 보는지 셀러가 바로 알 수 있게)
    if save:
        try:
            from . import collect_history_store

            images = draft.get("images") if isinstance(draft.get("images"), list) else []
            title = draft.get("title_ko") or draft.get("title") or draft.get("title_en") or "(제목 없음)"
            item_id = collect_history_store.append(
                source="quick",
                url=url,
                title=title,
                image=images[0] if images else "",
                price=str(draft.get("price_original") or draft.get("price") or ""),
                currency=draft.get("currency") or "",
                extra=draft,
                seller_id=_seller_id(),
            )
            response["id"] = item_id
            response["preview_url"] = f"/seller/collect/preview/{item_id}"
            response["history_url"] = "/seller/collect/history"
        except Exception as exc:
            logger.warning("수집 이력 저장 실패(%s): %s", url, exc)
            response["save_error"] = "수집은 됐지만 이력 저장에 실패했습니다."

    return jsonify(response)


def _quick_collect(url: str, source: str = "bookmarklet") -> dict:
    """공통 수집 코어 — 로그인 세션으로 URL 수집해 이력에 저장.

    Returns: {ok, item_id, message, status} (status=HTTP 코드). 북마클릿/공유(Share Target) 공용.
    """
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "item_id": None, "status": 400,
                "message": "올바른 상품 URL이 아닙니다. 상품 상세 페이지에서 다시 시도해주세요."}

    draft = None
    try:
        draft = _collect_real_draft(url, translate=True)
    except Exception as exc:
        logger.warning("빠른 수집 파이프라인 오류(%s): %s", url[:80], exc)

    if not draft:
        t = (request.args.get("t") or "").strip()
        img = (request.args.get("img") or "").strip()
        price = (request.args.get("p") or "").strip()
        currency = (request.args.get("c") or "").strip() or "USD"
        if t or img:
            draft = {
                "title": t, "title_ko": t, "title_en": t,
                "price_original": price, "price": price, "currency": currency,
                "images": [img] if img else [], "image": img,
                "description": "", "description_ko": "",
                "source": f"{source}_meta",
            }

    if not draft:
        return {"ok": False, "item_id": None, "status": 200,
                "message": ("이 페이지에서 상품 정보를 읽지 못했습니다. 상품 상세 페이지인지 확인하거나, "
                            "봇 차단 사이트(Temu·Amazon 등)는 PC 크롬 확장(고가수집기)에서 더 정확합니다.")}

    images = draft.get("images") if isinstance(draft.get("images"), list) else []
    title = draft.get("title_ko") or draft.get("title") or draft.get("title_en") or "(제목 없음)"
    from . import collect_history_store
    # v42 1-3: 중복 수집 방지 — 같은 상품이 이미 있으면 기존 항목 안내(북마클릿/공유도 동일).
    try:
        _dup = collect_history_store.find_by_product_key(url, seller_ids=_seller_identities())
    except Exception:
        _dup = None
    if _dup and _dup.get("id"):
        return {"ok": True, "item_id": _dup.get("id"), "status": 200, "duplicate": True,
                "message": "이미 수집한 상품입니다. 내 계정의 ‘수집 이력’에서 확인·편집할 수 있습니다."}
    try:
        item_id = collect_history_store.append(
            source=source, url=url, title=title,
            image=images[0] if images else draft.get("image", ""),
            price=str(draft.get("price_original") or draft.get("price") or ""),
            currency=draft.get("currency") or "",
            extra=draft, seller_id=_seller_id(),
        )
    except Exception as exc:
        logger.warning("빠른 수집 이력 저장 실패: %s", exc)
        return {"ok": False, "item_id": None, "status": 200,
                "message": "수집은 됐지만 이력 저장에 실패했습니다. 다시 시도해주세요."}

    _register_discovery_candidate_from_collection(url)
    return {"ok": True, "item_id": item_id, "status": 200,
            "message": "수집 이력에 저장했어요. 내 계정의 ‘수집 이력’에서 확인·편집할 수 있습니다."}


@bp.get("/collect/quick")
def collect_quick():
    """북마클릿 '새 탭 네비게이션' 수집 (Phase 218 — 토큰 없이 로그인 세션으로 작동).

    북마클릿이 `fetch` 대신 새 탭으로 이 URL을 열어 수집한다. 임의 쇼핑몰의 CSP가
    `fetch`를 막아도 페이지 '이동'은 막히지 않으므로 실제로 수집된다. 로그인 세션을 쓴다.

    Query: u(상품URL, 필수), t(제목), img(이미지), p(가격), c(통화) — 페이지에서 읽은 메타.
    """
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.full_path))

    url = (request.args.get("u") or request.args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        shared = request.args.get("text") or request.args.get("title") or ""
        m = re.search(r"https?://[^\s]+", shared)
        if m:
            url = m.group(0).strip()

    res = _quick_collect(url, source="bookmarklet")
    # 북마클릿은 편집 페이지로 바로 안 보내고 '수집됨'만 표시(오너 결정, Phase 219).
    return render_template(
        "collect_quick_result.html", ok=res["ok"], message=res["message"],
        url=url, item_id=res.get("item_id"),
    ), res["status"]


@bp.get("/collect/share")
def collect_share():
    """v39-M M2: 모바일 PWA 공유(Web Share Target) 수집 → 성공 시 편집 드로어로 바로 진입.

    manifest share_target.action = 이 라우트. 공유된 title/text/url에서 상품 URL을 뽑아 수집하고,
    성공하면 편집 화면(드로어 모드)으로 redirect — 한 손으로 공유→수집→편집까지.
    (북마클릿 /collect/quick은 '수집됨' 확인만 표시하던 흐름 유지.)
    """
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.full_path))

    url = (request.args.get("url") or request.args.get("u") or "").strip()
    if not url.startswith(("http://", "https://")):
        shared = request.args.get("text") or request.args.get("title") or ""
        m = re.search(r"https?://[^\s]+", shared)
        if m:
            url = m.group(0).strip()

    res = _quick_collect(url, source="share")
    if res["ok"] and res.get("item_id"):
        # 성공 → 편집 화면(모바일 풀스크린 드로어 모드)으로 바로 진입
        return redirect(url_for("seller_console.collect_preview_by_id",
                                item_id=res["item_id"]) + "?drawer=1&from=share")
    # 실패 → 정직한 안내(모바일: 확장 권장 등)
    return render_template(
        "collect_quick_result.html", ok=False, message=res["message"], url=url,
    ), res["status"]


def _extract_reviews(html: str, limit: int = 20) -> list[dict]:
    """페이지 HTML에서 리뷰를 best-effort 추출(JSON-LD 우선 + 보수적 휴리스틱).

    추출 못 하면 빈 리스트(정직 — 가짜 리뷰 생성 금지).
    """
    reviews: list[dict] = []
    if not html:
        return reviews
    try:
        from bs4 import BeautifulSoup
        import json as _json
        soup = BeautifulSoup(html, "html.parser")

        # 1) JSON-LD review (가장 신뢰도 높음)
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = _json.loads(s.string or s.get_text() or "")
            except Exception:
                continue
            for obj in (data if isinstance(data, list) else [data]):
                if not isinstance(obj, dict):
                    continue
                revs = obj.get("review") or obj.get("reviews")
                if isinstance(revs, dict):
                    revs = [revs]
                if not isinstance(revs, list):
                    continue
                for r in revs:
                    if not isinstance(r, dict):
                        continue
                    body = str(r.get("reviewBody") or r.get("description") or "").strip()
                    if not body:
                        continue
                    rating = None
                    rr = r.get("reviewRating")
                    if isinstance(rr, dict):
                        rating = rr.get("ratingValue")
                    author = r.get("author")
                    if isinstance(author, dict):
                        author = author.get("name")
                    reviews.append({"body": body[:500], "rating": rating,
                                    "author": str(author or "")[:60]})

        # 2) 보수적 휴리스틱(JSON-LD가 적을 때만): class에 review가 포함된 짧은 텍스트 블록
        if len(reviews) < 3:
            for el in soup.find_all(attrs={"class": True}):
                cls = " ".join(el.get("class") or []).lower()
                if "review" not in cls or "reviews" == cls:
                    continue
                txt = el.get_text(" ", strip=True)
                if 15 <= len(txt) <= 400:
                    reviews.append({"body": txt[:400], "rating": None, "author": ""})
                if len(reviews) >= limit:
                    break
    except Exception as exc:
        logger.debug("리뷰 추출 실패: %s", exc)

    # 중복 제거
    seen, out = set(), []
    for r in reviews:
        b = r.get("body", "")
        if not b or b in seen:
            continue
        seen.add(b)
        out.append(r)
        if len(out) >= limit:
            break
    return out


@bp.get("/collect/receiver")
def collect_receiver():
    """북마클릿 postMessage 수신 페이지 (Phase 219).

    북마클릿이 새 탭으로 이 페이지를 열고(로그인 세션), 페이지 HTML·이미지·메타를
    postMessage로 전달한다. 이 페이지가 같은 출처로 `/seller/collect/receive`에 저장 요청 →
    '수집됨'만 표시하고 편집 페이지로 이동하지 않는다(내 계정 수집 이력에서 확인).

    ※ 로그인 페이지로 튕기지 않도록 페이지 렌더는 인증 게이트를 두지 않는다(저장 POST에서만
    인증 확인). 미로그인 시 페이지 안에서 친절히 '로그인' 버튼을 보여준다.
    """
    return render_template("collect_receiver.html", authed=_check_auth())


@bp.post("/collect/receive")
def collect_receive():
    """북마클릿이 보낸 페이지 데이터(HTML 포함)를 받아 이미지·상세·리뷰까지 수집·저장.

    Request JSON: {url, title, price, currency, description, images[], html, translate}
    Response: {ok, id, history_url}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "올바른 상품 URL이 아닙니다."}), 400

    translate = data.get("translate", True) is not False
    html = data.get("html") if isinstance(data.get("html"), str) else ""
    client_images = [str(i).strip() for i in (data.get("images") or []) if str(i or "").strip()]

    # 1) 페이지 HTML 서버 파싱(이미지/상세/옵션) — 봇 차단 사이트도 브라우저 DOM 기반으로 수집
    draft = None
    if html:
        try:
            from src.collectors.universal_scraper import UniversalScraper
            scraped = UniversalScraper().parse_html(html, url)
            draft = _scraped_to_draft(scraped)
        except Exception as exc:
            logger.warning("receiver HTML 파싱 실패: %s", exc)

    if draft is None:
        draft = {
            "url": url, "source": "bookmarklet_meta", "title": "", "title_en": "",
            "title_ko": "", "description": "", "images": [], "price": None,
            "price_original": 0.0, "currency": "USD", "options": [],
        }

    # 2) 클라이언트가 보낸 메타/이미지로 빈 값 보강(사용자가 본 화면 우선)
    if not (draft.get("title") or "").strip() and data.get("title"):
        draft["title"] = draft["title_en"] = draft["title_ko"] = str(data["title"])[:300]
    if not (draft.get("description") or "").strip() and data.get("description"):
        draft["description"] = str(data["description"])
    if data.get("price") and not draft.get("price"):
        draft["price"] = str(data["price"])
        try:
            draft["price_original"] = float(str(data["price"]).replace(",", ""))
        except (TypeError, ValueError):
            pass
    if data.get("currency"):
        draft["currency"] = str(data["currency"]) or draft.get("currency") or "USD"
    # 이미지 병합(서버 파싱 + 클라이언트 DOM 이미지), 중복 제거·상한 30
    merged_imgs, seen = [], set()
    for src in list(draft.get("images") or []) + client_images:
        s = str(src or "").strip()
        if s and s not in seen and s.startswith(("http://", "https://")):
            seen.add(s)
            merged_imgs.append(s)
    draft["images"] = merged_imgs[:30]

    # 3) 리뷰 추출(best-effort)
    reviews = _extract_reviews(html) if html else []
    if reviews:
        draft["reviews"] = reviews

    # 의미있는 수집인지 확인
    if not (draft.get("title") or draft.get("images")):
        return jsonify({"ok": False, "error": "상품 정보를 읽지 못했습니다. 상품 상세 페이지인지 확인하세요."}), 200

    draft.setdefault("title_ko", draft.get("title") or "")
    if translate:
        try:
            draft = _translate_draft(draft)
        except Exception as exc:
            logger.warning("receiver 번역 실패(원문 유지): %s", exc)

    images = draft.get("images") or []
    title = draft.get("title_ko") or draft.get("title") or "(제목 없음)"
    try:
        from . import collect_history_store
        item_id = collect_history_store.append(
            source="bookmarklet",
            url=url,
            title=title,
            image=images[0] if images else "",
            price=str(draft.get("price_original") or draft.get("price") or ""),
            currency=draft.get("currency") or "",
            extra=draft,
            seller_id=_seller_id(),
        )
    except Exception as exc:
        logger.warning("receiver 수집 이력 저장 실패: %s", exc)
        return jsonify({"ok": False, "error": "수집은 됐지만 이력 저장에 실패했습니다."}), 200

    _register_discovery_candidate_from_collection(url)
    return jsonify({
        "ok": True, "id": item_id,
        "title": title,
        "image_count": len(images),
        "review_count": len(reviews),
        "translated": translate,
        "history_url": "/seller/collect/history",
        "edit_url": f"/seller/collect/preview/{item_id}",
    })


@bp.post("/collect/upload")
def collect_upload():
    """마켓 업로드 트리거 (JSON).

    Request body: {"product": {...}, "markets": ["coupang", "smartstore"], "target_margin_pct": 22}
    Response: {"ok": true, "result": {...}}
    """
    data = request.get_json(force=True, silent=True) or {}
    product_data = data.get("product") or {}
    markets = data.get("markets") or []

    if not product_data:
        return jsonify({"ok": False, "error": "상품 데이터가 필요합니다."}), 400

    if not markets:
        return jsonify({"ok": False, "error": "업로드 대상 마켓을 선택하세요."}), 400

    # Phase 190: target_margin_pct를 payload에 반영 (마진율 실반영)
    target_margin_pct = data.get("target_margin_pct")
    if target_margin_pct is not None:
        try:
            product_data["target_margin_pct"] = float(target_margin_pct)
        except (TypeError, ValueError):
            pass

    dispatcher = _get_upload_dispatcher()
    if dispatcher is None:
        return jsonify({"ok": False, "error": "업로드 디스패처 준비 중입니다."}), 503

    try:
        from . import market_credentials as mc

        with mc.seller_market_env(_seller_id(), markets):
            result = dispatcher.dispatch(product_data, markets)
        rd = result.to_dict()
        # v44-1: 서버가 성공 확인한 마켓만 항목에 영속 저장 → 목록에 '등록됨' 뱃지 영구 표시(가짜 성공 0).
        _persist_upload_status(data.get("item_id"), rd)
        return jsonify({"ok": True, "result": rd})
    except Exception as exc:
        # v11 P0: 가짜 일반 실패 금지 — 실제 사유를 패스스루로 노출.
        logger.warning("업로드 디스패처 오류: %s", exc)
        return jsonify({"ok": False, "error": f"업로드 중 오류: {exc}"}), 500


def _persist_upload_status(item_id, result_dict) -> None:
    """v44-1: 업로드 결과 중 '성공(success=true)' 마켓을 항목 extra_json.uploaded에 병합 저장.

    서버 응답이 확인한 성공만 저장(가짜 성공 금지). market 기준 dedup(재업로드 시 최신 url·시각으로 갱신).
    """
    if not item_id:
        return
    try:
        item = _get_owned_item(str(item_id))
        if not item:
            return
        extra = {}
        try:
            extra = json.loads(item.get("extra_json") or "{}") or {}
        except Exception:
            extra = {}
        uploaded = extra.get("uploaded") if isinstance(extra.get("uploaded"), list) else []
        by_market = {u.get("market"): u for u in uploaded if isinstance(u, dict) and u.get("market")}
        now = datetime.now(timezone.utc).isoformat()
        changed = False
        for r in (result_dict.get("results") or []):
            if r.get("success") and r.get("market"):
                by_market[r["market"]] = {
                    "market": r["market"],
                    "market_label": r.get("market_label") or r["market"],
                    "external_url": r.get("external_url") or "",
                    "at": now,
                }
                changed = True
        if not changed:
            return
        extra["uploaded"] = list(by_market.values())
        from .collect_history_store import update as _update
        _update(str(item_id), seller_ids=_seller_identities(),
                extra_json=json.dumps(extra, ensure_ascii=False))
    except Exception as exc:
        logger.warning("업로드 상태 영속 실패(무시): %s", exc)


@bp.post("/collect/prevalidate")
def collect_prevalidate():
    """마켓 업로드 사전검증 (Phase 190).

    Request body: {"product": {...}, "markets": ["coupang", "shopify"]}
    Response: {"ok": true, "results": [{"market": "shopify", "ok": true, ...}, ...]}
    """
    data = request.get_json(force=True, silent=True) or {}
    product_data = data.get("product") or {}
    markets = data.get("markets") or []

    if not product_data:
        return jsonify({"ok": False, "error": "상품 데이터가 필요합니다."}), 400
    if not markets:
        return jsonify({"ok": False, "error": "검증할 마켓을 선택하세요."}), 400

    dispatcher = _get_upload_dispatcher()
    if dispatcher is None:
        return jsonify({"ok": False, "error": "업로드 디스패처 준비 중입니다."}), 503

    try:
        from .upload_dispatcher import MARKET_LABELS
        from . import market_credentials as mc

        with mc.seller_market_env(_seller_id(), markets):
            results = dispatcher.prevalidate(product_data, markets)
        return jsonify({
            "ok": True,
            "results": [
                {
                    "market": r.market,
                    "market_label": MARKET_LABELS.get(r.market, r.market),
                    "ok": r.ok,
                    "error_code": r.error_code,
                    "message": r.message,
                    "hint": r.hint,
                }
                for r in results
            ],
            "all_ok": all(r.ok for r in results),
        })
    except Exception as exc:
        logger.warning("사전검증 오류: %s", exc)
        return jsonify({"ok": False, "error": "사전검증 중 오류가 발생했습니다."}), 500


@bp.post("/collect/localize")
def collect_localize():
    """수집 상품/카탈로그 상품을 타깃 locale로 현지화한다."""
    data = request.get_json(force=True, silent=True) or {}
    products = data.get("products")
    if products is None:
        product = data.get("product") or {}
        products = [product] if product else []
    if not isinstance(products, list) or not products:
        return jsonify({"ok": False, "error": "현지화할 상품이 필요합니다."}), 400

    target_locales = data.get("target_locales") or data.get("locales") or []
    if isinstance(target_locales, str):
        target_locales = [x.strip() for x in target_locales.split(",") if x.strip()]
    if not target_locales:
        return jsonify({"ok": False, "error": "타깃 언어(locale)를 선택하세요."}), 400

    from .localization_service import LocalizationService

    service = LocalizationService()
    if not service.is_configured():
        return jsonify(
            {
                "ok": True,
                "configured": False,
                "message": "번역 API가 설정되지 않아 원문을 유지했습니다. /admin/diagnostics에서 API 키를 설정하세요.",
                "total": len(products),
                "success": 0,
                "cache_hits": 0,
                "untranslated": len(products) * len(target_locales),
                "items": [],
            }
        )

    output_items = []
    translated_count = 0
    untranslated_count = 0
    cache_hits = 0

    for product in products:
        product_data = dict(product or {})
        source_lang = str(product_data.get("source_lang") or product_data.get("language") or "ko-KR")
        localized_map = product_data.get("localized") if isinstance(product_data.get("localized"), dict) else {}
        for locale in target_locales:
            result = service.localize_product(product_data, str(locale), source_lang=source_lang)
            localized_map[result.locale] = result.translated
            translated_count += result.translated_count
            cache_hits += result.cache_hits
            untranslated_count += int(result.untranslated)
        product_data["localized"] = localized_map
        product_data["localization_status"] = "localized" if localized_map else "not_localized"
        output_items.append(product_data)

    return jsonify(
        {
            "ok": True,
            "configured": True,
            "total": len(products),
            "success": len(output_items),
            "translated": translated_count,
            "cache_hits": cache_hits,
            "untranslated": untranslated_count,
            "items": output_items,
            "quality_notice": "기계번역 결과는 반드시 사람 검수 후 사용하세요.",
        }
    )


@bp.post("/collect/save")
def collect_save():
    """수집 결과를 Sheets catalog 워크시트에 저장 (Phase 128).

    Request body: 수집 결과 dict
    Response: {"ok": true, "saved": true}
    """
    payload = request.get_json(force=True, silent=True) or {}
    if not payload:
        return jsonify({"ok": False, "error": "저장할 데이터가 없습니다."}), 400

    try:
        from .market_status_sheets import MarketStatusSheetsAdapter
        from .market_status import MarketStatusItem
        from datetime import datetime

        adapter = MarketStatusSheetsAdapter()
        payload_currency = str(payload.get("currency") or "KRW").upper()
        payload_price = None
        if payload.get("price"):
            try:
                payload_price = float(payload["price"])
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "가격은 숫자 형식이어야 합니다."}), 400
        item = MarketStatusItem(
            marketplace=payload.get("marketplace", "collected"),
            product_id=payload.get("sku") or payload.get("asin") or f"col_{int(datetime.now().timestamp())}",
            state="active",
            sku=payload.get("sku") or payload.get("asin"),
            title=payload.get("title"),
            description=payload.get("description"),
            keywords=payload.get("keywords") if isinstance(payload.get("keywords"), list) else [],
            options=payload.get("options") if isinstance(payload.get("options"), list) else [],
            localized=payload.get("localized") if isinstance(payload.get("localized"), dict) else {},
            localization_status=str(payload.get("localization_status") or "not_localized"),
            price=payload_price,
            currency=payload_currency,
            price_krw=int(payload_price) if payload_currency == "KRW" and payload_price is not None else None,
            last_synced_at=datetime.now(),
        )
        saved = adapter.upsert_item(item)
        return jsonify({"ok": True, "saved": saved})
    except Exception as exc:
        logger.warning("collect_save 오류: %s", exc)
        return jsonify({"ok": False, "error": "저장 중 오류가 발생했습니다."}), 500


@bp.post("/collect/bulk")
def collect_bulk():
    """여러 소싱처 URL을 한 번에 수집해 수집 이력에 저장 (③ 일괄 수집).

    Request: {"urls": "url1\nurl2..." 또는 ["url1", "url2"]}
    Response: {"ok": true, "total": N, "success": M, "results": [{url, ok, title?, preview_url?, error?}]}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(force=True, silent=True) or {}
    raw = data.get("urls")
    if isinstance(raw, str):
        urls = [u.strip() for u in raw.splitlines() if u.strip()]
    elif isinstance(raw, list):
        urls = [str(u).strip() for u in raw if str(u).strip()]
    else:
        urls = []
    # 중복 제거(순서 유지) + 상한
    seen = set()
    urls = [u for u in urls if not (u in seen or seen.add(u))][:1000]
    if not urls:
        return jsonify({"ok": False, "error": "수집할 URL을 한 줄에 하나씩 입력하세요."}), 400

    from . import collect_history_store

    results = []
    success = 0
    for url in urls:
        if not (url.startswith("http://") or url.startswith("https://")):
            results.append({"url": url, "ok": False, "error": "http/https URL이 아닙니다."})
            continue
        try:
            # Phase 203: 목업 제거 — /collect/preview와 동일한 실 수집 파이프라인 사용
            d = _collect_real_draft(url, translate=True)
            if not d:
                results.append({"url": url, "ok": False, "error": "자동 추출 실패 (수동 입력 필요)"})
                continue
            title = d.get("title_ko") or d.get("title") or d.get("title_en") or "(제목 없음)"
            images = d.get("images") if isinstance(d.get("images"), list) else []
            item_id = collect_history_store.append(
                source="bulk",
                url=url,
                title=title,
                image=images[0] if images else "",
                price=str(d.get("price_original") or d.get("price") or ""),
                currency=d.get("currency") or "",
                extra=d,
                seller_id=_seller_id(),
            )
            results.append({
                "url": url, "ok": True, "title": title,
                "id": item_id, "preview_url": f"/seller/collect/preview/{item_id}",
            })
            success += 1
        except Exception as exc:
            logger.warning("벌크 수집 실패 (%s): %s", url, exc)
            results.append({"url": url, "ok": False, "error": "수집 실패 (URL/소싱처 확인)"})

    return jsonify({"ok": True, "total": len(urls), "success": success, "results": results})


@bp.post("/collect/bulk-upload")
def collect_bulk_upload():
    """수집 이력의 여러 상품을 선택해 여러 마켓에 일괄 등록 (④ 일괄 업로드).

    Request: {"item_ids": [...], "markets": [...], "target_margin_pct"?: float}
    Response: {"ok": true, "total": N, "succeeded": M, "results": [{id, title, ok, result}]}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids") if isinstance(data.get("item_ids"), list) else []
    item_ids = [str(i) for i in item_ids if str(i).strip()][:50]
    markets = data.get("markets") if isinstance(data.get("markets"), list) else []
    markets = [str(m).strip() for m in markets if str(m).strip()]
    if not item_ids:
        return jsonify({"ok": False, "error": "등록할 상품을 선택하세요."}), 400
    if not markets:
        return jsonify({"ok": False, "error": "등록할 마켓을 선택하세요."}), 400

    target_margin_pct = data.get("target_margin_pct")

    dispatcher = _get_upload_dispatcher()
    if dispatcher is None:
        return jsonify({"ok": False, "error": "업로드 디스패처 준비 중입니다."}), 503

    import json as _json
    from . import collect_history_store
    from . import market_credentials as mc

    results = []
    succeeded = 0
    try:
        with mc.seller_market_env(_seller_id(), markets):
            for item_id in item_ids:
                item = collect_history_store.get(item_id, seller_id=_seller_id())
                if not item:
                    results.append({"id": item_id, "ok": False, "error": "수집 항목을 찾을 수 없습니다."})
                    continue
                try:
                    product = _json.loads(item.get("extra_json") or "{}")
                except (TypeError, ValueError):
                    product = {}
                if not product:
                    product = {"title": item.get("title"), "url": item.get("url"),
                               "price": item.get("price"), "currency": item.get("currency")}
                if target_margin_pct is not None:
                    try:
                        product["target_margin_pct"] = float(target_margin_pct)
                    except (TypeError, ValueError):
                        pass
                dispatch_result = dispatcher.dispatch(product, markets)
                ok = dispatch_result.succeeded > 0
                if ok:
                    succeeded += 1
                results.append({
                    "id": item_id,
                    "title": item.get("title") or product.get("title") or "(제목 없음)",
                    "ok": ok,
                    "result": dispatch_result.to_dict(),
                })
    except Exception as exc:
        logger.warning("일괄 업로드 오류: %s", exc)
        return jsonify({"ok": False, "error": "일괄 업로드 중 오류가 발생했습니다."}), 500

    return jsonify({"ok": True, "total": len(item_ids), "succeeded": succeeded, "results": results})


@bp.post("/collect/bulk-delete")
def collect_bulk_delete():
    """수집 이력의 여러 항목을 일괄 삭제 (셀러 격리).

    Request: {"item_ids": [...]}
    Response: {"ok": true, "deleted": N}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids") if isinstance(data.get("item_ids"), list) else []
    item_ids = [str(i) for i in item_ids if str(i).strip()][:1000]
    if not item_ids:
        return jsonify({"ok": False, "error": "삭제할 상품을 선택하세요."}), 400

    try:
        from . import collect_history_store
        # v32: 목록과 동일한 관용 스코프로 삭제 → 별칭 불일치로 삭제 0건(재진입 부활) 방지.
        ids_set = _seller_identities()
        # v45 P1: 단일 batchUpdate 삭제 + 실제 삭제된 id 목록을 응답(프론트가 그 행만 제거).
        deleted_ids = collect_history_store.delete_ids(item_ids, seller_ids=ids_set)
        # v41 STEP 1-0 write-then-verify: 삭제 후 재읽기로 실제 사라졌는지 검증(부활 0). 남아있으면 정직 실패.
        still = collect_history_store.existing_ids(item_ids, seller_ids=ids_set)
    except Exception as exc:
        logger.warning("일괄 삭제 오류: %s", exc)
        return jsonify({"ok": False, "error": "일괄 삭제 중 오류가 발생했습니다."}), 500

    # 실제 삭제된 id 중 재읽기로도 사라짐이 검증된 것만 프론트에 통보 → 그 행만 DOM에서 제거.
    # (still = 삭제 시도했으나 여전히 잔존 = 미영속. 검증 통과분만 verified_gone.)
    verified_gone = [i for i in deleted_ids if i not in still]
    if still:
        logger.warning("일괄 삭제 미영속(재읽기서 %d건 잔존): %s", len(still), list(still)[:5])
        return jsonify({"ok": False, "deleted": len(verified_gone), "deleted_ids": verified_gone,
                        "error": f"{len(still)}건이 삭제되지 않았어요(서버 저장 실패). 새로고침 후 다시 시도해 주세요."}), 200
    return jsonify({"ok": True, "deleted": len(verified_gone), "deleted_ids": verified_gone})


# ── v47 STEP5: 엑셀 벌크 내보내기 / 가져오기 ─────────────────────────────────
def _excel_existing_ids() -> set:
    """내 수집목록의 모든 상품ID(가져오기 갱신 대상 판정용)."""
    try:
        from . import collect_history_store as ch
        rows = ch.list_items(seller_ids=_seller_identities(), days=3650, limit=None, lean=True)
        return {str(r.get("id")) for r in rows if r.get("id")}
    except Exception:
        return set()


@bp.post("/collect/export-xlsx")
def collect_export_xlsx():
    """선택(item_ids) 또는 전체(필터 무시, 최신 5000) 수집 상품을 xlsx로 내보낸다."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    item_ids = [str(i) for i in (data.get("item_ids") or []) if str(i).strip()]
    from . import collect_history_store as ch
    ids_set = _seller_identities()
    from .collect_excel import MAX_ROWS
    if item_ids:
        items = []
        for iid in item_ids[:MAX_ROWS]:
            it = ch.get(iid, seller_ids=ids_set)
            if it:
                items.append(it)
    else:
        items = ch.list_items(seller_ids=ids_set, days=3650, limit=MAX_ROWS)
    from .collect_excel import build_workbook
    try:
        xls = build_workbook(items)
    except Exception as exc:
        logger.warning("엑셀 내보내기 실패: %s", exc)
        return jsonify({"ok": False, "error": "엑셀 생성 중 오류가 발생했어요."}), 500
    resp = Response(xls, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    fname = quote_plus("고가브릿지_상품.xlsx").replace("+", "%20")
    resp.headers["Content-Disposition"] = "attachment; filename=goga_products.xlsx; filename*=UTF-8''" + fname
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/collect/export-template")
def collect_export_template():
    """빈 템플릿(헤더 + 예시 1행) 다운로드."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from .collect_excel import template_workbook
    xls = template_workbook()
    resp = Response(xls, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    fname = quote_plus("고가브릿지_템플릿.xlsx").replace("+", "%20")
    resp.headers["Content-Disposition"] = "attachment; filename=goga_template.xlsx; filename*=UTF-8''" + fname
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _excel_parse_and_validate():
    """업로드 파일 → (report, http_status). report={ok, new, update, errors, truncated, apply?}."""
    f = request.files.get("file")
    if not f:
        return {"ok": False, "error": "엑셀 파일을 선택하세요."}, 400
    raw = f.read()
    if not raw:
        return {"ok": False, "error": "빈 파일이에요."}, 400
    if len(raw) > 20 * 1024 * 1024:
        return {"ok": False, "error": "파일이 너무 커요(20MB 이하)."}, 400
    from .collect_excel import parse_workbook, validate_rows
    rows, perr, truncated = parse_workbook(raw)
    report = validate_rows(rows, _excel_existing_ids())
    report["errors"] = perr + report["errors"]
    report["truncated"] = truncated
    report["ok"] = True
    return report, 200


@bp.post("/collect/import-xlsx")
def collect_import_xlsx():
    """가져오기 1단계: 검증만(적용 안 함). 신규/갱신/오류 리포트 반환 → 사용자 확인 후 apply."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    try:
        report, code = _excel_parse_and_validate()
    except Exception as exc:
        logger.warning("엑셀 검증 실패: %s", exc)
        return jsonify({"ok": False, "error": "엑셀을 읽는 중 오류가 발생했어요. 템플릿 형식인지 확인해 주세요."}), 400
    if not report.get("ok"):
        return jsonify(report), code
    # 미리보기(최대 30행 요약)만 반환 — 적용은 같은 파일 재전송(stateless).
    preview = [{"row": a["_row"], "mode": a["mode"], "id": a["id"],
                "title": a["fields"].get("title_ko") or a["fields"].get("title_en"),
                "price": a["fields"].get("price")} for a in report.get("apply", [])[:30]]
    return jsonify({"ok": True, "new": report["new"], "update": report["update"],
                    "errors": report["errors"][:100], "error_count": len(report["errors"]),
                    "truncated": report["truncated"], "preview": preview,
                    "apply_count": len(report.get("apply", []))})


@bp.post("/collect/import-apply")
def collect_import_apply():
    """가져오기 2단계: 같은 파일 재검증 후 실제 적용(신규=추가/갱신=업데이트). 오류는 행별(전체 롤백 아님)."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    try:
        report, code = _excel_parse_and_validate()
    except Exception as exc:
        logger.warning("엑셀 적용 파싱 실패: %s", exc)
        return jsonify({"ok": False, "error": "엑셀을 읽는 중 오류가 발생했어요."}), 400
    if not report.get("ok"):
        return jsonify(report), code
    from . import collect_history_store as ch
    import json as _json
    from src.collectors.collect_status import compute_collect_status
    ids_set = _seller_identities()
    seller_id_val = _seller_id()
    created, updated = 0, 0
    row_errors = list(report["errors"])

    def _extra_from(fields, base=None):
        ex = dict(base or {})
        ex.update({
            "title_ko": fields["title_ko"], "title_en": fields["title_en"],
            "title": fields["title_ko"] or fields["title_en"],
            "category_code": fields["category"],
            "price": fields["price"], "currency": "KRW",
            "options": fields["options"],
            "gallery_images": fields["gallery"], "images": fields["gallery"],
            "detail_images": fields["detail_images"],
            "keywords": fields["keywords"],
            "thumbnail": fields["thumbnail"] or (fields["gallery"][0] if fields["gallery"] else ""),
            "source": "excel_import",
        })
        try:
            ex["collect_status"] = compute_collect_status(ex, title_fallback=ex["title"])
        except Exception:
            pass
        return ex

    for a in report.get("apply", []):
        rnum, mode, fields = a["_row"], a["mode"], a["fields"]
        thumb = fields["thumbnail"] or (fields["gallery"][0] if fields["gallery"] else "")
        try:
            if mode == "update":
                base = {}
                cur = ch.get(a["id"], seller_ids=ids_set)
                if not cur:
                    row_errors.append({"row": rnum, "reason": "갱신 대상을 찾지 못했어요(삭제됐을 수 있어요)."})
                    continue
                try:
                    base = _json.loads(cur.get("extra_json") or "{}")
                except Exception:
                    base = {}
                ex = _extra_from(fields, base)
                ok = ch.update(a["id"], seller_ids=ids_set,
                               title=ex["title"], image_url=thumb,
                               price=fields["price"], currency="KRW",
                               extra_json=_json.dumps(ex, ensure_ascii=False))
                if ok:
                    updated += 1
                else:
                    row_errors.append({"row": rnum, "reason": "갱신 저장에 실패했어요."})
            else:
                ex = _extra_from(fields)
                ret = ch.append(return_durable=True, source="excel_import",
                                url=fields["url"], title=ex["title"], image=thumb,
                                price=fields["price"], currency="KRW", status="ok",
                                extra=ex, seller_id=seller_id_val)
                iid, durable = ret if isinstance(ret, tuple) and len(ret) == 2 else (ret, True)
                if iid and durable:
                    created += 1
                else:
                    row_errors.append({"row": rnum, "reason": "저장 영속화에 실패했어요(재시도 필요)."})
        except Exception as exc:
            logger.warning("엑셀 적용 행 오류 row=%s: %s", rnum, exc)
            row_errors.append({"row": rnum, "reason": f"적용 중 오류: {str(exc)[:80]}"})

    return jsonify({"ok": True, "created": created, "updated": updated,
                    "errors": row_errors[:200], "error_count": len(row_errors),
                    "truncated": report["truncated"]})


@bp.post("/collect/bulk-category")
def collect_bulk_category():
    """수집 이력 여러 항목에 카테고리를 일괄 지정 (셀러 격리).

    Request: {"item_ids": [...], "category_code": "BAG"}  또는  {"item_ids": [...], "auto": true}
      - auto=true 면 각 항목 제목/키워드로 category_classifier.classify 자동 분류.
    Response: {"ok": true, "updated": N, "results": [{id, ok, category_code}]}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids") if isinstance(data.get("item_ids"), list) else []
    item_ids = [str(i) for i in item_ids if str(i).strip()][:1000]
    category_code = str(data.get("category_code") or "").strip().upper()
    auto = bool(data.get("auto"))
    if not item_ids:
        return jsonify({"ok": False, "error": "상품을 선택하세요."}), 400
    if not auto and not category_code:
        return jsonify({"ok": False, "error": "카테고리를 선택하거나 자동 분류를 켜세요."}), 400

    import json as _json
    from . import collect_history_store
    from .category_classifier import classify as _classify
    sid = _seller_id()
    updated = 0
    results = []
    try:
        for item_id in item_ids:
            item = collect_history_store.get(item_id, seller_ids=_seller_identities())
            if not item:
                results.append({"id": item_id, "ok": False, "error": "항목 없음"})
                continue
            try:
                extra = _json.loads(item.get("extra_json") or "{}")
            except (TypeError, ValueError):
                extra = {}
            code = category_code
            if auto:
                title = item.get("title") or extra.get("title_ko") or ""
                kws = extra.get("keywords")
                kw = ",".join(kws) if isinstance(kws, list) else (kws or "")
                code = _classify(title, extra.get("description_ko") or extra.get("description") or "", kw).get("code", "GEN")
            extra["category_code"] = code
            ok = collect_history_store.update(
                item_id, seller_ids=_seller_identities(), extra_json=_json.dumps(extra, ensure_ascii=False)
            )
            if ok:
                updated += 1
            results.append({"id": item_id, "ok": bool(ok), "category_code": code})
    except Exception as exc:
        logger.warning("일괄 카테고리 오류: %s", exc)
        return jsonify({"ok": False, "error": "일괄 카테고리 지정 중 오류가 발생했습니다."}), 500

    return jsonify({"ok": True, "updated": updated, "results": results})


@bp.post("/collect/bulk-translate")
def collect_bulk_translate():
    """수집 이력 여러 항목의 제목/설명을 한국어로 일괄 번역 (셀러 격리).

    Request: {"item_ids": [...]}
    Response: {"ok": true, "updated": N, "translated": M, "total": T, "message"?: str}
    정직성: OPENAI/DEEPL 키 미설정(stub) 시 원문 유지 + 안내(가짜 번역 없음).
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids") if isinstance(data.get("item_ids"), list) else []
    item_ids = [str(i) for i in item_ids if str(i).strip()][:300]
    if not item_ids:
        return jsonify({"ok": False, "error": "상품을 선택하세요."}), 400

    import json as _json
    from . import collect_history_store
    try:
        from .ai.translator import AITranslator
        translator = AITranslator()
    except Exception as exc:
        logger.warning("번역기 로드 실패: %s", exc)
        translator = None

    sid = _seller_id()
    # 번역 무료 사용량 미터(v3 P1-4): 무료 한도 내에서만 실제 번역, 초과 시 차단(구독/충전 안내).
    # 정직성: 무료 차감은 '실제 번역된 건'만(stub/키 없음은 차감·차단하지 않음).
    from . import translation_usage
    _limit = translation_usage.free_limit()
    _used_before = translation_usage.get_used(sid)
    _remaining = max(0, _limit - _used_before)
    # 무제한 = env 훅 또는 활성 유료 플랜(Plus/Pro). 유료 활성은 실제 결제 시에만(가짜 금지).
    _unlimited = os.getenv("TRANSLATION_UNLIMITED", "0") == "1"
    try:
        from . import billing_store
        if billing_store.is_unlimited(sid):
            _unlimited = True
    except Exception:
        pass

    updated = 0
    translated = 0
    blocked = 0
    results = []
    try:
        for item_id in item_ids:
            item = collect_history_store.get(item_id, seller_ids=_seller_identities())
            if not item:
                results.append({"id": item_id, "ok": False, "error": "항목 없음"})
                continue
            try:
                extra = _json.loads(item.get("extra_json") or "{}")
            except (TypeError, ValueError):
                extra = {}
            title = item.get("title") or extra.get("title_ko") or ""
            desc = extra.get("description") or extra.get("description_ko") or ""
            # 무료 한도 도달 시(실 번역기 있음) 이후 항목은 번역 차단 — 원문 유지.
            allow = _unlimited or (translated < _remaining)
            title_ko, desc_ko, provider = title, desc, "none"
            if allow and translator is not None and (title or desc):
                try:
                    out = translator.translate_product({"title": title, "description": desc})
                    title_ko = (out.get("title_ko") or "").strip() or title
                    desc_ko = (out.get("description_ko") or "").strip() or desc
                    provider = out.get("provider", "stub")
                except Exception as exc:
                    logger.debug("번역 실패(원문 유지): %s", exc)
            real = provider not in ("none", "stub", "")
            # 실 번역기가 있는데 무료 한도로 막힌 경우만 '차단'으로 집계(stub은 차단 아님).
            if (not allow) and translator is not None and (title or desc):
                blocked += 1
            extra["title_ko"] = title_ko
            extra["description_ko"] = desc_ko
            fields = {"extra_json": _json.dumps(extra, ensure_ascii=False)}
            # 실제 번역된 경우에만 표시 제목을 한국어로 갱신(가짜 번역으로 덮어쓰지 않음).
            if real and title_ko and title_ko != item.get("title"):
                fields["title"] = title_ko
            ok = collect_history_store.update(item_id, seller_ids=_seller_identities(), **fields)
            if ok:
                updated += 1
            if real:
                translated += 1
            results.append({"id": item_id, "ok": bool(ok), "translated": real,
                            "title": fields.get("title", item.get("title"))})
    except Exception as exc:
        logger.warning("일괄 번역 오류: %s", exc)
        return jsonify({"ok": False, "error": "일괄 번역 중 오류가 발생했습니다."}), 500

    # 실제 번역된 건수만큼만 무료 사용량 차감(정직).
    if translated > 0 and not _unlimited:
        try:
            translation_usage.increment(sid, translated)
        except Exception as exc:
            logger.warning("번역 사용량 증가 실패: %s", exc)
    new_remaining = _limit if _unlimited else max(0, _limit - (_used_before + translated))

    message = None
    if translated == 0 and blocked == 0:
        message = "번역기(OPENAI_API_KEY 또는 DEEPL_API_KEY)가 설정되지 않아 원문을 유지했습니다."
    elif blocked > 0:
        message = (f"무료 번역 {_limit}회를 모두 사용했습니다. {blocked}개는 번역하지 못했어요 — "
                   "구독하거나 토큰을 충전하면 계속 번역할 수 있습니다(결제 미설정 시 운영자 문의).")
    return jsonify({"ok": True, "updated": updated, "translated": translated,
                    "total": len(item_ids), "blocked": blocked,
                    "free_limit": _limit, "free_used": _used_before + translated,
                    "free_remaining": new_remaining, "unlimited": _unlimited,
                    "message": message, "results": results})


@bp.post("/collect/groups/create")
def collect_group_create():
    """상품 그룹 생성 (셀러 격리). Request: {"name": "..."}"""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "그룹 이름을 입력하세요."}), 400
    try:
        from . import collect_groups
        g = collect_groups.create_group(_seller_id(), name)
    except Exception as exc:
        logger.warning("그룹 생성 오류: %s", exc)
        return jsonify({"ok": False, "error": "그룹 생성 중 오류가 발생했습니다."}), 500
    if not g:
        return jsonify({"ok": False, "error": "그룹 이름이 올바르지 않습니다."}), 400
    return jsonify({"ok": True, "group": g})


@bp.post("/collect/groups/delete")
def collect_group_delete():
    """상품 그룹 삭제 (셀러 격리). Request: {"id": "..."}"""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    gid = str(data.get("id") or "").strip()
    if not gid:
        return jsonify({"ok": False, "error": "그룹 id가 필요합니다."}), 400
    try:
        from . import collect_groups
        ok = collect_groups.delete_group(_seller_id(), gid)
    except Exception as exc:
        logger.warning("그룹 삭제 오류: %s", exc)
        return jsonify({"ok": False, "error": "그룹 삭제 중 오류가 발생했습니다."}), 500
    return jsonify({"ok": bool(ok)})


@bp.post("/collect/bulk-group")
def collect_bulk_group():
    """선택 상품을 그룹에 일괄 배정 (셀러 격리). group_id="" 면 그룹 해제.

    Request: {"item_ids": [...], "group_id": "..."} (또는 "group_name" 신규 생성)
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids") if isinstance(data.get("item_ids"), list) else []
    item_ids = [str(i) for i in item_ids if str(i).strip()][:1000]
    if not item_ids:
        return jsonify({"ok": False, "error": "상품을 선택하세요."}), 400
    group_id = str(data.get("group_id") or "").strip()
    group_name = str(data.get("group_name") or "").strip()

    import json as _json
    from . import collect_history_store
    sid = _seller_id()
    group_obj = None
    if group_name and not group_id:
        try:
            from . import collect_groups
            group_obj = collect_groups.create_group(sid, group_name)
            group_id = (group_obj or {}).get("id", "")
        except Exception as exc:
            logger.warning("그룹 생성(배정 중) 오류: %s", exc)

    updated = 0
    try:
        for item_id in item_ids:
            item = collect_history_store.get(item_id, seller_ids=_seller_identities())
            if not item:
                continue
            try:
                extra = _json.loads(item.get("extra_json") or "{}")
            except (TypeError, ValueError):
                extra = {}
            if group_id:
                extra["group_id"] = group_id
            else:
                extra.pop("group_id", None)  # 그룹 해제
            if collect_history_store.update(item_id, seller_ids=_seller_identities(),
                                            extra_json=_json.dumps(extra, ensure_ascii=False)):
                updated += 1
    except Exception as exc:
        logger.warning("일괄 그룹 배정 오류: %s", exc)
        return jsonify({"ok": False, "error": "그룹 배정 중 오류가 발생했습니다."}), 500

    return jsonify({"ok": True, "updated": updated, "group": group_obj, "group_id": group_id})


@bp.get("/customs/pccc")
def pccc_page():
    """개인통관고유부호(PCCC) 입력·조회 페이지 (v3 P1-5)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from . import pccc_store
    q = request.args.get("q", "").strip()
    records = pccc_store.list_records(_seller_id(), q=q)
    return render_template("pccc.html", page="pccc", records=records, q=q)


@bp.post("/customs/pccc/add")
def pccc_add():
    """PCCC 추가. Request: {name, pccc, phone?, memo?}"""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    name = str(data.get("name") or "").strip()
    pccc = str(data.get("pccc") or "").strip()
    if not name or not pccc:
        return jsonify({"ok": False, "error": "이름과 통관고유부호를 입력하세요."}), 400
    from . import pccc_store
    valid = pccc_store.is_valid_pccc(pccc)
    try:
        rec = pccc_store.add(_seller_id(), name=name, pccc=pccc,
                             phone=str(data.get("phone") or ""), memo=str(data.get("memo") or ""))
    except Exception as exc:
        logger.warning("PCCC 추가 오류: %s", exc)
        return jsonify({"ok": False, "error": "저장 중 오류가 발생했습니다."}), 500
    # 형식이 P+12자리가 아니면 저장은 하되 경고(정직).
    msg = None if valid else "형식이 'P+12자리 숫자'와 달라요. 한 번 더 확인하세요(저장은 됨)."
    return jsonify({"ok": True, "record": rec, "valid_format": valid, "message": msg})


@bp.post("/customs/pccc/delete")
def pccc_delete():
    """PCCC 삭제. Request: {id}"""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    rid = str(data.get("id") or "").strip()
    if not rid:
        return jsonify({"ok": False, "error": "id가 필요합니다."}), 400
    from . import pccc_store
    return jsonify({"ok": bool(pccc_store.delete(_seller_id(), rid))})


@bp.get("/listing/word-rules")
def word_rules_page():
    """금지어/치환 규칙 설정 페이지 (v3 P1-5)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from . import word_rules
    rules = word_rules.get_rules(_seller_id())
    return render_template("word_rules.html", page="word_rules", rules=rules)


@bp.post("/listing/word-rules/save")
def word_rules_save():
    """규칙 저장. Request: {"banned": "..." or [...], "subs": [{from,to}...]}"""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    try:
        from . import word_rules
        norm = word_rules.save_rules(_seller_id(), data.get("banned"), data.get("subs"))
    except Exception as exc:
        logger.warning("규칙 저장 오류: %s", exc)
        return jsonify({"ok": False, "error": "규칙 저장 중 오류가 발생했습니다."}), 500
    return jsonify({"ok": True, "rules": norm})


@bp.post("/collect/bulk-clean")
def collect_bulk_clean():
    """선택 상품의 제목에 금지어/치환 규칙을 일괄 적용 (셀러 격리).

    Request: {"item_ids": [...]}
    Response: {"ok": true, "updated": N, "results": [{id, title, changed}]}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids") if isinstance(data.get("item_ids"), list) else []
    item_ids = [str(i) for i in item_ids if str(i).strip()][:1000]
    if not item_ids:
        return jsonify({"ok": False, "error": "상품을 선택하세요."}), 400

    import json as _json
    from . import collect_history_store, word_rules
    sid = _seller_id()
    rules = word_rules.get_rules(sid)
    if not rules.get("banned") and not rules.get("subs"):
        return jsonify({"ok": False, "error": "설정된 금지어/치환 규칙이 없습니다. 먼저 규칙을 저장하세요.",
                        "no_rules": True}), 400

    updated = 0
    results = []
    try:
        for item_id in item_ids:
            item = collect_history_store.get(item_id, seller_ids=_seller_identities())
            if not item:
                continue
            title = item.get("title") or ""
            res = word_rules.apply_rules(title, sid, rules=rules)
            if not res["changed"]:
                results.append({"id": item_id, "title": title, "changed": False})
                continue
            # extra_json의 title_ko도 함께 정제(표시 일관성)
            try:
                extra = _json.loads(item.get("extra_json") or "{}")
            except (TypeError, ValueError):
                extra = {}
            extra["title_ko"] = res["text"]
            ok = collect_history_store.update(item_id, seller_ids=_seller_identities(), title=res["text"],
                                              extra_json=_json.dumps(extra, ensure_ascii=False))
            if ok:
                updated += 1
            results.append({"id": item_id, "title": res["text"], "changed": True,
                            "removed": res["removed"], "substituted": res["substituted"]})
    except Exception as exc:
        logger.warning("상품명 정제 오류: %s", exc)
        return jsonify({"ok": False, "error": "상품명 정제 중 오류가 발생했습니다."}), 500

    return jsonify({"ok": True, "updated": updated, "results": results})


@bp.post("/media/process-image")
def media_process_image():
    """이미지 1장 정제(워터마크 제거·리사이즈·WebP·CDN 재호스팅) — image_pipeline 연결 (v3 P1-5).

    Request: {"image_url": "...", "channel"?: "..."}
    Response: {ok, processed_url, cdn_uploaded, watermark_removed, success, message}
    정직성: CDN(CLOUDINARY_*) 미설정/처리 미적용 시 원본 URL 유지 + 안내(가짜 호스팅 URL 금지).
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    image_url = str(data.get("image_url") or "").strip()
    if not image_url or not image_url.lower().startswith("http"):
        return jsonify({"ok": False, "error": "유효한 이미지 URL이 필요합니다."}), 400
    try:
        from src.media.image_pipeline import process_image
        res = process_image(image_url, channel=str(data.get("channel") or "default"))
        d = res.to_dict()
    except Exception as exc:
        logger.warning("이미지 처리 오류: %s", exc)
        return jsonify({"ok": False, "error": "이미지 처리 중 오류가 발생했습니다."}), 500
    processed = d.get("processed_url") or image_url
    cdn = bool(d.get("cdn_uploaded"))
    message = None
    if not cdn and processed == image_url:
        message = ("이미지 처리 결과를 호스팅할 CDN(CLOUDINARY_*)이 설정되지 않았거나 처리가 적용되지 "
                   "않아 원본 URL을 유지했습니다.")
    return jsonify({
        "ok": True,
        "processed_url": processed,
        "cdn_uploaded": cdn,
        "watermark_removed": bool(d.get("watermark_removed")),
        "success": bool(d.get("success", True)),
        "message": message,
    })


@bp.post("/collect/bulk-price")
def collect_bulk_price():
    """수집 이력 여러 항목에 목표 마진율/원가 배수를 일괄 적용 (셀러 격리).

    Request: {"item_ids": [...], "target_margin_pct"?: float, "price_multiplier"?: float}
      - target_margin_pct: 각 항목 extra_json.target_margin_pct 에 저장(업로드 시 사용).
      - price_multiplier: 저장된 수집가(원가)에 배수 적용(예 1.1 = +10%). >0 필요.
    Response: {"ok": true, "updated": N, "results": [...]}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids") if isinstance(data.get("item_ids"), list) else []
    item_ids = [str(i) for i in item_ids if str(i).strip()][:1000]
    if not item_ids:
        return jsonify({"ok": False, "error": "상품을 선택하세요."}), 400

    margin = data.get("target_margin_pct")
    multiplier = data.get("price_multiplier")
    try:
        margin = None if margin in (None, "") else float(margin)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "마진율이 올바르지 않습니다."}), 400
    try:
        multiplier = None if multiplier in (None, "") else float(multiplier)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "가격 배수가 올바르지 않습니다."}), 400
    if margin is None and multiplier is None:
        return jsonify({"ok": False, "error": "목표 마진율 또는 가격 배수 중 하나는 입력하세요."}), 400
    if margin is not None and not (0 <= margin <= 90):
        return jsonify({"ok": False, "error": "마진율은 0~90% 범위여야 합니다."}), 400
    if multiplier is not None and not (multiplier > 0):
        return jsonify({"ok": False, "error": "가격 배수는 0보다 커야 합니다."}), 400

    import json as _json
    from . import collect_history_store
    sid = _seller_id()
    updated = 0
    results = []
    try:
        for item_id in item_ids:
            item = collect_history_store.get(item_id, seller_ids=_seller_identities())
            if not item:
                results.append({"id": item_id, "ok": False, "error": "항목 없음"})
                continue
            try:
                extra = _json.loads(item.get("extra_json") or "{}")
            except (TypeError, ValueError):
                extra = {}
            fields = {}
            if margin is not None:
                extra["target_margin_pct"] = margin
                fields["extra_json"] = _json.dumps(extra, ensure_ascii=False)
            new_price = None
            if multiplier is not None:
                try:
                    cur = float(str(item.get("price") or "").replace(",", "").strip())
                    new_price = round(cur * multiplier, 2)
                    fields["price"] = str(new_price)
                except (TypeError, ValueError):
                    # 가격이 숫자가 아니면 가격 변경은 건너뛰되 마진은 적용(정직).
                    pass
            if not fields:
                results.append({"id": item_id, "ok": False, "error": "적용할 변경 없음(가격 비숫자)"})
                continue
            ok = collect_history_store.update(item_id, seller_ids=_seller_identities(), **fields)
            if ok:
                updated += 1
            results.append({"id": item_id, "ok": bool(ok), "price": new_price})
    except Exception as exc:
        logger.warning("일괄 가격/마진 오류: %s", exc)
        return jsonify({"ok": False, "error": "일괄 가격/마진 적용 중 오류가 발생했습니다."}), 500

    return jsonify({"ok": True, "updated": updated, "results": results})


# 일괄 상태변경 허용 값 (활성/보관)
_BULK_STATUS_ALLOWED = {"ok", "archived"}


@bp.post("/collect/bulk-status")
def collect_bulk_status():
    """수집 이력 여러 항목의 상태를 일괄 변경 (활성 ok / 보관 archived). 셀러 격리.

    Request: {"item_ids": [...], "status": "archived"}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids") if isinstance(data.get("item_ids"), list) else []
    item_ids = [str(i) for i in item_ids if str(i).strip()][:1000]
    status = str(data.get("status") or "").strip()
    if not item_ids:
        return jsonify({"ok": False, "error": "상품을 선택하세요."}), 400
    if status not in _BULK_STATUS_ALLOWED:
        return jsonify({"ok": False, "error": "상태값이 올바르지 않습니다."}), 400

    from . import collect_history_store
    sid = _seller_id()
    updated = 0
    try:
        for item_id in item_ids:
            if collect_history_store.update(item_id, seller_ids=_seller_identities(), status=status):
                updated += 1
    except Exception as exc:
        logger.warning("일괄 상태변경 오류: %s", exc)
        return jsonify({"ok": False, "error": "일괄 상태변경 중 오류가 발생했습니다."}), 500

    return jsonify({"ok": True, "updated": updated, "status": status})


@bp.post("/collect/bulk-duplicate")
def collect_bulk_duplicate():
    """수집 이력 여러 항목을 복제 (셀러 격리). 새 항목으로 추가.

    Request: {"item_ids": [...]}
    Response: {"ok": true, "duplicated": N, "new_ids": [...]}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids") if isinstance(data.get("item_ids"), list) else []
    item_ids = [str(i) for i in item_ids if str(i).strip()][:200]
    if not item_ids:
        return jsonify({"ok": False, "error": "상품을 선택하세요."}), 400

    import json as _json
    from . import collect_history_store
    sid = _seller_id()
    new_ids = []
    try:
        for item_id in item_ids:
            item = collect_history_store.get(item_id, seller_ids=_seller_identities())
            if not item:
                continue
            try:
                extra = _json.loads(item.get("extra_json") or "{}")
            except (TypeError, ValueError):
                extra = {}
            new_id = collect_history_store.append(
                source=item.get("source") or "manual",
                url=item.get("url") or "",
                title=((item.get("title") or "") + " (복제)").strip(),
                image=item.get("image_url") or "",
                price=item.get("price") or "",
                currency=item.get("currency") or "",
                status="ok",
                extra=extra,
                seller_id=sid,
            )
            new_ids.append(new_id)
    except Exception as exc:
        logger.warning("일괄 복제 오류: %s", exc)
        return jsonify({"ok": False, "error": "일괄 복제 중 오류가 발생했습니다."}), 500

    return jsonify({"ok": True, "duplicated": len(new_ids), "new_ids": new_ids})


# 속도: 첫 로드는 이 개수만 렌더(첫50) + 무한스크롤로 추가. 이름순도 전체 5000 로드 폐기 —
# 나이아 점프는 서버 버킷 인덱스(fs_buckets)로 해당 섹션만 lazy-fetch(fmt=rows&offset=…).
_FASTSCROLL_MAX = 5000   # (하위호환 상수 — 더는 전체 로드에 쓰지 않음)
_FS_PAGE = 50            # 첫 화면·무한스크롤 청크 크기

# 초성 버킷(JS kgp-fastscroll.js와 동일 규칙) — 서버가 버킷별 count/offset/샘플을 계산해
# 나이아 레일에 넘기면, 5000행을 DOM에 그리지 않고도 스크럽 오버레이·점프가 실데이터로 동작한다.
_FS_CHO19 = ["ㄱ", "ㄱ", "ㄴ", "ㄷ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅂ", "ㅅ", "ㅅ", "ㅇ",
             "ㅈ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
_FS_COMPAT = {
    "ㄱ": "ㄱ", "ㄲ": "ㄱ", "ㄳ": "ㄱ", "ㄴ": "ㄴ", "ㄵ": "ㄴ", "ㄶ": "ㄴ", "ㄷ": "ㄷ", "ㄸ": "ㄷ",
    "ㄹ": "ㄹ", "ㄺ": "ㄹ", "ㄻ": "ㄹ", "ㄼ": "ㄹ", "ㄽ": "ㄹ", "ㄾ": "ㄹ", "ㄿ": "ㄹ", "ㅀ": "ㄹ",
    "ㅁ": "ㅁ", "ㅂ": "ㅂ", "ㅃ": "ㅂ", "ㅄ": "ㅂ", "ㅅ": "ㅅ", "ㅆ": "ㅅ", "ㅇ": "ㅇ",
    "ㅈ": "ㅈ", "ㅉ": "ㅈ", "ㅊ": "ㅊ", "ㅋ": "ㅋ", "ㅌ": "ㅌ", "ㅍ": "ㅍ", "ㅎ": "ㅎ",
}


def _fs_bucket_of(key: str) -> str:
    s = (key or "").strip()
    if not s:
        return "#"
    ch = s[0]
    o = ord(ch)
    if 0xAC00 <= o <= 0xD7A3:               # 완성형 한글 → 초성
        return _FS_CHO19[(o - 0xAC00) // 588]
    if ch in _FS_COMPAT:                     # 호환 자모
        return _FS_COMPAT[ch]
    if ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
        return ch.upper()
    return "#"


def _fs_build_buckets(sorted_pairs):
    """정렬된 (title, img) 목록 → 버킷별 {count, offset, sample}(초성/A-Z/#).

    offset = 정렬 전체에서 그 버킷 첫 항목의 0-based 인덱스(무한스크롤 점프용).
    sample = 스크럽 오버레이용 실데이터(제목+이미지) 앞 12개(전체 렌더 없이 실데이터).
    """
    out: dict = {}
    for idx, (title, img) in enumerate(sorted_pairs):
        b = _fs_bucket_of(title)
        e = out.get(b)
        if e is None:
            out[b] = {"count": 1, "offset": idx, "sample": [{"title": title or "", "img": img or ""}]}
        else:
            e["count"] += 1
            if len(e["sample"]) < 12:
                e["sample"].append({"title": title or "", "img": img or ""})
    return out


@bp.get("/catalog")
def catalog():
    """상품 카탈로그 페이지 (Phase 128) — Sheets catalog 워크시트 뷰."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    page_num = max(1, request.args.get("page", 1, type=int))
    per_page = request.args.get("per_page", 50, type=int)
    if per_page not in (20, 50, 100):
        per_page = 50
    marketplace_filter = (request.args.get("marketplace") or "").strip()
    country_filter = (request.args.get("country") or "").strip().upper()
    state_filter = (request.args.get("state") or "").strip()
    search = (request.args.get("search") or "").strip().lower()
    sort = (request.args.get("sort") or "last_synced_desc").strip()
    # 속도: 무한스크롤·나이아 점프 공통 창(window) — offset부터 per_page개만 렌더.
    fmt = (request.args.get("fmt") or "").strip()
    offset = max(0, request.args.get("offset", 0, type=int))

    import time as _time
    _t0 = _time.monotonic()
    all_items = []
    total = 0
    source = "mock"
    error_msg = None

    try:
        from .market_status_sheets import MarketStatusSheetsAdapter
        from datetime import datetime
        from src.utils.perf import perf_block
        adapter = MarketStatusSheetsAdapter()
        with perf_block("db"):
            result = adapter.fetch_all()
        all_items = result.items
        source = result.source
        max_price_for_none = 10**15
        if marketplace_filter:
            all_items = [i for i in all_items if (i.marketplace or "") == marketplace_filter]
        if country_filter:
            all_items = [i for i in all_items if _marketplace_meta(i.marketplace).get("country") == country_filter]
        if state_filter:
            all_items = [i for i in all_items if (i.state or "") == state_filter]
        if search:
            all_items = [
                i
                for i in all_items
                if search in ((i.title or "").lower())
                or search in ((i.sku or "").lower())
                or search in ((i.product_id or "").lower())
            ]

        if sort == "last_synced_asc":
            all_items = sorted(all_items, key=lambda i: i.last_synced_at or datetime.min)
        elif sort == "price_desc":
            all_items = sorted(all_items, key=lambda i: i.price_krw or -1, reverse=True)
        elif sort == "price_asc":
            all_items = sorted(all_items, key=lambda i: i.price_krw if i.price_krw is not None else max_price_for_none)
        elif sort == "title_asc":
            all_items = sorted(all_items, key=lambda i: (i.title or "").lower())
        else:
            sort = "last_synced_desc"
            all_items = sorted(all_items, key=lambda i: i.last_synced_at or datetime.min, reverse=True)

        total = len(all_items)
    except Exception as exc:
        logger.warning("카탈로그 데이터 로드 실패: %s", exc)
        error_msg = str(exc)

    # 첫 화면·무한스크롤·나이아 점프 공통: offset부터 per_page개만(전체 5000 로드 폐기).
    items = all_items[offset:offset + per_page]
    has_more = (offset + len(items)) < total
    total_pages = max(1, (total + per_page - 1) // per_page)
    marketplace_options = [
        {"market": m, **_marketplace_meta(m)}
        for m in [
            "coupang",
            "smartstore",
            "11st",
            "kohganemultishop",
            "amazon",
            "ebay",
            "shopify",
            "shopee",
        ]
    ]
    country_options = sorted({str(o["country"]).upper() for o in marketplace_options if o.get("country")})
    view_items = []
    for item in items:
        meta = _marketplace_meta(item.marketplace)
        localized_title, is_fallback = _select_localized_field(item, str(meta.get("locale") or "ko-KR"), "title")
        market_price, price_note = _market_price_display(item, str(meta.get("currency") or "KRW"))
        view_items.append(
            {
                "marketplace": item.marketplace,
                "marketplace_label": _marketplace_label(item.marketplace),
                "country": meta.get("country"),
                "region": meta.get("region"),
                "currency": meta.get("currency"),
                "locale": meta.get("locale"),
                "is_ready": bool(meta.get("is_ready", True)),
                "product_id": item.product_id,
                "sku": item.sku,
                "title": localized_title,
                "is_localization_fallback": is_fallback,
                "state": item.state,
                "price_display": market_price,
                "price_note": price_note,
                "last_synced_at": item.last_synced_at,
            }
        )

    logger.info("[catalog] sort=%s total=%s offset=%s rendered=%s elapsed_ms=%.1f",
                sort, total, offset, len(view_items), (_time.monotonic() - _t0) * 1000)
    from src.utils.perf import perf_block as _pb

    # 무한스크롤·나이아 점프 요청 → 행 파셜만(경량).
    if fmt == "rows":
        with _pb("render"):
            return render_template("catalog_rows.html", items=view_items, offset=offset, has_more=has_more)

    # 전체 페이지: 이름순이면 나이아 버킷 인덱스(전체 렌더 없이 실데이터 샘플 + offset)를 넘긴다.
    fs_buckets = {}
    if sort == "title_asc":
        fs_buckets = _fs_build_buckets([((i.title or ""), "") for i in all_items])

    with _pb("render"):
      return render_template(
        "catalog.html",
        items=view_items,
        page="catalog",
        current_page=page_num,
        total_pages=total_pages,
        total=total,
        has_more=has_more,
        fs_buckets=fs_buckets,
        source=source,
        error_msg=error_msg,
        filters={
            "marketplace": marketplace_filter,
            "country": country_filter,
            "state": state_filter,
            "search": search,
            "sort": sort,
            "per_page": per_page,
        },
        marketplace_options=marketplace_options,
        country_options=country_options,
        fastscroll=(sort == "title_asc"),   # 이름순일 때만 인덱스 레일
    )


@bp.post("/catalog/<marketplace>/<product_id>/sync")
def catalog_sync_item(marketplace: str, product_id: str):
    """카탈로그 단일 상품 동기화(정직 모드 포함)."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    try:
        from datetime import datetime

        from .market_status_sheets import MarketStatusSheetsAdapter

        adapter = MarketStatusSheetsAdapter()
        result = adapter.fetch_all()
        if result.source == "mock":
            return jsonify(
                {
                    "ok": False,
                    "error": "실연동 설정이 없어 동기화를 실행할 수 없습니다. /seller/markets에서 연동 상태를 확인하세요.",
                }
            ), 503

        found = None
        for item in result.items:
            if (item.marketplace or "") == marketplace and str(item.product_id) == str(product_id):
                found = item
                break

        if found is None:
            return jsonify({"ok": False, "error": "상품을 찾을 수 없습니다."}), 404

        found.last_synced_at = datetime.now()
        if not adapter.upsert_item(found):
            return jsonify({"ok": False, "error": "동기화 저장에 실패했습니다."}), 503

        return jsonify({"ok": True, "marketplace": marketplace, "product_id": product_id})
    except Exception as exc:
        logger.warning("catalog_sync_item 오류 (%s/%s): %s", marketplace, product_id, exc)
        return jsonify({"ok": False, "error": "동기화 중 오류가 발생했습니다."}), 500


def _get_order_sync_service():
    """OrderSyncService 인스턴스 반환 (graceful import)."""
    try:
        from .orders.sync_service import OrderSyncService
        return OrderSyncService()
    except Exception as exc:
        logger.warning("OrderSyncService 로드 실패: %s", exc)
        return None


_ORDER_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "new": {"paid", "canceled"},
    "paid": {"preparing", "canceled", "refund_requested"},
    "preparing": {"shipped", "canceled"},
    "shipped": {"delivered", "returned", "exchanged"},
    "delivered": {"returned", "exchanged"},
    "refund_requested": {"returned", "canceled"},
    "returned": set(),
    "exchanged": set(),
    "canceled": set(),
}


def _log_order_op(level: str, action: str, marketplace: str = "-", order_id: str = "-", reason: str = "", exc: Exception | None = None) -> None:
    """주문 운영 로그 표준화 헬퍼.

    Args:
        level: "warning" 또는 "error". "error" 외 값은 warning으로 처리된다.
        action: 수행한 동작 식별자(e.g. status_update, bulk_tracking_update).
        marketplace: 대상 마켓 코드.
        order_id: 대상 주문 ID.
        reason: 실패/경고 원인 코드 또는 메시지.
        exc: 예외 객체(선택). error 레벨 로그의 스택트레이스에 포함된다.
    """
    message = "order_operation action=%s marketplace=%s order_id=%s reason=%s"
    if level == "error":
        logger.error(message, action, marketplace, order_id, reason, exc_info=exc)
        return
    logger.warning(message, action, marketplace, order_id, reason)


@bp.get("/orders")
def orders():
    """주문 관리 페이지 (Phase 129 — 실연동)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    filters = {
        "marketplace": request.args.getlist("marketplace") or None,
        "status": request.args.get("status") or None,
        "search": request.args.get("search") or None,
        "date_from": request.args.get("date_from") or None,
        "date_to": request.args.get("date_to") or None,
    }
    # None 값 제거
    filters = {k: v for k, v in filters.items() if v}

    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    svc = _get_order_sync_service()
    order_list = []
    kpi = {"today_new": 0, "pending_ship": 0, "shipped": 0, "returned_exchanged": 0, "source": "none"}
    ops_health = {
        "service_available": bool(svc),
        "routes": [
            {"method": "GET", "path": "/seller/orders", "healthy": True},
            {"method": "POST", "path": "/seller/orders/<marketplace>/<order_id>/status", "healthy": bool(svc)},
            {"method": "POST", "path": "/seller/orders/<marketplace>/<order_id>/tracking", "healthy": bool(svc)},
            {"method": "POST", "path": "/seller/orders/bulk/tracking", "healthy": bool(svc)},
            {"method": "GET", "path": "/seller/orders/export.csv", "healthy": bool(svc)},
        ],
    }
    if svc:
        order_list = svc.list_orders(filters=filters, limit=limit, offset=offset)
        kpi = svc.kpi_summary()

    from .orders.courier_catalog import get_courier_catalog
    order_dicts = [o.to_dict() for o in order_list]
    return render_template(
        "orders.html",
        page="orders",
        orders=order_dicts,
        kpi=kpi,
        filters=filters,
        limit=limit,
        offset=offset,
        ops_health=ops_health,
        courier_catalog=get_courier_catalog(include_dynamic=True),
    )


@bp.post("/orders/sync")
def orders_sync():
    """주문 동기화 트리거 (Phase 129).

    Response: {"ok": true, "results": {...}}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    svc = _get_order_sync_service()
    if svc is None:
        _log_order_op("warning", "orders_sync", reason="service_unavailable")
        return jsonify({"ok": False, "error": "OrderSyncService 준비 중입니다."}), 503

    try:
        results = svc.sync_all()
        return jsonify({"ok": True, "results": results})
    except Exception as exc:
        _log_order_op("error", "orders_sync", reason="internal_error", exc=exc)
        return jsonify({"ok": False, "error": "동기화 중 오류가 발생했습니다."}), 500


@bp.post("/orders/<marketplace>/<order_id>/status")
def order_update_status(marketplace: str, order_id: str):
    """주문 상태 전이 처리."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    svc = _get_order_sync_service()
    if svc is None:
        _log_order_op("warning", "status_update", marketplace=marketplace, order_id=order_id, reason="service_unavailable")
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    data = request.get_json(force=True, silent=True) or {}
    next_status = str(data.get("next_status") or "").strip().lower()
    reason = str(data.get("reason") or "").strip()
    if not next_status:
        _log_order_op("warning", "status_update", marketplace=marketplace, order_id=order_id, reason="missing_next_status")
        return jsonify({"ok": False, "error": "변경할 상태를 선택하세요."}), 400

    try:
        order_list = svc.list_orders(filters={"marketplace": marketplace, "search": order_id}, limit=10, offset=0)
        order = next((o for o in order_list if str(o.order_id) == str(order_id)), None)
        if order is None:
            _log_order_op("warning", "status_update", marketplace=marketplace, order_id=order_id, reason="order_not_found")
            return jsonify({"ok": False, "error": "주문을 찾을 수 없습니다."}), 404

        current_status = order.status.value if hasattr(order.status, "value") else str(order.status)
        allowed_next = _ORDER_STATUS_TRANSITIONS.get(current_status, set())
        if next_status == current_status:
            return jsonify({"ok": True, "status": current_status, "unchanged": True})
        if next_status not in allowed_next:
            _log_order_op(
                "warning",
                "status_update",
                marketplace=marketplace,
                order_id=order_id,
                reason=f"invalid_transition:{current_status}->{next_status}",
            )
            return jsonify(
                {
                    "ok": False,
                    "error": f"허용되지 않은 상태 전이입니다: {current_status} → {next_status}",
                    "allowed": sorted(allowed_next),
                }
            ), 400

        result = svc.update_status(order_id, marketplace, next_status, reason=reason)
        if not result.get("ok"):
            _log_order_op("warning", "status_update", marketplace=marketplace, order_id=order_id, reason=result.get("error") or "update_failed")
            return jsonify(result), 500
        return jsonify(result)
    except Exception as exc:
        _log_order_op("error", "status_update", marketplace=marketplace, order_id=order_id, reason="internal_error", exc=exc)
        return jsonify({"ok": False, "error": "상태 변경 중 오류가 발생했습니다."}), 500


@bp.get("/orders/<marketplace>/<order_id>")
def order_detail(marketplace: str, order_id: str):
    """주문 상세 조회 (JSON).

    Response: {"ok": true, "order": {...}}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    svc = _get_order_sync_service()
    if svc is None:
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    try:
        orders_list = svc.list_orders(
            filters={"marketplace": marketplace, "search": order_id},
            limit=1,
        )
        matched = [o for o in orders_list if o.order_id == order_id]
        if not matched:
            return jsonify({"ok": False, "error": "주문을 찾을 수 없습니다."}), 404
        return jsonify({"ok": True, "order": matched[0].to_dict()})
    except Exception as exc:
        logger.warning("order_detail 오류: %s", exc)
        return jsonify({"ok": False, "error": "조회 중 오류가 발생했습니다."}), 500


@bp.post("/orders/<marketplace>/<order_id>/tracking")
def order_tracking(marketplace: str, order_id: str):
    """운송장 등록 (Phase 129).

    Request body: {"courier": "CJ대한통운", "tracking_no": "1234567890"}
    Response: {"ok": true}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    courier = (data.get("courier") or "").strip()
    tracking_no = (data.get("tracking_no") or "").strip()

    if not courier or not tracking_no:
        _log_order_op("warning", "tracking_update", marketplace=marketplace, order_id=order_id, reason="missing_fields")
        return jsonify({"ok": False, "error": "택배사와 운송장 번호를 입력하세요."}), 400

    svc = _get_order_sync_service()
    if svc is None:
        _log_order_op("warning", "tracking_update", marketplace=marketplace, order_id=order_id, reason="service_unavailable")
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    try:
        ok = svc.update_tracking(order_id, marketplace, courier, tracking_no)
        return jsonify({"ok": ok})
    except Exception as exc:
        _log_order_op("error", "tracking_update", marketplace=marketplace, order_id=order_id, reason="internal_error", exc=exc)
        return jsonify({"ok": False, "error": "운송장 등록 중 오류가 발생했습니다."}), 500


@bp.post("/orders/bulk/tracking")
def orders_bulk_tracking():
    """일괄 운송장 등록 (Phase 129).

    Request body: {"items": [{"order_id": "...", "marketplace": "...", "courier": "...", "tracking_no": "..."}]}
    Response: {"ok": true, "results": [...]}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []

    if not items:
        _log_order_op("warning", "bulk_tracking_update", reason="empty_items")
        return jsonify({"ok": False, "error": "업데이트 항목이 없습니다."}), 400

    svc = _get_order_sync_service()
    if svc is None:
        _log_order_op("warning", "bulk_tracking_update", reason="service_unavailable")
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    results = []
    success_count = 0
    for item in items:
        order_id = str(item.get("order_id") or "").strip()
        marketplace = str(item.get("marketplace") or "").strip()
        courier = str(item.get("courier") or "").strip()
        tracking_no = str(item.get("tracking_no") or "").strip()
        if not order_id or not marketplace or not courier or not tracking_no:
            _log_order_op("warning", "bulk_tracking_update", marketplace=marketplace or "-", order_id=order_id or "-", reason="missing_item_fields")
            results.append(
                {
                    "order_id": order_id,
                    "marketplace": marketplace,
                    "ok": False,
                    "error": "주문번호/마켓/택배사/운송장 번호를 모두 입력하세요.",
                }
            )
            continue
        try:
            ok = svc.update_tracking(
                order_id,
                marketplace,
                courier,
                tracking_no,
            )
            if ok:
                success_count += 1
            results.append({"order_id": order_id, "marketplace": marketplace, "ok": ok})
        except Exception as exc:
            _log_order_op("error", "bulk_tracking_update", marketplace=marketplace, order_id=order_id, reason="internal_error", exc=exc)
            results.append({"order_id": order_id, "marketplace": marketplace, "ok": False, "error": "운송장 등록 중 오류가 발생했습니다."})

    failed_count = len([x for x in results if not x.get("ok")])
    return jsonify({"ok": failed_count == 0, "success_count": success_count, "failed_count": failed_count, "results": results})


@bp.post("/orders/bulk/status")
def orders_bulk_status():
    """선택 주문 일괄 상태 변경."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    next_status = str(data.get("next_status") or "").strip().lower()
    reason = str(data.get("reason") or "").strip()

    if not items:
        _log_order_op("warning", "bulk_status_update", reason="empty_items")
        return jsonify({"ok": False, "error": "상태를 변경할 주문이 없습니다."}), 400
    if not next_status:
        _log_order_op("warning", "bulk_status_update", reason="missing_next_status")
        return jsonify({"ok": False, "error": "변경할 상태를 선택하세요."}), 400

    svc = _get_order_sync_service()
    if svc is None:
        _log_order_op("warning", "bulk_status_update", reason="service_unavailable")
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    results = []
    success_count = 0
    for item in items:
        order_id = str(item.get("order_id") or "").strip()
        marketplace = str(item.get("marketplace") or "").strip()
        if not order_id or not marketplace:
            _log_order_op("warning", "bulk_status_update", marketplace=marketplace or "-", order_id=order_id or "-", reason="missing_item_fields")
            results.append({"order_id": order_id, "marketplace": marketplace, "ok": False, "error": "주문 식별자가 올바르지 않습니다."})
            continue

        try:
            order_list = svc.list_orders(filters={"marketplace": marketplace, "search": order_id}, limit=10, offset=0)
            order = next((o for o in order_list if str(o.order_id) == str(order_id)), None)
            if order is None:
                _log_order_op("warning", "bulk_status_update", marketplace=marketplace, order_id=order_id, reason="order_not_found")
                results.append({"order_id": order_id, "marketplace": marketplace, "ok": False, "error": "주문을 찾을 수 없습니다."})
                continue

            current_status = order.status.value if hasattr(order.status, "value") else str(order.status)
            allowed_next = _ORDER_STATUS_TRANSITIONS.get(current_status, set())
            if next_status == current_status:
                results.append({"order_id": order_id, "marketplace": marketplace, "ok": True, "status": current_status, "unchanged": True})
                success_count += 1
                continue
            if next_status not in allowed_next:
                _log_order_op(
                    "warning",
                    "bulk_status_update",
                    marketplace=marketplace,
                    order_id=order_id,
                    reason=f"invalid_transition:{current_status}->{next_status}",
                )
                results.append(
                    {
                        "order_id": order_id,
                        "marketplace": marketplace,
                        "ok": False,
                        "error": f"허용되지 않은 상태 전이입니다: {current_status} → {next_status}",
                        "allowed": sorted(allowed_next),
                    }
                )
                continue

            result = svc.update_status(order_id, marketplace, next_status, reason=reason)
            if result.get("ok"):
                success_count += 1
                results.append(
                    {
                        "order_id": order_id,
                        "marketplace": marketplace,
                        "ok": True,
                        "status": result.get("status") or next_status,
                        "adapter": result.get("adapter"),
                        "unchanged": result.get("unchanged", False),
                    }
                )
            else:
                _log_order_op("warning", "bulk_status_update", marketplace=marketplace, order_id=order_id, reason=result.get("error") or "update_failed")
                results.append({"order_id": order_id, "marketplace": marketplace, "ok": False, "error": result.get("error") or "상태 변경 실패"})
        except Exception as exc:
            _log_order_op("error", "bulk_status_update", marketplace=marketplace, order_id=order_id, reason="internal_error", exc=exc)
            results.append({"order_id": order_id, "marketplace": marketplace, "ok": False, "error": "상태 변경 중 오류가 발생했습니다."})

    failed_count = len([x for x in results if not x.get("ok")])
    return jsonify({"ok": failed_count == 0, "success_count": success_count, "failed_count": failed_count, "results": results})


@bp.get("/orders/export.csv")
def orders_export_csv():
    """주문 목록 CSV 내보내기 (Phase 129)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    import csv
    import io
    from flask import Response

    svc = _get_order_sync_service()
    if svc is None:
        _log_order_op("warning", "orders_export_csv", reason="service_unavailable")
        return Response(
            "주문 서비스가 준비 중입니다. 잠시 후 다시 시도하세요.",
            status=503,
            mimetype="text/plain; charset=utf-8",
        )

    try:
        orders_list = svc.list_orders(limit=1000)
    except Exception as exc:
        _log_order_op("error", "orders_export_csv", reason="internal_error", exc=exc)
        return Response(
            "주문 CSV 생성 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
            status=500,
            mimetype="text/plain; charset=utf-8",
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "order_id", "marketplace", "status", "placed_at",
        "buyer_name_masked", "total_krw", "items_count",
        "courier", "tracking_no", "notes",
    ])
    for o in orders_list:
        writer.writerow([
            o.order_id, o.marketplace,
            o.status.value if hasattr(o.status, "value") else o.status,
            o.placed_at.isoformat() if o.placed_at else "",
            o.buyer_name_masked or "",
            str(o.total_krw),
            len(o.items),
            o.courier or "",
            o.tracking_no or "",
            o.notes or "",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders.csv"},
    )


@bp.get("/api-status")
def api_status():
    """API 상태 페이지 (관리자 전용 — v17: 일반 유저에게 개발 안내 비노출)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    if not _is_admin_user():
        return redirect(url_for("seller_console.index"))

    try:
        from src.utils.env_catalog import get_api_status as _get_api_status
        api_data = _get_api_status()
        # api_data 는 dict (categories, apis, summary, render_env_note)
        api_list = api_data.get("apis", [])
        summary = api_data.get("summary", {})
        categories = api_data.get("categories", [])
        render_env_note = api_data.get("render_env_note", "")
    except Exception as exc:
        logger.warning("API 상태 로드 실패: %s", exc)
        api_list = []
        summary = {}
        categories = []
        render_env_note = ""

    return render_template(
        "api_status.html",
        page="api_status",
        api_list=api_list,
        summary=summary,
        categories=categories,
        render_env_note=render_env_note,
    )


@bp.get("/api/status")
def api_status_alias():
    """API 상태 별칭 경로 (Phase 145)."""
    return redirect(url_for("seller_console.api_status"))


@bp.get("/api-status/json")
def api_status_json():
    """API 상태 JSON 응답 (관리자 전용 — v17)."""
    if not _check_auth() or not _is_admin_user():
        return jsonify({"ok": False, "error": "권한이 없습니다."}), 403
    try:
        from src.utils.env_catalog import get_api_status as _get_api_status
        data = _get_api_status()
        return jsonify({"ok": True, **data})
    except Exception as exc:
        logger.warning("API 상태 JSON 오류: %s", exc)
        # 내부 오류 메시지를 외부에 노출하지 않음
        return jsonify({"ok": False, "error": "API 상태 로드 중 오류가 발생했습니다."}), 500


@bp.get("/notifications")
def notifications():
    """알림 설정 페이지 (Phase 133)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    from src.utils.env_catalog import is_active as _is_active
    telegram_active = _is_active("telegram")
    resend_active = _is_active("resend")
    return render_template(
        "notifications.html",
        page="notifications",
        telegram_active=telegram_active,
        resend_active=resend_active,
    )


@bp.post("/notifications/test")
def notifications_test():
    """텔레그램 테스트 메시지 전송 (Phase 130)."""
    try:
        from src.notifications.telegram import send_telegram
        ok = send_telegram("✅ 고가브릿지 알림 테스트 메시지입니다.", urgency="info")
        if ok:
            return jsonify({"ok": True, "message": "텔레그램 메시지 전송 성공"})
        return jsonify({"ok": False, "message": "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 미설정 — 알림 비활성"}), 200
    except Exception as exc:
        logger.warning("텔레그램 테스트 오류: %s", exc)
        return jsonify({"ok": False, "error": "메시지 전송 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# 마이페이지 (Phase 133)
# ---------------------------------------------------------------------------

@bp.get("/me")
def my_page():
    """셀러 마이페이지 (Phase 133)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from flask import session as _session
    user_id = _session.get("user_id")
    user = None
    if user_id:
        try:
            from src.auth.user_store import get_store
            user = get_store().find_by_id(user_id)
        except Exception as exc:
            logger.warning("마이페이지 사용자 조회 실패: %s", exc)

    # v34 P0: 개인 전용 작업공간 — 내 플랜·토큰·연동 마켓·소싱처·수집 수(전부 본인 스코프, 가짜 0 금지)
    sid = _seller_id()
    plan, token_balance = "free", 0
    try:
        from . import billing_store
        _acc = billing_store.get_account(sid) or {}
        plan = _acc.get("plan", "free")
        token_balance = int(_acc.get("token_balance", 0) or 0)
    except Exception:
        pass
    markets_connected, markets_total = 0, 0
    try:
        from . import market_credentials as _mc
        markets_total = len(_mc.SUPPORTED_MARKETS)
        markets_connected = sum(1 for m in _mc.SUPPORTED_MARKETS if _mc.is_connected(sid, m))
    except Exception:
        pass
    sources_count = 0
    try:
        from .my_sources_store import list_sources as _list_my_sources
        sources_count = len(_list_my_sources())
    except Exception:
        pass
    collected_count = 0
    try:
        collected_count = int((collect_history_store.summary(seller_ids=_seller_identities()) or {}).get("total", 0))
    except Exception:
        pass
    from . import billing_store as _bs
    plan_meta = _bs.PLANS.get(plan, _bs.PLANS["free"])

    return render_template(
        "me.html",
        page="me",
        user=user,
        telegram_active=bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        resend_active=bool(os.getenv("RESEND_API_KEY")),
        plan=plan,
        plan_meta=plan_meta,
        token_balance=token_balance,
        markets_connected=markets_connected,
        markets_total=markets_total,
        sources_count=sources_count,
        collected_count=collected_count,
    )


@bp.post("/me/deactivate")
def deactivate_account():
    """계정 비활성화 (soft delete, Phase 133)."""
    from flask import session as _session
    user_id = _session.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    try:
        from src.auth.user_store import get_store
        store = get_store()
        user = store.find_by_id(user_id)
        if user:
            user.active = False
            store.update(user)
        _session.clear()
        return jsonify({"ok": True, "message": "계정이 비활성화되었습니다."})
    except Exception as exc:
        logger.warning("계정 비활성화 오류: %s", exc)
        return jsonify({"ok": False, "error": "계정 비활성화 중 오류가 발생했습니다."}), 500


@bp.get("/pricing")
def pricing():
    """마진 계산기 페이지."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    all_marketplaces = [
        {"id": "coupang", "label": "쿠팡"},
        {"id": "smartstore", "label": "스마트스토어"},
        {"id": "11st", "label": "11번가"},
        {"id": "kohganemultishop", "label": "코가네멀티샵"},
        {"id": "shopify", "label": "Shopify"},
    ]
    return render_template(
        "pricing_console.html",
        page="pricing",
        all_marketplaces=all_marketplaces,
        default_currencies=["KRW", "USD", "JPY", "EUR", "CNY"],
        default_target_margin=22,
    )


@bp.get("/margin")
def margin_alias():
    """마진 계산기 별칭 경로 (Phase 145)."""
    return redirect(url_for("seller_console.pricing"))


@bp.post("/pricing/calc")
def pricing_calc():
    """단일 마켓 마진 계산 (JSON).

    Request body: 계산 파라미터
    Response: {"ok": true, "result": {...}}
    """
    data = request.get_json(force=True, silent=True) or {}

    try:
        buy_price = Decimal(str(data.get("buy_price", 0)))
        currency = str(data.get("currency", "USD")).upper()
        qty = int(data.get("qty", 1))
        forwarder_fee = Decimal(str(data.get("forwarder_fee", 0)))
        international_shipping = Decimal(str(data.get("international_shipping", 0)))
        domestic_shipping = Decimal(str(data.get("domestic_shipping", 0)))
        # 하위 호환: shipping_fee → domestic_shipping 으로 매핑
        if "shipping_fee" in data and not data.get("domestic_shipping"):
            domestic_shipping = Decimal(str(data["shipping_fee"]))
        customs_rate_pct = Decimal(str(data.get("customs_rate", 20)))
        customs_rate = customs_rate_pct / Decimal("100")
        marketplace = str(data.get("marketplace", "coupang"))
        # 하위 호환: market_fee_rate 직접 지정 허용
        if "market_fee_rate" in data:
            commission_rate = Decimal(str(data["market_fee_rate"]))
        else:
            from .margin_calculator import default_commission_rate
            commission_rate = default_commission_rate(marketplace)
        pg_fee_rate = Decimal(str(data.get("pg_fee_rate", 0)))
        target_margin_pct = Decimal(str(data.get("target_margin_pct", 22)))
        sell_price_raw = data.get("sell_price")
        sell_price = Decimal(str(sell_price_raw)) if sell_price_raw else None
        fx_override_raw = data.get("fx_override") or data.get("fx_rate")
        fx_override = Decimal(str(fx_override_raw)) if fx_override_raw else None
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"ok": False, "error": "입력값 형식이 올바르지 않습니다."}), 400

    if buy_price <= Decimal("0"):
        return jsonify({"ok": False, "error": "매입가를 입력하세요."}), 400

    try:
        from .margin_calculator import CostInput, MarginCalculator, MarketInput
        cost = CostInput(
            buy_price=buy_price,
            buy_currency=currency,
            qty=qty,
            forwarder_fee=forwarder_fee,
            international_shipping=international_shipping,
            domestic_shipping=domestic_shipping,
            customs_rate=customs_rate,
            fx_override=fx_override,
        )
        market = MarketInput(
            marketplace=marketplace,
            commission_rate=commission_rate,
            pg_fee_rate=pg_fee_rate,
            target_margin_pct=target_margin_pct,
        )
        calc = MarginCalculator()
        result = calc.calculate(cost, market, sell_price=sell_price)
        return jsonify({"ok": True, "result": _result_to_dict(result)})
    except Exception as exc:
        logger.warning("마진 계산 오류: %s", exc)
        return jsonify({"ok": False, "error": "계산 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/compare")
def pricing_compare():
    """여러 마켓 동시 비교 (JSON).

    Request body: 계산 파라미터 + marketplaces 목록
    Response: {"ok": true, "results": [...]}
    """
    data = request.get_json(force=True, silent=True) or {}

    try:
        buy_price = Decimal(str(data.get("buy_price", 0)))
        currency = str(data.get("currency", "USD")).upper()
        qty = int(data.get("qty", 1))
        forwarder_fee = Decimal(str(data.get("forwarder_fee", 0)))
        international_shipping = Decimal(str(data.get("international_shipping", 0)))
        domestic_shipping = Decimal(str(data.get("domestic_shipping", 0)))
        if "shipping_fee" in data and not data.get("domestic_shipping"):
            domestic_shipping = Decimal(str(data["shipping_fee"]))
        customs_rate_pct = Decimal(str(data.get("customs_rate", 20)))
        customs_rate = customs_rate_pct / Decimal("100")
        target_margin_pct = Decimal(str(data.get("target_margin_pct", 22)))
        marketplaces = data.get("marketplaces") or ["coupang", "smartstore", "11st", "kohganemultishop"]
        sell_price_raw = data.get("sell_price")
        sell_price = Decimal(str(sell_price_raw)) if sell_price_raw else None
        fx_override_raw = data.get("fx_override") or data.get("fx_rate")
        fx_override = Decimal(str(fx_override_raw)) if fx_override_raw else None
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"ok": False, "error": "입력값 형식이 올바르지 않습니다."}), 400

    if buy_price <= Decimal("0"):
        return jsonify({"ok": False, "error": "매입가를 입력하세요."}), 400

    try:
        from .margin_calculator import CostInput, MarginCalculator
        cost = CostInput(
            buy_price=buy_price,
            buy_currency=currency,
            qty=qty,
            forwarder_fee=forwarder_fee,
            international_shipping=international_shipping,
            domestic_shipping=domestic_shipping,
            customs_rate=customs_rate,
            fx_override=fx_override,
        )
        cost.customs_threshold_krw = Decimal(str(data.get("customs_threshold_krw", 150000)))
        calc = MarginCalculator()
        results = calc.compare_marketplaces(
            cost,
            marketplaces=marketplaces,
            sell_price=sell_price,
        )
        return jsonify({
            "ok": True,
            "results": [_result_to_dict(r) for r in results],
            "target_margin_pct": str(target_margin_pct),
        })
    except Exception as exc:
        logger.warning("마진 비교 계산 오류: %s", exc)
        return jsonify({"ok": False, "error": "계산 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/apply")
def pricing_apply():
    """계산된 판매가를 상품에 실제 반영(로컬 저장 + 가능 시 마켓 어댑터 적용)."""
    data = request.get_json(force=True, silent=True) or {}
    marketplace = str(data.get("marketplace") or "").strip()
    product_id = str(data.get("product_id") or "").strip()
    sku = str(data.get("sku") or "").strip()
    note = str(data.get("note") or "").strip()
    try:
        new_price = int(Decimal(str(data.get("price"))))
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({"ok": False, "error": "유효한 판매가를 입력하세요."}), 400
    if new_price <= 0:
        return jsonify({"ok": False, "error": "판매가는 1원 이상이어야 합니다."}), 400
    if not marketplace:
        return jsonify({"ok": False, "error": "marketplace가 필요합니다."}), 400

    try:
        from .market_status_sheets import MarketStatusSheetsAdapter
        from .market_adapters.coupang_adapter import CoupangAdapter
        from .market_adapters.smartstore_adapter import SmartStoreAdapter
        from .market_adapters.eleven_adapter import ElevenAdapter
        from .market_adapters.woocommerce_adapter import WooCommerceAdapter
        from src.pricing.history_store import PriceHistoryStore
    except Exception as exc:
        logger.warning("pricing_apply 모듈 로드 실패: %s", exc)
        return jsonify({"ok": False, "error": "가격 반영 모듈 준비 중입니다."}), 503

    adapter = MarketStatusSheetsAdapter()
    fetched = adapter.fetch_all()
    target = None
    for item in fetched.items:
        if product_id and str(item.product_id) != product_id:
            continue
        if str(item.marketplace or "") != marketplace:
            continue
        if sku and str(item.sku or "") != sku:
            continue
        target = item
        break
    if target is None:
        return jsonify({"ok": False, "error": "가격을 반영할 상품을 찾을 수 없습니다."}), 404

    old_price = int(target.price_krw or 0)
    target.price_krw = new_price
    target.last_synced_at = datetime.now(timezone.utc)
    applied_local = adapter.upsert_item(target)
    if not applied_local:
        return jsonify({"ok": False, "error": "카탈로그 가격 저장에 실패했습니다."}), 500

    adapter_map = {
        "coupang": CoupangAdapter(),
        "smartstore": SmartStoreAdapter(),
        "11st": ElevenAdapter(),
        "kohganemultishop": WooCommerceAdapter(),
        "woocommerce": WooCommerceAdapter(),
    }
    market_adapter = adapter_map.get(marketplace)
    market_result = {"applied": False, "simulated": True}
    if market_adapter and hasattr(market_adapter, "update_price") and target.sku:
        try:
            result = market_adapter.update_price(target.sku, new_price)
            market_result["applied"] = bool(result.get("updated") or result.get("ok"))
            market_result["simulated"] = bool(result.get("_dry_run") or result.get("reason") == "missing_credentials")
            market_result["detail"] = result
        except Exception as exc:
            logger.warning("마켓 가격 반영 실패 (%s/%s): %s", marketplace, target.sku, exc)
            market_result["detail"] = {"error": str(exc)}
    else:
        market_result["detail"] = {"reason": "adapter_unavailable_or_sku_missing"}

    try:
        PriceHistoryStore().append(
            sku=target.sku or target.product_id,
            old_price_krw=old_price,
            new_price_krw=new_price,
            rules_applied=["manual_apply"],
            applied_by="seller_console",
        )
    except Exception as exc:
        logger.warning("가격 이력 저장 실패: %s", exc)

    message = "가격이 저장되었습니다."
    if market_result.get("simulated") and not market_result.get("applied"):
        message = "가격이 로컬에 저장되었습니다. 외부 마켓은 미연동/시뮬레이션 상태입니다."
    if note:
        message = f"{message} ({note})"

    return jsonify(
        {
            "ok": True,
            "marketplace": marketplace,
            "product_id": target.product_id,
            "sku": target.sku,
            "old_price": old_price,
            "new_price": new_price,
            "market_result": market_result,
            "message": message,
        }
    )


@bp.get("/market-status")
def market_status():
    """마켓 상품 현황 페이지 (기존 URL 유지 — /seller/markets로 리다이렉트)."""
    return redirect(url_for("seller_console.markets_overview"))


@bp.get("/markets")
def markets_overview():
    """마켓 현황 상세 페이지 (Phase 127)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from .market_status_service import MarketStatusService
        svc = MarketStatusService()
        result = svc.get_all()
        market_data = result.to_legacy_dict()
        for market in market_data.get("markets", []):
            meta = _marketplace_meta(market.get("marketplace", ""))
            market["country"] = meta.get("country")
            market["currency"] = meta.get("currency")
            market["locale"] = meta.get("locale")
            market["region"] = meta.get("region")
            market["is_ready"] = bool(meta.get("is_ready", True))
        # items도 템플릿에 전달
        items = []
        for item in result.items:
            meta = _marketplace_meta(item.marketplace)
            price_display, price_note = _market_price_display(item, str(meta.get("currency") or "KRW"))
            items.append(
                {
                    "marketplace": item.marketplace,
                    "marketplace_label": _marketplace_label(item.marketplace),
                    "country": meta.get("country"),
                    "currency": meta.get("currency"),
                    "region": meta.get("region"),
                    "locale": meta.get("locale"),
                    "is_ready": bool(meta.get("is_ready", True)),
                    "product_id": item.product_id,
                    "sku": item.sku or "",
                    "title": item.title or "",
                    "state": item.state,
                    "price_display": price_display,
                    "price_note": price_note,
                    "last_synced_at": item.last_synced_at.isoformat() if item.last_synced_at else "",
                    "error_message": item.error_message or "",
                }
            )
        marketplace_filters = [
            {
                "marketplace": market_code,
                **_marketplace_meta(market_code),
            }
            for market_code in ["coupang", "smartstore", "11st", "kohganemultishop", "amazon", "ebay", "shopify", "shopee"]
        ]
        country_filters = sorted({str(m["country"]).upper() for m in marketplace_filters if m.get("country")})
        summary_by_market = {
            str(m.get("marketplace") or ""): m
            for m in market_data.get("markets", [])
            if isinstance(m, dict)
        }
    except Exception as exc:
        logger.warning("마켓 현황 데이터 로드 실패: %s", exc)
        from .data_aggregator import get_market_product_status
        market_data = get_market_product_status()
        items = []
        marketplace_filters = []
        country_filters = []
        summary_by_market = {}

    market_hub_cards = []
    try:
        from .market_integration_diagnostics import MARKET_GUIDES, market_status_badge
    except Exception:
        MARKET_GUIDES = {}
        market_status_badge = lambda status: {"label": status, "class_name": "bg-secondary"}  # type: ignore[assignment]
    for market_code in ["shopify", "coupang", "smartstore", "11st", "amazon", "ebay", "shopee", "woocommerce"]:
        meta = _marketplace_meta(market_code)
        summary = summary_by_market.get(market_code, {})
        configured = _market_configured_for_seller(market_code)
        status_label = "연결됨" if configured else "미연동"
        status_style = "success" if configured else "secondary"
        note = ""
        if market_code == "woocommerce":
            note = "kohganemultishop.org (WordPress/WooCommerce) — 별도 트랙, 연동 예정/별도 설정"
            status_style = "warning"
            status_label = "별도 트랙"
        elif market_code in {"amazon", "ebay", "shopee"}:
            note = "글로벌 확장 스텁 — 연동 예정"
        elif not configured:
            note = _market_required_env_hint(market_code)

        diagnostic_meta = MARKET_GUIDES.get(market_code, {})
        pending_badge = market_status_badge("api_error") if diagnostic_meta else {"label": "", "class_name": "bg-secondary"}
        market_hub_cards.append(
            {
                "marketplace": market_code,
                "label": meta.get("label"),
                "currency": meta.get("currency"),
                "country": meta.get("country"),
                "status_label": status_label,
                "status_style": status_style,
                "total": int(summary.get("total") or 0),
                "active": int(summary.get("active") or 0),
                "last_synced_at": market_data.get("fetched_at") or "",
                "note": note,
                "integration_supported": bool(diagnostic_meta),
                "docs_path": diagnostic_meta.get("docs_path", ""),
                "required_env": diagnostic_meta.get("required_env", []),
                "required_scopes": diagnostic_meta.get("required_scopes", []),
                "check_locations": diagnostic_meta.get("check_locations", []),
                "pending_badge_label": pending_badge.get("label", ""),
                "pending_badge_class": pending_badge.get("class_name", "bg-secondary"),
            }
        )

    return render_template(
        "markets.html",
        market_data=market_data,
        items=items,
        marketplace_filters=marketplace_filters,
        country_filters=country_filters,
        market_hub_cards=market_hub_cards,
        page="market_status",
    )


@bp.get("/markets/status")
def markets_status():
    """JSON: 모든 마켓 상태 (Phase 127)."""
    try:
        from .market_status_service import MarketStatusService
        svc = MarketStatusService()
        result = svc.get_all()
        return jsonify({
            "summaries": [s.to_dict() for s in result.summaries],
            "fetched_at": result.fetched_at.isoformat(),
            "source": result.source,
        })
    except Exception as exc:
        logger.warning("markets_status API 오류: %s", exc)
        return jsonify({"error": "마켓 상태 조회 중 오류가 발생했습니다."}), 500


@bp.post("/markets/sync")
def markets_sync():
    """라이브 동기화 트리거 (Phase 127 — stub, Phase 130에서 실 API 활성화).

    Request body: {"marketplace": "coupang" | "all"}
    Response: {"coupang": 0, ...}
    """
    data = request.get_json(force=True, silent=True) or {}
    marketplace = str(data.get("marketplace", "all")).strip()

    try:
        from .market_status_service import MarketStatusService
        svc = MarketStatusService()
        if marketplace == "all":
            results = {m: svc.sync_marketplace(m) for m in svc.live_adapters}
        else:
            results = {marketplace: svc.sync_marketplace(marketplace)}
        return jsonify({"ok": True, "results": results})
    except Exception as exc:
        logger.warning("markets_sync API 오류: %s", exc)
        return jsonify({"error": "동기화 중 오류가 발생했습니다."}), 500


@bp.post("/markets/shopify/check-connection")
def markets_shopify_check_connection():
    """JSON: Shopify 연결 자가진단."""
    if not _check_auth():
        return jsonify({"ok": False, "status": "unauthorized", "message": "로그인이 필요합니다."}), 401

    try:
        from src.markets.adapters.shopify import ShopifyAdapter
        from . import market_credentials as mc

        with mc.temp_env(mc.all_credential_env(_seller_id())):
            result = ShopifyAdapter().check_connection()
        return jsonify(result), 200
    except Exception as exc:
        logger.warning("markets_shopify_check_connection API 오류: %s", exc)
        return jsonify(
            {
                "ok": False,
                "status": "internal_error",
                "message": "Shopify 연결 확인 중 오류가 발생했습니다.",
            }
        ), 500


@bp.get("/markets/integration-diagnostics")
def markets_integration_diagnostics():
    """JSON: 마켓 실연동 smoke 진단."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    try:
        from .market_integration_diagnostics import normalize_market_diagnostic_result, run_all_market_diagnostics
        from . import market_credentials as mc

        with mc.temp_env(mc.all_credential_env(_seller_id())):
            results = [normalize_market_diagnostic_result(item) for item in run_all_market_diagnostics()]
        return jsonify({"ok": True, "results": results}), 200
    except Exception as exc:
        logger.warning("markets_integration_diagnostics API 오류: %s", exc)
        return jsonify({"ok": False, "error": "마켓 연동 진단 중 오류가 발생했습니다."}), 500


@bp.post("/markets/integration-diagnostics")
def markets_integration_diagnostics_refresh():
    """JSON: 단일 마켓 smoke 진단 재실행."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(force=True, silent=True) or {}
    market = str(data.get("market") or "").strip().lower()
    if not market:
        return jsonify({"ok": False, "error": "market 값이 필요합니다."}), 400

    try:
        from .market_integration_diagnostics import normalize_market_diagnostic_result, run_market_diagnostic
        from . import market_credentials as mc

        with mc.temp_env(mc.all_credential_env(_seller_id())):
            result = normalize_market_diagnostic_result(run_market_diagnostic(market))
        return jsonify({"ok": True, "result": result}), 200
    except KeyError:
        return jsonify({"ok": False, "error": "지원하지 않는 마켓입니다."}), 404
    except Exception as exc:
        logger.warning("markets_integration_diagnostics_refresh API 오류 (%s): %s", market, exc)
        return jsonify({"ok": False, "error": "마켓 연동 진단 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# 셀프서비스 마켓 연결 (SaaS 대비) — 셀러가 직접 키 입력/테스트/저장
# ---------------------------------------------------------------------------

def _seller_id() -> str:
    """현재 셀러 식별자. 단일 테넌트(오너)/요청 컨텍스트 밖에서는 'default'."""
    try:
        return str(session.get("user_id") or session.get("user_email") or "default")
    except Exception:
        return "default"


def _seller_identities() -> set:
    """현재 사용자의 식별자 집합(user_id + email + 기본키) — 수집 저장 seller_id와
    이력 필터 seller_id가 별칭(user_id vs email)으로 어긋날 때도 본인 항목을 보이게
    하는 관용 매칭용(v9 P0). 모두 '본인' 값이라 타 셀러 누출 없음.
    """
    ids = set()
    try:
        for v in (session.get("user_id"), session.get("user_email")):
            if v:
                ids.add(str(v))
    except Exception:
        pass
    ids.add(_seller_id())
    return ids


def _get_owned_item(item_id: str) -> "dict | None":
    """수집 항목 단건 — 목록과 동일한 관용 식별자 스코프로 조회(v30 단일소스).

    목록(list_items)은 seller_ids 집합으로 보여주는데 상세/저장이 exact seller_id로
    조회하면 별칭(user_id vs email) 불일치 시 목록엔 보이는데 클릭하면 404가 났다(v30 회귀).
    같은 스코프(seller_ids)로 통일해 재발을 막는다.
    """
    try:
        from .collect_history_store import get as history_get
        return history_get(item_id, seller_ids=_seller_identities())
    except Exception as exc:
        logger.warning("수집 항목 조회 실패(id=%s): %s", item_id, exc)
        return None


def _diag_market_key(market: str) -> str:
    """자격증명 마켓 키 → 진단 서브시스템 키 (11번가만 상이)."""
    return "11st" if market == "elevenst" else market


def _connect_market_key(market: str) -> str:
    """진단/URL 키 → 자격증명 저장 키 (11st → elevenst)."""
    m = (market or "").strip().lower()
    return "elevenst" if m == "11st" else m


@bp.get("/markets/connect")
def markets_connect():
    """셀프서비스 마켓 연결 관리 화면 (전체)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from . import market_credentials as mc
    from .market_guide import guide_map

    seller = _seller_id()
    statuses = mc.all_status(seller)
    chips = [{"market": s["market"], "label": s["label"], "connected": s["connected"]} for s in statuses]
    return render_template(
        "markets_connect.html", page="markets",
        market_statuses=statuses, market_chips=chips, single_market=None, guide_entry=None,
        guide_map=guide_map(), server_ip=_server_outbound_ip(),
    )


# 서버 아웃바운드 IP 캐시(쿠팡/네이버 허용 IP 등록용 — 화면에 복사 제공)
_SERVER_IP_CACHE = {"ip": None, "tried": False}


def _server_outbound_ip() -> str:
    """서버 아웃바운드 IP. env SERVER_OUTBOUND_IP 우선, 없으면 1회 조회·캐시(실패 시 '')."""
    env_ip = (os.getenv("SERVER_OUTBOUND_IP") or "").strip()
    if env_ip:
        return env_ip
    if _SERVER_IP_CACHE["ip"] is not None:
        return _SERVER_IP_CACHE["ip"]
    if _SERVER_IP_CACHE["tried"]:
        return ""
    _SERVER_IP_CACHE["tried"] = True
    ip = ""
    try:
        import urllib.request
        for svc in ("https://api.ipify.org", "https://checkip.amazonaws.com"):
            try:
                with urllib.request.urlopen(svc, timeout=3) as r:
                    cand = (r.read().decode("utf-8") or "").strip()
                    if cand and len(cand) <= 45:
                        ip = cand
                        break
            except Exception:
                continue
    except Exception:
        ip = ""
    _SERVER_IP_CACHE["ip"] = ip
    return ip


@bp.get("/markets/connect/<market>")
def markets_connect_one(market):
    """마켓별 단독 연결 페이지 (키 발급 안내 + 입력칸)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from . import market_credentials as mc
    from .market_guide import get_guide, guide_map

    market = _connect_market_key(market)
    if market not in mc.MARKET_CRED_FIELDS:
        return redirect(url_for("seller_console.markets_connect"))

    seller = _seller_id()
    chips = [{"market": s["market"], "label": s["label"], "connected": s["connected"]} for s in mc.all_status(seller)]
    guide_entry = next((g for g in get_guide() if g.get("key") == market), None)
    return render_template(
        "markets_connect.html", page="markets",
        market_statuses=[mc.status(seller, market)], market_chips=chips,
        single_market=market, guide_entry=guide_entry,
        guide_map=guide_map(), server_ip=_server_outbound_ip(),
    )


@bp.get("/markets/guide")
def markets_guide():
    """마켓 API 키 발급 가이드 (그림 포함, 인앱)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from .market_guide import get_guide

    return render_template("markets_guide.html", page="markets", guide=get_guide())


@bp.get("/m")
def mobile_home():
    """모바일 앱 셸 — '간단 수집 + 주문처리'에 집중(PWA, v3 P1-6).

    하단 탭(수집/주문/더보기) + 고가브릿지 토큰 + BETA. 풀기능은 데스크톱 안내.
    """
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    sid = _seller_id()
    recent = []
    try:
        from .collect_history_store import list_items
        items = list_items(days=14, seller_id=sid)[:8]
        for it in items:
            thumb = (it.get("image_url") or "").strip()
            if not thumb:
                try:
                    ex = json.loads(it.get("extra_json") or "{}")
                    imgs = ex.get("images") if isinstance(ex.get("images"), list) else []
                    thumb = (imgs[0] if imgs else "") or ""
                except Exception:
                    thumb = ""
            recent.append({"id": it.get("id"), "title": it.get("title") or "(제목 없음)",
                           "price": it.get("price"), "currency": it.get("currency"),
                           "thumb": thumb, "domain": it.get("domain")})
    except Exception as exc:
        logger.debug("모바일 최근 수집 조회 실패: %s", exc)

    kpi = {"today_new": 0, "pending_ship": 0, "shipped": 0, "returned_exchanged": 0}
    orders = []
    try:
        from .orders.sync_service import OrderSyncService
        svc = OrderSyncService()
        k = svc.kpi_summary() or {}
        for key in kpi:
            kpi[key] = int(k.get(key, 0) or 0)
        orders = (svc.list_orders(limit=10) or [])[:10]
    except Exception as exc:
        logger.debug("모바일 주문 조회 실패: %s", exc)

    return render_template("mobile_home.html", recent=recent, kpi=kpi, orders=orders)


@bp.get("/billing")
def billing_page():
    """요금제·충전 — 쉽고 간편(v6). 무료/Plus/Pro 카드 + 토큰 잔액."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from . import billing_store, translation_usage
    sid = _seller_id()
    acc = billing_store.get_account(sid)
    pay_ready = bool(os.getenv("TOSS_CLIENT_KEY")) and bool(os.getenv("TOSS_SECRET_KEY"))
    notice = (request.args.get("notice") or "").strip()
    error = (request.args.get("error") or "").strip()
    toss_client_key = os.getenv("TOSS_CLIENT_KEY", "") if pay_ready else ""
    return render_template("billing.html", account=acc, plans=billing_store.PLANS,
                           pay_ready=pay_ready,
                           toss_client_key=toss_client_key,
                           notice=notice,
                           error=error,
                           free_remaining=translation_usage.remaining(sid),
                           free_limit=translation_usage.free_limit())


@bp.post("/billing/select")
def billing_select():
    """플랜 선택. free=즉시 적용. 유료=결제 연동 시에만 활성(가짜 활성 금지)."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    plan = str(data.get("plan") or "").strip()
    from . import billing_store
    if plan not in billing_store.PLANS:
        return jsonify({"ok": False, "error": "알 수 없는 플랜입니다."}), 400
    if plan == "free":
        try:
            billing_store.set_plan(_seller_id(), "free")
        except billing_store.BillingCommitError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503
        return jsonify({"ok": True, "plan": "free", "message": "무료 플랜으로 전환했습니다."})
    # 유료: 결제 연동 필요 — 미설정이면 정직 안내(활성 안 함)
    pay_ready = bool(os.getenv("TOSS_CLIENT_KEY")) and bool(os.getenv("TOSS_SECRET_KEY"))
    if not pay_ready:
        return jsonify({"ok": False, "pay_unconfigured": True,
                        "error": "결제 준비 중입니다 — 곧 열립니다."}), 200
    # 결제 설정됨 — 실제 결제 요청 정보 생성(활성 반영은 성공 콜백 승인 후에만).
    sid = _seller_id()
    amount = int(billing_store.PLANS[plan]["price_krw"] or 0)
    order_id = f"BILL-{uuid.uuid4().hex[:20]}"
    order_name = f"{billing_store.PLANS[plan]['label']} 월 구독"
    billing_store.create_pending_payment(
        seller_id=sid,
        plan=plan,
        order_id=order_id,
        amount=amount,
    )
    return jsonify({
        "ok": True,
        "checkout": True,
        "plan": plan,
        "message": "결제창을 여는 중입니다.",
        "checkout_payload": {
            "client_key": os.getenv("TOSS_CLIENT_KEY", ""),
            "amount": amount,
            "order_id": order_id,
            "order_name": order_name,
            "success_url": url_for("seller_console.billing_success", _external=True),
            "fail_url": url_for("seller_console.billing_fail", _external=True),
            "customer_name": (session.get("user_name") or session.get("user_email") or "고객"),
        },
    })


@bp.get("/billing/success")
def billing_success():
    """토스 결제 성공 콜백 — 승인 확인 후 플랜 반영(가짜 활성 금지)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    payment_key = (request.args.get("paymentKey") or "").strip()
    order_id = (request.args.get("orderId") or "").strip()
    amount_raw = (request.args.get("amount") or "0").strip()
    try:
        amount = int(amount_raw)
    except (TypeError, ValueError):
        amount = 0

    from . import billing_store
    pending = billing_store.get_pending_payment(order_id)
    sid = _seller_id()
    if not pending or pending.get("seller_id") != sid:
        return redirect(url_for("seller_console.billing_page", error="결제 확인 정보를 찾지 못했어요. 다시 시도해주세요."))
    if int(pending.get("amount") or 0) != amount:
        return redirect(url_for("seller_console.billing_page", error="결제 금액이 일치하지 않아 확인에 실패했어요."))
    if not payment_key:
        return redirect(url_for("seller_console.billing_page", error="결제 확인 키가 없어 결제를 완료하지 못했어요."))

    from src.payments.toss import confirm_payment
    result = confirm_payment(payment_key=payment_key, order_id=order_id, amount=amount) or {}
    if not result.get("ok"):
        return redirect(url_for("seller_console.billing_page", error="결제 승인 확인에 실패했어요. 잠시 후 다시 확인해주세요."))
    if str(result.get("status") or "").upper() != "DONE":
        return redirect(url_for("seller_console.billing_page", error="결제 상태를 완료로 확인하지 못했어요."))

    plan = str(pending.get("plan") or "free")
    try:
        billing_store.set_plan(sid, plan)
    except billing_store.BillingCommitError as exc:
        return redirect(url_for("seller_console.billing_page", error=str(exc)))
    billing_store.pop_pending_payment(order_id)
    label = billing_store.PLANS.get(plan, {}).get("label", plan)
    return redirect(url_for("seller_console.billing_page", notice=f"{label} 플랜 결제가 완료되었습니다."))


@bp.get("/billing/fail")
def billing_fail():
    """토스 결제 실패 콜백 — 정직 안내."""
    code = (request.args.get("code") or "").strip()
    message = (request.args.get("message") or "").strip()
    reason = message or "결제가 완료되지 않았어요."
    if code:
        reason = f"{reason} (사유: {code})"
    return redirect(url_for("seller_console.billing_page", error=reason))


@bp.get("/about")
def about_page():
    """소개 — '고가브릿지란?' (애플 톤, v5). 로그인 없이도 볼 수 있음."""
    return render_template("about.html")


@bp.get("/start")
def onboarding_wizard():
    """For Beginners 키노트형 온보딩 위저드 (v5).

    풀스크린 + 좌측 스텝퍼 + 화면당 1~2버튼. 각 단계는 실제 동작(구글 로그인/마켓 연결/
    확장 설치/첫 수집)으로 이어진다. 로그인 없이도 진입 가능(구글 로그인 단계가 첫 관문).
    """
    logged_in = bool(session.get("user_id"))
    # 마켓 연결 여부(로그인 시) — 단계 완료 자동 판정
    markets_connected = 0
    if logged_in:
        try:
            from . import market_credentials as mc
            sid = _seller_id()
            markets_connected = sum(1 for m in ("shopify", "coupang", "smartstore", "elevenst", "woocommerce")
                                    if mc.is_connected(sid, m))
        except Exception:
            markets_connected = 0
    return render_template("onboarding_wizard.html",
                           logged_in=logged_in, markets_connected=markets_connected)


@bp.get("/guide/business")
def guide_business():
    """사업자등록 · 통신판매업 신고 · 구매대행 유의 클릭-스루 가이드 (Phase 243, 브리프 §4.3).

    공식 사이트 딥링크 + 단계 설명 + 체크리스트 + 면책(법·세무는 변동되며 최종은
    관할 세무서/전문가 확인 — 단정 금지).
    """
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    return render_template("guide_business.html", page="guide_business")


@bp.post("/markets/connect/<market>")
def markets_connect_save(market):
    """셀러 마켓 자격증명 저장 (JSON)."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    from . import market_credentials as mc

    market = (market or "").strip().lower()
    if market not in mc.MARKET_CRED_FIELDS:
        return jsonify({"ok": False, "error": "지원하지 않는 마켓입니다."}), 404

    data = request.get_json(force=True, silent=True) or {}
    values = data.get("values")
    if not isinstance(values, dict):
        return jsonify({"ok": False, "error": "values 형식이 올바르지 않습니다."}), 400

    try:
        mc.save(_seller_id(), market, values)
        return jsonify({"ok": True, "status": mc.status(_seller_id(), market)})
    except Exception as exc:
        logger.warning("마켓 자격증명 저장 오류 (%s): %s", market, exc)
        return jsonify({"ok": False, "error": "저장 중 오류가 발생했습니다."}), 500


@bp.post("/markets/connect/<market>/test")
def markets_connect_test(market):
    """셀러 자격증명(저장값 + 입력 중 값)으로 라이브 연결 테스트."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    from . import market_credentials as mc
    from .market_integration_diagnostics import normalize_market_diagnostic_result, run_market_diagnostic

    market = (market or "").strip().lower()
    if market not in mc.MARKET_CRED_FIELDS:
        return jsonify({"ok": False, "error": "지원하지 않는 마켓입니다."}), 404

    data = request.get_json(force=True, silent=True) or {}
    pending = data.get("values") if isinstance(data.get("values"), dict) else {}
    allowed = {f["env"] for f in mc.MARKET_CRED_FIELDS[market]}
    extra = {k: str(v).strip() for k, v in pending.items() if k in allowed and str(v).strip()}

    try:
        with mc.seller_market_env(_seller_id(), market, extra=extra):
            result = normalize_market_diagnostic_result(run_market_diagnostic(_diag_market_key(market)))
        return jsonify({"ok": True, "result": result})
    except KeyError:
        return jsonify({"ok": False, "error": "지원하지 않는 마켓입니다."}), 404
    except Exception as exc:
        logger.warning("마켓 연결 테스트 오류 (%s): %s", market, exc)
        return jsonify({"ok": False, "error": "연결 테스트 중 오류가 발생했습니다."}), 500


@bp.post("/markets/connect/<market>/disconnect")
def markets_connect_disconnect(market):
    """셀러 마켓 자격증명 삭제(연결 해제)."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    from . import market_credentials as mc

    market = (market or "").strip().lower()
    if market not in mc.MARKET_CRED_FIELDS:
        return jsonify({"ok": False, "error": "지원하지 않는 마켓입니다."}), 404

    removed = mc.delete(_seller_id(), market)
    return jsonify({"ok": True, "removed": removed, "status": mc.status(_seller_id(), market)})


# ---------------------------------------------------------------------------
# Phase 134: AI 카피라이터 엔드포인트
# ---------------------------------------------------------------------------

@bp.post("/collect/ai-copy")
def collect_ai_copy():
    """AI 카피 생성 (Phase 134).

    Request body: {
        "title": str,
        "description": str,
        "brand": str,
        "marketplace": str,
        "source_lang": str,
        "variants": int,
        "price_krw": int,
    }
    Response: {"ok": true, "results": [...]}
    """
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "상품명이 필요합니다."}), 400

    from src.ai.budget import BudgetExceededError
    try:
        from src.ai.copywriter import AICopywriter, CopyRequest

        req = CopyRequest(
            title=title,
            description=data.get("description", ""),
            brand=data.get("brand"),
            marketplace=data.get("marketplace"),
            source_lang=data.get("source_lang", "en"),
            price_krw=int(data["price_krw"]) if data.get("price_krw") else None,
            variants=max(1, min(int(data.get("variants", 1)), 5)),
        )
        writer = AICopywriter()
        results = writer.generate(req)
        return jsonify({"ok": True, "results": [r.to_dict() for r in results]})
    except BudgetExceededError as exc:
        return jsonify({"ok": False, "error": "AI 월 예산을 초과했습니다.", "budget": exc.summary}), 402
    except Exception as exc:
        logger.warning("AI 카피 생성 오류: %s", exc)
        return jsonify({"ok": False, "error": "AI 카피 생성 중 오류가 발생했습니다."}), 500


@bp.get("/ai-budget")
def ai_budget():
    """AI 예산 현황 JSON (Phase 134)."""
    try:
        from src.ai.budget import BudgetGuard
        guard = BudgetGuard()
        return jsonify({"ok": True, "budget": guard.summary()})
    except Exception as exc:
        logger.warning("AI 예산 조회 오류: %s", exc)
        return jsonify({"ok": False, "error": "예산 조회 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# Phase 134: 다채널 메시징 엔드포인트
# ---------------------------------------------------------------------------

@bp.get("/messaging")
def messaging():
    """다채널 메시징 페이지 (Phase 134)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from src.messaging.router import MessageRouter
        router = MessageRouter()
        channels_status = router.channels_status()
        log = router._log.recent(50)
    except Exception as exc:
        logger.warning("메시징 상태 로드 실패: %s", exc)
        channels_status = []
        log = []

    events = [
        "order_received", "payment_confirmed", "order_shipped",
        "order_delivered", "refund_requested", "refund_completed",
        "out_of_stock", "cs_auto_reply",
    ]
    locales = ["ko", "ja", "en", "zh-CN"]

    return render_template(
        "messaging.html",
        page="messaging",
        channels_status=channels_status,
        log=log,
        events=events,
        locales=locales,
    )


@bp.get("/cs/messaging")
def cs_messaging_alias():
    """CS 메시징 별칭 경로 (Phase 145)."""
    return redirect(url_for("seller_console.messaging"))


@bp.get("/cs/inbox")
def cs_inbox():
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    if not _cs_role_allowed():
        abort(403)
    from src.cs_bot.faq_store import FAQStore
    from src.cs_bot.inbox_store import InboxStore
    from src.cs_bot.replier import suggest_reply_details

    store = InboxStore()
    faq_store = FAQStore()
    status = (request.args.get("status") or "").strip()
    channel = (request.args.get("channel") or "").strip()
    query = (request.args.get("q") or "").strip().lower()
    selected_id = (request.args.get("msg") or "").strip()

    messages = store.list_messages(status=status or None, channel=channel or None, limit=200)
    if query:
        messages = [
            m
            for m in messages
            if query in (m.body or "").lower() or query in (m.customer_name or "").lower() or query in (m.order_no or "").lower()
        ]

    selected = store.get(selected_id) if selected_id else (messages[0] if messages else None)
    if selected and not selected.suggested_reply:
        suggested, _, matched_faq = suggest_reply_details(selected, faq_store)
        selected.suggested_reply = suggested
        selected.matched_faq_id = matched_faq.faq_id if matched_faq else ""
        store.upsert(selected)

    identity = _infer_customer_identity(selected) if selected else {}
    matched_channels = _find_cross_channel_messages(messages, identity)

    stats = store.stats_24h()
    return render_template(
        "cs_inbox.html",
        page="cs_bot",
        messages=messages,
        selected=selected,
        identity=identity,
        matched_channels=matched_channels,
        stats=stats,
        filters={"status": status, "channel": channel, "q": query},
    )


@bp.get("/cs/autoreply")
def cs_autoreply_alias():
    """CS 자동응답 별칭 경로 (Phase 145)."""
    return redirect(url_for("seller_console.cs_inbox"))


@bp.route("/cs/faq", methods=["GET", "POST"])
def cs_faq():
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    if not _cs_role_allowed():
        abort(403)
    from src.cs_bot.faq_store import FAQEntry, FAQStore

    store = FAQStore()
    if request.method == "POST":
        action = (request.form.get("action") or "create").strip()
        if action == "delete":
            faq_id = (request.form.get("faq_id") or "").strip()
            if faq_id:
                store.delete(faq_id)
        else:
            faq_id = (request.form.get("faq_id") or f"faq_{uuid.uuid4().hex[:10]}").strip()
            language = (request.form.get("language") or request.form.get("locale") or "ko").strip()
            if language == "zh-CN":
                language = "zh"
            if language not in _CS_FAQ_SUPPORTED_LOCALES:
                language = "ko"
            keywords = (request.form.get("keywords") or request.form.get("keyword") or "").strip()
            question = (request.form.get("question") or keywords or "").strip()
            answer_template = (request.form.get("answer_template") or request.form.get("answer") or "").strip()
            category = (request.form.get("category") or "general").strip()
            entry = FAQEntry(
                faq_id=faq_id,
                category=category or "general",
                language=language,
                question=question,
                keywords=[x.strip() for x in keywords.split(",") if x.strip()],
                answer_template=answer_template,
                priority=int(request.form.get("priority") or 0),
                enabled=request.form.get("enabled", "1") in {"1", "true", "on", "yes"},
            )
            if action == "update":
                store.update(entry)
            elif question and answer_template:
                store.create(entry)

    preview_text = (request.args.get("preview") or "").strip()
    preview = store.search_by_keywords(preview_text, language=(request.args.get("language") or "ko")) if preview_text else []
    faq_items = store.list_all(enabled_only=False)
    return render_template(
        "cs_faq.html",
        page="cs_bot",
        faq_items=faq_items,
        worksheet="cs_faq",
        locales=sorted(_CS_FAQ_SUPPORTED_LOCALES),
        preview_text=preview_text,
        preview=preview[:5],
    )


@bp.post("/cs/inbox/respond")
def cs_inbox_respond():
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    if not _cs_role_allowed():
        abort(403)
    from src.cs_bot.inbox_store import InboxStore
    from src.cs_bot.multi_channel_send import Customer, send_to_channels
    from src.cs_bot.quality_logger import log_reply_quality
    from src.cs_bot.inbound_telegram import _send_customer_reply

    message_id = (request.form.get("message_id") or "").strip()
    action = (request.form.get("action") or "").strip()
    final_reply = (request.form.get("final_reply") or "").strip()
    multi_channels = request.form.getlist("channels")
    if not message_id:
        return redirect("/seller/cs/inbox")
    store = InboxStore()
    row = store.get(message_id)
    if not row:
        return redirect("/seller/cs/inbox")

    if action == "send":
        reply = final_reply or row.suggested_reply
        row.final_reply = reply
        row.status = "resolved"
        row.responded_at = datetime.now(timezone.utc).isoformat()
        if row.channel == "telegram":
            _send_customer_reply(row.customer_id, reply)
    elif action == "hold":
        row.status = "in_progress"
        row.final_reply = final_reply or row.final_reply
    elif action == "resolve":
        row.status = "resolved"
        row.final_reply = final_reply or row.final_reply
        row.responded_at = datetime.now(timezone.utc).isoformat()
    elif action == "multi_send":
        reply = final_reply or row.suggested_reply
        identity = _infer_customer_identity(row)
        customer = Customer(
            customer_id=row.customer_id,
            customer_name=row.customer_name,
            language=row.language or "ko",
            email=identity.get("email", ""),
            phone=identity.get("phone", ""),
            telegram_chat_id=row.customer_id if row.channel == "telegram" else "",
        )
        result = send_to_channels(customer, reply, multi_channels)
        if any(result.values()):
            row.status = "resolved"
            row.final_reply = reply
            row.responded_at = datetime.now(timezone.utc).isoformat()
    store.upsert(row)
    if action in {"send", "resolve", "multi_send"}:
        final_text = row.final_reply or final_reply or row.suggested_reply
        accepted = bool(row.suggested_reply and _text_similarity(final_text, row.suggested_reply) >= 0.95)
        log_reply_quality(row, row.suggested_reply, final_text, accepted)
    return redirect(f"/seller/cs/inbox?msg={row.message_id}")


@bp.route("/cs/quality", methods=["GET", "POST"])
def cs_quality():
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    if not _cs_role_allowed():
        abort(403)
    from src.cs_bot.faq_store import FAQStore
    from src.cs_bot.quality_logger import get_low_quality_records
    from src.cs_bot.inbox_store import InboxStore

    faq_store = FAQStore()
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        faq_id = (request.form.get("faq_id") or "").strip()
        if action == "promote" and faq_id:
            final_reply = (request.form.get("last_final") or "").strip()
            target = faq_store.get(faq_id)
            if target and final_reply:
                target.answer_template = final_reply
                faq_store.update(target)

    low_quality = get_low_quality_records(threshold=float(request.args.get("threshold", 0.5)))
    rows = InboxStore().list_messages(limit=5000)
    response_minutes: list[float] = []
    for row in rows:
        if not row.received_at or not row.responded_at:
            continue
        try:
            recv = datetime.fromisoformat(row.received_at.replace("Z", "+00:00"))
            resp = datetime.fromisoformat(row.responded_at.replace("Z", "+00:00"))
            if resp >= recv:
                response_minutes.append((resp - recv).total_seconds() / 60)
        except Exception:
            continue
    return render_template(
        "cs_quality.html",
        page="cs_bot",
        low_quality=low_quality,
        avg_response=round(sum(response_minutes) / len(response_minutes), 1) if response_minutes else 0.0,
        p95_response=round(_p95(response_minutes), 1),
    )


def _text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").strip(), (b or "").strip()).ratio()


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(len(ordered) * 0.95), len(ordered) - 1)
    return float(ordered[idx])


@bp.get("/cs/sla")
def cs_sla():
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    if not _cs_role_allowed():
        abort(403)
    from src.cs_bot.inbox_store import InboxStore
    from src.cs_bot.sla import classify_sla

    store = InboxStore()
    rows = store.list_messages(limit=5000)
    summary = classify_sla(rows)
    by_channel: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for row in rows:
        by_channel[row.channel] = by_channel.get(row.channel, 0) + 1
        by_category[row.category or "general"] = by_category.get(row.category or "general", 0) + 1
    return render_template(
        "cs_sla.html",
        page="cs_bot",
        summary=summary,
        by_channel=by_channel,
        by_category=by_category,
    )


@bp.get("/cs/mobile")
def cs_mobile():
    """운영자 모바일 PWA."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    if not _cs_role_allowed():
        abort(403)
    from src.cs_bot.inbox_store import InboxStore
    store = InboxStore()
    # 미응답 우선 정렬
    messages = store.list_messages(status="open", limit=50)
    stats = store.stats_24h()
    return render_template(
        "cs_mobile.html",
        page="cs_bot",
        messages=messages,
        stats=stats,
    )


@bp.get("/cs/stats")
def cs_stats():
    """CS 통계 대시보드."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    if not _cs_role_allowed():
        abort(403)
    from src.cs_bot.inbox_store import InboxStore
    store = InboxStore()
    rows = store.list_messages(limit=5000)
    # 채널별 통계
    by_channel: dict[str, dict] = {}
    by_category: dict[str, dict] = {}
    by_language: dict[str, int] = {}
    response_times: list[float] = []
    ai_suggested = 0
    ai_used = 0

    for row in rows:
        # 채널
        ch = row.channel or "unknown"
        by_channel.setdefault(ch, {"total": 0, "resolved": 0})
        by_channel[ch]["total"] += 1
        if row.status in {"resolved", "auto_handled"}:
            by_channel[ch]["resolved"] += 1
        # 카테고리
        cat = row.category or "general"
        by_category.setdefault(cat, {"total": 0, "resolved": 0})
        by_category[cat]["total"] += 1
        if row.status in {"resolved", "auto_handled"}:
            by_category[cat]["resolved"] += 1
        # 언어
        lang = row.language or "ko"
        by_language[lang] = by_language.get(lang, 0) + 1
        # 응답 시간
        if row.received_at and row.responded_at:
            try:
                recv = datetime.fromisoformat(row.received_at.replace("Z", "+00:00"))
                resp = datetime.fromisoformat(row.responded_at.replace("Z", "+00:00"))
                if resp >= recv:
                    response_times.append((resp - recv).total_seconds() / 60)
            except Exception:
                pass
        # AI 제안 채택률
        if row.suggested_reply:
            ai_suggested += 1
            if row.final_reply:
                # 간단한 유사도: 같거나 포함이면 채택
                if row.final_reply.strip() == row.suggested_reply.strip() or row.suggested_reply.strip() in row.final_reply:
                    ai_used += 1

    avg_response = round(sum(response_times) / len(response_times), 1) if response_times else 0.0
    ai_adoption_rate = round(ai_used / ai_suggested * 100, 1) if ai_suggested else 0.0

    stats_summary = store.stats_24h()
    return render_template(
        "cs_stats.html",
        page="cs_bot",
        by_channel=by_channel,
        by_category=by_category,
        by_language=by_language,
        avg_response=avg_response,
        ai_adoption_rate=ai_adoption_rate,
        ai_suggested=ai_suggested,
        stats=stats_summary,
        total_messages=len(rows),
    )


@bp.post("/messaging/test")
def messaging_test():
    """테스트 메시지 발송 (Phase 134).

    Request body: {"channel": str, "locale": str, "event": str}
    Response: {"ok": true, "result": {...}}
    """
    data = request.get_json(force=True, silent=True) or {}
    channel = (data.get("channel") or "").strip()
    locale = (data.get("locale") or "ko").strip()
    event = (data.get("event") or "order_received").strip()

    try:
        from src.messaging.router import MessageRouter
        router = MessageRouter()
        result = router.test_send(channel, locale, event, {})
        # Sanitize result: only expose safe fields to external response
        safe_result = {
            "sent": result.get("sent", False),
            "channel": result.get("channel", ""),
            "fallback": result.get("fallback"),
        }
        return jsonify({"ok": True, "result": safe_result})
    except Exception as exc:
        logger.warning("테스트 메시지 오류: %s", exc)
        return jsonify({"ok": False, "error": "테스트 메시지 발송 중 오류가 발생했습니다."}), 500


@bp.get("/messaging/log")
def messaging_log():
    """메시지 발송 로그 JSON (Phase 134)."""
    n = request.args.get("n", 50, type=int)
    try:
        from src.messaging.router import MessageLog
        log = MessageLog()
        rows = log.recent(n)
        return jsonify({"ok": True, "log": rows})
    except Exception as exc:
        logger.warning("메시지 로그 조회 오류: %s", exc)
        return jsonify({"ok": False, "error": "로그 조회 중 오류가 발생했습니다."}), 500


@bp.get("/health")
def health():
    """셀러 콘솔 헬스체크."""
    try:
        from src.utils.env_catalog import get_api_status
        _api_data = get_api_status()
        api_statuses = _api_data.get("apis", []) if isinstance(_api_data, dict) else _api_data
        active_count = sum(1 for a in api_statuses if a["status"] == "active")
        missing_count = sum(1 for a in api_statuses if a["status"] == "missing")
    except Exception:
        api_statuses = []
        active_count = 0
        missing_count = 0

    return jsonify({
        "ok": True,
        "service": "seller_console",
        "phase": 128,
        "auth_enabled": _AUTH_ENABLED,
        "api_keys": {
            "active": active_count,
            "missing": missing_count,
            "total": len(api_statuses),
        },
    })


# ---------------------------------------------------------------------------
# 헬퍼: 마켓 레이블
# ---------------------------------------------------------------------------

_MARKETPLACE_LABELS = {
    "coupang": "쿠팡",
    "smartstore": "스마트스토어",
    "11st": "11번가",
    "elevenst": "11번가",
    "kohganemultishop": "코가네멀티샵",
    "woocommerce": "WooCommerce",
    "shopify": "Shopify",
    "amazon": "Amazon",
    "ebay": "eBay",
    "shopee": "Shopee",
}


def _marketplace_label(marketplace: str) -> str:
    try:
        from src.markets.adapters.base import get_marketplace_meta

        meta = get_marketplace_meta(marketplace)
        if meta.get("label"):
            return str(meta["label"])
    except Exception:
        pass
    return _MARKETPLACE_LABELS.get(marketplace, marketplace)


def _marketplace_meta(marketplace: str) -> dict:
    try:
        from src.markets.adapters.base import get_marketplace_meta

        return get_marketplace_meta(marketplace)
    except Exception:
        return {
            "market": marketplace,
            "label": _marketplace_label(marketplace),
            "country": "KR",
            "currency": "KRW",
            "locale": "ko-KR",
            "region": "동아시아",
            "is_ready": True,
        }


def _market_configured_for_seller(marketplace: str) -> bool:
    """전역 환경변수 + 셀러 인앱 저장 자격증명을 함께 고려한 연결 설정 여부."""
    from . import market_credentials as mc
    with mc.temp_env(mc.all_credential_env(_seller_id())):
        return _market_is_configured(marketplace)


def _market_is_configured(marketplace: str) -> bool:
    market = (marketplace or "").strip().lower()
    if market == "shopify":
        return bool((os.getenv("SHOPIFY_SHOP") or "").strip()) and bool(
            (os.getenv("SHOPIFY_AUTO_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_TOKEN") or "").strip()
        )
    if market == "coupang":
        return all(
            bool((os.getenv(k) or "").strip())
            for k in ["COUPANG_VENDOR_ID", "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY"]
        )
    if market == "smartstore":
        return all(
            bool((os.getenv(k) or "").strip())
            for k in ["NAVER_COMMERCE_CLIENT_ID", "NAVER_COMMERCE_CLIENT_SECRET"]
        )
    if market == "11st":
        return bool((os.getenv("ELEVENST_API_KEY") or "").strip())
    return False


def _market_required_env_hint(marketplace: str) -> str:
    market = (marketplace or "").strip().lower()
    hints = {
        "shopify": "필요 env: SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET, SHOPIFY_AUTO_TOKEN(atk_), SHOPIFY_API_VERSION, SHOPIFY_SHOP",
        "coupang": "필요 env: COUPANG_VENDOR_ID, COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY",
        "smartstore": "필요 env: NAVER_COMMERCE_CLIENT_ID, NAVER_COMMERCE_CLIENT_SECRET",
        "11st": "필요 env: ELEVENST_API_KEY",
        "amazon": "필요 env: AMAZON_SP_CLIENT_ID, AMAZON_SP_CLIENT_SECRET, AMAZON_SP_REFRESH_TOKEN, AMAZON_SP_SELLER_ID",
        "ebay": "필요 env: EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, EBAY_REFRESH_TOKEN",
        "shopee": "필요 env: SHOPEE_PARTNER_ID, SHOPEE_PARTNER_KEY, SHOPEE_SHOP_ID",
    }
    return hints.get(market, "")


def _market_price_display(item, target_currency: str) -> tuple[str, str]:
    """마켓 기준 가격 표시 문자열을 생성한다.

    Returns:
        (formatted_price, conversion_note)
    """
    from .market_status import convert_amount, format_currency_amount

    if item.price is None and item.price_krw is not None:
        if target_currency == "KRW":
            return format_currency_amount(float(item.price_krw), "KRW"), ""
        converted, ok = convert_amount(float(item.price_krw), "KRW", target_currency)
        if ok and converted is not None:
            return format_currency_amount(converted, target_currency), "KRW 환산"
        return f"{format_currency_amount(float(item.price_krw), 'KRW')} (미환산)", "환율 미가용"

    if item.price is None:
        return "—", ""

    converted, ok = convert_amount(float(item.price), item.currency, target_currency)
    if ok and converted is not None:
        note = "" if item.currency == target_currency else f"{item.currency}→{target_currency} 환산"
        return format_currency_amount(converted, target_currency), note
    return f"{format_currency_amount(float(item.price), item.currency)} (미환산)", "환율 미가용"


def _select_localized_field(item, target_locale: str, field_name: str) -> tuple[str, bool]:
    """상품의 locale별 번역본을 우선 사용하고, 없으면 원문 폴백한다."""
    localized_map = item.localized if isinstance(getattr(item, "localized", None), dict) else {}
    locale = (target_locale or "ko-KR").strip()
    language = locale.split("-")[0].lower() if locale else "ko"

    candidate = localized_map.get(locale)
    if isinstance(candidate, dict):
        value = str(candidate.get(field_name) or "").strip()
        if value:
            return value, False

    for key, row in localized_map.items():
        if not isinstance(row, dict):
            continue
        if str(key).split("-")[0].lower() != language:
            continue
        value = str(row.get(field_name) or "").strip()
        if value:
            return value, False

    original = str(getattr(item, field_name, "") or "").strip()
    return original, bool(localized_map)


# ---------------------------------------------------------------------------
# 헬퍼: MarginResult → dict 직렬화
# ---------------------------------------------------------------------------

def _result_to_dict(result) -> Dict[str, Any]:
    """MarginResult 인스턴스를 JSON 직렬화 가능한 dict로 변환."""
    try:
        from .margin_calculator import MarginCalculator
        labels = MarginCalculator.MARKETPLACE_LABELS
    except Exception:
        labels = {
            "coupang": "쿠팡", "smartstore": "스마트스토어", "11st": "11번가",
            "kohganemultishop": "코가네멀티샵", "shopify": "Shopify",
        }
    return {
        "marketplace": result.marketplace,
        "marketplace_label": labels.get(result.marketplace, result.marketplace),
        "cost_in_krw": int(result.cost_in_krw),
        "customs_in_krw": int(result.customs_in_krw),
        "total_landed_cost": int(result.total_landed_cost),
        "recommended_price": int(result.recommended_price),
        "given_price": int(result.given_price) if result.given_price is not None else None,
        "actual_margin_krw": int(result.actual_margin_krw),
        "actual_margin_pct": float(result.actual_margin_pct),
        "breakeven_price": int(result.breakeven_price),
        "fx_used": result.fx_used,
        "warnings": result.warnings,
        # 하위 호환 필드 (기존 UI가 참조)
        "buy_price_krw": int(result.cost_in_krw),
        "customs_amount_krw": int(result.customs_in_krw),
        "cost_krw": int(result.total_landed_cost),
        "sell_price_krw": int(result.given_price if result.given_price is not None else result.recommended_price),
        "breakeven_krw": int(result.breakeven_price),
    }


# ---------------------------------------------------------------------------
# 공개 API — /api/v1/pricing/calculate
# ---------------------------------------------------------------------------

# 공개 API Blueprint 없이 직접 메인 앱에 붙이기 위해 lazy registration 패턴
def _register_api_routes(app):
    """메인 Flask 앱에 공개 마진 계산 API 라우트 등록."""

    @app.route("/api/v1/pricing/calculate", methods=["POST"])
    def api_pricing_calculate():
        """공개 마진 계산 API.

        Request body: 계산 파라미터 (pricing/calc 와 동일)
        Response: {"ok": true, "result": {...}}
        """
        # 인증 stub — Phase 24/129에서 실제 토큰 검증으로 교체
        data = request.get_json(force=True, silent=True) or {}
        try:
            buy_price = Decimal(str(data.get("buy_price", 0)))
            currency = str(data.get("currency", "USD")).upper()
            marketplace = str(data.get("marketplace", "coupang"))
            customs_rate_pct = Decimal(str(data.get("customs_rate", 20)))
            customs_rate = customs_rate_pct / Decimal("100")
            domestic_shipping = Decimal(str(data.get("domestic_shipping") or data.get("shipping_fee", 0)))
            international_shipping = Decimal(str(data.get("international_shipping", 0)))
            forwarder_fee = Decimal(str(data.get("forwarder_fee", 0)))
            if "market_fee_rate" in data:
                commission_rate = Decimal(str(data["market_fee_rate"]))
            else:
                from .margin_calculator import default_commission_rate
                commission_rate = default_commission_rate(marketplace)
            pg_fee_rate = Decimal(str(data.get("pg_fee_rate", 0)))
            target_margin_pct = Decimal(str(data.get("target_margin_pct", 22)))
            sell_price_raw = data.get("sell_price")
            sell_price = Decimal(str(sell_price_raw)) if sell_price_raw else None
        except (TypeError, ValueError, InvalidOperation):
            return jsonify({"ok": False, "error": "입력값 형식이 올바르지 않습니다."}), 400

        if buy_price <= Decimal("0"):
            return jsonify({"ok": False, "error": "매입가를 입력하세요."}), 400

        try:
            from .margin_calculator import CostInput, MarginCalculator, MarketInput
            cost = CostInput(
                buy_price=buy_price,
                buy_currency=currency,
                forwarder_fee=forwarder_fee,
                international_shipping=international_shipping,
                domestic_shipping=domestic_shipping,
                customs_rate=customs_rate,
            )
            market = MarketInput(
                marketplace=marketplace,
                commission_rate=commission_rate,
                pg_fee_rate=pg_fee_rate,
                target_margin_pct=target_margin_pct,
            )
            calc = MarginCalculator()
            result = calc.calculate(cost, market, sell_price=sell_price)
            return jsonify({"ok": True, "result": _result_to_dict(result)})
        except Exception as exc:
            logger.warning("공개 API 마진 계산 오류: %s", exc)
            return jsonify({"ok": False, "error": "계산 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# Phase 135: Personal Access Token 관리
# ---------------------------------------------------------------------------

@bp.get("/me/tokens")
def personal_tokens():
    """Personal Access Token 관리 페이지 (Phase 135)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    user_id = _current_user_id()

    tokens = []
    try:
        from src.auth.personal_tokens import list_tokens
        # v39 C: 별칭(user_id↔email)으로 발급된 토큰도 본인 목록에 보이게(표시·삭제 스코프 일치 → 부활 방지).
        tokens = list_tokens(user_id, user_ids=_seller_identities())
    except Exception as exc:
        logger.warning("토큰 목록 조회 실패: %s", exc)

    # v38 #6: 활성 토큰만 메인 목록에, 폐기(삭제)된 토큰은 '발급/폐기 이력'으로 분리(목록 어지럽힘 방지).
    active_tokens = [t for t in tokens if not t.get("revoked")]
    revoked_tokens = [t for t in tokens if t.get("revoked")]

    return render_template(
        "personal_tokens.html",
        page="me",
        tokens=active_tokens,
        active_tokens=active_tokens,
        revoked_tokens=revoked_tokens,
        valid_scopes=["collect.write", "catalog.read", "markets.write"],
    )


@bp.get("/api/tokens")
def api_tokens_alias():
    """API 토큰 별칭 경로 (Phase 145)."""
    return redirect(url_for("seller_console.personal_tokens"))


@bp.post("/me/tokens/generate")
def personal_tokens_generate():
    """새 Personal Access Token 발급 (Phase 135).

    Request body: {"scopes": ["collect.write", ...], "expires_days": 365}
    Response: {"ok": true, "raw_token": "tok_...", "expires_at": "..."}
    주의: raw_token은 1회만 반환됨.
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user_id = _current_user_id()

    data = request.get_json(force=True, silent=True) or {}
    scopes = data.get("scopes") or ["collect.write"]
    expires_days = int(data.get("expires_days", 365))

    try:
        from src.auth import personal_tokens as _pt
        result = _pt.generate_token(user_id=user_id, scopes=scopes, expires_days=expires_days)
        return jsonify({"ok": True, **result})
    except _pt.TokenStoreCommitError as exc:
        logger.warning("토큰 발급 저장 실패: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception as exc:
        logger.warning("토큰 발급 실패: %s", exc)
        return jsonify({"ok": False, "error": "토큰 발급 중 오류가 발생했습니다."}), 500


@bp.post("/me/tokens/revoke")
def personal_tokens_revoke():
    """Personal Access Token 회수 (Phase 135).

    Request body: {"token_hash": "..."}
    Response: {"ok": true}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user_id = _current_user_id()

    data = request.get_json(force=True, silent=True) or {}
    token_hash = (data.get("token_hash") or "").strip()
    if not token_hash:
        return jsonify({"ok": False, "error": "token_hash가 필요합니다."}), 400

    try:
        from src.auth.personal_tokens import revoke_token
        # v39 C: 별칭으로 발급된 토큰도 삭제되게 관용 식별자 매칭(삭제 0건 → 부활 방지). 실제 커밋 시에만 ok.
        ok = revoke_token(token_hash=token_hash, user_id=user_id, user_ids=_seller_identities())
        if not ok:
            return jsonify({"ok": False, "error": "삭제할 토큰을 찾지 못했어요(이미 삭제됐거나 권한 없음). 새로고침 후 확인해 주세요."}), 200
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("토큰 회수 실패: %s", exc)
        return jsonify({"ok": False, "error": "토큰 회수 중 오류가 발생했습니다."}), 500


@bp.post("/me/tokens/revoke-bulk")
def personal_tokens_revoke_bulk():
    """토큰 다중선택 삭제 — 체크박스로 고른 여러 토큰을 한 번에 폐기.

    Request body: {"token_hashes": ["...", ...]}
    각 토큰은 revoke_token(PG면 소프트삭제=durable)으로 폐기. 실제 폐기된 것만 revoked에 담아
    정직 집계(부활 0). 본인 스코프(관용 식별자) 밖 토큰은 무시.
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user_id = _current_user_id()
    data = request.get_json(force=True, silent=True) or {}
    hashes = data.get("token_hashes") or []
    if not isinstance(hashes, list) or not hashes:
        return jsonify({"ok": False, "error": "삭제할 토큰을 선택해 주세요."}), 400

    try:
        from src.auth.personal_tokens import revoke_token
        ids = _seller_identities()
        revoked, missed = [], []
        for th in hashes:
            th = (th or "").strip()
            if not th:
                continue
            if revoke_token(token_hash=th, user_id=user_id, user_ids=ids):
                revoked.append(th)
            else:
                missed.append(th)   # 이미 삭제됐거나 본인 것 아님(정직)
        return jsonify({"ok": len(revoked) > 0, "revoked": revoked, "revoked_count": len(revoked), "missed_count": len(missed)})
    except Exception as exc:
        logger.warning("토큰 다중 회수 실패: %s", exc)
        return jsonify({"ok": False, "error": "토큰 삭제 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# Phase 135: 북마클릿
# ---------------------------------------------------------------------------

@bp.get("/bookmarklet")
def bookmarklet():
    """북마클릿 설치 페이지 (Phase 135)."""
    from flask import session as _session
    server_url = os.getenv("APP_BASE_URL", "https://kohganepercentiii.com")

    # 사용자 토큰 힌트
    user_id = _session.get("user_id", "dev")

    return render_template(
        "bookmarklet.html",
        page="bookmarklet",
        server_url=server_url,
        user_id=user_id,
    )


def _bookmarklet_js(server: str, token: str, translate: bool) -> str:
    """북마클릿 javascript: 코드(내 토큰 baked) — 크롬 북마크 가져오기 파일 HREF에 넣는다.

    v46 STEP4: **가져오기 신뢰성 우선.** 과거엔 공유 추출기(~20KB)를 인라인해 javascript: URL이 29KB가
    되어 크롬 '북마크 가져오기'가 실패했다 → **경량화**(≈2KB): 클라이언트는 og 메타+대표 이미지+페이지
    HTML만 담아 보내고, **서버가 posted HTML에서 풍부 추출**(JSON-LD/초기상태/DOM). partial 판정도 서버
    응답(d.partial). 확장(격리월드 대응 JS 추출기)과 로직은 서버 추출로 공유, 북마클릿 URL은 작게 유지.
    (HTML 이스케이프는 호출부 html.escape가 처리 — 이번 원인은 이스케이프가 아니라 URL 길이였음.)
    """
    tr = "true" if translate else "false"
    return (
        "javascript:(function(){"
        "var S='" + server + "',T='" + token + "';"
        "try{var _c=0;document.querySelectorAll('a[href] img').forEach(function(i){if((i.naturalWidth||0)>=120)_c++});"
        "if(_c>=8){if(!confirm('이 페이지엔 상품이 여러 개 같아요. 북마클릿은 상품 1개 상세용입니다. 여러 상품은 크롬 확장을 쓰세요. 이 페이지를 1개로 수집할까요?'))return;}}catch(e){}"
        "function M(p){var e=document.querySelector('meta[property=\"'+p+'\"],meta[name=\"'+p+'\"]');return e?(e.content||''):''}"
        "function G(s){if(!s||s.indexOf('data:')===0)return false;if(/(logo|sprite|icon|avatar|placeholder|loading|blank|pixel|banner|thumb_)/i.test(s))return false;return true;}"
        "var imgs=[];var og=M('og:image');if(G(og))imgs.push(og);"
        "try{[].forEach.call(document.images||[],function(im){if(im&&im.src&&G(im.src)&&(im.naturalWidth||0)>=300&&(im.naturalHeight||0)>=300)imgs.push(im.src)})}catch(e){}"
        "var data={url:location.href,title:(M('og:title')||document.title||'').slice(0,300),"
        "price:M('product:price:amount')||'',currency:M('product:price:currency')||'',"
        "description:M('og:description')||M('description')||'',images:imgs.slice(0,30),"
        "html:(document.documentElement?document.documentElement.outerHTML:'').slice(0,900000),"
        "ext_version:'bookmarklet',translate:" + tr + "};"
        "function K(m,ok){var t=document.getElementById('kgpbm');if(!t){t=document.createElement('div');t.id='kgpbm';t.style.cssText='position:fixed;right:20px;bottom:84px;z-index:2147483647;display:flex;align-items:center;gap:8px;max-width:300px;padding:10px 14px;border-radius:10px;font:13px/1.4 -apple-system,BlinkMacSystemFont,sans-serif;color:#fff;box-shadow:0 6px 20px rgba(0,0,0,.3)';var ic=document.createElement('img');ic.src=S+'/seller/static/favicon-32.png?v=181';ic.alt='';ic.style.cssText='width:20px;height:20px;border-radius:5px;flex:none;background:#fff';t.appendChild(ic);var tx=document.createElement('span');tx.id='kgpbmx';tx.style.whiteSpace='pre-wrap';t.appendChild(tx);document.body.appendChild(t);}t.style.background=ok?'#16a34a':'#dc2626';var x=document.getElementById('kgpbmx');if(x)x.textContent=m;t.style.opacity='1';clearTimeout(t._h);t._h=setTimeout(function(){t.style.opacity='0'},4500);}"
        "try{if(/(^|\\.)temu\\.com$/i.test(location.hostname))K('테무는 상품 데이터가 API로만 로드돼 북마클릿은 일부만 수집돼요.\\n정확한 수집은 크롬 확장(고가수집기)을 쓰세요.',false)}catch(e){}"
        "K('수집 중…',true);"
        "try{console.log('[고가수집기] 전송요약',{price:data.price,currency:data.currency,images:(data.images||[]).length,desc:(data.description||'').length+'자',html:(data.html||'').length+'자'})}catch(e){}"
        "var _ST=0,_HTML=false;"
        "fetch(S+'/api/v1/collect/extension',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+T},body:JSON.stringify(data)})"
        ".then(function(r){_ST=r.status;return r.text().then(function(x){_HTML=/^\\s*<(!doctype|html)/i.test(x);try{return JSON.parse(x)}catch(e){return{}}})})"
        ".then(function(d){try{console.log('[고가수집기] /api/v1/collect/extension →',_ST,d)}catch(e){}"
        "if(d&&d.ok&&d.partial){K('부분 수집 — 페이지 정보를 충분히 못 읽었어요. 셀러 콘솔에서 확인·보완하세요',false);}"
        "else if(d&&d.ok){K('수집 완료 · 셀러 콘솔 ‘수집한 상품’에서 확인',true);}"
        "else if(_HTML){K('서버 응답 오류(로그인 확인이 필요할 수 있어요). HTTP '+_ST,false);}"
        "else{K('수집 실패 (HTTP '+_ST+'): '+((d&&d.error)||'잠시 후 다시 시도'),false);}})"
        ".catch(function(e){try{console.error('[고가수집기] 수집 요청 실패:',e)}catch(_){}"
        "K('이 사이트는 보안정책(CSP)으로 직접 수집이 막혀요.\\n크롬 확장(고가수집기)을 쓰세요.',false);});"
        "})();"
    )


_BRIDGE_ICON_DATA_URI = None


def _bridge_icon_data_uri() -> str:
    """북마크 ICON 속성용 브릿지 마크(favicon-48 v8) data:image/png;base64 — 1회 캐시."""
    global _BRIDGE_ICON_DATA_URI
    if _BRIDGE_ICON_DATA_URI is None:
        import base64
        p = os.path.join(os.path.dirname(__file__), "static", "favicon-48.png")
        with open(p, "rb") as f:
            _BRIDGE_ICON_DATA_URI = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    return _BRIDGE_ICON_DATA_URI


def _netscape_bookmark(href: str, icon_data_uri: str, label: str = "고가수집") -> str:
    """크롬 '북마크 가져오기'가 읽는 NETSCAPE-Bookmark-file-1 HTML. ICON 속성에 브릿지 마크.

    HREF는 html.escape로 이스케이프(크롬 가져오기 시 엔티티 디코드) → 아이콘이 북마크에 고정.
    v49 STEP3 수리: 앵커 텍스트=**가시 문자열 '고가수집'**. (v40-B가 쓰던 제로폭 U+200B는 가져오기
    후 북마크 이름이 '투명/빈칸'으로 보여 사용자가 못 찾는 버그의 근원 — 오너 실기기 확정. 이제 이름이
    '고가수집'으로 또렷이 보인다. 빈 문자열의 javascript: URL 폴백 우려도 해소.)
    """
    import html as _html
    href_esc = _html.escape(href, quote=True)
    label = _html.escape(label or "고가수집")
    return (
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n"
        "<META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\">\n"
        "<TITLE>Bookmarks</TITLE>\n"
        "<H1>Bookmarks</H1>\n"
        "<DL><p>\n"
        f"    <DT><A HREF=\"{href_esc}\" ICON=\"{icon_data_uri}\">{label}</A>\n"
        "</DL><p>\n"
    )


@bp.post("/bookmarklet/file")
def bookmarklet_file():
    """'내 북마클릿 파일 받기' — 토큰 발급(Supabase) 후 크롬 가져오기용 북마크 HTML을 내려준다.

    토큰 저장(Supabase 1단계)이 선행 — 저장 실패면 파일도 만들지 않고 정직한 실패(JSON).
    성공 시 Content-Disposition: attachment; filename="고가수집기.html".
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user_id = _current_user_id()
    translate = (request.form.get("translate") or request.args.get("translate") or "1") != "0"

    try:
        from src.auth import personal_tokens as _pt
        result = _pt.generate_token(user_id=user_id, scopes=["collect.write"], expires_days=365)
        raw = result.get("raw_token")
        if not raw:
            raise RuntimeError("토큰이 비어 있습니다.")
    except Exception as exc:
        # 토큰 저장 실패 → 파일 생성 실패(정직). 원인 1줄 로깅.
        logger.warning("북마클릿 파일 토큰 발급 실패: %s", exc)
        return jsonify({"ok": False, "error": "토큰을 저장하지 못해 파일을 만들지 못했어요. 잠시 후 다시 시도해 주세요."}), 503

    server = request.host_url.rstrip("/")
    href = _bookmarklet_js(server, raw, translate)
    html_body = _netscape_bookmark(href, _bridge_icon_data_uri())
    resp = Response(html_body, mimetype="text/html; charset=utf-8")
    fname = quote_plus("고가수집기.html").replace("+", "%20")
    resp.headers["Content-Disposition"] = (
        "attachment; filename=gogasujipgi.html; filename*=UTF-8''" + fname
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.post("/bookmarklet/code")
def bookmarklet_code():
    """v47 STEP3: '북마클릿 코드 복사' — 토큰 발급(Supabase) 후 javascript: 코드를 텍스트로 반환.

    진단: 크롬 '북마크 가져오기'(파일)는 최신 크롬에서 javascript: HREF를 보안상 드롭하거나 '가져온
    항목' 폴더에 묻히는 등 실기기 실패 사례가 있다. 또 **주소창에 javascript: 를 붙여넣으면 크롬이
    접두어를 지운다**(anti-XSS). 유일하게 안전한 경로 = **북마크 편집 대화상자의 URL 칸에 붙여넣기**.
    → 이 라우트가 코드를 주고, 클라가 클립보드에 복사 → 사용자가 '북마크 추가 → 편집 → URL칸 붙여넣기'.
    토큰 저장 실패면 코드도 안 준다(정직 503, 가짜 성공 0).
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    user_id = _current_user_id()
    translate = (request.form.get("translate") or request.args.get("translate") or "1") != "0"
    try:
        from src.auth import personal_tokens as _pt
        result = _pt.generate_token(user_id=user_id, scopes=["collect.write"], expires_days=365)
        raw = result.get("raw_token")
        if not raw:
            raise RuntimeError("토큰이 비어 있습니다.")
    except Exception as exc:
        logger.warning("북마클릿 코드 토큰 발급 실패: %s", exc)
        return jsonify({"ok": False, "error": "토큰을 저장하지 못해 코드를 만들지 못했어요. 잠시 후 다시 시도해 주세요."}), 503
    server = request.host_url.rstrip("/")
    code = _bookmarklet_js(server, raw, translate)
    return jsonify({"ok": True, "code": code})


def _chrome_extension_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "extensions", "chrome-collector"))


def _chrome_extension_version() -> str:
    try:
        with open(os.path.join(_chrome_extension_dir(), "manifest.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version", ""))
    except Exception:
        return ""


@bp.get("/extension")
def extension_install():
    """크롬 확장 설치 가이드 + 다운로드 (Phase 226)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    return render_template("extension_install.html", page="collect", version=_chrome_extension_version())


@bp.get("/extension/download")
def extension_download():
    """크롬 확장(고가네 수집)을 ZIP으로 즉석 패키징해 내려준다 — 설치용."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    import io
    import zipfile

    ext_dir = _chrome_extension_dir()
    if not os.path.isdir(ext_dir):
        abort(404)
    include = [
        "manifest.json", "background.js", "kgp-net.js", "kgp-extractor.js", "kgp-main.js", "content_script.js",
        "popup.html", "popup.js", "options.html", "options.js", "README.md",
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # manifest.json이 ZIP '루트'에 오게 한다(하위폴더 X). 그래야 압축 푼 폴더를
        # 그대로 '압축해제된 확장 로드'로 선택했을 때 크롬이 manifest를 찾는다.
        for name in include:
            p = os.path.join(ext_dir, name)
            if os.path.isfile(p):
                z.write(p, arcname=name)
        icons_dir = os.path.join(ext_dir, "icons")
        if os.path.isdir(icons_dir):
            for ic in sorted(os.listdir(icons_dir)):
                fp = os.path.join(icons_dir, ic)
                if os.path.isfile(fp):
                    z.write(fp, arcname=f"icons/{ic}")
    buf.seek(0)
    version = _chrome_extension_version() or "1"
    # v15: 일반 유저 친화 파일명 '고가수집기'(gogasujipgi). 받자마자 무엇인지 알게.
    fname = f"gogasujipgi-v{version}.zip"
    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------------------------------------------------------------------------
# Phase 135: Discovery 봇
# ---------------------------------------------------------------------------

@bp.get("/discovery")
def discovery():
    """Discovery 후보 목록 페이지 (Phase 135)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from src.discovery.scout import DiscoveryScout
        scout = DiscoveryScout()
        candidates = scout.get_candidates(status=request.args.get("status") or "pending")
    except Exception as exc:
        logger.warning("Discovery 후보 조회 실패: %s", exc)
        candidates = []

    return render_template(
        "discovery.html",
        page="discovery",
        candidates=candidates,
        status_filter=request.args.get("status", "pending"),
    )


@bp.post("/discovery/approve")
def discovery_approve():
    """Discovery 후보 도메인 승인 (Phase 135).

    Request body: {"domain": "example.com"}
    Response: {"ok": true}
    """
    data = request.get_json(force=True, silent=True) or {}
    domain = (data.get("domain") or "").strip().lower()
    if not domain:
        return jsonify({"ok": False, "error": "domain이 필요합니다."}), 400

    try:
        from src.discovery.scout import DiscoveryScout
        ok = DiscoveryScout().approve(domain)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("Discovery 승인 실패: %s", exc)
        return jsonify({"ok": False, "error": "승인 중 오류가 발생했습니다."}), 500


@bp.post("/discovery/reject")
def discovery_reject():
    """Discovery 후보 도메인 거부 (Phase 135).

    Request body: {"domain": "example.com"}
    Response: {"ok": true}
    """
    data = request.get_json(force=True, silent=True) or {}
    domain = (data.get("domain") or "").strip().lower()
    if not domain:
        return jsonify({"ok": False, "error": "domain이 필요합니다."}), 400

    try:
        from src.discovery.scout import DiscoveryScout
        ok = DiscoveryScout().reject(domain)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("Discovery 거부 실패: %s", exc)
        return jsonify({"ok": False, "error": "거부 중 오류가 발생했습니다."}), 500


@bp.get("/discovery/keywords")
def discovery_keywords():
    """Discovery 키워드 관리 페이지 (Phase 135)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from src.discovery.scout import DiscoveryScout
        keywords = DiscoveryScout().get_keywords()
    except Exception as exc:
        logger.warning("키워드 목록 조회 실패: %s", exc)
        keywords = []

    return render_template(
        "discovery_keywords.html",
        page="discovery",
        keywords=keywords,
    )


@bp.post("/discovery/keywords/add")
def discovery_keywords_add():
    """키워드 추가 (Phase 135).

    Request body: {"keyword": "yoga wear brand"}
    Response: {"ok": true}
    """
    data = request.get_json(force=True, silent=True) or {}
    keyword = (data.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"ok": False, "error": "keyword가 필요합니다."}), 400

    try:
        from src.discovery.scout import DiscoveryScout
        ok = DiscoveryScout().add_keyword(keyword)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("키워드 추가 실패: %s", exc)
        return jsonify({"ok": False, "error": "키워드 추가 중 오류가 발생했습니다."}), 500


@bp.post("/discovery/keywords/remove")
def discovery_keywords_remove():
    """키워드 삭제 (Phase 135).

    Request body: {"keyword": "yoga wear brand"}
    Response: {"ok": true}
    """
    data = request.get_json(force=True, silent=True) or {}
    keyword = (data.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"ok": False, "error": "keyword가 필요합니다."}), 400

    try:
        from src.discovery.scout import DiscoveryScout
        ok = DiscoveryScout().remove_keyword(keyword)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("키워드 삭제 실패: %s", exc)
        return jsonify({"ok": False, "error": "키워드 삭제 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# Phase 135.2: /seller/collect/history + /seller/collect/preview/<id>
# ---------------------------------------------------------------------------

@bp.get("/collect/history")
def collect_history():
    """수집 이력 페이지 (Phase 135.2)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    # v45(6): UI 언어 토글 — 목록 제목을 해당 언어만 표시(원문 폴백 시 '원문' 뱃지).
    try:
        from .i18n import normalize_lang as _norm_lang
        _current_lang = _norm_lang(request.cookies.get("kgp_lang"))
    except Exception:
        _current_lang = "ko"

    domain = request.args.get("domain", "").strip()
    source = request.args.get("source", "").strip()
    days = int(request.args.get("days", "30"))
    q = request.args.get("q", "").strip()
    status_f = request.args.get("status", "").strip()          # ""=전체 / ok / archived
    group_f = request.args.get("group", "").strip()            # 그룹 id 필터
    sort = (request.args.get("sort") or "newest").strip()
    per_page = request.args.get("per_page", 50, type=int)
    if per_page not in (20, 50, 100):
        per_page = 50
    page = max(1, request.args.get("page", 1, type=int))
    # 속도: 무한스크롤·나이아 점프 공통 창.
    fmt = (request.args.get("fmt") or "").strip()
    offset = max(0, request.args.get("offset", 0, type=int))

    # 속도: 기본 뷰(최신순·필터 없음)는 목록을 SQL LIMIT/OFFSET로 그 페이지만 가져온다
    #   (전체 스캔 회피 — 상품 많아도 첫 페이지 비용 고정). 필터/타 정렬은 기존 전체 로드 경로.
    _sql_page = (sort == "newest" and not q and not status_f and not group_f and not domain and not source)

    items = []
    summ = {"total": 0, "today": 0, "domains": 0, "by_source": {"extension": 0, "bookmarklet": 0, "manual": 0, "bulk": 0}}
    domains = []
    try:
        from .collect_history_store import list_items, summary, distinct_domains
        from src.utils.perf import perf_block
        _sid = _seller_id()
        _ids = _seller_identities()
        # v49 STEP2: DB 시간은 pg 레이어(query/tx)가 쿼리별로 계측한다(뷰 레벨 perf_block("db") 제거 —
        #   같은 쿼리를 이중 계상하던 것 해소). 목록은 lean=True(대형 컬럼 제외), 그룹 필터일 때만 full.
        _use_lean = not group_f
        if _sql_page:
            items = list_items(days=days, seller_ids=_ids, limit=per_page, offset=offset, lean=True)
        else:
            items = list_items(domain=domain, source=source, days=days, seller_ids=_ids, lean=_use_lean)
        # 속도: 무한스크롤 조각(fmt=rows)은 행만 렌더 → summary·도메인 스캔 2회 전부 생략(1쿼리).
        if fmt != "rows":
            summ = summary(days=days, seller_ids=_ids)
            domains = distinct_domains(seller_ids=_ids)
        logger.info("[collect-history] seller_id=%s identities=%s total=%s sql_page=%s fmt=%s", _sid, sorted(_ids), summ.get("total"), _sql_page, fmt or "-")
    except Exception as exc:
        logger.warning("수집 이력 조회 실패: %s", exc)

    if _sql_page:
        # SQL이 이미 최신순·해당 페이지만 반환 — 파이썬 필터/정렬/슬라이스 생략.
        total_filtered = summ.get("total", len(items))
        fastscroll = False
        all_rows = items
        has_more = (offset + len(items)) < total_filtered
        total_pages = max(1, (total_filtered + per_page - 1) // per_page)
        page = min(page, total_pages)
    else:
        # 상태 필터(활성/보관)
        if status_f in ("ok", "archived"):
            items = [it for it in items if (it.get("status") or "") == status_f]

        # 그룹 필터 (extra_json.group_id)
        if group_f:
            def _grp(it):
                try:
                    return (json.loads(it.get("extra_json") or "{}") or {}).get("group_id") or ""
                except Exception:
                    return ""
            items = [it for it in items if _grp(it) == group_f]

        # 검색(제목/도메인/URL 부분일치)
        if q:
            ql = q.lower()
            items = [it for it in items
                     if ql in (it.get("title") or "").lower()
                     or ql in (it.get("domain") or "").lower()
                     or ql in (it.get("url") or "").lower()]

        # 정렬
        def _price_num(it):
            try:
                return float(str(it.get("price") or "").replace(",", "").strip())
            except (TypeError, ValueError):
                return -1.0
        if sort == "oldest":
            items.sort(key=lambda r: r.get("collected_at", ""))
        elif sort == "price_high":
            items.sort(key=_price_num, reverse=True)
        elif sort == "price_low":
            items.sort(key=_price_num)
        elif sort == "title":
            items.sort(key=lambda r: (r.get("title") or "").lower())
        else:  # newest (기본)
            items.sort(key=lambda r: r.get("collected_at", ""), reverse=True)

        # 첫 offset~per_page개만(전체 로드 후 슬라이스). 이름순은 나이아 점프용 all_rows 필요.
        total_filtered = len(items)
        fastscroll = (sort == "title")
        all_rows = items                                  # 정렬된 전체(버킷 인덱스용)
        items = all_rows[offset:offset + per_page]
        has_more = (offset + len(items)) < total_filtered
        total_pages = max(1, (total_filtered + per_page - 1) // per_page)
        page = 1 if fastscroll else min(page, total_pages)

    # 속도 ② 페이로드 다이어트: extra_json은 항목당 **한 번만** 파싱(기존 3회 → 1회), 목록 썸네일은
    #   **대표 1장만**(목록은 한눈 확인용 — 갤러리 5장은 편집 드로어에서). 무거운 extra_json은 클라로 안 보냄(HTML만).
    for it in items:
        try:
            ex = json.loads(it.get("extra_json") or "{}")
        except Exception:
            ex = {}
        rep = (it.get("image_url") or "").strip()
        if not rep:                                   # 대표 없으면 수집 이미지 첫 장
            imgs = ex.get("images") if isinstance(ex.get("images"), list) else []
            for u in imgs:
                u = (str(u) or "").strip()
                if u:
                    rep = u
                    break
        it["thumbs"] = [rep] if rep else []           # 목록=대표 1장
        # v45(6): 한/영 분리 표시 — UI 언어 토글(current_lang)에 맞는 언어만(원문 폴백 시 '원문' 뱃지).
        _tko = (str(ex.get("title_ko") or "").strip()) or (str(it.get("title") or "").strip())
        _ten = str(ex.get("title_en") or ex.get("title") or it.get("title") or "").strip()
        _translated = bool(_tko) and bool(_ten) and _tko != _ten
        if _current_lang == "en":
            it["title_display"] = _ten or _tko or "(제목 없음)"
            it["title_is_original"] = not bool(_ten)
        else:  # ko
            it["title_display"] = (_tko if _translated else (_ten or _tko)) or "(제목 없음)"
            it["title_is_original"] = not _translated
        # v44-1: 업로드 성공한 마켓 라벨(등록됨 뱃지용) — extra_json.uploaded(서버 확인분)만.
        up = ex.get("uploaded")
        it["uploaded_markets"] = [str(u.get("market_label") or u.get("market"))
                                  for u in up if isinstance(u, dict) and (u.get("market_label") or u.get("market"))] if isinstance(up, list) else []
        # v47 STEP2: 수집 필드 상태(성공/부분 + 누락 필드) — 목록 상태 컬럼에 정직 표기.
        #   저장된 값이 있으면 그대로, 없으면(옛 레코드) 지금 판정(무음 실패·가짜 성공 금지).
        cs = ex.get("collect_status") if isinstance(ex.get("collect_status"), dict) else None
        if not cs:
            try:
                from src.collectors.collect_status import compute_collect_status as _ccs
                cs = _ccs(ex, title_fallback=it.get("title") or "")
            except Exception:
                cs = None
        it["collect_status"] = cs

    from .upload_dispatcher import MARKET_LABELS, SUPPORTED_MARKETS
    upload_markets = [{"code": m, "label": MARKET_LABELS.get(m, m)} for m in SUPPORTED_MARKETS]
    from .category_classifier import CATEGORY_OPTIONS
    # 번역 무료 사용량(v3 P1-4) — UI에 '무료 N/한도 남음' 표시
    try:
        from . import translation_usage
        _sid2 = _seller_id()
        translation_free = {
            "limit": translation_usage.free_limit(),
            "used": translation_usage.get_used(_sid2),
            "remaining": translation_usage.remaining(_sid2),
        }
    except Exception:
        translation_free = {"limit": 20, "used": 0, "remaining": 20}
    logger.info("[collect-history] sort=%s total=%s offset=%s rendered=%s", sort, total_filtered, offset, len(items))
    from src.utils.perf import perf_block

    # 무한스크롤·나이아 점프 요청 → 행 파셜만(경량).
    if fmt == "rows":
        with perf_block("render"):
            return render_template("collect_history_rows.html", items=items)

    # 상품 그룹(v3 P1-5)
    try:
        from . import collect_groups
        groups = collect_groups.list_groups(_seller_id())
    except Exception:
        groups = []

    # 이름순이면 나이아 버킷 인덱스(전체 렌더 없이 실데이터 샘플+offset). 이미지=대표(image_url).
    fs_buckets = {}
    if fastscroll:
        fs_buckets = _fs_build_buckets([((r.get("title") or ""), (r.get("image_url") or "")) for r in all_rows])

    with perf_block("render"):
      return render_template(
        "collect_history.html",
        page="collect_history",
        items=items,
        summary=summ,
        domains=domains,
        has_more=has_more,
        fs_buckets=fs_buckets,
        filters={"domain": domain, "source": source, "days": days,
                 "q": q, "status": status_f, "group": group_f, "sort": sort, "per_page": per_page},
        pagination={"page": page, "per_page": per_page, "total": total_filtered,
                    "total_pages": total_pages},
        upload_markets=upload_markets,
        category_options=CATEGORY_OPTIONS,
        translation_free=translation_free,
        groups=groups,
        fastscroll=fastscroll,
    )


@bp.get("/collect-history")
def collect_history_alias():
    """수집 이력 별칭 경로 (Phase 145)."""
    return redirect(url_for("seller_console.collect_history"))


@bp.get("/collect/history/count")
def collect_history_count():
    """수집 이력 총건수(경량 폴링용) — v41 STEP 1-0b.

    수집이력 화면이 열려 있으면 이 값을 폴링/탭포커스로 재조회해, 서버에 실제로
    영속 저장된 건수가 늘었을 때만 자동 새로고침을 트리거한다(가짜 실시간 금지).
    정직 데이터: 실제 저장 스코프(user_id+email 관용집합)로 재읽기한 값만 반환.
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "auth"}), 401
    try:
        days = int(request.args.get("days", "30"))
    except (TypeError, ValueError):
        days = 30
    total = 0
    try:
        from .collect_history_store import summary
        summ = summary(days=days, seller_ids=_seller_identities())
        total = int(summ.get("total") or 0)
    except Exception as exc:
        logger.warning("[collect-history-count] 조회 실패: %s", exc)
        return jsonify({"ok": False, "error": "server"}), 200
    return jsonify({"ok": True, "total": total})


@bp.get("/collect/preview/<item_id>")
def collect_preview_by_id(item_id: str):
    """수집된 상품 미리보기 (Phase 135.2)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    # v30: 목록과 동일한 관용 스코프로 조회 → 별칭 불일치 404 회귀 방지.
    item = _get_owned_item(item_id)
    if not item:
        # v39 F: 404 페이지(신뢰 깨짐) 금지 → 드로어/페이지 안에서 '수집 실패' 빈 상태(200, 정직).
        logger.info("[collect-preview] 항목 없음 → 수집 실패 빈 상태: id=%s seller=%s", item_id, _seller_id())
        return render_template("collect_preview_missing.html", page="collect_history",
                               item_id=item_id, drawer=bool(request.args.get("drawer")))

    extra = {}
    try:
        extra = json.loads(item.get("extra_json") or "{}")
    except Exception:
        pass

    # v39 D: 과거 수집분에 남아있을 수 있는 플레이스홀더 토큰을 편집 프리필 직전에 제거(렌더 안전망).
    try:
        from src.collectors.universal_scraper import strip_placeholder_tokens as _strip_ph
        if item.get("title"):
            item = dict(item); item["title"] = _strip_ph(item["title"])
        for _k in ("title", "title_ko", "title_en", "description", "description_ko"):
            if extra.get(_k):
                extra[_k] = _strip_ph(extra[_k])
    except Exception:
        pass

    # 원화 환산용 환율 주입 (편집 페이지 환율 계산기). 실패해도 편집은 동작.
    fx_rates: dict = {"KRW": 1.0}
    fx_is_mock = True
    fx_updated = ""
    try:
        from .data_aggregator import get_fx_rates
        fxd = get_fx_rates() or {}
        for code in ("USD", "JPY", "CNY", "EUR"):
            if isinstance(fxd.get(code), (int, float)):
                fx_rates[code] = float(fxd[code])
        fx_is_mock = bool(fxd.get("is_mock", True))
        fx_updated = str(fxd.get("updated_at") or "")
    except Exception as exc:
        logger.debug("FX 환율 주입 실패: %s", exc)

    # 마켓 연동 상태(셀러별) — 편집 화면에서 어떤 마켓이 연결됐는지 한눈에
    market_connected: dict = {}
    try:
        from . import market_credentials as mc
        for m in ("shopify", "coupang", "smartstore", "elevenst", "woocommerce"):
            market_connected[m] = bool(mc.is_connected(_seller_id(), m))
    except Exception as exc:
        logger.debug("마켓 연결 상태 조회 실패: %s", exc)

    # 카테고리 자동 분류(현재값 없으면 제목/키워드로 제안) + 카테고리별 추천 키워드
    from .category_classifier import CATEGORY_OPTIONS, classify as _classify, suggest_keywords as _suggest_kw
    cur_cat = (extra.get("category_code") or extra.get("category") or "").strip()
    _title_for_cat = item.get("title") or extra.get("title_ko") or ""
    cat_suggestion = _classify(
        _title_for_cat,
        extra.get("description_ko") or extra.get("description") or "",
        ",".join(extra.get("keywords") or []) if isinstance(extra.get("keywords"), list) else (extra.get("keywords") or ""),
    )
    # 이미 카테고리가 정해져 있으면 그 카테고리 기준 추천 키워드를 제공
    if cur_cat:
        cat_suggestion = {**cat_suggestion, "suggested_keywords": _suggest_kw(cur_cat, _title_for_cat)}

    # v47 STEP2: 수집 로그(어느 소스가 어느 필드를 줬는지) — 드로어 하단 접이식. 저장값 우선, 없으면 판정.
    collect_status = extra.get("collect_status") if isinstance(extra.get("collect_status"), dict) else None
    if not collect_status:
        try:
            from src.collectors.collect_status import compute_collect_status as _ccs
            collect_status = _ccs(extra, title_fallback=item.get("title") or "")
        except Exception:
            collect_status = None

    from src.utils.perf import perf_block as _pb
    with _pb("render"):
      return render_template(
        "collect_preview.html",
        page="collect_history",
        item=item,
        extra=extra,
        collect_status=collect_status,
        fx_rates=fx_rates,
        fx_is_mock=fx_is_mock,
        fx_updated=fx_updated,
        market_connected=market_connected,
        category_options=CATEGORY_OPTIONS,
        current_category=cur_cat,
        category_suggestion=cat_suggestion,
    )


@bp.post("/collect/classify")
def collect_classify():
    """상품명/설명으로 카테고리 자동 분류 (Phase 224).

    Request: {"title": "...", "description": "...", "keywords": "..."}
    Response: {"ok": true, "code": "BAG", "label": "가방/지갑", "confidence": 0.8, "matched": [...]}
    """
    data = request.get_json(force=True, silent=True) or {}
    from .category_classifier import classify
    res = classify(
        str(data.get("title") or ""),
        str(data.get("description") or ""),
        str(data.get("keywords") or ""),
    )
    return jsonify({"ok": True, **res})


@bp.post("/collect/preview/<item_id>/ai-description")
def collect_ai_description(item_id: str):
    """v39-E2 #3: 상세설명이 없거나 빈약할 때 AI 상세 '초안' 생성(자동 확정 금지 — 사용자 편집/승인).

    Request: {"title": "...", "category": "...", "keywords": "...", optional specs}
    Response: {"ok": true, "text": "...", "provider": "openai"|"stub", "is_draft": true}
    키 미설정/dry-run/실패 = provider "stub"(가짜 상세 생성 0, 확인된 정보만 구조화).
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    item = _get_owned_item(item_id)
    if not item:
        return jsonify({"ok": False, "error": "항목을 찾을 수 없습니다."}), 200

    extra = {}
    try:
        extra = json.loads(item.get("extra_json") or "{}")
    except Exception:
        pass

    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or item.get("title") or extra.get("title_ko") or "").strip()
    category = (data.get("category") or extra.get("category_code") or "").strip()
    keywords = data.get("keywords") or extra.get("keywords") or []
    specs = extra.get("detail_specs") or []
    # 옵션도 스펙 힌트로(예: 색상/사이즈) — 확인된 정보만
    for opt in (extra.get("options") or []):
        if isinstance(opt, dict) and opt.get("name") and opt.get("values"):
            specs = list(specs) + [[opt["name"], ", ".join(map(str, opt["values"][:8]))]]

    try:
        from .ai.translator import AITranslator
        res = AITranslator().generate_description({
            "title": title, "category": category, "keywords": keywords,
            "specs": specs, "brand": extra.get("brand") or "",
        })
    except Exception as exc:
        logger.warning("AI 상세 생성 오류: %s", exc)
        return jsonify({"ok": False, "error": "AI 상세 생성 중 오류가 발생했습니다."}), 500

    return jsonify({"ok": True, "text": res.get("text", ""),
                    "provider": res.get("provider", "stub"), "is_draft": True})


@bp.post("/collect/preview/<item_id>/save")
def collect_preview_save(item_id: str):
    """수집 항목 중간 편집 저장 (Phase 201).

    수집→확인·수정→업로드 흐름에서 제목·가격·통화·상세설명·이미지·옵션을
    셀러가 편집한 뒤 저장한다. extra_json에 상세 필드를 머지해 보관한다.

    Request body: {title, price, currency, description, images:[...], options:[{name,values}]}
    Response: {"ok": true, "product": {...}}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(force=True, silent=True) or {}
    from . import collect_history_store

    item = _get_owned_item(item_id)        # v30: 목록과 동일 스코프
    if not item:
        return jsonify({"ok": False, "error": "항목을 찾을 수 없습니다."}), 404

    try:
        extra = json.loads(item.get("extra_json") or "{}")
        if not isinstance(extra, dict):
            extra = {}
    except Exception:
        extra = {}

    title = (data.get("title") or "").strip()
    price = (str(data.get("price")) if data.get("price") is not None else "").strip()
    currency = (data.get("currency") or item.get("currency") or "").strip()
    description = data.get("description")
    images = data.get("images")
    options = data.get("options")

    # 이미지 정규화 (빈 항목 제거, 순서 유지)
    if isinstance(images, list):
        images = [str(u).strip() for u in images if str(u).strip()]
    else:
        images = None

    # 옵션 정규화 [{name, values:[...]}]
    if isinstance(options, list):
        norm_opts = []
        for opt in options:
            if not isinstance(opt, dict):
                continue
            name = (opt.get("name") or "").strip()
            if not name:
                continue
            vals = opt.get("values")
            if isinstance(vals, str):
                vals = [v.strip() for v in vals.split(",") if v.strip()]
            elif isinstance(vals, list):
                vals = [str(v).strip() for v in vals if str(v).strip()]
            else:
                vals = []
            norm_opts.append({"name": name, "values": vals})
        options = norm_opts
    else:
        options = None

    # extra_json 머지 (수정된 값으로 갱신, 미수정 항목은 보존)
    if title:
        extra["title"] = title
        extra["title_ko"] = title
    if description is not None:
        extra["description"] = description
        extra["description_ko"] = description
    if images is not None:
        extra["images"] = images
    # v39-E2 #2: 갤러리(대표)·상세설명 이미지 버킷 보존(분리 저장).
    _gi = data.get("gallery_images")
    if isinstance(_gi, list):
        extra["gallery_images"] = [str(u).strip() for u in _gi if str(u).strip()]
    _di = data.get("detail_images")
    if isinstance(_di, list):
        extra["detail_images"] = [str(u).strip() for u in _di if str(u).strip()]
    # v40-C: 마켓별 상세페이지 블록(공통 + 마켓 오버라이드) 보존.
    _db = data.get("detail_blocks")
    if isinstance(_db, dict):
        clean = {}
        for mkey, blocks in _db.items():
            if not isinstance(blocks, list):
                continue
            norm = []
            for b in blocks:
                if isinstance(b, dict) and b.get("type") in ("text", "image", "highlight", "divider"):
                    norm.append({"type": b["type"], "content": str(b.get("content") or "")[:5000]})
            clean[str(mkey)[:20]] = norm
        extra["detail_blocks"] = clean
    if options is not None:
        extra["options"] = options
    if price:
        extra["price"] = price
        extra["price_original"] = price
    if currency:
        extra["currency"] = currency

    # 키워드/태그 정규화 (배열 또는 쉼표 문자열 허용)
    keywords = data.get("keywords")
    if keywords is None:
        keywords = data.get("tags")
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    if isinstance(keywords, list):
        keywords = [str(k).strip() for k in keywords if str(k).strip()]
        extra["keywords"] = keywords
        extra["tags"] = keywords

    # 카테고리(자동 분류 결과 또는 셀러 선택) 저장 — 각 마켓 업로더가 매핑
    category_code = (data.get("category_code") or data.get("category") or "").strip()
    if category_code:
        extra["category_code"] = category_code
        extra["category"] = category_code
    extra["edited"] = True

    ok = collect_history_store.update(
        item_id,
        # v30: 저장 항목의 실제 seller_id로 쓰기 가드 일치(별칭 불일치로 저장 실패 방지)
        seller_id=item.get("seller_id") or _seller_id(),
        title=title or item.get("title") or "",
        price=price or item.get("price") or "",
        currency=currency or item.get("currency") or "",
        image_url=(images[0] if images else item.get("image_url") or ""),
        extra_json=json.dumps(extra, ensure_ascii=False),
    )
    if not ok:
        return jsonify({"ok": False, "error": "저장에 실패했습니다."}), 500

    return jsonify({"ok": True, "product": extra})


# ---------------------------------------------------------------------------
# Phase 136: 자동 가격 조정 룰 관리 + 이력 + cron
# ---------------------------------------------------------------------------

def _get_pricing_rule_store():
    try:
        from src.pricing.rule import PricingRuleStore
        return PricingRuleStore()
    except Exception as exc:
        logger.warning("PricingRuleStore 로드 실패: %s", exc)
        return None


def _get_competitor_monitor():
    try:
        from src.pricing.competitor_monitor import CompetitorMonitor
        return CompetitorMonitor()
    except Exception as exc:
        logger.warning("CompetitorMonitor 로드 실패: %s", exc)
        return None


def _get_fx_impact_analyzer():
    try:
        from src.pricing.fx_impact import FXImpactAnalyzer
        return FXImpactAnalyzer()
    except Exception as exc:
        logger.warning("FXImpactAnalyzer 로드 실패: %s", exc)
        return None


@bp.get("/pricing/rules")
def pricing_rules():
    """가격 정책 룰 관리 페이지 (Phase 136)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    store = _get_pricing_rule_store()
    rules = []
    if store:
        try:
            rules = [r.to_dict() for r in store.list_all()]
        except Exception as exc:
            logger.warning("룰 목록 로드 실패: %s", exc)

    dry_run_active = os.getenv("PRICING_DRY_RUN", "1") == "1"

    return render_template(
        "pricing_rules.html",
        page="pricing_rules",
        rules=rules,
        dry_run_active=dry_run_active,
    )


@bp.post("/pricing/rules")
def pricing_rules_create():
    """가격 룰 신규 생성 (Phase 136).

    Request body: 룰 파라미터 (JSON)
    Response: {"ok": true, "rule": {...}}
    """
    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다.", "login_url": "/auth/login"}), 401
    if session.get("user_role") not in ("seller", "admin"):
        return jsonify({"ok": False, "error": "권한이 없습니다."}), 403

    data = request.get_json(force=True, silent=True) or {}
    if not data.get("name"):
        return jsonify({"ok": False, "error": "룰 이름이 필요합니다."}), 400

    store = _get_pricing_rule_store()
    if store is None:
        return jsonify({"ok": False, "error": "가격 엔진 준비 중입니다."}), 503

    try:
        from src.pricing.rule import PricingRule
        rule = PricingRule.from_dict(data)
        rule = store.create(rule)
        return jsonify({"ok": True, "rule": rule.to_dict()}), 201
    except Exception as exc:
        logger.warning("룰 생성 실패: %s", exc)
        return jsonify({"ok": False, "error": "룰 생성 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/rules/<rule_id>/edit")
def pricing_rules_edit(rule_id: str):
    """가격 룰 수정 (Phase 136)."""
    data = request.get_json(force=True, silent=True) or {}
    store = _get_pricing_rule_store()
    if store is None:
        return jsonify({"ok": False, "error": "가격 엔진 준비 중입니다."}), 503

    rule = store.get(rule_id)
    if not rule:
        return jsonify({"ok": False, "error": "룰을 찾을 수 없습니다."}), 404

    try:
        from src.pricing.rule import PricingRule
        data["rule_id"] = rule_id
        updated_rule = PricingRule.from_dict({**rule.to_dict(), **data})
        ok = store.update(updated_rule)
        return jsonify({"ok": ok, "rule": updated_rule.to_dict()})
    except Exception as exc:
        logger.warning("룰 수정 실패: %s", exc)
        return jsonify({"ok": False, "error": "룰 수정 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/rules/<rule_id>/delete")
def pricing_rules_delete(rule_id: str):
    """가격 룰 삭제 (Phase 136)."""
    store = _get_pricing_rule_store()
    if store is None:
        return jsonify({"ok": False, "error": "가격 엔진 준비 중입니다."}), 503

    ok = store.delete(rule_id)
    if not ok:
        return jsonify({"ok": False, "error": "룰을 찾을 수 없습니다."}), 404
    return jsonify({"ok": True})


@bp.post("/pricing/rules/<rule_id>/toggle")
def pricing_rules_toggle(rule_id: str):
    """가격 룰 활성/비활성 토글 (Phase 136)."""
    store = _get_pricing_rule_store()
    if store is None:
        return jsonify({"ok": False, "error": "가격 엔진 준비 중입니다."}), 503

    new_state = store.toggle(rule_id)
    if new_state is None:
        return jsonify({"ok": False, "error": "룰을 찾을 수 없습니다."}), 404
    return jsonify({"ok": True, "enabled": new_state})


@bp.post("/pricing/rules/reorder")
def pricing_rules_reorder():
    """룰 우선순위 재정렬 (Phase 136).

    Request body: {"ordered_ids": ["rule_id_1", "rule_id_2", ...]}
    """
    data = request.get_json(force=True, silent=True) or {}
    ordered_ids = data.get("ordered_ids") or []
    if not ordered_ids:
        return jsonify({"ok": False, "error": "ordered_ids가 필요합니다."}), 400

    store = _get_pricing_rule_store()
    if store is None:
        return jsonify({"ok": False, "error": "가격 엔진 준비 중입니다."}), 503

    try:
        store.reorder(ordered_ids)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.warning("룰 재정렬 실패: %s", exc)
        return jsonify({"ok": False, "error": "재정렬 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/simulate")
def pricing_simulate():
    """가격 시뮬레이션 (dry_run=True) — 영향 SKU 미리보기 (Phase 136).

    Response: {"ok": true, "results": {...}}
    """
    try:
        from src.pricing.auto_adjuster import PricingAutoAdjuster
        results = PricingAutoAdjuster().evaluate(dry_run=True)
        return jsonify({"ok": True, "results": results})
    except Exception as exc:
        logger.warning("자동 조정 시뮬레이션 오류(엔진 폴백): %s", exc)
        try:
            from src.pricing.engine import PricingEngine
            results = PricingEngine().evaluate(dry_run=True)
            return jsonify({"ok": True, "results": results})
        except Exception as fallback_exc:
            logger.warning("가격 시뮬레이션 폴백 오류: %s", fallback_exc)
            return jsonify({"ok": False, "error": "시뮬레이션 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/run-now")
def pricing_run_now():
    """가격 즉시 실행 (Phase 136).

    Request body: {"dry_run": true|false}
    Response: {"ok": true, "results": {...}}
    """
    data = request.get_json(force=True, silent=True) or {}
    dry_run = data.get("dry_run", True)

    try:
        from src.pricing.auto_adjuster import PricingAutoAdjuster
        results = PricingAutoAdjuster().evaluate(dry_run=bool(dry_run))
        return jsonify({"ok": True, "results": results})
    except Exception as exc:
        logger.warning("자동 가격 실행 오류(엔진 폴백): %s", exc)
        try:
            from src.pricing.engine import PricingEngine
            results = PricingEngine().evaluate(dry_run=bool(dry_run))
            return jsonify({"ok": True, "results": results})
        except Exception as fallback_exc:
            logger.warning("가격 즉시 실행 폴백 오류: %s", fallback_exc)
            return jsonify({"ok": False, "error": "실행 중 오류가 발생했습니다."}), 500


@bp.get("/pricing/competitors")
def pricing_competitors():
    """경쟁사 모니터링 대상 관리 + 가격 추이 페이지 (Phase 140)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    monitor = _get_competitor_monitor()
    targets = []
    trend_map: Dict[str, list] = {}
    if monitor:
        try:
            targets = [t.to_dict() for t in monitor.list_targets()]
            for t in targets:
                trend_map[t["competitor_id"]] = monitor.get_price_trend(t["competitor_id"], points=20)
        except Exception as exc:
            logger.warning("경쟁사 목록 로드 실패: %s", exc)

    return render_template(
        "pricing_competitors.html",
        page="pricing_competitors",
        targets=targets,
        trend_map=trend_map,
    )


@bp.post("/pricing/competitors")
def pricing_competitors_create():
    payload = request.get_json(force=True, silent=True) or {}
    monitor = _get_competitor_monitor()
    if monitor is None:
        return jsonify({"ok": False, "error": "경쟁사 모니터 모듈 준비 중입니다."}), 503
    if not payload.get("url"):
        return jsonify({"ok": False, "error": "URL이 필요합니다."}), 400
    target = monitor.create_target(payload)
    return jsonify({"ok": True, "target": target.to_dict()}), 201


@bp.post("/pricing/competitors/<competitor_id>/edit")
def pricing_competitors_edit(competitor_id: str):
    payload = request.get_json(force=True, silent=True) or {}
    monitor = _get_competitor_monitor()
    if monitor is None:
        return jsonify({"ok": False, "error": "경쟁사 모니터 모듈 준비 중입니다."}), 503
    target = monitor.update_target(competitor_id, payload)
    if not target:
        return jsonify({"ok": False, "error": "대상을 찾을 수 없습니다."}), 404
    return jsonify({"ok": True, "target": target.to_dict()})


@bp.post("/pricing/competitors/<competitor_id>/delete")
def pricing_competitors_delete(competitor_id: str):
    monitor = _get_competitor_monitor()
    if monitor is None:
        return jsonify({"ok": False, "error": "경쟁사 모니터 모듈 준비 중입니다."}), 503
    ok = monitor.delete_target(competitor_id)
    if not ok:
        return jsonify({"ok": False, "error": "대상을 찾을 수 없습니다."}), 404
    return jsonify({"ok": True})


@bp.post("/pricing/competitors/monitor-now")
def pricing_competitors_monitor_now():
    monitor = _get_competitor_monitor()
    if monitor is None:
        return jsonify({"ok": False, "error": "경쟁사 모니터 모듈 준비 중입니다."}), 503
    payload = request.get_json(force=True, silent=True) or {}
    competitor_id = payload.get("competitor_id")
    result = monitor.monitor_now(competitor_id=competitor_id)
    return jsonify({"ok": True, "result": result})


@bp.get("/pricing/fx-impact")
def pricing_fx_impact():
    """환율 영향 페이지 (Phase 140)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    analyzer = _get_fx_impact_analyzer()
    data = {"alerts": [], "impacted": [], "threshold_pct": 0}
    if analyzer:
        try:
            data = analyzer.detect_and_notify()
        except Exception as exc:
            logger.warning("FX 영향 분석 실패: %s", exc)

    return render_template(
        "pricing_fx_impact.html",
        page="pricing_fx_impact",
        fx_data=data,
    )


@bp.post("/pricing/fx-impact/reprice")
def pricing_fx_impact_reprice():
    analyzer = _get_fx_impact_analyzer()
    if analyzer is None:
        return jsonify({"ok": False, "error": "FX 영향 분석 모듈 준비 중입니다."}), 503
    impacted = analyzer.impacted_products()
    sku_filter = {str(x.get("sku") or "") for x in impacted if x.get("sku")}
    try:
        from src.pricing.auto_adjuster import PricingAutoAdjuster
        dry_run = request.args.get("dry_run", "1") != "0"
        results = PricingAutoAdjuster().evaluate(dry_run=dry_run, product_filter=sku_filter)
        return jsonify({"ok": True, "results": results, "impacted": impacted})
    except Exception as exc:
        logger.warning("FX 일괄 재가격 오류: %s", exc)
        return jsonify({"ok": False, "error": "일괄 재가격 실행 중 오류가 발생했습니다."}), 500


@bp.get("/pricing/history")
def pricing_history():
    """가격 변동 이력 페이지 (Phase 136)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    sku = request.args.get("sku", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    items = []
    try:
        from src.pricing.history_store import PriceHistoryStore
        store = PriceHistoryStore()
        items = store.list_history(
            sku=sku or None,
            date_from=date_from or None,
            date_to=date_to or None,
        )
    except Exception as exc:
        logger.warning("가격 이력 조회 실패: %s", exc)

    return render_template(
        "pricing_history.html",
        page="pricing_rules",
        items=items,
        filters={"sku": sku, "date_from": date_from, "date_to": date_to},
    )


@bp.post("/pricing/history/<history_id>/rollback")
def pricing_history_rollback(history_id: str):
    """가격 롤백 (Phase 136) — 이전 가격으로 복원.

    Response: {"ok": true, "new_history": {...}}
    """
    from flask import session as _session
    applied_by = _session.get("user_email") or _session.get("user_id") or "manual"

    try:
        from src.pricing.history_store import PriceHistoryStore
        store = PriceHistoryStore()
        new_item = store.rollback(history_id, applied_by=applied_by)
        if not new_item:
            return jsonify({"ok": False, "error": "이력을 찾을 수 없습니다."}), 404
        return jsonify({"ok": True, "new_history": new_item})
    except Exception as exc:
        logger.warning("가격 롤백 오류: %s", exc)
        return jsonify({"ok": False, "error": "롤백 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# Phase 142 — 자동 리오더 + 할인 캠페인 라우트
# ---------------------------------------------------------------------------

@bp.get("/inventory/reorder")
def inventory_reorder():
    """자동 리오더 권장 발주 목록 페이지 (Phase 142)."""
    if not session.get("user_id"):
        return redirect(url_for("auth.login", next=request.url))

    try:
        from src.inventory.auto_reorder import AutoReorderEngine
        engine = AutoReorderEngine()
        recommendations = engine.get_recommendations()
        enabled = os.getenv("AUTO_REORDER_ENABLED", "0") == "1"
        auto_place = os.getenv("AUTO_REORDER_AUTO_PLACE", "0") == "1"
        daily_budget = int(os.getenv("AUTO_REORDER_DAILY_BUDGET_KRW", "500000"))
    except Exception as exc:
        logger.warning("auto_reorder 로드 실패: %s", exc)
        recommendations = []
        enabled = False
        auto_place = False
        daily_budget = 0

    body_rows = ""
    for item in recommendations:
        est = item.get("estimated_cost_krw", 0)
        body_rows += (
            f"<tr>"
            f"<td><code>{item['sku']}</code></td>"
            f"<td>{item['title']}</td>"
            f"<td>{item['vendor']}</td>"
            f"<td class='text-center'>{item['current_stock']}</td>"
            f"<td class='text-center'>{item['sales_velocity_daily']:.1f}/일</td>"
            f"<td class='text-center fw-bold text-primary'>{item['recommended_qty']}</td>"
            f"<td class='text-end'>₩{est:,}</td>"
            f"<td><span class='badge bg-warning text-dark'>{item['status']}</span></td>"
            "</tr>"
        )

    total_cost = sum(i.get("estimated_cost_krw", 0) for i in recommendations)
    status_badge = '<span class="badge bg-success">ON</span>' if enabled else '<span class="badge bg-secondary">OFF</span>'
    auto_badge = '<span class="badge bg-danger">자동발주 ON</span>' if auto_place else '<span class="badge bg-secondary">승인 필요</span>'

    from markupsafe import Markup
    body = Markup(
        f"<h4 class='mb-3'>📦 자동 리오더 — 권장 발주 목록</h4>"
        f"<div class='mb-3 d-flex gap-2 align-items-center flex-wrap'>"
        f"  자동 리오더: {status_badge}"
        f"  발주 모드: {auto_badge}"
        f"  일일 예산: ₩{daily_budget:,}"
        f"</div>"
        + (
            "<div class='alert alert-warning'>자동 리오더가 비활성화되어 있습니다. <code>AUTO_REORDER_ENABLED=1</code>로 설정하세요.</div>"
            if not enabled else ""
        )
        + (
            "<div class='alert alert-info'>권장 발주 없음 — 재고가 안전 수준 이상입니다.</div>"
            if not recommendations else
            f"<div class='mb-2'>총 <strong>{len(recommendations)}</strong>건, 예상 비용 <strong>₩{total_cost:,}</strong></div>"
            f"<div class='table-responsive'>"
            f"<table class='table table-hover table-sm'>"
            f"<thead><tr><th>SKU</th><th>상품명</th><th>소싱처</th><th>현재고</th><th>판매속도</th><th>권장발주량</th><th class='text-end'>예상비용</th><th>상태</th></tr></thead>"
            f"<tbody>{body_rows}</tbody>"
            f"</table>"
            f"</div>"
        )
        + "<div class='mt-3'><a href='/admin/diagnostics' class='btn btn-outline-secondary btn-sm'>← 진단 대시보드</a></div>"
    )

    return _render_seller_page("자동 리오더", body, page="inventory_reorder")


@bp.post("/inventory/reorder/approve")
def inventory_reorder_approve():
    """선택 SKU 발주 승인 (Phase 142)."""
    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "로그인 필요"}), 401

    skus = request.json.get("skus", []) if request.is_json else request.form.getlist("skus")
    if not skus:
        return jsonify({"ok": False, "error": "SKU를 선택하세요"}), 400

    try:
        from src.inventory.auto_reorder import AutoReorderEngine
        engine = AutoReorderEngine()
        result = engine.approve_and_place(skus)
        return jsonify(result)
    except Exception as exc:
        logger.warning("reorder_approve 오류: %s", exc)
        return jsonify({"ok": False, "error": "처리 중 오류가 발생했습니다"}), 500


@bp.get("/marketing/campaigns")
def marketing_campaigns():
    """할인 캠페인 관리 페이지 (Phase 142)."""
    if not session.get("user_id"):
        return redirect(url_for("auth.login", next=request.url))

    try:
        from src.marketing.discount_campaign import DiscountCampaignEngine
        engine = DiscountCampaignEngine()
        recommendations = engine.get_recommendations()
        active = engine.get_active_campaigns()
        enabled = os.getenv("DISCOUNT_CAMPAIGN_ENABLED", "0") == "1"
        max_pct = int(os.getenv("DISCOUNT_CAMPAIGN_MAX_PCT", "20"))
        margin_floor = int(os.getenv("DISCOUNT_CAMPAIGN_MARGIN_FLOOR_PCT", "10"))
    except Exception as exc:
        logger.warning("discount_campaign 로드 실패: %s", exc)
        recommendations = []
        active = []
        enabled = False
        max_pct = 20
        margin_floor = 10

    def _campaign_rows(items: list) -> str:
        rows = ""
        for c in items:
            margin_class = "text-success" if c.get("margin_pct_after", 0) >= margin_floor else "text-danger"
            rows += (
                f"<tr>"
                f"<td><code>{c['sku']}</code></td>"
                f"<td>{c['title']}</td>"
                f"<td>{c['market']}</td>"
                f"<td class='text-end'>₩{c['original_price_krw']:,}</td>"
                f"<td class='text-center text-primary fw-bold'>{c['discount_pct']:.0f}%</td>"
                f"<td class='text-end fw-bold'>₩{c['discounted_price_krw']:,}</td>"
                f"<td class='text-center {margin_class}'>{c['margin_pct_after']:.1f}%</td>"
                f"<td><span class='badge bg-{'warning text-dark' if c['status'] == 'recommended' else 'success'}'>{c['status']}</span></td>"
                "</tr>"
            )
        return rows

    from markupsafe import Markup
    status_badge = '<span class="badge bg-success">ON</span>' if enabled else '<span class="badge bg-secondary">OFF</span>'
    body = Markup(
        f"<h4 class='mb-3'>🎟️ 할인 캠페인 자동화 (Phase 142)</h4>"
        f"<div class='mb-3 d-flex gap-2 align-items-center'>"
        f"  활성화: {status_badge}"
        f"  최대할인: {max_pct}%"
        f"  마진하한: {margin_floor}%"
        f"</div>"
        + (
            "<div class='alert alert-warning'>할인 캠페인이 비활성화되어 있습니다. <code>DISCOUNT_CAMPAIGN_ENABLED=1</code>로 설정하세요.</div>"
            if not enabled else ""
        )
        + f"<h5 class='mt-3'>추천 캠페인 ({len(recommendations)}건)</h5>"
        + (
            "<div class='alert alert-info'>추천 캠페인 없음 — 재고 과잉 SKU가 없습니다.</div>"
            if not recommendations else
            f"<div class='table-responsive'><table class='table table-hover table-sm'>"
            f"<thead><tr><th>SKU</th><th>상품명</th><th>마켓</th><th class='text-end'>원가</th><th>할인율</th><th class='text-end'>할인가</th><th>할인후마진</th><th>상태</th></tr></thead>"
            f"<tbody>{_campaign_rows(recommendations)}</tbody></table></div>"
        )
        + f"<h5 class='mt-4'>활성 캠페인 ({len(active)}건)</h5>"
        + (
            "<div class='alert alert-info'>활성 캠페인 없음</div>"
            if not active else
            f"<div class='table-responsive'><table class='table table-hover table-sm'>"
            f"<thead><tr><th>SKU</th><th>상품명</th><th>마켓</th><th class='text-end'>원가</th><th>할인율</th><th class='text-end'>할인가</th><th>할인후마진</th><th>상태</th></tr></thead>"
            f"<tbody>{_campaign_rows(active)}</tbody></table></div>"
        )
        + "<div class='mt-3'><a href='/admin/diagnostics' class='btn btn-outline-secondary btn-sm'>← 진단 대시보드</a></div>"
    )

    return _render_seller_page("할인 캠페인", body, page="marketing_campaigns")


@bp.post("/marketing/campaigns/approve")
def marketing_campaigns_approve():
    """캠페인 승인 (Phase 142)."""
    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "로그인 필요"}), 401

    data = request.json or {}
    sku = data.get("sku", "")
    market = data.get("market", "")
    if not sku or not market:
        return jsonify({"ok": False, "error": "sku와 market을 제공하세요"}), 400

    try:
        from src.marketing.discount_campaign import DiscountCampaignEngine
        engine = DiscountCampaignEngine()
        result = engine.approve_campaign(sku, market)
        return jsonify(result)
    except Exception as exc:
        logger.warning("campaign_approve 오류: %s", exc)
        return jsonify({"ok": False, "error": "처리 중 오류가 발생했습니다"}), 500


# ---------------------------------------------------------------------------
# Phase 143: 소싱 파이프라인 — Watch CRUD + 후보 큐
# ---------------------------------------------------------------------------

@bp.get("/keywords")
def keyword_trends():
    """키워드/검색어 트렌드 대시보드 (Phase 160)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    period = _normalize_keyword_period(request.args.get("period"))
    keywords = _parse_keywords(request.args.get("q"))
    context = _build_keyword_trend_context(keywords, period)
    return render_template(
        "keywords.html",
        page="keywords",
        **context,
    )


@bp.get("/sourcing")
def sourcing_hub():
    """AI 소싱 허브 (Phase 160)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    period = _normalize_keyword_period(request.args.get("period"))
    keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
    keyword_terms = _parse_keywords(keyword)
    keyword_context = _build_keyword_trend_context(keyword_terms, period)

    discovery_candidates: list[dict[str, Any]] = []
    try:
        from src.discovery.scout import DiscoveryScout
        discovery_candidates = DiscoveryScout().get_candidates(status=None)
    except Exception as exc:
        logger.debug("Discovery 후보 조회 스킵: %s", exc)

    queue_candidates = []
    try:
        from src.sourcing.pipeline import get_candidate_queue
        queue_candidates = get_candidate_queue().list_all(status=None)
    except Exception as exc:
        logger.debug("후보 큐 조회 스킵: %s", exc)

    recommendations = _build_sourcing_recommendations(
        keyword=keyword,
        keyword_context=keyword_context,
        discovery_candidates=discovery_candidates,
        queue_candidates=queue_candidates,
    )

    # 소싱처 등록소 — 알파벳순 정렬 (Phase 162)
    registry_sources = []
    try:
        from src.seller_console.my_sources_store import list_sources
        registry_sources = list_sources()
    except Exception as exc:
        logger.debug("My Sources 조회 스킵: %s", exc)

    # v12: 국내 베스트셀러(네이버 쇼핑 실데이터) + 소싱처 검색 딥링크 + 분석(실데이터/없으면 '데이터 없음')
    domestic_products: list[dict[str, Any]] = []
    domestic_enabled = False
    domestic_total: int | None = None
    try:
        from src.sourcing import naver_shopping
        domestic_enabled = naver_shopping.is_configured()
        if keyword and domestic_enabled:
            _res = naver_shopping.search_domestic(keyword, limit=12)
            domestic_products = _res.get("items") or []
            domestic_total = _res.get("total")
    except Exception as exc:
        logger.debug("국내 베스트셀러 조회 스킵: %s", exc)
    analysis = _build_sourcing_analysis(domestic_products, keyword_context, keyword,
                                        domestic_total=domestic_total)

    return render_template(
        "sourcing.html",
        page="sourcing",
        keyword=keyword,
        period=period,
        period_options=_KEYWORD_PERIOD_LABELS,
        keyword_context=keyword_context,
        recommendations=recommendations,
        my_sources=registry_sources,
        registry_sources=registry_sources,
        domestic_products=domestic_products,
        domestic_enabled=domestic_enabled,
        sourcing_search_links=_sourcing_search_links(keyword),
        amazon_search_countries=_AMAZON_SEARCH_COUNTRIES,
        analysis=analysis,
        collect_url=(request.args.get("url") or "").strip(),
        notice=(request.args.get("notice") or "").strip(),
        admin_ok=_is_admin_user(),
    )


@bp.post("/sourcing/my-sources")
def sourcing_my_sources():
    """My Sources 추가/삭제/사용시각 갱신 (Phase 160)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    action = (request.form.get("action") or "add").strip().lower()
    keyword = (request.form.get("keyword") or "").strip()
    domain = (request.form.get("domain") or request.form.get("url") or "").strip()
    notice = ""
    try:
        from src.seller_console.my_sources_store import add_source, remove_source, touch_source
        if action == "remove":
            ok = remove_source(domain)
            notice = "소스를 제거했습니다." if ok else "제거할 소스를 찾지 못했습니다."
        elif action == "touch":
            ok = touch_source(domain)
            notice = "최근 사용 시각을 갱신했습니다." if ok else "소스를 찾지 못했습니다."
        else:
            item = add_source(
                domain,
                label=(request.form.get("label") or "").strip(),
                note=(request.form.get("note") or "").strip(),
            )
            _register_discovery_candidate_from_collection(item.get("domain", ""), keyword_hint=keyword)
            status = item.get("openness_status", "partial")
            if status == "restricted":
                notice = "소싱처로 저장했습니다. (수집 어려움 — 폐쇄/차단 가능성, 경고)"
            elif status == "partial":
                notice = "소싱처로 저장했습니다. (부분 수집 가능 — OG/JSON-LD 미확인)"
            else:
                notice = "소싱처로 저장했습니다. (수집 가능)"
    except ValueError as exc:
        notice = str(exc)
    except Exception as exc:
        logger.warning("My Sources 처리 실패: %s", exc)
        notice = "My Sources 처리 중 오류가 발생했습니다."

    return redirect(
        url_for(
            "seller_console.sourcing_hub",
            keyword=keyword or None,
            notice=notice or None,
        )
    )


@bp.post("/sourcing/registry/add")
def sourcing_registry_add():
    """소싱처 등록소 — JSON API 등록 엔드포인트 (Phase 162).

    개방성 검증 후 소싱처로 등록, Discovery 후보 자동 연계.
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인 필요"}), 401

    data = request.get_json(force=True, silent=True) or {}
    value = (data.get("url") or data.get("domain") or "").strip()
    label = (data.get("label") or "").strip()
    note = (data.get("note") or "").strip()
    keyword = (data.get("keyword") or "").strip()

    if not value:
        return jsonify({"ok": False, "error": "URL 또는 도메인을 입력해 주세요."}), 400

    try:
        from src.seller_console.my_sources_store import add_source, probe_collectability, normalize_domain
        domain = normalize_domain(value)
        if not domain:
            return jsonify({"ok": False, "error": "도메인 형식이 올바르지 않습니다."}), 400

        # 개방성 프로빙
        probe = probe_collectability(value)
        entry = add_source(
            value,
            label=label,
            note=note,
            openness_status=probe["status"],
            adapter_name=probe["adapter_name"],
        )

        # Discovery 후보 자동 등록
        _register_discovery_candidate_from_collection(domain, keyword_hint=keyword)

        return jsonify({
            "ok": True,
            "domain": entry["domain"],
            "label": entry["label"],
            "openness_status": entry["openness_status"],
            "adapter_name": entry["adapter_name"],
            "probe_detail": probe.get("detail", ""),
            "is_large_platform": probe.get("is_large_platform", False),
        })
    except ValueError as exc:
        logger.debug("소싱처 등록 입력 오류: %s", exc)
        return jsonify({"ok": False, "error": "올바른 도메인 또는 URL을 입력해주세요."}), 400
    except Exception as exc:
        logger.warning("소싱처 등록 실패: %s", exc)
        return jsonify({"ok": False, "error": "소싱처 등록 중 오류가 발생했습니다."}), 500


@bp.post("/sourcing/registry/<path:domain>/recollect")
def sourcing_registry_recollect(domain: str):
    """등록된 소싱처 재수집 트리거 (Phase 162)."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인 필요"}), 401

    from src.seller_console.my_sources_store import normalize_domain, update_last_collect
    clean_domain = normalize_domain(domain)
    if not clean_domain:
        return jsonify({"ok": False, "error": "올바르지 않은 도메인"}), 400

    try:
        from src.seller_console.collectors.dispatcher import collect
        url = f"https://{clean_domain}"
        result = collect(url)
        summary = result.title or ("수집 성공" if result.success else "수집 실패")
        if result.warnings:
            summary += f" (경고: {result.warnings[0]})"
        update_last_collect(clean_domain, summary[:200])
        return jsonify({
            "ok": True,
            "domain": clean_domain,
            "success": result.success,
            "title": result.title or "",
            "source": result.source or "",
            "summary": summary,
        })
    except Exception as exc:
        logger.warning("소싱처 재수집 실패 (%s): %s", domain, exc)
        update_last_collect(clean_domain, f"오류: {str(exc)[:100]}")
        return jsonify({"ok": False, "error": "재수집 중 오류가 발생했습니다."}), 500


def _parse_history_extra(item: dict) -> dict:
    """수집 이력 항목의 extra_json을 dict로 파싱(실패 시 빈 dict)."""
    raw = item.get("extra_json") or item.get("extra") or ""
    if isinstance(raw, dict):
        return raw
    try:
        import json as _json
        parsed = _json.loads(raw) if raw else {}
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _check_source_change(item: dict) -> dict:
    """수집 상품 1건의 소싱처를 재확인해 가격/재고/옵션 변화를 판정한다.

    실 스크래핑(UniversalScraper)으로 현재 상태를 가져와 수집 당시 값과 비교.
    추출 불가(봇 차단/네트워크)면 가짜 변화 대신 '확인 불가'로 정직하게 처리한다.
    """
    url = (item.get("url") or "").strip()
    extra = _parse_history_extra(item)

    def _to_float(v):
        try:
            return float(str(v).replace(",", "").strip())
        except (TypeError, ValueError):
            return None

    base_price = _to_float(item.get("price")) or _to_float(extra.get("price_original")) or _to_float(extra.get("price"))
    base_options = extra.get("options") or {}

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "current_price": None,
        "currency": item.get("currency") or extra.get("currency") or "",
        "in_stock": None,
        "change": "unknown",
        "summary": "확인 불가",
        "method": "",
    }
    if not url.startswith(("http://", "https://")):
        result["summary"] = "URL 없음 — 확인 불가"
        return result

    try:
        from src.collectors.universal_scraper import UniversalScraper
        sp = UniversalScraper().fetch(url)
    except Exception as exc:
        logger.warning("소싱처 변화 확인 실패(%s): %s", url[:80], exc)
        sp = None

    if sp is None or (getattr(sp, "price", None) is None and getattr(sp, "in_stock", None) is None):
        # 추출 불가 — 거짓 변화 금지(정직)
        result["summary"] = "확인 불가 (봇 차단/네트워크/비표준 페이지)"
        return result

    cur_price = _to_float(getattr(sp, "price", None))
    in_stock = getattr(sp, "in_stock", None)
    cur_options = getattr(sp, "options", None) or {}
    result["current_price"] = cur_price
    result["in_stock"] = in_stock
    result["method"] = getattr(sp, "extraction_method", "") or ""
    if getattr(sp, "currency", None):
        result["currency"] = sp.currency

    changes = []
    if in_stock is False:
        changes.append("품절")
        result["change"] = "out_of_stock"
    if base_price is not None and cur_price is not None and abs(cur_price - base_price) >= 0.01:
        arrow = "▲" if cur_price > base_price else "▼"
        pct = ((cur_price - base_price) / base_price * 100) if base_price else 0
        changes.append(f"가격 {arrow} {base_price:g}→{cur_price:g} ({pct:+.0f}%)")
        if result["change"] != "out_of_stock":
            result["change"] = "price"
    # 옵션/사이즈 변경 감지(값 집합 비교)
    def _opt_values(opts):
        vals = set()
        if isinstance(opts, dict):
            for v in opts.values():
                if isinstance(v, (list, tuple)):
                    vals.update(str(x).strip() for x in v if str(x).strip())
        return vals
    base_set, cur_set = _opt_values(base_options), _opt_values(cur_options)
    if base_set and cur_set and base_set != cur_set:
        removed = base_set - cur_set
        if removed:
            changes.append("옵션/사이즈 일부 소진/변경")
            if result["change"] == "unknown":
                result["change"] = "options"

    if changes:
        result["summary"] = " · ".join(changes)
        if result["change"] == "unknown":
            result["change"] = "changed"
    else:
        result["change"] = "none"
        result["summary"] = "변화 없음"
    return result


def _persist_monitor_result(item_id: str, seller_id: str, item: dict, mon: dict) -> None:
    """변화 확인 결과를 수집 이력 extra_json에 저장(다음 방문 시 마지막 상태 표시)."""
    try:
        from . import collect_history_store
        import json as _json
        extra = _parse_history_extra(item)
        extra["monitor"] = mon
        collect_history_store.update(item_id, seller_id=seller_id, extra_json=_json.dumps(extra, ensure_ascii=False))
    except Exception as exc:
        logger.warning("모니터 결과 저장 실패(%s): %s", item_id, exc)


def run_auto_source_monitor(*, days: int = 14, max_items: int = 200, only_stale_hours: float = 6.0,
                            seller_id: Optional[str] = None) -> dict:
    """모든(또는 특정 셀러) 최근 수집 상품의 소싱처를 자동 재확인한다.

    Render Cron(`/cron/sourcing-monitor`) 또는 페이지 자동확인에서 호출.
    최근 확인분(only_stale_hours 이내)은 건너뛰어 과도한 스크래핑을 방지한다.
    """
    from . import collect_history_store
    from datetime import datetime as _dt

    items = collect_history_store.list_items(days=days, seller_id=seller_id)
    checked = changed = skipped = 0
    alerts: list[dict] = []
    for it in items[:max_items]:
        extra = _parse_history_extra(it)
        mon = extra.get("monitor") or {}
        last = mon.get("checked_at")
        if last and only_stale_hours:
            try:
                age_h = (datetime.now(timezone.utc) - _dt.fromisoformat(last)).total_seconds() / 3600.0
                if age_h < only_stale_hours:
                    skipped += 1
                    continue
            except Exception:
                pass
        sid = str(it.get("seller_id") or "") or None
        res = _check_source_change(it)
        _persist_monitor_result(it.get("id"), sid, it, res)
        checked += 1
        if res.get("change") not in ("none", "unknown", None):
            changed += 1
            alerts.append({"id": it.get("id"), "title": it.get("title"), "summary": res.get("summary")})
    return {"total": len(items), "checked": checked, "changed": changed,
            "skipped": skipped, "alerts": alerts[:50]}


@bp.get("/sourcing/monitor")
def sourcing_monitor():
    """수집한 상품의 소싱처 변화(품절/가격/옵션) 모니터링 페이지."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from . import collect_history_store
    items = collect_history_store.list_items(days=90, seller_id=_seller_id())
    rows = []
    for it in items:
        extra = _parse_history_extra(it)
        mon = extra.get("monitor") or {}
        rows.append({
            "id": it.get("id"),
            "title": it.get("title") or extra.get("title_ko") or extra.get("title") or "(제목 없음)",
            "url": it.get("url") or "",
            "domain": it.get("domain") or "",
            "image": it.get("image_url") or (extra.get("images") or [""])[0] if extra.get("images") else it.get("image_url") or "",
            "price": it.get("price") or extra.get("price_original") or "",
            "currency": it.get("currency") or extra.get("currency") or "",
            "monitor": mon,
        })
    return render_template("sourcing_monitor.html", rows=rows, total=len(rows))


@bp.post("/sourcing/monitor/check")
def sourcing_monitor_check():
    """수집 상품의 소싱처 변화 확인 (단건 또는 다건).

    Request: {"item_id": "..."} 또는 {"item_ids": [...]}
    Response: {"ok": true, "results": [{id, summary, change, current_price, in_stock, checked_at}]}
    """
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    data = request.get_json(force=True, silent=True) or {}
    ids = data.get("item_ids")
    if not ids:
        single = data.get("item_id")
        ids = [single] if single else []
    ids = [str(i) for i in ids if i][:30]
    if not ids:
        return jsonify({"ok": False, "error": "확인할 항목이 없습니다."}), 400

    from . import collect_history_store
    sid = _seller_id()
    results = []
    for item_id in ids:
        item = collect_history_store.get(item_id, seller_ids=_seller_identities())
        if not item:
            results.append({"id": item_id, "ok": False, "summary": "항목을 찾을 수 없습니다."})
            continue
        mon = _check_source_change(item)
        _persist_monitor_result(item_id, sid, item, mon)
        results.append({"id": item_id, "ok": True, **mon})
    return jsonify({"ok": True, "results": results})


def _sourcing_require_admin():
    """소싱/등록/이미지 페이지 접근 가드.

    멀티유저 SaaS — 로그인한 셀러면 누구나 접근 가능(소싱 watches/후보 큐/등록 이력/
    이미지 큐는 셀러 작업 화면이라 관리자 전용이 아님). 과거엔 관리자 전용이라
    ADMIN_EMAILS 미설정 시 셀러가 403을 받아 좌측 메뉴가 '동작 안 함'으로 보였다.
    인증 강제(_AUTH_ENABLED)가 켜져 있을 때만 로그인을 요구하고, 그 외(테스트/오픈)는 통과.
    """
    if not _AUTH_ENABLED:
        return None
    if not session.get("user_id"):
        return redirect(url_for("auth.login", next=request.url))
    return None


@bp.get("/sourcing/watches")
def sourcing_watches():
    """소싱 Watch 목록 + 등록 페이지 (Phase 143)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    from src.sourcing.pipeline import get_watch_store
    store = get_watch_store()
    watches = store.list_all()

    def _watch_rows(items):
        rows = ""
        for w in items:
            active_badge = (
                '<span class="badge bg-success">활성</span>'
                if w.active else
                '<span class="badge bg-secondary">비활성</span>'
            )
            last_checked = (w.last_checked_at or "-")[:19]
            rows += (
                f"<tr>"
                f"<td><code>{w.watch_id}</code></td>"
                f"<td>{w.platform}</td>"
                f"<td>{w.keyword}</td>"
                f"<td>{w.category or '-'}</td>"
                f"<td>{w.currency}</td>"
                f"<td>{int(w.min_price) if w.min_price else '-'} ~ {int(w.max_price) if w.max_price else '∞'}</td>"
                f"<td>{active_badge}</td>"
                f"<td>{last_checked}</td>"
                f"<td>"
                f"  <button class='btn btn-sm btn-outline-primary me-1' onclick=\"runWatch('{w.watch_id}')\">▶ 실행</button>"
                f"  <button class='btn btn-sm btn-outline-danger' onclick=\"deleteWatch('{w.watch_id}')\">🗑</button>"
                f"</td>"
                "</tr>"
            )
        return rows

    from markupsafe import Markup
    body = Markup(
        "<h4 class='mb-3'>🔎 소싱 Watch 관리 (Phase 143)</h4>"
        "<div class='row mb-4'>"
        "  <div class='col-md-6'>"
        "    <div class='card'>"
        "      <div class='card-header fw-bold'>Watch 등록</div>"
        "      <div class='card-body'>"
        "        <form id='watchForm'>"
        "          <div class='mb-2'>"
        "            <label class='form-label small'>플랫폼</label>"
        "            <select class='form-select form-select-sm' name='platform'>"
        "              <option value='rakuten'>라쿠텐</option>"
        "              <option value='amazon_jp'>아마존JP</option>"
        "              <option value='yahoo_shopping'>Yahoo Shopping</option>"
        "            </select>"
        "          </div>"
        "          <div class='mb-2'>"
        "            <label class='form-label small'>키워드 *</label>"
        "            <input type='text' class='form-control form-control-sm' name='keyword' placeholder='예: ユニクロ' required>"
        "          </div>"
        "          <div class='mb-2'>"
        "            <label class='form-label small'>카테고리</label>"
        "            <input type='text' class='form-control form-control-sm' name='category' placeholder='예: 패션'>"
        "          </div>"
        "          <div class='row mb-2'>"
        "            <div class='col'>"
        "              <label class='form-label small'>최소가 (JPY)</label>"
        "              <input type='number' class='form-control form-control-sm' name='min_price' value='0' min='0'>"
        "            </div>"
        "            <div class='col'>"
        "              <label class='form-label small'>최대가 (JPY, 0=제한없음)</label>"
        "              <input type='number' class='form-control form-control-sm' name='max_price' value='0' min='0'>"
        "            </div>"
        "          </div>"
        "          <button type='submit' class='btn btn-primary btn-sm'>Watch 등록</button>"
        "        </form>"
        "      </div>"
        "    </div>"
        "  </div>"
        "</div>"
        f"<h5>등록된 Watch ({len(watches)}개)</h5>"
        + (
            "<div class='alert alert-info'>등록된 Watch가 없습니다.</div>"
            if not watches else
            "<div class='table-responsive'>"
            "<table class='table table-hover table-sm'>"
            "<thead><tr><th>ID</th><th>플랫폼</th><th>키워드</th><th>카테고리</th><th>통화</th><th>가격 범위</th><th>상태</th><th>마지막 체크</th><th>액션</th></tr></thead>"
            f"<tbody>{_watch_rows(watches)}</tbody></table></div>"
        )
        + "<div class='mt-3'><a href='/seller/sourcing/candidates' class='btn btn-outline-success btn-sm'>📋 후보 큐 보기</a></div>"
        + """
<script>
function _watchToast(msg, type) {
  if (window.showGlobalToast) { showGlobalToast(msg, type || 'success'); return; }
  var el = document.getElementById('watchPageToast');
  var body = document.getElementById('watchPageToastMsg');
  if (!el || !body) return;
  body.textContent = msg;
  var map = {success:'bg-success',danger:'bg-danger',warning:'bg-warning text-dark'};
  el.className = 'toast text-white border-0 ' + (map[type] || 'bg-success');
  new bootstrap.Toast(el, {delay: 3500}).show();
}
document.getElementById('watchForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = Object.fromEntries(fd.entries());
    body.min_price = parseFloat(body.min_price) || 0;
    body.max_price = parseFloat(body.max_price) || 0;
    const r = await fetch('/seller/sourcing/watches', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    const d = await r.json();
    if(d.ok) { _watchToast('Watch 등록 완료: ' + d.watch_id, 'success'); setTimeout(() => location.reload(), 1200); }
    else { _watchToast('오류: ' + (d.error || '알 수 없음'), 'danger'); }
});
async function runWatch(wid) {
    if(!confirm('이 Watch를 지금 실행하시겠습니까?')) return;
    const r = await fetch('/seller/sourcing/watches/' + wid + '/run', {method:'POST'});
    const d = await r.json();
    _watchToast('발견: ' + d.discovered + '건 / 큐 적재: ' + d.queued + '건', 'success');
    setTimeout(() => location.reload(), 1500);
}
async function deleteWatch(wid) {
    if(!confirm('Watch를 삭제하시겠습니까?')) return;
    const r = await fetch('/seller/sourcing/watches/' + wid, {method:'DELETE'});
    const d = await r.json();
    if(d.ok) { location.reload(); }
    else { _watchToast('오류: ' + (d.error || '알 수 없음'), 'danger'); }
}
</script>
<div class='position-fixed bottom-0 end-0 p-3 pc-toast-stack' style='z-index:1100'>
  <div id='watchPageToast' class='toast' role='alert'>
    <div class='toast-header'><strong class='me-auto'>알림</strong>
    <button type='button' class='btn-close' data-bs-dismiss='toast'></button></div>
    <div class='toast-body' id='watchPageToastMsg'></div>
  </div>
</div>"""
    )

    return _render_seller_page("소싱 Watch", body, page="sourcing_watches")


@bp.post("/sourcing/watches")
def sourcing_watches_add():
    """Watch 등록 API (Phase 143)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    data = request.get_json(force=True, silent=True) or {}
    platform = (data.get("platform") or "").strip()
    keyword = (data.get("keyword") or "").strip()
    if not platform or not keyword:
        return jsonify({"ok": False, "error": "platform과 keyword는 필수입니다"}), 400

    try:
        from src.sourcing.pipeline import get_watch_store
        store = get_watch_store()
        watch = store.add(
            platform=platform,
            keyword=keyword,
            category=data.get("category", ""),
            currency=data.get("currency", "JPY"),
            min_price=float(data.get("min_price", 0) or 0),
            max_price=float(data.get("max_price", 0) or 0),
        )
        return jsonify({"ok": True, "watch_id": watch.watch_id, "watch": watch.to_dict()})
    except ValueError as exc:
        logger.warning("sourcing_watches_add 입력 오류: %s", exc)
        return jsonify({"ok": False, "error": "입력값이 올바르지 않습니다"}), 400
    except Exception as exc:
        logger.warning("sourcing_watches_add 오류: %s", exc)
        return jsonify({"ok": False, "error": "처리 중 오류가 발생했습니다"}), 500


@bp.delete("/sourcing/watches/<watch_id>")
def sourcing_watches_delete(watch_id: str):
    """Watch 삭제 API (Phase 143)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    from src.sourcing.pipeline import get_watch_store
    ok = get_watch_store().delete(watch_id)
    return jsonify({"ok": ok})


@bp.post("/sourcing/watches/<watch_id>/run")
def sourcing_watches_run(watch_id: str):
    """Watch 즉시 실행 — 발견 + 마진시뮬 + 큐 적재 (Phase 143)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    try:
        from src.sourcing.pipeline import run_watch_cycle
        result = run_watch_cycle(watch_id)
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        logger.debug("sourcing_watches_run ValueError: %s", exc)
        return jsonify({"ok": False, "error": "watch_id를 찾을 수 없거나 비활성 상태입니다"}), 404
    except Exception as exc:
        logger.warning("sourcing_watches_run 오류: %s", exc)
        return jsonify({"ok": False, "error": "실행 중 오류가 발생했습니다"}), 500


@bp.get("/sourcing/candidates")
def sourcing_candidates():
    """소싱 후보 큐 + 일괄 승인 페이지 (Phase 143)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    from src.sourcing.pipeline import get_candidate_queue
    queue = get_candidate_queue()
    status_filter = request.args.get("status", "pending")
    candidates = queue.list_all(status=status_filter)
    stats = queue.stats()

    def _candidate_rows(items):
        rows = ""
        for c in items:
            margin_class = "text-success" if c.estimated_margin_pct >= 20 else ("text-warning" if c.estimated_margin_pct >= 15 else "text-danger")
            new_badge = '<span class="badge bg-info">신상품</span>' if c.is_new else ""
            disc_badge = f'<span class="badge bg-danger">{c.discount_pct:.0f}% 할인</span>' if c.is_discounted else ""
            status_colors = {"pending": "warning text-dark", "approved": "success", "rejected": "secondary", "listed": "primary"}
            status_color = status_colors.get(c.status, "secondary")
            rows += (
                f"<tr>"
                f"<td><small><code>{c.candidate_id}</code></small></td>"
                f"<td>{c.platform}</td>"
                f"<td>{c.product_name[:30]} {new_badge}{disc_badge}</td>"
                f"<td class='text-end'>¥{c.source_price:,.0f}</td>"
                f"<td class='text-end'>₩{c.estimated_selling_price_krw:,.0f}</td>"
                f"<td class='text-center {margin_class} fw-bold'>{c.estimated_margin_pct:.1f}%</td>"
                f"<td><span class='badge bg-{status_color}'>{c.status}</span></td>"
                f"<td class='small'>{c.discovered_at[:16]}</td>"
                f"<td>"
                + (
                    f"<button class='btn btn-sm btn-success me-1' onclick=\"approveCandidate('{c.candidate_id}')\">✅ 승인</button>"
                    f"<button class='btn btn-sm btn-outline-danger' onclick=\"rejectCandidate('{c.candidate_id}')\">❌ 거절</button>"
                    if c.status == "pending" else
                    f"<button class='btn btn-sm btn-outline-primary' onclick=\"publishCandidate('{c.candidate_id}')\">📤 등록</button>"
                    if c.status == "approved" else ""
                )
                + "</td>"
                "</tr>"
            )
        return rows

    from markupsafe import Markup
    stat_html = Markup(
        f"<div class='row mb-3'>"
        f"<div class='col'><div class='card text-center p-2'><div class='fs-4 fw-bold'>{stats['last_24h']}</div><small class='text-muted'>24h 후보</small></div></div>"
        f"<div class='col'><div class='card text-center p-2'><div class='fs-4 fw-bold text-warning'>{stats['pending']}</div><small class='text-muted'>승인 대기</small></div></div>"
        f"<div class='col'><div class='card text-center p-2'><div class='fs-4 fw-bold text-success'>{stats['approved']}</div><small class='text-muted'>승인됨</small></div></div>"
        f"<div class='col'><div class='card text-center p-2'><div class='fs-4 fw-bold text-primary'>{stats['listed']}</div><small class='text-muted'>등록됨</small></div></div>"
        f"<div class='col'><div class='card text-center p-2'><div class='fs-4 fw-bold'>{stats['avg_margin_pct']}%</div><small class='text-muted'>평균 마진</small></div></div>"
        f"</div>"
    )

    filter_tabs = Markup(
        "<div class='btn-group mb-3'>"
        + "".join(
            f"<a href='/seller/sourcing/candidates?status={s}' class='btn btn-sm {'btn-primary' if status_filter == s else 'btn-outline-secondary'}'>{l}</a>"
            for s, l in [("pending", "대기"), ("approved", "승인"), ("rejected", "거절"), ("listed", "등록")]
        )
        + "</div>"
    )

    body = Markup(
        "<h4 class='mb-3'>📋 소싱 후보 큐 (Phase 143)</h4>"
    ) + stat_html + filter_tabs + Markup(
        (
            "<div class='alert alert-info'>해당 상태의 후보가 없습니다.</div>"
            if not candidates else
            "<div class='table-responsive'>"
            "<table class='table table-hover table-sm'>"
            "<thead><tr><th>ID</th><th>플랫폼</th><th>상품명</th><th class='text-end'>소싱가</th><th class='text-end'>예상판매가</th><th>마진</th><th>상태</th><th>발견</th><th>액션</th></tr></thead>"
            f"<tbody>{_candidate_rows(candidates)}</tbody></table></div>"
        )
        + "<div class='mt-3 d-flex gap-2'>"
        + "<a href='/seller/sourcing/watches' class='btn btn-outline-secondary btn-sm'>← Watch 목록</a>"
        + (
            f"<button class='btn btn-success btn-sm' onclick=\"bulkApprove()\">✅ 전체 승인 ({stats['pending']}건)</button>"
            if stats["pending"] > 0 else ""
        )
        + "</div>"
        + """
<script>
function _candidateToast(msg, type) {
  if (window.showGlobalToast) { showGlobalToast(msg, type || 'success'); return; }
  var el = document.getElementById('candidatePageToast');
  var body = document.getElementById('candidatePageToastMsg');
  if (!el || !body) return;
  body.textContent = msg;
  var map = {success:'bg-success',danger:'bg-danger',warning:'bg-warning text-dark'};
  el.className = 'toast text-white border-0 ' + (map[type] || 'bg-success');
  new bootstrap.Toast(el, {delay: 3500}).show();
}
async function approveCandidate(cid) {
    const r = await fetch('/seller/sourcing/candidates/' + cid + '/approve', {method:'POST'});
    const d = await r.json();
    if(d.ok) location.reload();
    else _candidateToast('오류: ' + (d.error || '알 수 없음'), 'danger');
}
function rejectCandidate(cid) {
    document.getElementById('candidateRejectId').value = cid;
    document.getElementById('candidateRejectReason').value = '';
    new bootstrap.Modal(document.getElementById('candidateRejectModal')).show();
    setTimeout(() => document.getElementById('candidateRejectReason')?.focus(), 120);
}
async function submitCandidateReject() {
    const cid = document.getElementById('candidateRejectId').value;
    const reason = document.getElementById('candidateRejectReason').value.trim();
    const r = await fetch('/seller/sourcing/candidates/' + cid + '/reject', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({reason})});
    const d = await r.json();
    if(d.ok) {
      bootstrap.Modal.getInstance(document.getElementById('candidateRejectModal'))?.hide();
      location.reload();
    }
    else _candidateToast('오류: ' + (d.error || '알 수 없음'), 'danger');
}
async function publishCandidate(cid) {
    if(!confirm('이 후보를 자동 등록하시겠습니까?')) return;
    const r = await fetch('/seller/sourcing/candidates/' + cid + '/publish', {method:'POST'});
    const d = await r.json();
    if(d.ok) { _candidateToast('등록 완료: ' + (d.product_id || cid), 'success'); setTimeout(() => location.reload(), 1200); }
    else { _candidateToast('등록 실패: ' + (d.error || '알 수 없음'), 'danger'); }
}
async function bulkApprove() {
    if(!confirm('모든 대기 후보를 승인하시겠습니까?')) return;
    const r = await fetch('/seller/sourcing/candidates/bulk-approve', {method:'POST'});
    const d = await r.json();
    _candidateToast('승인 완료: ' + d.approved_count + '건', 'success');
    setTimeout(() => location.reload(), 1200);
}
</script>
<div class='position-fixed bottom-0 end-0 p-3 pc-toast-stack' style='z-index:1100'>
  <div id='candidatePageToast' class='toast' role='alert'>
    <div class='toast-header'><strong class='me-auto'>알림</strong>
    <button type='button' class='btn-close' data-bs-dismiss='toast'></button></div>
    <div class='toast-body' id='candidatePageToastMsg'></div>
  </div>
</div>
<div class='modal fade' id='candidateRejectModal' tabindex='-1' aria-hidden='true'>
  <div class='modal-dialog'>
    <div class='modal-content'>
      <div class='modal-header'>
        <h5 class='modal-title'>후보 거절</h5>
        <button type='button' class='btn-close' data-bs-dismiss='modal'></button>
      </div>
      <div class='modal-body'>
        <input type='hidden' id='candidateRejectId'>
        <label class='form-label' for='candidateRejectReason'>거절 사유 (선택)</label>
        <textarea id='candidateRejectReason' class='form-control' rows='3' placeholder='거절 사유를 입력하세요.'></textarea>
      </div>
      <div class='modal-footer'>
        <button type='button' class='btn btn-secondary' data-bs-dismiss='modal'>취소</button>
        <button type='button' class='btn btn-danger' onclick='submitCandidateReject()'>거절</button>
      </div>
    </div>
  </div>
</div>"""
    )

    return _render_seller_page("소싱 후보 큐", body, page="sourcing_candidates")


@bp.post("/sourcing/candidates/<candidate_id>/approve")
def sourcing_candidate_approve(candidate_id: str):
    """후보 승인 API (Phase 143)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    from src.sourcing.pipeline import get_candidate_queue
    c = get_candidate_queue().approve(candidate_id)
    if c is None:
        return jsonify({"ok": False, "error": "후보를 찾을 수 없습니다"}), 404
    return jsonify({"ok": True, "candidate": c.to_dict()})


@bp.post("/sourcing/candidates/<candidate_id>/reject")
def sourcing_candidate_reject(candidate_id: str):
    """후보 거절 API (Phase 143)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    data = request.get_json(force=True, silent=True) or {}
    reason = data.get("reason", "")
    from src.sourcing.pipeline import get_candidate_queue
    c = get_candidate_queue().reject(candidate_id, reason)
    if c is None:
        return jsonify({"ok": False, "error": "후보를 찾을 수 없습니다"}), 404
    return jsonify({"ok": True, "candidate": c.to_dict()})


@bp.post("/sourcing/candidates/bulk-approve")
def sourcing_candidates_bulk_approve():
    """대기 후보 일괄 승인 API (Phase 143)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    from src.sourcing.pipeline import get_candidate_queue
    queue = get_candidate_queue()
    pending = [c.candidate_id for c in queue.list_all(status="pending")]
    approved = queue.bulk_approve(pending)
    return jsonify({"ok": True, "approved_count": len(approved), "candidate_ids": [c.candidate_id for c in approved]})


@bp.post("/sourcing/candidates/<candidate_id>/publish")
def sourcing_candidate_publish(candidate_id: str):
    """승인된 후보 자동 등록 트리거 (Phase 143)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    from src.sourcing.pipeline import get_candidate_queue
    queue = get_candidate_queue()
    c = queue.get(candidate_id)
    if c is None:
        return jsonify({"ok": False, "error": "후보를 찾을 수 없습니다"}), 404
    if c.status not in ("approved", "pending"):
        return jsonify({"ok": False, "error": f"현재 상태 '{c.status}'에서는 등록할 수 없습니다"}), 400

    try:
        from src.listing.auto_publish import auto_publish
        result = auto_publish(c)
        queue.mark_listed(candidate_id)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        logger.warning("sourcing_candidate_publish 오류: %s", exc)
        return jsonify({"ok": False, "error": "등록 중 오류가 발생했습니다"}), 500


# ---------------------------------------------------------------------------
# Phase 144: 등록 이력 (/seller/listing/history)
# ---------------------------------------------------------------------------

@bp.get("/listing/history")
def listing_history():
    """등록 이력 페이지 (Phase 144)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    try:
        from src.listing.auto_publish import listing_stats
        stats = listing_stats()
    except Exception:
        stats = {}

    from markupsafe import Markup

    listings_24h = stats.get("listings_24h", 0)
    image_success_pct = stats.get("image_success_pct", 0)

    body = Markup(
        "<h4 class='mb-3'>📤 등록 이력 (Phase 144)</h4>"
        "<div class='row mb-4'>"
        "  <div class='col-md-3'>"
        "    <div class='card text-center'>"
        "      <div class='card-body'>"
        f"       <h2 class='fw-bold text-primary'>{listings_24h}</h2>"
        "        <div class='text-muted small'>24h 등록</div>"
        "      </div>"
        "    </div>"
        "  </div>"
        "  <div class='col-md-3'>"
        "    <div class='card text-center'>"
        "      <div class='card-body'>"
        f"       <h2 class='fw-bold text-success'>{image_success_pct}%</h2>"
        "        <div class='text-muted small'>이미지 처리 성공률</div>"
        "      </div>"
        "    </div>"
        "  </div>"
        "</div>"
        "<div class='alert alert-info'>"
        "  📋 자동 등록된 상품 목록입니다. 쿠팡/스마트스토어/11번가 채널별 결과를 확인하세요."
        "</div>"
        "<div class='d-flex gap-2 mt-3'>"
        "  <a href='/seller/sourcing/candidates' class='btn btn-outline-primary btn-sm'>📥 후보 큐</a>"
        "  <a href='/seller/sourcing/watches' class='btn btn-outline-secondary btn-sm'>🔎 Watch 관리</a>"
        "  <a href='/seller/media/queue' class='btn btn-outline-success btn-sm'>🖼️ 이미지 큐</a>"
        "</div>"
    )
    return _render_seller_page("📤 등록 이력", body, page="listing_history")


# ---------------------------------------------------------------------------
# Phase 144: 이미지 큐 (/seller/media/queue)
# ---------------------------------------------------------------------------

@bp.get("/media/queue")
def media_queue():
    """이미지 처리 큐 페이지 (Phase 144)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    status = {
        "enabled": os.getenv("IMAGE_PIPELINE_ENABLED", "1") == "1",
        "inpaint_enabled": os.getenv("IMAGE_INPAINT_ENABLED", "1") == "1",
        "provider": "pillow",
        "queue_size": 0,
    }

    from markupsafe import Markup

    enabled = status.get("enabled", True)
    inpaint = status.get("inpaint_enabled", True)
    provider = status.get("provider", "pillow")
    queue_size = status.get("queue_size", 0)

    enabled_badge = (
        "<span class='badge bg-success'>ON</span>" if enabled
        else "<span class='badge bg-secondary'>OFF</span>"
    )
    inpaint_badge = (
        "<span class='badge bg-success'>ON</span>" if inpaint
        else "<span class='badge bg-secondary'>OFF</span>"
    )

    body = Markup(
        "<h4 class='mb-3'>🖼️ 이미지 처리 큐 (Phase 144)</h4>"
        "<div class='row mb-4'>"
        "  <div class='col-md-4'>"
        "    <div class='card'>"
        "      <div class='card-body'>"
        "        <ul class='list-unstyled mb-0'>"
        f"          <li>파이프라인: {enabled_badge}</li>"
        f"          <li>Inpainting (워터마크 제거): {inpaint_badge}</li>"
        f"          <li>Provider: <code>{provider}</code></li>"
        f"          <li>대기 중: <strong>{queue_size}건</strong></li>"
        "        </ul>"
        "      </div>"
        "    </div>"
        "  </div>"
        "</div>"
        "<div class='alert alert-info'>"
        "  🖼️ 소싱된 상품 이미지 자동 처리 현황입니다. 배경 제거·워터마크 인페인팅 결과를 확인하세요."
        "</div>"
        "<div class='d-flex gap-2 mt-3'>"
        "  <a href='/seller/listing/history' class='btn btn-outline-primary btn-sm'>📦 등록 이력</a>"
        "  <a href='/seller/sourcing/candidates' class='btn btn-outline-secondary btn-sm'>📥 후보 큐</a>"
        "</div>"
    )
    return _render_seller_page("🖼️ 이미지 큐", body, page="media_queue")


# ---------------------------------------------------------------------------
# Phase 144: 광고 캠페인 (/seller/ads/campaigns)
# ---------------------------------------------------------------------------

@bp.get("/ads/campaigns")
def ads_campaigns():
    """광고 자동 운영 캠페인 페이지 (Phase 144)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    from src.ads.auto_campaign import ads_stats, _active_campaigns, _campaign_recs
    from markupsafe import Markup

    stats = ads_stats()
    recs = list(_campaign_recs.values())
    active = list(_active_campaigns.values())

    def _rec_rows(items):
        if not items:
            return "<tr><td colspan='7' class='text-center text-muted'>추천 캠페인 없음</td></tr>"
        rows = ""
        for r in items:
            status_badge = {
                "pending": "<span class='badge bg-warning text-dark'>대기</span>",
                "approved": "<span class='badge bg-info'>승인</span>",
                "launched": "<span class='badge bg-success'>활성</span>",
                "paused": "<span class='badge bg-secondary'>일시정지</span>",
            }.get(r.status, r.status)
            rows += (
                f"<tr>"
                f"<td>{r.rec_id}</td>"
                f"<td>{r.product_name}</td>"
                f"<td>{r.channel}</td>"
                f"<td>{', '.join(r.keywords[:2])}</td>"
                f"<td>{r.estimated_roas:.2f}</td>"
                f"<td>{r.daily_budget_krw:,}원</td>"
                f"<td>{status_badge}</td>"
                "</tr>"
            )
        return rows

    def _active_rows(items):
        if not items:
            return "<tr><td colspan='5' class='text-center text-muted'>활성 캠페인 없음</td></tr>"
        rows = ""
        for c in items:
            status_badge = (
                "<span class='badge bg-success'>활성</span>" if c.get("status") == "active"
                else "<span class='badge bg-secondary'>일시정지</span>"
            )
            rows += (
                f"<tr>"
                f"<td><code>{c['campaign_id']}</code></td>"
                f"<td>{c.get('product_name', '')}</td>"
                f"<td>{c.get('channel', '')}</td>"
                f"<td>{c.get('daily_budget_krw', 0):,}원</td>"
                f"<td>{status_badge}</td>"
                "</tr>"
            )
        return rows

    enabled_badge = (
        "<span class='badge bg-success'>ON</span>" if stats["enabled"]
        else "<span class='badge bg-secondary'>OFF</span>"
    )
    auto_launch_badge = (
        "<span class='badge bg-danger'>자동 launch</span>" if stats["auto_launch"]
        else "<span class='badge bg-secondary'>수동 승인</span>"
    )

    body = Markup(
        f"<h4 class='mb-3'>📣 광고 자동 운영 (Phase 144)</h4>"
        "<div class='row mb-4'>"
        "  <div class='col-md-2'><div class='card text-center'><div class='card-body'>"
        f"    <h3 class='fw-bold text-primary'>{stats['active_campaigns']}</h3>"
        "    <div class='text-muted small'>활성 캠페인</div></div></div></div>"
        "  <div class='col-md-2'><div class='card text-center'><div class='card-body'>"
        f"    <h3 class='fw-bold text-success'>{stats['roas_24h']:.2f}</h3>"
        "    <div class='text-muted small'>24h ROAS</div></div></div></div>"
        "  <div class='col-md-2'><div class='card text-center'><div class='card-body'>"
        f"    <h3 class='fw-bold text-warning'>{stats['pending_recs']}</h3>"
        "    <div class='text-muted small'>추천 대기</div></div></div></div>"
        "  <div class='col-md-3'><div class='card text-center'><div class='card-body'>"
        f"    <h3 class='fw-bold'>{stats['cost_krw_24h']:,}원</h3>"
        "    <div class='text-muted small'>24h 광고비</div></div></div></div>"
        "  <div class='col-md-3'><div class='card text-center'><div class='card-body'>"
        f"    <h3 class='fw-bold'>{stats['revenue_krw_24h']:,}원</h3>"
        "    <div class='text-muted small'>24h 매출</div></div></div></div>"
        "</div>"
        "<div class='row mb-3'>"
        "  <div class='col-md-12'>"
        "    <div class='alert alert-light border mb-3'>"
        f"      자동 운영: {enabled_badge} &nbsp; launch 모드: {auto_launch_badge} &nbsp; "
        f"      일일 예산: <strong>{stats['daily_budget_krw']:,}원</strong> &nbsp; "
        f"      목표 ROAS: <strong>{stats['target_roas']}</strong>"
        "    </div>"
        "  </div>"
        "</div>"
        f"<h5 class='mb-2'>추천 캠페인</h5>"
        "<div class='table-responsive mb-4'>"
        "<table class='table table-sm table-hover'>"
        "<thead><tr><th>ID</th><th>상품</th><th>채널</th><th>키워드</th><th>예상 ROAS</th><th>일일 예산</th><th>상태</th></tr></thead>"
        f"<tbody>{_rec_rows(recs)}</tbody></table></div>"
        "<div class='mb-3'>"
        "  <button class='btn btn-primary btn-sm' onclick=\"fetch('/seller/ads/recommend', {method:'POST'}).then(r=>r.json()).then(d=>location.reload())\">"
        "    🔄 추천 갱신</button>"
        "</div>"
        f"<h5 class='mb-2'>활성 캠페인</h5>"
        "<div class='table-responsive'>"
        "<table class='table table-sm table-hover'>"
        "<thead><tr><th>캠페인 ID</th><th>상품</th><th>채널</th><th>일일 예산</th><th>상태</th></tr></thead>"
        f"<tbody>{_active_rows(active)}</tbody></table></div>"
        "<div class='mt-3 d-flex gap-2'>"
        "  <a href='/seller/sourcing/watches' class='btn btn-outline-secondary btn-sm'>🔎 소싱 Watch</a>"
        "  <a href='/seller/sourcing/candidates' class='btn btn-outline-secondary btn-sm'>📥 후보 큐</a>"
        "</div>"
    )
    return _render_seller_page("📣 광고 캠페인", body, page="ads_campaigns")


@bp.post("/ads/recommend")
def ads_recommend():
    """추천 캠페인 갱신 API (Phase 144)."""
    guard = _sourcing_require_admin()
    if guard is not None:
        return guard

    from src.ads.auto_campaign import recommend_campaigns
    recs = recommend_campaigns()
    return jsonify({"ok": True, "count": len(recs), "recs": [r.to_dict() for r in recs]})


@bp.get("/ads/keywords")
def ads_keywords():
    """키워드 최적화 화면 (실동작)."""
    from markupsafe import escape

    product_title = (request.args.get("title") or "").strip()
    tags_raw = (request.args.get("tags") or "").strip()
    candidates_raw = [x.strip() for x in re.split(r"[,/\n]+", tags_raw) if x.strip()]
    if product_title:
        candidates_raw.extend([x.strip() for x in product_title.split() if x.strip()])
    candidate_keywords = list(dict.fromkeys(candidates_raw))[:20]

    rec_rows = []
    if product_title and candidate_keywords:
        try:
            from src.ads.keyword_optimizer import match_keywords_to_product, recommend_bids

            metrics = match_keywords_to_product(product_title, candidate_keywords)
            rec_rows = recommend_bids(metrics[:12])
        except Exception as exc:
            logger.warning("키워드 최적화 추천 실패: %s", exc)
            rec_rows = []

    rows_html = "".join(
        (
            "<tr>"
            f"<td>{escape(r.get('keyword', ''))}</td>"
            f"<td class='text-end'>{int(r.get('monthly_search') or 0):,}</td>"
            f"<td class='text-end'>{float(r.get('competition') or 0):.2f}</td>"
            f"<td class='text-end'>{int(r.get('avg_cpc_krw') or 0):,}원</td>"
            f"<td class='text-end'>{int(r.get('recommended_bid_krw') or 0):,}원</td>"
            f"<td class='text-end'>{float(r.get('match_score') or 0):.2f}</td>"
            "</tr>"
        )
        for r in rec_rows
    ) or "<tr><td colspan='6' class='text-center text-muted py-3'>상품명/태그를 입력하면 추천 키워드가 생성됩니다.</td></tr>"

    body = (
        "<h4 class='mb-3'>🎯 키워드 최적화</h4>"
        "<form class='card mb-3' method='get' action='/seller/ads/keywords'>"
        "  <div class='card-body'>"
        "    <div class='row g-2'>"
        "      <div class='col-md-5'><label class='form-label small'>상품명</label>"
        f"        <input class='form-control form-control-sm' name='title' value='{escape(product_title)}' placeholder='예: LOWRIDER BEAR T-SHIRT'></div>"
        "      <div class='col-md-5'><label class='form-label small'>태그/후보 키워드</label>"
        f"        <input class='form-control form-control-sm' name='tags' value='{escape(tags_raw)}' placeholder='예: 스트리트, 베어, 반팔'></div>"
        "      <div class='col-md-2 d-flex align-items-end'><button class='btn btn-primary btn-sm w-100' type='submit'>최적화</button></div>"
        "    </div>"
        "  </div>"
        "</form>"
        "<div class='card'>"
        "  <div class='card-body p-0'>"
        "    <div class='table-responsive'>"
        "      <table class='table table-sm mb-0'>"
        "        <thead><tr><th>키워드</th><th class='text-end'>월 검색량</th><th class='text-end'>경쟁도</th><th class='text-end'>평균 CPC</th><th class='text-end'>추천 입찰가</th><th class='text-end'>매칭점수</th></tr></thead>"
        f"        <tbody>{rows_html}</tbody>"
        "      </table>"
        "    </div>"
        "  </div>"
        "</div>"
    )
    return _render_seller_page("🎯 키워드 최적화", body, page="ads_keywords")


@bp.get("/orders/auto")
def orders_auto():
    """주문 자동 처리 대시보드 (Phase 145)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    from src.orders.auto_processor import OrderAutoProcessor

    processor = OrderAutoProcessor()
    queue_source = "simulation"
    queue = []
    svc = _get_order_sync_service()
    if svc is not None:
        try:
            raw_orders = svc.list_orders(limit=200, offset=0)
            stage_map = {
                "new": "신규",
                "paid": "결제완료",
                "preparing": "발주대기",
                "shipped": "배송중",
                "delivered": "완료",
                "canceled": "취소",
                "returned": "반품",
                "exchanged": "교환",
                "refund_requested": "환불요청",
            }
            for row in raw_orders:
                status = str(getattr(row.status, "value", row.status) or "").strip().lower()
                if status in {"delivered", "canceled", "returned", "exchanged"}:
                    continue
                queue.append({
                    "order_id": row.order_id,
                    "marketplace": row.marketplace,
                    "stage": stage_map.get(status, status or "확인필요"),
                    "needs_manual": status in {"refund_requested"} or not bool(row.items),
                })
            queue_source = "live"
        except Exception as exc:
            logger.warning("주문 자동 처리 큐 로드 실패: %s", exc)

    if not queue:
        queue = processor.queue()

    summary = {
        "new_orders_24h": len(queue),
        "auto_processed_24h": len([item for item in queue if not item.get("needs_manual")]),
        "manual_intervention_24h": len([item for item in queue if item.get("needs_manual")]),
        "auto_place_po": processor.auto_place_po,
        "source": queue_source,
    }

    rows = "".join(
        (
            "<tr>"
            f"<td><code>{item['order_id']}</code></td>"
            f"<td>{item.get('marketplace', '-')}</td>"
            f"<td>{item['stage']}</td>"
            f"<td>{'수동 개입 필요' if item['needs_manual'] else '자동 처리 가능'}</td>"
            "</tr>"
        )
        for item in queue
    )
    if not rows:
        rows = "<tr><td colspan='4' class='text-center text-muted'>대기 중인 주문이 없습니다.</td></tr>"

    source_badge = (
        "<span class='badge bg-success'>실데이터</span>"
        if queue_source == "live"
        else "<span class='badge bg-secondary'>시뮬레이션</span>"
    )
    source_note = (
        "주문 시트 기반 큐입니다."
        if queue_source == "live"
        else "연동 주문이 없어 시뮬레이션/대기 상태로 표시됩니다."
    )

    body = (
        "<h4 class='mb-3'>📦 주문 자동 처리 큐</h4>"
        "<div class='row mb-3'>"
        f"<div class='col-md-3'><div class='card text-center'><div class='card-body'><h5>{summary['new_orders_24h']}</h5><small>처리 대상</small></div></div></div>"
        f"<div class='col-md-3'><div class='card text-center'><div class='card-body'><h5>{summary['auto_processed_24h']}</h5><small>자동 처리 가능</small></div></div></div>"
        f"<div class='col-md-3'><div class='card text-center'><div class='card-body'><h5>{summary['manual_intervention_24h']}</h5><small>수동 개입</small></div></div></div>"
        f"<div class='col-md-3'><div class='card text-center'><div class='card-body'><h5>{'ON' if summary['auto_place_po'] else 'OFF'}</h5><small>자동 발주</small></div></div></div>"
        "</div>"
        "<div class='alert alert-light border d-flex justify-content-between align-items-center flex-wrap gap-2'>"
        f"<div>데이터 소스: {source_badge} · {source_note}</div>"
        "<button class='btn btn-primary btn-sm' type='button' onclick='runOrderAutoProcess()'>자동 처리 실행</button>"
        "</div>"
        "<div id='order-auto-run-result' class='small text-muted mb-2'></div>"
        "<table class='table table-sm table-hover'><thead><tr><th>주문 ID</th><th>마켓</th><th>단계</th><th>처리 상태</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "<script>"
        "function runOrderAutoProcess(){"
        "const box=document.getElementById('order-auto-run-result');"
        "box.textContent='실행 중...';"
        "fetch('/seller/orders/auto/process',{method:'POST'})"
        ".then(r=>r.json().then(d=>({ok:r.ok,data:d})))"
        ".then(({ok,data})=>{"
        "if(!ok||!data.ok){throw new Error((data&&data.error)||'실행 실패');}"
        "const summary=(data.summary||{});"
        "box.innerHTML=`실행 완료 · 모드: <strong>${data.mode}</strong> · 자동처리 ${summary.auto_processed||0}건 / 수동개입 ${summary.manual_required||0}건 / 시뮬레이션 ${summary.simulation_pending||0}건`;"
        "})"
        ".catch(err=>{box.textContent='실행 실패: '+err.message;});"
        "}"
        "</script>"
    )
    return _render_seller_page("📦 주문 자동 처리", body, page="orders_auto")


@bp.post("/orders/auto/process")
def orders_auto_process():
    """주문 자동 처리 실행 (실데이터/시뮬레이션 모두 정직 표기)."""
    if not _check_auth():
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401

    from src.orders.auto_processor import OrderAutoProcessor

    processor = OrderAutoProcessor()
    mode = "simulation"
    results = []

    svc = _get_order_sync_service()
    orders_list = []
    if svc is not None:
        try:
            orders_list = svc.list_orders(limit=200, offset=0)
            mode = "live"
        except Exception as exc:
            logger.warning("주문 자동 처리 실행 전 주문 로드 실패: %s", exc)
            orders_list = []

    if not orders_list:
        return jsonify({
            "ok": True,
            "mode": mode,
            "results": [],
            "summary": {"auto_processed": 0, "manual_required": 0, "simulation_pending": 0},
        })

    for row in orders_list:
        status = str(getattr(row.status, "value", row.status) or "").strip().lower()
        if status in {"delivered", "canceled", "returned", "exchanged"}:
            continue

        auto_order = processor.enqueue(
            row.order_id,
            supplier=str(row.marketplace),
            stage=status or "new",
            stock_ok=True,
            address_ok=True,
            payment_ok=status in {"paid", "preparing", "shipped"},
        )
        needs_manual = auto_order.needs_manual or status in {"refund_requested"} or not bool(row.items)
        if needs_manual:
            results.append({
                "order_id": row.order_id,
                "marketplace": row.marketplace,
                "status": "manual_required",
                "message": "수동 개입 필요",
            })
            continue

        po_result = processor.create_purchase_order(auto_order)
        if po_result.get("ok"):
            outcome = "auto_processed"
            message = "자동 발주 성공"
        elif mode == "live":
            outcome = "simulation_pending"
            message = "자동 발주 비활성화(대기)"
        else:
            outcome = "simulation_pending"
            message = "시뮬레이션 모드(외부 미연동)"
        results.append({
            "order_id": row.order_id,
            "marketplace": row.marketplace,
            "status": outcome,
            "message": message,
        })

    return jsonify({
        "ok": True,
        "mode": mode,
        "results": results,
        "summary": {
            "auto_processed": len([r for r in results if r["status"] == "auto_processed"]),
            "manual_required": len([r for r in results if r["status"] == "manual_required"]),
            "simulation_pending": len([r for r in results if r["status"] == "simulation_pending"]),
        },
    })


@bp.get("/shipping/tracking")
def shipping_tracking():
    """배송 모니터링 화면 (Phase 145)."""
    from src.shipping.tracker import ShippingMonitor

    monitor = ShippingMonitor()
    status = monitor.summary()
    body = (
        "<h4 class='mb-3'>🚚 배송 모니터링</h4>"
        "<div class='row mb-3'>"
        f"<div class='col-md-4'><div class='card text-center'><div class='card-body'><h5>{status['tracking_count']}</h5><small>추적 중</small></div></div></div>"
        f"<div class='col-md-4'><div class='card text-center'><div class='card-body'><h5 class='text-warning'>{status['delay_suspected']}</h5><small>지연 의심</small></div></div></div>"
        f"<div class='col-md-4'><div class='card text-center'><div class='card-body'><h5 class='text-danger'>{status['lost_suspected']}</h5><small>분실 의심</small></div></div></div>"
        "</div>"
        "<div class='alert alert-secondary'>택배사 API 연동 공급자: "
        f"<code>{status['provider']}</code></div>"
    )
    return _render_seller_page("🚚 배송 모니터링", body, page="shipping_tracking")


@bp.get("/returns/inbox")
def returns_inbox():
    """반품/환불 자동화 인박스 (Phase 146)."""
    from html import escape
    from src.returns.auto_processor import ReturnsAutoProcessor

    reason = (request.args.get("reason") or "").strip()
    status = (request.args.get("status") or "").strip()
    processor = ReturnsAutoProcessor()
    processor.collect_market_requests([])
    processor.process()
    rows = processor.list_requests(reason=reason, status=status)
    body_rows = ""
    for x in rows:
        request_id = escape(str(x.get("request_id", "-")), quote=True)
        order_id = escape(str(x.get("order_id", "-")), quote=True)
        reason_text = escape(str(x.get("reason", "-")))
        status_text = escape(str(x.get("status", "-")))
        badge_class = "bg-success" if x.get("status") == "approved" else "bg-secondary"
        body_rows += (
            "<tr>"
            f"<td><input type='checkbox' class='return-row-chk' value='{request_id}'></td>"
            f"<td><code>{request_id}</code></td>"
            f"<td>{order_id}</td>"
            f"<td>{reason_text}</td>"
            f"<td><span class='badge {badge_class}'>{status_text}</span></td>"
            f"<td><button class='btn btn-outline-primary btn-sm py-0 js-partial-refund-btn' type='button' data-request-id='{request_id}' data-order-id='{order_id}'>부분 환불</button></td>"
            "</tr>"
        )
    if not body_rows:
        body_rows = "<tr><td colspan='6' class='text-center text-muted'>반품 요청이 없습니다.</td></tr>"

    pending_count = sum(1 for x in rows if x.get("status") in ("requested", "manual_review"))
    bulk_disabled = 'disabled title="처리할 요청이 없습니다"' if not pending_count else ""
    body = (
        "<h4 class='mb-3'>↩️ 반품/환불 인박스</h4>"
        "<form class='row g-2 mb-3'>"
        "<div class='col-auto'><input name='reason' class='form-control form-control-sm' placeholder='사유 필터(defective 등)' value='"
        + reason
        + "'></div>"
        "<div class='col-auto'><input name='status' class='form-control form-control-sm' placeholder='상태 필터(approved 등)' value='"
        + status
        + "'></div>"
        "<div class='col-auto'><button class='btn btn-sm btn-primary'>적용</button></div>"
        "</form>"
        "<div class='d-flex gap-2 mb-2 align-items-center'>"
        f"<button class='btn btn-success btn-sm' type='button' id='bulkApproveBtn' onclick='bulkApproveReturns()' {bulk_disabled}>일괄 승인</button>"
        f"<button class='btn btn-outline-danger btn-sm' type='button' id='bulkRejectBtn' onclick='bulkRejectReturns()' {bulk_disabled}>거부</button>"
        "</div>"
        "<table class='table table-sm table-hover'>"
        "<thead><tr>"
        "<th><input type='checkbox' id='chkAll' title='전체 선택' onchange='toggleAllReturns(this)'></th>"
        "<th>요청 ID</th><th>주문</th><th>사유</th><th>상태</th><th>액션</th>"
        "</tr></thead>"
        f"<tbody>{body_rows}</tbody></table>"
        "<div class='position-fixed bottom-0 end-0 p-3 pc-toast-stack' style='z-index:1100'>"
        "<div id='returnsToast' class='toast' role='alert'>"
        "<div class='toast-header'><strong class='me-auto'>알림</strong>"
        "<button type='button' class='btn-close' data-bs-dismiss='toast'></button></div>"
        "<div class='toast-body' id='returnsToastMsg'></div></div></div>"
        "<div class='modal fade' id='partialRefundModal' tabindex='-1' aria-hidden='true'>"
        "<div class='modal-dialog'><div class='modal-content'>"
        "<div class='modal-header'><h5 class='modal-title'>부분 환불 처리</h5>"
        "<button type='button' class='btn-close' data-bs-dismiss='modal'></button></div>"
        "<div class='modal-body'>"
        "<input type='hidden' id='partialRefundRequestId'>"
        "<div class='small text-muted mb-3' id='partialRefundOrderLabel'></div>"
        "<div class='mb-3'><label class='form-label' for='partialRefundAmount'>환불 금액 (원)</label>"
        "<input type='number' min='1' step='1' class='form-control' id='partialRefundAmount' placeholder='예: 15000'></div>"
        "<div><label class='form-label' for='partialRefundReason'>사유 (선택)</label>"
        "<textarea class='form-control' id='partialRefundReason' rows='3' placeholder='부분 환불 사유를 입력하세요.'></textarea></div>"
        "</div>"
        "<div class='modal-footer'><button type='button' class='btn btn-secondary' data-bs-dismiss='modal'>취소</button>"
        "<button type='button' class='btn btn-primary' id='partialRefundSaveBtn' onclick='submitPartialRefund()'>환불 처리</button></div>"
        "</div></div></div>"
        """<script>
function _returnsToast(msg, type) {
  var el = document.getElementById('returnsToast');
  var body = document.getElementById('returnsToastMsg');
  if (!el || !body) return;
  body.textContent = msg;
  var map = {success:'bg-success',danger:'bg-danger',warning:'bg-warning'};
  el.className = 'toast text-white border-0 ' + (map[type] || 'bg-success');
  new bootstrap.Toast(el, {delay: 3500}).show();
}
function toggleAllReturns(masterChk) {
  document.querySelectorAll('.return-row-chk').forEach(c => { c.checked = masterChk.checked; });
}
function _getCheckedIds() {
  return Array.from(document.querySelectorAll('.return-row-chk:checked')).map(c => c.value);
}
document.addEventListener('click', function(event) {
  var btn = event.target.closest('.js-partial-refund-btn');
  if (!btn) return;
  openPartialRefundModal(btn.dataset.requestId || '', btn.dataset.orderId || '');
});
function openPartialRefundModal(requestId, orderId) {
  document.getElementById('partialRefundRequestId').value = requestId;
  document.getElementById('partialRefundOrderLabel').textContent = '주문 ' + orderId + ' / 요청 ' + requestId;
  document.getElementById('partialRefundAmount').value = '';
  document.getElementById('partialRefundReason').value = '';
  var modal = new bootstrap.Modal(document.getElementById('partialRefundModal'));
  modal.show();
  setTimeout(() => document.getElementById('partialRefundAmount')?.focus(), 120);
}
async function submitPartialRefund() {
  var requestId = document.getElementById('partialRefundRequestId').value;
  var amount = document.getElementById('partialRefundAmount').value;
  var reason = document.getElementById('partialRefundReason').value.trim();
  if (!amount || Number(amount) <= 0) {
    _returnsToast('환불 금액을 입력하세요.', 'warning');
    return;
  }
  var btn = document.getElementById('partialRefundSaveBtn');
  if (btn) btn.disabled = true;
  try {
    var r = await fetch('/seller/returns/' + encodeURIComponent(requestId) + '/partial-refund', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({amount_krw: amount, reason: reason})
    });
    var d = await r.json();
    if (r.ok && d.ok) {
      bootstrap.Modal.getInstance(document.getElementById('partialRefundModal'))?.hide();
      _returnsToast('부분 환불 완료: ' + (d.refund_amount || amount) + '원', 'success');
      setTimeout(() => location.reload(), 1200);
    } else {
      _returnsToast('오류: ' + (d.error || '알 수 없음'), 'danger');
    }
  } catch(e) {
    _returnsToast('요청 실패: ' + e.message, 'danger');
  } finally {
    if (btn) btn.disabled = false;
  }
}
async function bulkApproveReturns() {
  var ids = _getCheckedIds();
  if (!ids.length) { _returnsToast('승인할 요청을 선택하세요.', 'warning'); return; }
  var btn = document.getElementById('bulkApproveBtn');
  if (btn) btn.disabled = true;
  try {
    var r = await fetch('/seller/returns/bulk-approve', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({request_ids: ids})
    });
    var d = await r.json();
    if (d.ok) {
      _returnsToast('승인 완료: ' + d.approved_count + '건', 'success');
      setTimeout(() => location.reload(), 1200);
    } else {
      _returnsToast('오류: ' + (d.error || '알 수 없음'), 'danger');
    }
  } catch(e) {
    _returnsToast('요청 실패: ' + e.message, 'danger');
  } finally {
    if (btn) btn.disabled = false;
  }
}
async function bulkRejectReturns() {
  var ids = _getCheckedIds();
  if (!ids.length) { _returnsToast('거부할 요청을 선택하세요.', 'warning'); return; }
  if (!confirm(ids.length + '건을 거부하시겠습니까?')) return;
  var btn = document.getElementById('bulkRejectBtn');
  if (btn) btn.disabled = true;
  try {
    var r = await fetch('/seller/returns/bulk-reject', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({request_ids: ids})
    });
    var d = await r.json();
    if (d.ok) {
      _returnsToast('거부 완료: ' + d.rejected_count + '건', 'success');
      setTimeout(() => location.reload(), 1200);
    } else {
      _returnsToast('오류: ' + (d.error || '알 수 없음'), 'danger');
    }
  } catch(e) {
    _returnsToast('요청 실패: ' + e.message, 'danger');
  } finally {
    if (btn) btn.disabled = false;
  }
}
</script>"""
    )
    return _render_seller_page("↩️ 반품/환불 인박스", body, page="returns_inbox")


@bp.post("/returns/bulk-approve")
def returns_bulk_approve():
    """반품/환불 일괄 승인 (선택된 요청 ID 목록).

    Request body: {"request_ids": ["RET-001", ...]}
    Response: {"ok": true, "approved_count": N, "results": [...]}
    """
    data = request.get_json(force=True, silent=True) or {}
    request_ids: list[str] = [str(x) for x in (data.get("request_ids") or []) if x]
    if not request_ids:
        return jsonify({"ok": False, "error": "승인할 요청 ID가 없습니다."}), 400

    results = []
    approved_count = 0
    try:
        from src.returns_automation.automation_manager import ReturnsAutomationManager
        mgr = ReturnsAutomationManager()
        for rid in request_ids:
            try:
                req_obj = mgr.approve(rid, notes="셀러 콘솔 일괄 승인")
                results.append({"request_id": rid, "ok": True, "status": req_obj.status.value if hasattr(req_obj.status, "value") else str(req_obj.status)})
                approved_count += 1
            except KeyError:
                results.append({"request_id": rid, "ok": False, "error": "요청을 찾을 수 없습니다."})
            except Exception as exc:
                logger.warning("returns_bulk_approve 항목 오류 %s: %s", rid, exc)
                results.append({"request_id": rid, "ok": False, "error": "처리 중 오류가 발생했습니다."})
    except Exception as exc:
        logger.error("returns_bulk_approve 서비스 오류: %s", exc)
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    return jsonify({"ok": True, "approved_count": approved_count, "results": results})


@bp.post("/returns/bulk-reject")
def returns_bulk_reject():
    """반품/환불 일괄 거부 (선택된 요청 ID 목록).

    Request body: {"request_ids": ["RET-001", ...], "notes": "사유"}
    Response: {"ok": true, "rejected_count": N, "results": [...]}
    """
    data = request.get_json(force=True, silent=True) or {}
    request_ids: list[str] = [str(x) for x in (data.get("request_ids") or []) if x]
    notes = str(data.get("notes") or "셀러 콘솔 일괄 거부")
    if not request_ids:
        return jsonify({"ok": False, "error": "거부할 요청 ID가 없습니다."}), 400

    results = []
    rejected_count = 0
    try:
        from src.returns_automation.automation_manager import ReturnsAutomationManager
        mgr = ReturnsAutomationManager()
        for rid in request_ids:
            try:
                req_obj = mgr.reject(rid, notes=notes)
                results.append({"request_id": rid, "ok": True, "status": req_obj.status.value if hasattr(req_obj.status, "value") else str(req_obj.status)})
                rejected_count += 1
            except KeyError:
                results.append({"request_id": rid, "ok": False, "error": "요청을 찾을 수 없습니다."})
            except Exception as exc:
                logger.warning("returns_bulk_reject 항목 오류 %s: %s", rid, exc)
                results.append({"request_id": rid, "ok": False, "error": "처리 중 오류가 발생했습니다."})
    except Exception as exc:
        logger.error("returns_bulk_reject 서비스 오류: %s", exc)
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    return jsonify({"ok": True, "rejected_count": rejected_count, "results": results})


@bp.post("/returns/<request_id>/partial-refund")
def returns_partial_refund(request_id: str):
    """반품 요청 개별 부분 환불 처리."""
    from decimal import Decimal, InvalidOperation

    data = request.get_json(force=True, silent=True) or {}
    raw_amount = data.get("amount_krw")
    reason = str(data.get("reason") or "").strip()
    try:
        amount = Decimal(str(raw_amount))
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({"ok": False, "error": "올바른 환불 금액을 입력하세요."}), 400
    if amount <= 0:
        return jsonify({"ok": False, "error": "환불 금액은 0보다 커야 합니다."}), 400

    try:
        from src.returns_automation.automation_manager import ReturnsAutomationManager
        mgr = ReturnsAutomationManager()
    except Exception as exc:
        logger.error("returns_partial_refund 서비스 오류: %s", exc)
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    req = mgr.get_request_object(request_id)
    if req is None:
        return jsonify({"ok": False, "error": "요청을 찾을 수 없습니다."}), 404

    try:
        result = mgr.process_partial_refund(request_id, amount, reason=reason)
        req = mgr.get_request_object(request_id) or req
        status_value = req.status.value if hasattr(req.status, "value") else str(req.status)
        return jsonify({"ok": True, "request_id": request_id, "refund_amount": str(amount), "status": status_value, "result": result})
    except Exception as exc:
        logger.warning("returns_partial_refund 처리 오류 %s: %s", request_id, exc)
        return jsonify({"ok": False, "error": "부분 환불 처리 중 오류가 발생했습니다."}), 500


@bp.get("/settlement")
def settlement_report():
    """월별 정산 리포트 화면 (Phase 146)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from src.settlement.reporter import SettlementReporter

    month = (request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")).strip()
    reporter = SettlementReporter()
    report = reporter.monthly_report(month, rows=[])
    channels = "".join(
        f"<li>{ch}: {amt:,}원</li>" for ch, amt in report["by_channel"].items()
    ) or "<li>-</li>"

    # 실 주문 KPI(연동 시 실데이터, 미연동 시 0 — 가짜 값 금지)
    kpi = {"today_new": 0, "pending_ship": 0, "shipped": 0, "returned_exchanged": 0}
    try:
        from .orders.sync_service import OrderSyncService
        k = OrderSyncService().kpi_summary() or {}
        for key in kpi:
            kpi[key] = int(k.get(key, 0) or 0)
    except Exception as exc:
        logger.debug("장부 주문 KPI 조회 실패: %s", exc)

    body = (
        "<h4 class='mb-1'>💰 장부 · 정산 (수익 관리)</h4>"
        "<p class='text-muted small mb-3'>매출·정산 요약과 주문 현황입니다. 숫자는 연동된 마켓/주문 데이터 기준이며, "
        "미연동 시 0으로 정직하게 표시됩니다.</p>"
        "<form class='row g-2 mb-3'>"
        "<div class='col-auto'><input name='month' class='form-control form-control-sm' value='"
        + month
        + "'></div>"
        "<div class='col-auto'><button class='btn btn-primary btn-sm'>조회</button></div>"
        "</form>"
        "<div class='row g-2 mb-3'>"
        f"<div class='col-6 col-md-3'><div class='card text-center p-2'><div class='fs-5 fw-bold'>{kpi['today_new']}</div><small class='text-muted'>오늘 신규주문</small></div></div>"
        f"<div class='col-6 col-md-3'><div class='card text-center p-2'><div class='fs-5 fw-bold text-warning'>{kpi['pending_ship']}</div><small class='text-muted'>배송 대기</small></div></div>"
        f"<div class='col-6 col-md-3'><div class='card text-center p-2'><div class='fs-5 fw-bold text-success'>{kpi['shipped']}</div><small class='text-muted'>배송 완료</small></div></div>"
        f"<div class='col-6 col-md-3'><div class='card text-center p-2'><div class='fs-5 fw-bold text-danger'>{kpi['returned_exchanged']}</div><small class='text-muted'>반품/교환</small></div></div>"
        "</div>"
        f"<div class='alert alert-light border'>이번달 매출(예정): <strong>{report['total_sales_krw']:,}원</strong><br>"
        f"실 입금 예정액: <strong>{report['total_expected_deposit_krw']:,}원</strong><br>"
        f"다음 정산일: {report['next_settlement_date']}</div>"
        "<h6>채널별 순이익</h6><ul>" + channels + "</ul>"
        "<div class='d-flex flex-wrap gap-2'>"
        f"<a class='btn btn-gold btn-sm' href='/seller/settlement/export.csv?month={month}'>CSV 내보내기</a>"
        f"<a class='btn btn-gold btn-sm' href='/seller/settlement/export.xlsx?month={month}'>Excel 내보내기</a>"
        "<a class='btn btn-outline-secondary btn-sm' href='/seller/analytics'>📊 BI 분석</a>"
        "<a class='btn btn-outline-secondary btn-sm' href='/seller/margin'>🧮 마진 계산기</a>"
        "</div>"
    )
    return _render_seller_page("💰 장부 · 정산", body, page="settlement")


@bp.get("/settlement/export.csv")
def settlement_export_csv():
    """정산 CSV 내보내기."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from src.settlement.reporter import SettlementReporter

    month = (request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")).strip()
    csv_text = SettlementReporter().export_csv(month, rows=[])
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=settlement-{month}.csv"},
    )


@bp.get("/settlement/export.xlsx")
def settlement_export_xlsx():
    """정산 Excel 내보내기(XML Spreadsheet)."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from src.settlement.reporter import SettlementReporter

    month = (request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")).strip()
    xml_text = SettlementReporter().export_excel_xml(month, rows=[])
    return Response(
        xml_text,
        mimetype="application/vnd.ms-excel",
        headers={"Content-Disposition": f"attachment; filename=settlement-{month}.xls"},
    )


# ---------------------------------------------------------------------------
# Phase 147 — 옴니채널 재고 동기화
# ---------------------------------------------------------------------------

@bp.get("/inventory/omni")
def inventory_omni():
    """옴니채널 재고 동기화 화면 (Phase 147)."""
    from src.inventory.omni_sync import OmniInventorySyncer

    syncer = OmniInventorySyncer()
    summary = syncer.summary()
    sku = (request.args.get("sku") or "").strip()
    channel_stocks = []
    if sku:
        channel_stocks = [cs.to_dict() for cs in syncer.channel_stocks(sku)]

    mode_badge = (
        "<span class='badge bg-primary'>common_pool</span>"
        if summary["mode"] == "common_pool"
        else "<span class='badge bg-secondary'>per_channel</span>"
    )
    enabled_badge = (
        "<span class='badge bg-success'>ON</span>"
        if summary["enabled"]
        else "<span class='badge bg-secondary'>OFF (INVENTORY_OMNI_SYNC_ENABLED=0)</span>"
    )

    stock_rows = ""
    for cs in channel_stocks:
        status_class = "success" if cs["sync_status"] == "ok" else ("warning" if cs["sync_status"] == "delayed" else "danger")
        stock_rows += (
            f"<tr>"
            f"<td>{cs['channel']}</td>"
            f"<td>{cs['stock']}</td>"
            f"<td><span class='badge bg-{status_class}'>{cs['sync_status']}</span></td>"
            f"<td class='small text-muted'>{cs.get('error', '')}</td>"
            "</tr>"
        )

    channels_html = ", ".join(summary["configured_channels"]) or "연동된 채널 없음"

    body = (
        "<h4 class='mb-3'>🔄 옴니채널 재고 동기화 (Phase 147)</h4>"
        "<div class='row mb-3'>"
        f"<div class='col-md-3'><div class='card text-center'><div class='card-body'><h5>{summary['channel_count']}</h5><small>연동 채널</small></div></div></div>"
        f"<div class='col-md-3'><div class='card text-center'><div class='card-body'><h5 class='text-danger'>{summary['failure_24h']}</h5><small>24h 실패</small></div></div></div>"
        f"<div class='col-md-3'><div class='card text-center'><div class='card-body'><h5>{summary['sync_interval_sec']}초</h5><small>동기화 주기</small></div></div></div>"
        "</div>"
        "<div class='alert alert-light border mb-3'>"
        f"활성화: {enabled_badge} &nbsp; 모드: {mode_badge}<br>"
        f"<small>연동 채널: {channels_html}</small>"
        "</div>"
        "<h5 class='mb-2'>SKU별 재고 조회</h5>"
        "<form class='row g-2 mb-3'>"
        f"<div class='col-auto'><input name='sku' class='form-control form-control-sm' placeholder='SKU 입력' value='{sku}'></div>"
        "<div class='col-auto'><button class='btn btn-sm btn-primary' style='min-height:36px'>조회</button></div>"
        "</form>"
    )
    if sku:
        body += (
            "<div class='table-responsive mb-3'>"
            "<table class='table table-sm table-hover'>"
            "<thead><tr><th>채널</th><th>재고</th><th>동기화 상태</th><th>오류</th></tr></thead>"
            f"<tbody>{stock_rows or '<tr><td colspan=4 class=text-center>조회 결과 없음</td></tr>'}</tbody>"
            "</table></div>"
            "<form method='post' action='/seller/inventory/omni/sync' class='d-inline'>"
            f"<input type='hidden' name='sku' value='{sku}'>"
            "<button class='btn btn-outline-primary btn-sm' style='min-height:36px'>🔄 수동 동기화</button>"
            "</form>"
        )
    return _render_seller_page("🔄 옴니채널 재고", body, page="inventory_omni")


@bp.post("/inventory/omni/sync")
def inventory_omni_sync():
    """수동 동기화 트리거 (Phase 147)."""
    from src.inventory.omni_sync import OmniInventorySyncer

    sku = (request.form.get("sku") or "").strip()
    if not sku:
        return redirect(url_for("seller_console.inventory_omni"))
    syncer = OmniInventorySyncer()
    syncer.manual_sync(sku)
    return redirect(url_for("seller_console.inventory_omni", sku=sku))


# ---------------------------------------------------------------------------
# Phase 147 — 푸시 알림 설정 (/me/notifications)
# ---------------------------------------------------------------------------

@bp.get("/me/notifications")
def me_notifications():
    """푸시 알림 구독/해제 + 카테고리별 설정 (Phase 147)."""
    from src.notifications.web_push import push_status, get_vapid_public_key

    status = push_status()
    vapid_pub = get_vapid_public_key()
    vapid_badge = (
        '<span class="badge bg-success">✅ 설정됨</span>'
        if status["vapid_configured"]
        else '<span class="badge bg-warning">⚠️ 미설정 (기능 제한)</span>'
    )

    body = (
        "<h4 class='mb-3'>🔔 푸시 알림 설정 (Phase 147)</h4>"
        "<div class='alert alert-light border mb-3'>"
        f"VAPID 공개키: {vapid_badge}<br>"
        f"현재 구독자: <strong>{status['subscriber_count']}</strong>명"
        "</div>"
    )

    if status['vapid_configured']:
        body += (
            "<div class='card mb-3'>"
            "<div class='card-header fw-bold'>📱 이 기기 푸시 구독</div>"
            "<div class='card-body'>"
            "<div id='pushStatus' class='mb-2 text-muted small'>푸시 구독 상태 확인 중...</div>"
            "<button id='subscribeBtn' class='btn btn-primary me-2' style='min-height:44px' onclick='subscribePush()'>🔔 구독</button>"
            "<button id='unsubscribeBtn' class='btn btn-outline-secondary' style='min-height:44px;display:none' onclick='unsubscribePush()'>🔕 구독 해제</button>"
            "</div>"
            "</div>"
            "<div class='card mb-3'>"
            "<div class='card-header fw-bold'>📋 알림 카테고리 ON/OFF</div>"
            "<div class='card-body'>"
            "<form id='categoryForm'>"
            "<div class='form-check form-switch mb-2'><input class='form-check-input' type='checkbox' id='cat_order' name='order' checked><label class='form-check-label' for='cat_order'>🛒 신규 주문</label></div>"
            "<div class='form-check form-switch mb-2'><input class='form-check-input' type='checkbox' id='cat_cs' name='cs' checked><label class='form-check-label' for='cat_cs'>🚨 긴급 CS</label></div>"
            "<div class='form-check form-switch mb-2'><input class='form-check-input' type='checkbox' id='cat_shipping' name='shipping' checked><label class='form-check-label' for='cat_shipping'>⚠️ 배송 지연</label></div>"
            "<div class='form-check form-switch mb-2'><input class='form-check-input' type='checkbox' id='cat_ads' name='ads' checked><label class='form-check-label' for='cat_ads'>📊 ROAS 급변</label></div>"
            "</form>"
            "</div>"
            "</div>"
            "<div class='card mb-3'>"
            "<div class='card-header fw-bold'>🔬 테스트 전송</div>"
            "<div class='card-body'>"
            "<button class='btn btn-outline-primary btn-sm' style='min-height:44px'"
            "  onclick=\"fetch('/seller/me/notifications/test', {method:'POST'}).then(r=>r.json()).then(d=>alert(d.message||d.error))\">"
            "  📤 테스트 알림 전송"
            "</button>"
            "</div>"
            "</div>"
        )
        body += (
            f"<script>"
            f"const VAPID_PUB_KEY = '{vapid_pub}';"
            """
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  return Uint8Array.from(atob(base64), c => c.charCodeAt(0));
}
async function subscribePush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    alert('이 브라우저는 Web Push를 지원하지 않습니다.'); return;
  }
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(VAPID_PUB_KEY)
  });
  const resp = await fetch('/seller/me/notifications/subscribe', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({subscription: sub.toJSON()})
  });
  const data = await resp.json();
  document.getElementById('pushStatus').textContent = data.ok ? '✅ 구독 완료' : '❌ 구독 실패: ' + data.error;
}
async function unsubscribePush() {
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) { alert('구독 중인 항목이 없습니다.'); return; }
  await sub.unsubscribe();
  await fetch('/seller/me/notifications/unsubscribe', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({endpoint: sub.endpoint})});
  document.getElementById('pushStatus').textContent = '구독 해제됨';
}
navigator.serviceWorker && navigator.serviceWorker.ready.then(reg => {
  reg.pushManager.getSubscription().then(sub => {
    document.getElementById('pushStatus').textContent = sub ? '✅ 구독 중' : '구독 안 됨';
  });
});
"""
            f"</script>"
        )
    else:
        body += (
            "<div class='alert alert-warning'>"
            "⚠️ VAPID 키가 설정되지 않았습니다. 환경변수 <code>WEB_PUSH_VAPID_PUBLIC</code>, <code>WEB_PUSH_VAPID_PRIVATE</code>를 설정하세요.<br>"
            "<a href='/admin/diagnostics'>🛠️ /admin/diagnostics에서 생성 가이드 확인</a>"
            "</div>"
        )

    return _render_seller_page("🔔 푸시 알림", body, page="push_notifications")


@bp.post("/me/notifications/subscribe")
def me_notifications_subscribe():
    """Web Push 구독 등록 API (Phase 147)."""
    from src.notifications.web_push import PushSubscription, PushSubscriptionStore

    try:
        data = request.get_json(force=True) or {}
        sub_data = data.get("subscription", {})
        keys = sub_data.get("keys", {})
        user_id = session.get("user_id", "anonymous")
        sub = PushSubscription(
            user_id=user_id,
            endpoint=sub_data.get("endpoint", ""),
            p256dh=keys.get("p256dh", ""),
            auth=keys.get("auth", ""),
        )
        if not sub.endpoint:
            return jsonify({"ok": False, "error": "endpoint 필수"}), 400
        PushSubscriptionStore().subscribe(sub)
        return jsonify({"ok": True, "message": "구독 완료"})
    except Exception as exc:
        logger.warning("push subscribe 오류: %s", exc)
        return jsonify({"ok": False, "error": "구독 처리 중 오류"}), 500


@bp.post("/me/notifications/unsubscribe")
def me_notifications_unsubscribe():
    """Web Push 구독 해제 API (Phase 147)."""
    from src.notifications.web_push import PushSubscriptionStore

    try:
        data = request.get_json(force=True) or {}
        endpoint = data.get("endpoint", "")
        if not endpoint:
            return jsonify({"ok": False, "error": "endpoint 필수"}), 400
        ok = PushSubscriptionStore().unsubscribe(endpoint)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("push unsubscribe 오류: %s", exc)
        return jsonify({"ok": False, "error": "처리 중 오류"}), 500


@bp.post("/me/notifications/test")
def me_notifications_test():
    """테스트 푸시 알림 전송 (Phase 147)."""
    from src.notifications.web_push import PushSubscriptionStore, send_push

    user_id = session.get("user_id", "anonymous")
    subs = PushSubscriptionStore().list_for_user(user_id)
    if not subs:
        return jsonify({"ok": False, "error": "구독 중인 기기가 없습니다."})
    results = [send_push(s, title="🔔 테스트 알림", body=f"{get_brand_name_ko()} 푸시 알림이 정상 작동 중입니다.") for s in subs]
    return jsonify({"ok": any(results), "message": f"{sum(results)}/{len(results)} 기기에 전송 완료"})


# ---------------------------------------------------------------------------
# Phase 148 — B2B 도매 모드 (/seller/wholesale/*)
# ---------------------------------------------------------------------------

@bp.get("/wholesale/tiers")
def wholesale_tiers():
    """도매 등급/할인 룰 관리 (Phase 148)."""
    from src.wholesale.tier_manager import WholesaleTierManager
    mgr = WholesaleTierManager()
    tiers = mgr.list_tiers()
    body = (
        "<h4 class='mb-4 fw-bold'>🏢 B2B 도매 등급 관리 <small class='text-muted fs-6'>Phase 148</small></h4>"
        + ("<div class='alert alert-warning'>⚠️ 도매 기능이 비활성화되어 있습니다 (WHOLESALE_ENABLED=0).</div>" if not mgr.enabled else "")
        + "<div class='table-responsive'><table class='table table-bordered table-hover'>"
        + "<thead class='table-dark'><tr><th>등급</th><th>이름</th><th>MOQ</th><th>할인 구간</th><th>설명</th></tr></thead><tbody>"
    )
    for t in tiers:
        brackets_html = " / ".join(
            f"{b.min_qty}~{b.max_qty if b.max_qty else '∞'}개 × {b.multiplier}"
            for b in t.brackets
        )
        body += (
            f"<tr><td><code>{t.level.value}</code></td>"
            f"<td><strong>{t.label}</strong></td>"
            f"<td>{t.moq}개 이상</td>"
            f"<td>{brackets_html}</td>"
            f"<td class='text-muted'>{t.description}</td></tr>"
        )
    body += (
        "</tbody></table></div>"
        "<div class='alert alert-info mt-3'>"
        "<strong>수량 구간 할인:</strong> 도매 1~9개 ❌ (MOQ 미달) · 10~49개 ×0.9 · 50개+ ×0.8 | VIP ×0.75"
        "</div>"
        "<a href='/seller/wholesale/applications' class='btn btn-outline-primary btn-sm'>📋 B2B 신청 목록</a>"
    )
    return _render_seller_page("🏢 도매 등급 관리", body, page="wholesale_tiers")


@bp.get("/wholesale/applications")
def wholesale_applications():
    """B2B 가입 신청 승인 큐 (Phase 148)."""
    from src.wholesale.application_manager import WholesaleApplicationManager, ApplicationStatus
    mgr = WholesaleApplicationManager()
    pending = mgr.list_applications(status=ApplicationStatus.PENDING)
    approved = mgr.list_applications(status=ApplicationStatus.APPROVED)
    body = (
        "<h4 class='mb-4 fw-bold'>📋 B2B 신청 승인 큐 <small class='text-muted fs-6'>Phase 148</small></h4>"
        f"<div class='mb-3'><span class='badge bg-warning text-dark me-2'>대기 {len(pending)}건</span>"
        f"<span class='badge bg-success me-2'>승인 {len(approved)}건</span></div>"
    )
    if not pending:
        body += "<div class='alert alert-secondary'>대기 중인 B2B 신청이 없습니다.</div>"
    else:
        body += (
            "<div class='table-responsive'><table class='table table-hover'>"
            "<thead class='table-light'><tr><th>신청 ID</th><th>회사명</th><th>사업자번호</th><th>연락처</th><th>신청일</th><th>조작</th></tr></thead><tbody>"
        )
        for a in pending:
            body += (
                f"<tr><td><small>{a.application_id[:8]}…</small></td>"
                f"<td><strong>{a.business_name}</strong></td>"
                f"<td>{a.business_reg_number}</td>"
                f"<td>{a.contact_email}</td>"
                f"<td><small>{a.submitted_at[:10]}</small></td>"
                f"<td>"
                f"<form method='post' action='/seller/wholesale/applications/{a.application_id}/approve' class='d-inline'>"
                f"<button class='btn btn-success btn-sm me-1'>✅ 승인</button></form>"
                f"<form method='post' action='/seller/wholesale/applications/{a.application_id}/reject' class='d-inline'>"
                f"<button class='btn btn-danger btn-sm'>❌ 거절</button></form>"
                f"</td></tr>"
            )
        body += "</tbody></table></div>"
    body += "<a href='/seller/wholesale/tiers' class='btn btn-outline-secondary btn-sm mt-3'>← 등급 관리</a>"
    return _render_seller_page("📋 B2B 신청 큐", body, page="wholesale_applications")


@bp.post("/wholesale/applications/<application_id>/approve")
def wholesale_application_approve(application_id: str):
    """B2B 신청 승인 (Phase 148)."""
    from src.wholesale.application_manager import WholesaleApplicationManager
    WholesaleApplicationManager().approve(application_id, reviewer_note="관리자 승인")
    return redirect("/seller/wholesale/applications")


@bp.post("/wholesale/applications/<application_id>/reject")
def wholesale_application_reject(application_id: str):
    """B2B 신청 거절 (Phase 148)."""
    from src.wholesale.application_manager import WholesaleApplicationManager
    WholesaleApplicationManager().reject(application_id, reviewer_note="관리자 거절")
    return redirect("/seller/wholesale/applications")


# ---------------------------------------------------------------------------
# Phase 148 — 정기구독 상품 (/seller/subscriptions, /seller/me/subscriptions)
# ---------------------------------------------------------------------------

@bp.get("/subscriptions")
def seller_subscriptions():
    """판매자 정기구독 관리 화면 (Phase 148)."""
    from src.product_subscriptions.subscription_products import ProductSubscriptionManager
    mgr = ProductSubscriptionManager()
    summary = mgr.summary()
    active_subs = mgr.list_active()
    body = (
        "<h4 class='mb-4 fw-bold'>🔁 정기구독 상품 관리 <small class='text-muted fs-6'>Phase 148</small></h4>"
        + ("<div class='alert alert-warning'>⚠️ 구독 기능이 비활성화되어 있습니다 (SUBSCRIPTION_ENABLED=0).</div>" if not mgr.enabled else "")
        + "<div class='row g-3 mb-4'>"
        + f"<div class='col-md-3'><div class='card text-center shadow-sm'><div class='card-body'><h6 class='text-muted'>활성 구독</h6><h3>{summary['active_count']}</h3></div></div></div>"
        + f"<div class='col-md-3'><div class='card text-center shadow-sm'><div class='card-body'><h6 class='text-muted'>이번주 결제</h6><h3>{summary['billed_this_week']}</h3></div></div></div>"
        + f"<div class='col-md-3'><div class='card text-center shadow-sm'><div class='card-body'><h6 class='text-muted'>결제 실패</h6><h3 class='text-danger'>{summary['failed_count']}</h3></div></div></div>"
        + f"<div class='col-md-3'><div class='card text-center shadow-sm'><div class='card-body'><h6 class='text-muted'>PG 제공사</h6><h5><code>{summary['pg_provider']}</code></h5></div></div></div>"
        + "</div>"
    )
    if not active_subs:
        body += "<div class='alert alert-secondary'>활성 구독이 없습니다.</div>"
    else:
        body += (
            "<div class='table-responsive'><table class='table table-hover'>"
            "<thead class='table-light'><tr><th>구독 ID</th><th>사용자</th><th>상품</th><th>주기</th><th>단가</th><th>다음 결제일</th></tr></thead><tbody>"
        )
        for s in active_subs[:50]:
            body += (
                f"<tr><td><small>{s.subscription_id[:8]}…</small></td>"
                f"<td>{s.user_id}</td>"
                f"<td>{s.product_name or s.product_id}</td>"
                f"<td>{s.cycle.label}</td>"
                f"<td>₩{s.unit_price:,}</td>"
                f"<td>{s.next_billing_at[:10] if s.next_billing_at else '-'}</td></tr>"
            )
        body += "</tbody></table></div>"
    return _render_seller_page("🔁 정기구독 관리", body, page="subscriptions")


@bp.get("/me/subscriptions")
def me_subscriptions():
    """사용자 자신의 구독 관리 (Phase 148)."""
    from src.product_subscriptions.subscription_products import ProductSubscriptionManager, SubscriptionStatus
    user_id = session.get("user_id", "anonymous")
    mgr = ProductSubscriptionManager()
    subs = mgr.list_for_user(user_id)
    body = (
        "<h4 class='mb-4 fw-bold'>🔁 내 구독 관리 <small class='text-muted fs-6'>Phase 148</small></h4>"
    )
    if not subs:
        body += (
            "<div class='alert alert-info'>"
            "현재 구독 중인 상품이 없습니다. 상품 상세 페이지에서 '정기구독' 버튼을 눌러 구독을 시작하세요."
            "</div>"
        )
    else:
        body += (
            "<div class='table-responsive'><table class='table table-hover'>"
            "<thead class='table-light'><tr><th>상품</th><th>주기</th><th>단가</th><th>상태</th><th>다음 결제</th><th>조작</th></tr></thead><tbody>"
        )
        for s in subs:
            status_badge = {
                SubscriptionStatus.ACTIVE: "<span class='badge bg-success'>활성</span>",
                SubscriptionStatus.PAUSED: "<span class='badge bg-warning text-dark'>일시정지</span>",
                SubscriptionStatus.CANCELLED: "<span class='badge bg-secondary'>해지</span>",
            }.get(s.status, s.status.value)
            actions = ""
            if s.status == SubscriptionStatus.ACTIVE:
                actions = (
                    f"<form method='post' action='/seller/me/subscriptions/{s.subscription_id}/pause' class='d-inline'>"
                    "<button class='btn btn-outline-warning btn-sm me-1'>일시정지</button></form>"
                    f"<form method='post' action='/seller/me/subscriptions/{s.subscription_id}/skip' class='d-inline'>"
                    "<button class='btn btn-outline-secondary btn-sm me-1'>스킵</button></form>"
                    f"<form method='post' action='/seller/me/subscriptions/{s.subscription_id}/cancel' class='d-inline'>"
                    "<button class='btn btn-outline-danger btn-sm'>해지</button></form>"
                )
            elif s.status == SubscriptionStatus.PAUSED:
                actions = (
                    f"<form method='post' action='/seller/me/subscriptions/{s.subscription_id}/resume' class='d-inline'>"
                    "<button class='btn btn-outline-success btn-sm'>재개</button></form>"
                )
            body += (
                f"<tr><td>{s.product_name or s.product_id}</td>"
                f"<td>{s.cycle.label}</td>"
                f"<td>₩{s.unit_price:,}</td>"
                f"<td>{status_badge}</td>"
                f"<td>{s.next_billing_at[:10] if s.next_billing_at else '-'}</td>"
                f"<td>{actions}</td></tr>"
            )
        body += "</tbody></table></div>"
    return _render_seller_page("🔁 내 구독", body, page="me_subscriptions")


@bp.post("/me/subscriptions/<subscription_id>/pause")
def me_subscription_pause(subscription_id: str):
    from src.product_subscriptions.subscription_products import ProductSubscriptionManager
    ProductSubscriptionManager().pause(subscription_id)
    return redirect("/seller/me/subscriptions")


@bp.post("/me/subscriptions/<subscription_id>/resume")
def me_subscription_resume(subscription_id: str):
    from src.product_subscriptions.subscription_products import ProductSubscriptionManager
    ProductSubscriptionManager().resume(subscription_id)
    return redirect("/seller/me/subscriptions")


@bp.post("/me/subscriptions/<subscription_id>/cancel")
def me_subscription_cancel(subscription_id: str):
    from src.product_subscriptions.subscription_products import ProductSubscriptionManager
    ProductSubscriptionManager().cancel(subscription_id)
    return redirect("/seller/me/subscriptions")


@bp.post("/me/subscriptions/<subscription_id>/skip")
def me_subscription_skip(subscription_id: str):
    from src.product_subscriptions.subscription_products import ProductSubscriptionManager
    ProductSubscriptionManager().skip_next(subscription_id)
    return redirect("/seller/me/subscriptions")


# ---------------------------------------------------------------------------
# Phase 160 — 키워드 트렌드 대시보드
# ---------------------------------------------------------------------------

_PERIOD_LABELS = {
    "realtime": "실시간(시간별)",
    "day": "일별",
    "week": "주별",
    "month": "월별",
    "year": "년별",
}


@bp.get("/keywords")
def seller_keywords():
    """키워드/검색어 트렌드 대시보드 (Phase 160).

    기간 토글(실시간/일/주/월/년) + 검색량·경쟁도·추세 + 급상승/연관/롱테일 키워드.
    """
    query = (request.args.get("q") or "").strip()
    period = request.args.get("period", "month")
    if period not in ("realtime", "day", "week", "month", "year"):
        period = "month"

    metrics = []
    related_kws = {"related": [], "expanded": [], "longtail": []}
    query_terms = [k.strip() for k in query.replace(",", " ").split() if k.strip()]
    keywords = query_terms or ["해외직구", "일본직구", "유니클로", "에코백"]

    try:
        from src.ads.keyword_optimizer import get_keyword_trends, get_related_keywords

        metrics = get_keyword_trends(keywords, period)
        if keywords:
            related_kws = get_related_keywords(keywords[0]) or related_kws
    except Exception as exc:
        logger.warning("키워드 트렌드 조회 실패: %s", exc)

    try:
        from src.ads.keyword_optimizer import get_rising_keywords
        rising = get_rising_keywords()
    except Exception as exc:
        logger.warning("급상승 키워드 조회 실패: %s", exc)
        rising = []

    return render_template(
        "keywords.html",
        query_text=query,
        period=period,
        period_label=_PERIOD_LABELS.get(period, "월별"),
        period_options=_PERIOD_LABELS,
        provider=(os.getenv("KEYWORD_OPT_PROVIDER", "mock") or "mock").strip().lower(),
        fallback_active=(os.getenv("KEYWORD_OPT_PROVIDER", "mock") or "mock").strip().lower() == "mock",
        rows=[
            {
                "keyword": m.get("keyword"),
                "search_volume": m.get("monthly_search", 0),
                "competition": m.get("competition", 0),
                "product_count": m.get("product_count", 0),
                "avg_cpc_krw": m.get("avg_cpc_krw", 0),
                "trend_pct": m.get("trend_pct", 0),
                "series": m.get("series", []),
            }
            for m in metrics
        ],
        risers=rising,
        related_keywords=list(dict.fromkeys((related_kws.get("related", []) + related_kws.get("expanded", []))))[:12],
        long_tail_keywords=related_kws.get("longtail", []),
    )


@bp.post("/keywords/search")
def seller_keywords_search():
    """키워드 트렌드 검색 API (JSON) — Phase 160."""
    data = request.get_json(force=True, silent=True) or {}
    keywords = data.get("keywords") or []
    period = data.get("period", "month")
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.replace(",", " ").split() if k.strip()]
    if period not in ("realtime", "day", "week", "month", "year"):
        period = "month"
    try:
        from src.ads.keyword_optimizer import get_keyword_trends
        metrics = get_keyword_trends(keywords, period)
        return jsonify({"ok": True, "metrics": metrics, "period": period})
    except Exception as exc:
        logger.warning("키워드 검색 API 오류: %s", exc)
        return jsonify({"ok": False, "error": "키워드 조회 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# Phase 160 — AI 소싱 허브 추가 API
# ---------------------------------------------------------------------------


@bp.post("/sourcing/recommend")
def seller_sourcing_recommend():
    """AI 소싱 후보 추천 API (JSON) — Phase 160."""
    data = request.get_json(force=True, silent=True) or {}
    keyword = (data.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"ok": False, "error": "keyword가 필요합니다."}), 400
    try:
        keyword_context = _build_keyword_trend_context([keyword], "week")
        recs = _build_sourcing_recommendations(keyword=keyword, keyword_context=keyword_context)
        return jsonify({"ok": True, "recommendations": recs})
    except Exception as exc:
        logger.warning("소싱 추천 API 오류: %s", exc)
        return jsonify({"ok": False, "error": "소싱 추천 중 오류가 발생했습니다."}), 500


@bp.post("/sourcing/collect")
def seller_sourcing_collect():
    """원클릭 범용 수집 API (JSON) — Phase 160.

    JSON body: {"url": "https://..."}
    신규 도메인 → Discovery candidates에 자동 등록.
    """
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "url이 필요합니다."}), 400

    try:
        from src.seller_console.collectors.dispatcher import collect
        result = collect(url)
    except Exception as exc:
        logger.warning("범용 수집 실패: %s", exc)
        return jsonify({"ok": False, "error": "수집 중 오류가 발생했습니다."}), 500

    # 신규 도메인 → Discovery candidates 자동 등록
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain:
            from src.discovery.scout import DiscoveryScout
            DiscoveryScout().add_candidate(domain, source_keyword="manual_collect")
    except Exception as exc:
        logger.debug("Discovery 후보 자동 등록 실패(무시): %s", exc)

    if result and result.ok:
        return jsonify({
            "ok": True,
            "title": result.title or "",
            "price": str(result.price) if result.price else "",
            "image_url": result.image_url or "",
            "preview_url": f"/seller/collect/preview-result?url={url}",
        })
    else:
        msg = getattr(result, "error", "수집 결과를 가져오지 못했습니다.")
        return jsonify({"ok": False, "error": msg}), 400


@bp.get("/sourcing/collect")
def seller_sourcing_collect_get():
    """GET /seller/sourcing/collect?url=... — URL 수집 후 미리보기로 리다이렉트 (Phase 160)."""
    url = (request.args.get("url") or request.args.get("domain", "")).strip()
    if not url:
        return redirect("/seller/sourcing")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    # Validate URL before redirecting to prevent open redirect via injected schemes
    from urllib.parse import urlparse, urlencode
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return redirect("/seller/sourcing")
    safe_url = urlencode({"url": url})
    return redirect(f"/seller/manual-collect?{safe_url}")


# ---------------------------------------------------------------------------
# Phase 160 — My Sources CRUD
# ---------------------------------------------------------------------------


@bp.post("/sourcing/my-sources/add")
def sourcing_my_sources_add():
    """My Sources 즐겨찾기 추가 (Phase 160)."""
    data = request.get_json(force=True, silent=True) or {}
    domain = (data.get("domain") or "").strip()
    label = (data.get("label") or "").strip()
    url_example = (data.get("url_example") or "").strip()
    if not domain:
        return jsonify({"ok": False, "error": "domain이 필요합니다."}), 400
    try:
        from src.seller_console.my_sources_store import MySourcesStore
        entry = MySourcesStore().add(domain=domain, label=label, url_example=url_example)
        return jsonify({"ok": True, "domain": entry.domain, "label": entry.label})
    except Exception as exc:
        logger.warning("My Sources 추가 실패: %s", exc)
        return jsonify({"ok": False, "error": "즐겨찾기 추가 중 오류가 발생했습니다."}), 500


@bp.post("/sourcing/my-sources/remove")
def sourcing_my_sources_remove():
    """My Sources 즐겨찾기 삭제 (Phase 160)."""
    data = request.get_json(force=True, silent=True) or {}
    domain = (data.get("domain") or "").strip()
    if not domain:
        return jsonify({"ok": False, "error": "domain이 필요합니다."}), 400
    try:
        from src.seller_console.my_sources_store import MySourcesStore
        ok = MySourcesStore().remove(domain)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("My Sources 삭제 실패: %s", exc)
        return jsonify({"ok": False, "error": "즐겨찾기 삭제 중 오류가 발생했습니다."}), 500


@bp.get("/sourcing/my-sources")
def sourcing_my_sources_list():
    """My Sources 진입(화면) + 목록 API(JSON, format=json) — Phase 160."""
    wants_json = (request.args.get("format") or "").strip().lower() == "json"
    if not wants_json:
        return redirect(
            url_for(
                "seller_console.sourcing_hub",
                notice="자사몰·소규모 브랜드몰 등 원하는 몰을 직접 등록하세요.",
                _anchor="registryDomainInput",
            )
        )
    try:
        from src.seller_console.my_sources_store import MySourcesStore
        entries = [e.to_dict() for e in MySourcesStore().list()]
        return jsonify({"ok": True, "sources": entries})
    except Exception as exc:
        logger.warning("My Sources 목록 조회 실패: %s", exc)
        return jsonify({"ok": False, "error": "즐겨찾기 목록 조회 중 오류가 발생했습니다."}), 500
