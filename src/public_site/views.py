"""L1(오너 2026-10-05) — 비로그인 공개 페이지: /pricing · /terms · /privacy · /contact(noindex 아님).

카카오쇼핑(톡스토어) 연동 솔루션사·ESM(지마켓·옥션) 셀링툴사 심사자가 로그인 없이 서비스를 확인한다.
루트(/) 랜딩은 기존 `landing.html`(비로그인 → 랜딩, 로그인 → 콘솔)에 L1 섹션(`public/_l1_*.html`)을 넣는다.
`site_info`는 모든 템플릿에 들어간다(공통 푸터 `public/_site_footer.html`).
"""
from __future__ import annotations

from flask import Blueprint, render_template

from . import site_info

bp = Blueprint("public_site", __name__, template_folder="templates", static_folder="static",
               static_url_path="/public-static")

# 연동 상태(정직): live = 지금 등록·주문이 실제로 도는 마켓, soon = 준비 중(신청·심사 단계)
MARKETS_LIVE = ("쿠팡", "네이버 스마트스토어", "Shopify", "WooCommerce")
MARKETS_SOON = ("지마켓·옥션(ESM)", "카카오 톡스토어", "11번가", "롯데온")


@bp.app_context_processor
def _inject_site_info():
    try:
        return {"site_info": site_info.info()}
    except Exception:                                    # noqa: BLE001 — 푸터가 페이지를 깨지 않게
        return {"site_info": {}}


def landing_context() -> dict:
    """랜딩(`/`)에 넣는 L1 재료 — 실측 숫자 3개 · 연동/준비 중 마켓."""
    from . import stats
    return {"l1_stats": stats.live(), "l1_live": MARKETS_LIVE, "l1_soon": MARKETS_SOON}


@bp.get("/pricing")
def pricing():
    return render_template("public/pricing.html", free_items=site_info.plan_free_items(),
                           live=MARKETS_LIVE, page="pricing")


@bp.get("/terms")
def terms():
    return render_template("public/terms.html", page="terms")


@bp.get("/privacy")
def privacy():
    return render_template("public/privacy.html", page="privacy")


@bp.get("/contact")
def contact():
    return render_template("public/contact.html", page="contact")
