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
from typing import Any, Dict
from difflib import SequenceMatcher

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from urllib.parse import quote_plus

from flask import Blueprint, abort, jsonify, redirect, render_template, render_template_string, request, session, url_for, Response
from src.utils.branding import get_brand_name

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
_AUTH_ENABLED = os.getenv("SELLER_CONSOLE_AUTH", "0") == "1"
_ONBOARDING_DISMISS_COOKIE = "seller_onboarding_dismissed"
_ONBOARDING_DISMISS_COOKIE_MAX_AGE = 60 * 60 * 24 * 180


@bp.app_context_processor
def inject_seller_template_flags():
    return {
        "diagnostic_reveal_enabled": os.getenv("DIAGNOSTIC_REVEAL", "0") == "1",
        "sidebar_grouped": os.getenv("SIDEBAR_GROUPED", "1") == "1",
        "brand_name": get_brand_name(),
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
    """인증 확인 stub. SELLER_CONSOLE_AUTH=1 시 추후 실제 인증으로 교체."""
    if not _AUTH_ENABLED:
        return True
    # TODO: Phase 24 OAuth 미들웨어 연결
    return True


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

def _get_widgets() -> list:
    """위젯 데이터 목록 조회 (graceful import)."""
    try:
        from .widgets import build_all_widgets
        return build_all_widgets()
    except Exception as exc:
        logger.warning("위젯 로드 실패: %s", exc)
        return []


def _get_collector_service():
    """ManualCollectorService 인스턴스 반환 (graceful import)."""
    try:
        from .manual_collector import ManualCollectorService
        return ManualCollectorService()
    except Exception as exc:
        logger.warning("ManualCollectorService 로드 실패: %s", exc)
        return None


def _get_upload_dispatcher():
    """UploadDispatcher 인스턴스 반환 (graceful import)."""
    try:
        from .upload_dispatcher import UploadDispatcher
        return UploadDispatcher()
    except Exception as exc:
        logger.warning("UploadDispatcher 로드 실패: %s", exc)
        return None


def _get_trust_checker():
    """TaobaoSellerTrustChecker 인스턴스 반환 (graceful import)."""
    try:
        from .seller_trust import TaobaoSellerTrustChecker
        return TaobaoSellerTrustChecker()
    except Exception as exc:
        logger.warning("TaobaoSellerTrustChecker 로드 실패: %s", exc)
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
    try:
        from src.seller_console.onboarding import compute_onboarding_state
        onboarding = compute_onboarding_state(
            connected_markets=connected_count,
            source_count=source_count,
            product_count=product_count,
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
            "service_name": "Proxy Commerce",
            "version": dashboard_version,
            "policy_links": [
                {"label": "이용약관", "href": "/terms"},
                {"label": "개인정보처리방침", "href": "/privacy"},
                {"label": "도움말", "href": "/seller/cs/messaging"},
            ],
        },
    }


def _render_dashboard_home():
    widgets = _get_widgets()
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

    return render_template(
        "manual_collect.html",
        page="collect",
        api_status=api_status,
        marketplace_cards=marketplace_cards,
        locale_options=locale_options,
        localization_configured=localization_configured,
    )


@bp.get("/manual-collect")
def manual_collect_alias():
    """수동 수집기 별칭 경로 (Phase 145)."""
    return redirect(url_for("seller_console.collect"))


@bp.post("/collect/preview")
def collect_preview():
    """URL → 메타데이터 추출 결과 (JSON).

    Phase 128: 실 수집기 우선 시도 → 기존 ManualCollectorService 폴백.

    Request body: {"url": "https://..."}
    Response: {"ok": true, "draft": {...}}
    """
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    keyword_hint = (data.get("keyword") or "").strip()

    if not url:
        return jsonify({"ok": False, "error": "URL이 필요합니다."}), 400

    # Phase 128: 실 수집기 dispatcher 우선 사용
    try:
        from src.seller_console.collectors.dispatcher import collect as dispatcher_collect
        result = dispatcher_collect(url)
        if result.success:
            # 기존 draft 형식과 호환되도록 변환
            draft_dict = result.to_dict()
            # 하위 호환 필드 추가
            draft_dict.update({
                "title_en": result.title or "",
                "title_ko": result.title or "",
                "price_original": float(result.price) if result.price else 0.0,
                "is_mock": False,
                "adapter_used": result.source,
            })
            _register_discovery_candidate_from_collection(url, keyword_hint=keyword_hint)
            return jsonify({
                "ok": True,
                "draft": draft_dict,
                "trust": None,
                "source": result.source,
                "warnings": result.warnings,
            })
    except Exception as exc:
        logger.debug("실 수집기 실패, 기존 수집기로 폴백: %s", exc)

    # 기존 ManualCollectorService 폴백
    collector = _get_collector_service()
    if collector is None:
        return jsonify({"ok": False, "error": "수집기 모듈 준비 중입니다."}), 503

    try:
        draft = collector.extract(url)
        draft_dict = draft.to_dict()

        # 타오바오 URL인 경우 셀러 신뢰도 자동 추가
        trust_info = None
        if draft.seller_id and draft.source in ("taobao", "alibaba"):
            checker = _get_trust_checker()
            if checker and draft.seller_id:
                trust_score = checker.evaluate(draft.seller_id)
                trust_info = trust_score.to_dict()

        _register_discovery_candidate_from_collection(url, keyword_hint=keyword_hint)
        return jsonify({
            "ok": True,
            "draft": draft_dict,
            "trust": trust_info,
        })
    except ValueError:
        return jsonify({"ok": False, "error": "URL 형식이 올바르지 않습니다."}), 400
    except Exception as exc:
        logger.warning("수집기 오류: %s", exc)
        return jsonify({"ok": False, "error": "추출 중 오류가 발생했습니다."}), 500


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
        return jsonify({"ok": True, "result": result.to_dict()})
    except Exception as exc:
        logger.warning("업로드 디스패처 오류: %s", exc)
        return jsonify({"ok": False, "error": "업로드 중 오류가 발생했습니다."}), 500


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

    items = []
    total = 0
    source = "mock"
    error_msg = None

    try:
        from .market_status_sheets import MarketStatusSheetsAdapter
        from datetime import datetime
        adapter = MarketStatusSheetsAdapter()
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
        start = (page_num - 1) * per_page
        items = all_items[start:start + per_page]
    except Exception as exc:
        logger.warning("카탈로그 데이터 로드 실패: %s", exc)
        error_msg = str(exc)

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

    return render_template(
        "catalog.html",
        items=view_items,
        page="catalog",
        current_page=page_num,
        total_pages=total_pages,
        total=total,
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
    """API 상태 페이지 (Phase 130: 카테고리 그루핑)."""
    if not _check_auth():
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
    """API 상태 JSON 응답 (Phase 130: 구조화된 응답)."""
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
        ok = send_telegram("✅ proxy-commerce 알림 테스트 메시지입니다.", urgency="info")
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
    from flask import session as _session
    user_id = _session.get("user_id")
    user = None
    if user_id:
        try:
            from src.auth.user_store import get_store
            user = get_store().find_by_id(user_id)
        except Exception as exc:
            logger.warning("마이페이지 사용자 조회 실패: %s", exc)

    return render_template(
        "me.html",
        page="me",
        user=user,
        telegram_active=bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        resend_active=bool(os.getenv("RESEND_API_KEY")),
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
        configured = _market_is_configured(market_code)
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
    """현재 셀러 식별자. 단일 테넌트(오너)에서는 'default'."""
    return str(session.get("user_id") or session.get("user_email") or "default")


def _diag_market_key(market: str) -> str:
    """자격증명 마켓 키 → 진단 서브시스템 키 (11번가만 상이)."""
    return "11st" if market == "elevenst" else market


@bp.get("/markets/connect")
def markets_connect():
    """셀프서비스 마켓 연결 관리 화면."""
    if not _check_auth():
        return redirect(url_for("auth.login", next=request.url))
    from . import market_credentials as mc

    statuses = mc.all_status(_seller_id())
    return render_template("markets_connect.html", page="markets", market_statuses=statuses)


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
    from flask import session as _session
    user_id = _session.get("user_id", "dev")

    tokens = []
    try:
        from src.auth.personal_tokens import list_tokens
        tokens = list_tokens(user_id)
    except Exception as exc:
        logger.warning("토큰 목록 조회 실패: %s", exc)

    return render_template(
        "personal_tokens.html",
        page="me",
        tokens=tokens,
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
    from flask import session as _session
    user_id = _session.get("user_id", "dev")

    data = request.get_json(force=True, silent=True) or {}
    scopes = data.get("scopes") or ["collect.write"]
    expires_days = int(data.get("expires_days", 365))

    try:
        from src.auth.personal_tokens import generate_token
        result = generate_token(user_id=user_id, scopes=scopes, expires_days=expires_days)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        logger.warning("토큰 발급 실패: %s", exc)
        return jsonify({"ok": False, "error": "토큰 발급 중 오류가 발생했습니다."}), 500


@bp.post("/me/tokens/revoke")
def personal_tokens_revoke():
    """Personal Access Token 회수 (Phase 135).

    Request body: {"token_hash": "..."}
    Response: {"ok": true}
    """
    from flask import session as _session
    user_id = _session.get("user_id", "dev")

    data = request.get_json(force=True, silent=True) or {}
    token_hash = (data.get("token_hash") or "").strip()
    if not token_hash:
        return jsonify({"ok": False, "error": "token_hash가 필요합니다."}), 400

    try:
        from src.auth.personal_tokens import revoke_token
        ok = revoke_token(token_hash=token_hash, user_id=user_id)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("토큰 회수 실패: %s", exc)
        return jsonify({"ok": False, "error": "토큰 회수 중 오류가 발생했습니다."}), 500


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

    domain = request.args.get("domain", "").strip()
    source = request.args.get("source", "").strip()
    days = int(request.args.get("days", "30"))

    items = []
    summ = {"total": 0, "today": 0, "domains": 0, "by_source": {"extension": 0, "bookmarklet": 0, "manual": 0, "bulk": 0}}
    domains = []
    try:
        from .collect_history_store import list_items, summary, distinct_domains
        items = list_items(domain=domain, source=source, days=days)
        summ = summary(days=days)
        domains = distinct_domains()
    except Exception as exc:
        logger.warning("수집 이력 조회 실패: %s", exc)

    return render_template(
        "collect_history.html",
        page="collect_history",
        items=items,
        summary=summ,
        domains=domains,
        filters={"domain": domain, "source": source, "days": days},
    )


@bp.get("/collect-history")
def collect_history_alias():
    """수집 이력 별칭 경로 (Phase 145)."""
    return redirect(url_for("seller_console.collect_history"))


@bp.get("/collect/preview/<item_id>")
def collect_preview_by_id(item_id: str):
    """수집된 상품 미리보기 (Phase 135.2)."""
    from flask import abort
    item = None
    try:
        from .collect_history_store import get as history_get
        item = history_get(item_id)
    except Exception as exc:
        logger.warning("미리보기 조회 실패: %s", exc)

    if not item:
        abort(404)

    extra = {}
    try:
        extra = json.loads(item.get("extra_json") or "{}")
    except Exception:
        pass

    return render_template(
        "collect_preview.html",
        page="collect_history",
        item=item,
        extra=extra,
    )


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


def _sourcing_require_admin():
    """소싱 페이지 관리자 권한 확인."""
    from src.auth.admin_resolver import is_admin_session
    if not session.get("user_id"):
        return redirect(url_for("auth.login", next=request.url))
    admin_ok, _ = is_admin_session(session)
    if not admin_ok:
        return jsonify({"ok": False, "error": "관리자 권한이 필요합니다"}), 403
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
    from src.settlement.reporter import SettlementReporter

    month = (request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")).strip()
    reporter = SettlementReporter()
    report = reporter.monthly_report(month, rows=[])
    channels = "".join(
        f"<li>{ch}: {amt:,}원</li>" for ch, amt in report["by_channel"].items()
    ) or "<li>-</li>"
    body = (
        "<h4 class='mb-3'>💰 월별 정산 리포트</h4>"
        "<form class='row g-2 mb-3'>"
        "<div class='col-auto'><input name='month' class='form-control form-control-sm' value='"
        + month
        + "'></div>"
        "<div class='col-auto'><button class='btn btn-sm btn-primary'>조회</button></div>"
        "</form>"
        f"<div class='alert alert-light border'>이번달 매출(예정): <strong>{report['total_sales_krw']:,}원</strong><br>"
        f"실 입금 예정액: <strong>{report['total_expected_deposit_krw']:,}원</strong><br>"
        f"다음 정산일: {report['next_settlement_date']}</div>"
        "<h6>채널별 순이익</h6><ul>" + channels + "</ul>"
        "<div class='d-flex gap-2'>"
        f"<a class='btn btn-outline-secondary btn-sm' href='/seller/settlement/export.csv?month={month}'>CSV 내보내기</a>"
        f"<a class='btn btn-outline-secondary btn-sm' href='/seller/settlement/export.xlsx?month={month}'>Excel 내보내기</a>"
        "</div>"
    )
    return _render_seller_page("💰 정산 리포트", body, page="settlement")


@bp.get("/settlement/export.csv")
def settlement_export_csv():
    """정산 CSV 내보내기."""
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
    results = [send_push(s, title="🔔 테스트 알림", body="Proxy Commerce 푸시 알림이 정상 작동 중입니다.") for s in subs]
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
    """My Sources 즐겨찾기 목록 API (JSON) — Phase 160."""
    try:
        from src.seller_console.my_sources_store import MySourcesStore
        entries = [e.to_dict() for e in MySourcesStore().list()]
        return jsonify({"ok": True, "sources": entries})
    except Exception as exc:
        logger.warning("My Sources 목록 조회 실패: %s", exc)
        return jsonify({"ok": False, "error": "즐겨찾기 목록 조회 중 오류가 발생했습니다."}), 500
