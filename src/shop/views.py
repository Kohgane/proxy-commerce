"""src/shop/views.py — 자체몰 (코가네멀티샵) Flask Blueprint (Phase 131).

라우트:
  GET  /shop/               → 자체몰 랜딩
  GET  /shop/products       → 상품 목록 (카테고리/검색)
  GET  /shop/products/<slug> → 상품 상세
  GET  /shop/cart           → 장바구니
  POST /shop/cart/add       → 카트 추가
  POST /shop/cart/update    → 카트 수량 변경
  POST /shop/cart/remove    → 카트 상품 제거
  POST /shop/cart/clear     → 카트 비우기
  GET  /shop/checkout       → 결제 페이지
  POST /shop/checkout/create → 주문 생성 → 토스 위젯 렌더
  GET  /shop/checkout/confirm → 토스 결제 승인 콜백
  GET  /shop/orders/<order_id> → 주문 상태
  GET  /shop/health         → 자체몰 헬스체크
  GET  /cron/track-shipments → 운송장 자동 추적 cron (30분 폴링)
"""
from __future__ import annotations

import json
import logging
import os

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

logger = logging.getLogger(__name__)

# 토스페이먼츠 sandbox 클라이언트 키 (공개 테스트용, 비밀정보 아님)
_TOSS_SANDBOX_CLIENT_KEY = "test_ck_D5GePWvyJnrK0W0k6q8gLzN97Eoq"

shop_bp = Blueprint(
    "shop",
    __name__,
    url_prefix="/shop",
    template_folder="templates",
    static_folder="static",
    static_url_path="/shop/static",
)

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _get_catalog():
    from .catalog import get_catalog
    return get_catalog()


def _get_cart():
    from .cart import get_cart
    return get_cart()


def _get_checkout():
    from .checkout import CheckoutService
    return CheckoutService()


# ---------------------------------------------------------------------------
# 자체몰 랜딩
# ---------------------------------------------------------------------------

@shop_bp.get("/")
def landing():
    """자체몰 메인 랜딩."""
    try:
        catalog = _get_catalog()
        featured = catalog.list_featured(limit=8)
        categories = catalog.get_categories()
    except Exception as exc:
        logger.debug("카탈로그 로드 실패 (mock 표시): %s", exc)
        featured = []
        categories = []

    cart = _get_cart()
    return render_template(
        "shop/landing.html",
        featured=featured,
        categories=categories,
        cart_count=cart.count(),
    )


# ---------------------------------------------------------------------------
# 상품 목록
# ---------------------------------------------------------------------------

@shop_bp.get("/products")
def product_list():
    """상품 목록 (카테고리/검색 필터)."""
    category = request.args.get("category", "")
    q = request.args.get("q", "")
    page = max(1, int(request.args.get("page", 1)))
    per_page = 24

    try:
        catalog = _get_catalog()
        if q:
            items = catalog.search(q)
            total = len(items)
            products = items[(page - 1) * per_page: page * per_page]
        else:
            products, total = catalog.list_by_category(category, page=page, per_page=per_page)
        categories = catalog.get_categories()
    except Exception as exc:
        logger.debug("카탈로그 로드 실패 (mock): %s", exc)
        products, total, categories = [], 0, []

    total_pages = max(1, (total + per_page - 1) // per_page)
    cart = _get_cart()
    return render_template(
        "shop/product_list.html",
        products=products,
        categories=categories,
        current_category=category,
        q=q,
        page=page,
        total_pages=total_pages,
        total=total,
        cart_count=cart.count(),
    )


# ---------------------------------------------------------------------------
# 상품 상세
# ---------------------------------------------------------------------------

@shop_bp.get("/products/<slug>")
def product_detail(slug: str):
    """상품 상세 페이지."""
    try:
        catalog = _get_catalog()
        product = catalog.get_by_slug(slug)
        categories = catalog.get_categories()
    except Exception as exc:
        logger.debug("상품 조회 실패: %s", exc)
        product = None
        categories = []

    if not product:
        return render_template("shop/product_list.html", products=[], categories=[], current_category="", q="", page=1, total_pages=1, total=0, cart_count=0, error="상품을 찾을 수 없습니다."), 404

    # 관련 상품 (같은 카테고리)
    try:
        related, _ = _get_catalog().list_by_category(product.category, page=1, per_page=4)
        related = [p for p in related if p.slug != slug][:4]
    except Exception:
        related = []

    cart = _get_cart()
    return render_template(
        "shop/product_detail.html",
        product=product,
        related=related,
        categories=categories,
        cart_count=cart.count(),
    )


# ---------------------------------------------------------------------------
# 장바구니
# ---------------------------------------------------------------------------

@shop_bp.get("/cart")
def cart_view():
    """장바구니 페이지."""
    cart = _get_cart()
    summary = cart.summary()
    return render_template(
        "shop/cart.html",
        summary=summary,
        cart_count=summary["item_count"],
    )


@shop_bp.post("/cart/add")
def cart_add():
    """카트에 상품 추가."""
    data = request.get_json(force=True, silent=True) or request.form
    slug = str(data.get("slug", "")).strip()
    qty = max(1, int(data.get("qty", 1)))
    options_raw = data.get("options", {})
    if isinstance(options_raw, str):
        try:
            options_raw = json.loads(options_raw)
        except Exception:
            options_raw = {}

    if not slug:
        return jsonify({"ok": False, "error": "slug 필수"}), 400

    cart = _get_cart()
    cart.add(slug, qty, options_raw)
    return jsonify({"ok": True, "cart_count": cart.count()})


@shop_bp.post("/cart/update")
def cart_update():
    """카트 수량 변경."""
    data = request.get_json(force=True, silent=True) or request.form
    slug = str(data.get("slug", "")).strip()
    qty = int(data.get("qty", 0))
    options_raw = data.get("options", {})
    if isinstance(options_raw, str):
        try:
            options_raw = json.loads(options_raw)
        except Exception:
            options_raw = {}

    cart = _get_cart()
    cart.update(slug, qty, options_raw)
    return jsonify({"ok": True, "cart_count": cart.count()})


@shop_bp.post("/cart/remove")
def cart_remove():
    """카트에서 상품 제거."""
    data = request.get_json(force=True, silent=True) or request.form
    slug = str(data.get("slug", "")).strip()
    cart = _get_cart()
    cart.remove(slug)
    return jsonify({"ok": True, "cart_count": cart.count()})


@shop_bp.post("/cart/clear")
def cart_clear():
    """카트 전체 비우기."""
    _get_cart().clear()
    return jsonify({"ok": True, "cart_count": 0})


# ---------------------------------------------------------------------------
# 체크아웃
# ---------------------------------------------------------------------------

@shop_bp.get("/checkout")
def checkout_view():
    """결제 페이지."""
    cart = _get_cart()
    summary = cart.summary()
    if not summary["items"]:
        return redirect(url_for("shop.cart_view"))

    return render_template(
        "shop/checkout.html",
        summary=summary,
        cart_count=summary["item_count"],
        toss_client_key=os.getenv("TOSS_CLIENT_KEY", _TOSS_SANDBOX_CLIENT_KEY),
        sandbox=not bool(os.getenv("TOSS_CLIENT_KEY")),
    )


@shop_bp.post("/checkout/create")
def checkout_create():
    """주문 생성 → 토스 위젯 props JSON 반환."""
    cart = _get_cart()
    summary = cart.summary()
    if not summary["items"]:
        return jsonify({"ok": False, "error": "카트가 비어있습니다."}), 400

    data = request.get_json(force=True, silent=True) or request.form
    buyer_info = {
        "name": str(data.get("name", "")).strip(),
        "phone": str(data.get("phone", "")).strip(),
        "address": str(data.get("address", "")).strip(),
        "memo": str(data.get("memo", "")).strip(),
    }

    if not buyer_info["name"] or not buyer_info["phone"] or not buyer_info["address"]:
        return jsonify({"ok": False, "error": "이름/연락처/주소는 필수입니다."}), 400

    svc = _get_checkout()
    order_id = svc.create_order(summary, buyer_info)
    props = svc.request_payment(order_id)

    # 세션에 저장 (confirm 시 사용)
    session["pending_order_id"] = order_id
    session["buyer_phone"] = buyer_info["phone"]
    session.modified = True

    # 카트 비우기 (주문 생성 후)
    cart.clear()

    return jsonify({"ok": True, "order_id": order_id, "payment_props": props})


@shop_bp.get("/checkout/confirm")
def checkout_confirm():
    """토스 결제 승인 콜백."""
    payment_key = request.args.get("paymentKey", "")
    order_id = request.args.get("orderId", "")
    amount_str = request.args.get("amount", "0")

    try:
        amount = int(float(amount_str))
    except (ValueError, TypeError):
        amount = 0

    if not payment_key or not order_id:
        return render_template("shop/order_confirm.html", success=False, error="결제 정보가 올바르지 않습니다.", cart_count=0), 400

    svc = _get_checkout()
    result = svc.confirm_payment(payment_key, order_id, amount)

    if result.get("ok"):
        buyer_phone = session.get("buyer_phone", "")
        token = svc.generate_order_token(order_id, buyer_phone)
        return redirect(url_for("shop.order_status", order_id=order_id, token=token))

    return render_template(
        "shop/order_confirm.html",
        success=False,
        error=result.get("error", "결제 승인 실패"),
        order_id=order_id,
        cart_count=0,
    )


# ---------------------------------------------------------------------------
# 주문 상태 조회
# ---------------------------------------------------------------------------

@shop_bp.get("/orders/<order_id>")
def order_status(order_id: str):
    """주문 상태 페이지 (비로그인 token 방식)."""
    token = request.args.get("token", "")

    svc = _get_checkout()
    order = svc.get_order_for_display(order_id, token=token or None)

    if not order:
        return render_template(
            "shop/order_status.html",
            order=None,
            error="주문을 찾을 수 없습니다.",
            cart_count=0,
        ), 404

    # 운송장 추적 정보
    tracking_info = None
    tracking_no = order.get("tracking_no", "")
    courier = order.get("courier", "")
    if tracking_no and courier:
        try:
            from src.seller_console.orders.tracking_sweet import SweetTrackerClient
            client = SweetTrackerClient()
            tracking_info = client.track(courier, tracking_no)
        except Exception as exc:
            logger.debug("운송장 추적 실패: %s", exc)

    try:
        items = json.loads(order.get("items_json", "[]"))
    except Exception:
        items = []

    return render_template(
        "shop/order_status.html",
        order=order,
        items=items,
        tracking_info=tracking_info,
        order_token=token,
        cart_count=0,
        error=None,
    )


# ---------------------------------------------------------------------------
# 자체몰 헬스체크
# ---------------------------------------------------------------------------

@shop_bp.get("/health")
def shop_health():
    """자체몰 헬스체크."""
    try:
        catalog = _get_catalog()
        products = catalog.list_all()
        featured = [p for p in products if p.featured]
        catalog_detail = f"진열 상품 {len(products)}개 (featured {len(featured)}개)"
        catalog_status = "ok"
    except Exception as exc:
        logger.warning("shop_health: catalog 로드 실패: %s", exc)
        catalog_detail = "카탈로그 로드 실패"
        catalog_status = "fail"

    sandbox = not bool(os.getenv("TOSS_CLIENT_KEY"))
    payments_detail = f"토스페이먼츠 활성 ({'sandbox' if sandbox else 'live'})"

    return jsonify({
        "status": "ok",
        "shop": "kohganemultishop",
        "checks": [
            {"name": "shop_catalog", "status": catalog_status, "detail": catalog_detail},
            {
                "name": "shop_payments",
                "status": "ok",
                "detail": payments_detail,
                "provider": "toss",
                "mode": "sandbox" if sandbox else "live",
            },
        ],
    })
