"""구매대행 통합 API — 수집/편집/업로드/마진계산 엔드포인트.

Blueprint: proxy_bp (/api/proxy/*)
"""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

proxy_bp = Blueprint('proxy', __name__, url_prefix='/api/proxy')


def _get_calculator():
    from src.proxy_calc.margin_calc import ProxyMarginCalculator
    return ProxyMarginCalculator()


def _get_editor():
    from src.editor.editor import ProductEditor
    return ProductEditor()


@proxy_bp.route('/calc/margin', methods=['POST'])
def calc_margin():
    """마진 계산."""
    data = request.get_json(silent=True) or {}
    buy_price = data.get('buy_price')
    currency = data.get('currency', 'USD')
    if buy_price is None:
        return jsonify({'error': 'buy_price 필수'}), 400
    try:
        buy_price = float(buy_price)
    except (ValueError, TypeError):
        return jsonify({'error': 'buy_price는 숫자여야 합니다'}), 400

    calc = _get_calculator()
    result = calc.calculate(
        buy_price=buy_price,
        currency=currency,
        source_country=data.get('source_country', 'US'),
        target_market=data.get('target_market', 'coupang'),
        category=data.get('category', 'default'),
        margin_pct=float(data.get('margin_pct', 25)),
        shipping_method=data.get('shipping_method', 'standard'),
        extra_cost_krw=float(data.get('extra_cost_krw', 0)),
    )
    return jsonify(result)


@proxy_bp.route('/calc/compare', methods=['POST'])
def calc_compare():
    """마켓별 판매가 비교."""
    data = request.get_json(silent=True) or {}
    buy_price = data.get('buy_price')
    currency = data.get('currency', 'USD')
    if buy_price is None:
        return jsonify({'error': 'buy_price 필수'}), 400
    try:
        buy_price = float(buy_price)
    except (ValueError, TypeError):
        return jsonify({'error': 'buy_price는 숫자여야 합니다'}), 400

    calc = _get_calculator()
    result = calc.compare_markets(
        buy_price=buy_price,
        currency=currency,
        source_country=data.get('source_country', 'US'),
        margin_pct=float(data.get('margin_pct', 25)),
        markets=data.get('markets'),
    )
    return jsonify({'markets': result})


@proxy_bp.route('/calc/reverse', methods=['POST'])
def calc_reverse():
    """목표 판매가에서 역산."""
    data = request.get_json(silent=True) or {}
    target_sell_price = data.get('target_sell_price')
    currency = data.get('currency', 'USD')
    if target_sell_price is None:
        return jsonify({'error': 'target_sell_price 필수'}), 400
    try:
        target_sell_price = float(target_sell_price)
    except (ValueError, TypeError):
        return jsonify({'error': 'target_sell_price는 숫자여야 합니다'}), 400

    calc = _get_calculator()
    result = calc.reverse_calculate(
        target_sell_price=target_sell_price,
        currency=currency,
        source_country=data.get('source_country', 'US'),
        target_market=data.get('target_market', 'coupang'),
        category=data.get('category', 'default'),
        shipping_method=data.get('shipping_method', 'standard'),
        extra_cost_krw=float(data.get('extra_cost_krw', 0)),
    )
    return jsonify(result)


@proxy_bp.route('/calc/batch', methods=['POST'])
def calc_batch():
    """일괄 마진 계산."""
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'error': 'items 필수'}), 400

    calc = _get_calculator()
    results = calc.batch_calculate(items)
    return jsonify({'results': results})


@proxy_bp.route('/editor/generate', methods=['POST'])
def editor_generate():
    """상세페이지 HTML 생성."""
    data = request.get_json(silent=True) or {}
    title = data.get('title', '')
    if not title:
        return jsonify({'error': 'title 필수'}), 400

    editor = _get_editor()
    product = {
        'title_ko': title,
        'brand': data.get('brand', ''),
        'origin_country': data.get('origin', ''),
        'images': data.get('images', []),
        'features': data.get('features', []),
        'description_ko': data.get('description', ''),
    }
    html = editor.generate_detail_page(product)
    return jsonify({'html': html})


@proxy_bp.route('/editor/update', methods=['POST'])
def editor_update():
    """상세페이지 HTML 필드 수정 — 업데이트 필드로 상세페이지 재생성."""
    data = request.get_json(silent=True) or {}
    html = data.get('html', '')
    updates = data.get('updates', {})
    if not html:
        return jsonify({'error': 'html 필수'}), 400

    editor = _get_editor()
    base_product = {'title_ko': '', 'brand': '', 'description_ko': '', 'images': []}
    updated = editor.edit_fields(base_product, updates)
    new_html = editor.generate_detail_page(updated)
    return jsonify({'html': new_html})


@proxy_bp.route('/collect', methods=['POST'])
def collect_product():
    """단일 상품 수집."""
    data = request.get_json(silent=True) or {}
    url = data.get('url', '')
    platform = data.get('platform', '')
    if not url:
        return jsonify({'error': 'url 필수'}), 400

    try:
        from src.collectors.dispatcher import collect as dispatcher_collect
        scraped = dispatcher_collect(url)
        if scraped and scraped.title:
            product = {
                'source_url': scraped.source_url,
                'title': scraped.title,
                'description': scraped.description,
                'price': getattr(scraped, 'price', None),
                'currency': getattr(scraped, 'currency', None),
                'images': getattr(scraped, 'images', []),
                'domain': scraped.domain,
            }
            return jsonify({'ok': True, 'product': product})
        return jsonify({'ok': False, 'error': '상품 수집 실패'}), 502
    except Exception as exc:
        logger.warning('collect_product failed: %s', exc)
        return jsonify({'ok': False, 'error': str(exc)}), 500


@proxy_bp.route('/collect/batch', methods=['POST'])
def collect_batch():
    """일괄 상품 수집."""
    data = request.get_json(silent=True) or {}
    urls = data.get('urls', [])
    platform = data.get('platform', '')
    if not urls:
        return jsonify({'error': 'urls 필수'}), 400

    results = []
    from src.collectors.dispatcher import collect as dispatcher_collect
    for url in urls[:100]:
        try:
            scraped = dispatcher_collect(url)
            ok = bool(scraped and scraped.title)
            product = None
            if ok:
                product = {
                    'source_url': scraped.source_url,
                    'title': scraped.title,
                    'description': scraped.description,
                    'images': getattr(scraped, 'images', []),
                    'domain': scraped.domain,
                }
            results.append({'url': url, 'ok': ok, 'product': product})
        except Exception as exc:
            results.append({'url': url, 'ok': False, 'error': str(exc)})

    success = sum(1 for r in results if r.get('ok'))
    return jsonify({'total': len(results), 'success': success, 'results': results})


@proxy_bp.route('/upload', methods=['POST'])
def upload_product():
    """단일 상품 마켓 업로드."""
    data = request.get_json(silent=True) or {}
    market = data.get('market', '')
    product = data.get('product', {})
    if not market or not product:
        return jsonify({'error': 'market, product 필수'}), 400

    try:
        from src.uploaders.upload_manager import UploadManager
        mgr = UploadManager()
        uploader = mgr._get_uploader(market)
        prepared = uploader.prepare_product(product)
        result = uploader.upload_product(prepared)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.warning('upload_product failed: %s', exc)
        return jsonify({'success': False, 'error': str(exc)}), 500
