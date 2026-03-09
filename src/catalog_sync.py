import os, time
from decimal import Decimal
from .utils.sheets import open_sheet
from .translate import ko_to_en_if_needed, ja_to_ko, fr_to_ko
from .image_uploader import ensure_images
from .price import calc_price, _build_fx_rates
from .vendors.shopify_client import upsert_product as shopify_upsert
from .vendors.woocommerce_client import upsert_product as woo_upsert

PRIMARY_LOCALE = os.getenv('PRIMARY_LOCALE', 'ko')
SECONDARY_LOCALE = os.getenv('SECONDARY_LOCALE', 'en')
MARGIN = Decimal(os.getenv('TARGET_MARGIN_PCT', '22'))
FX_USDKRW = Decimal(os.getenv('FX_USDKRW', '1350'))
FX_JPYKRW = Decimal(os.getenv('FX_JPYKRW', '9.0'))
FX_EURKRW = Decimal(os.getenv('FX_EURKRW', '1470'))
SHIPPING_FEE_DEFAULT = Decimal(os.getenv('SHIPPING_FEE_DEFAULT', '12000'))

FX_RATES = _build_fx_rates(fx_usdkrw=FX_USDKRW, fx_jpykrw=FX_JPYKRW, fx_eurkrw=FX_EURKRW, use_live=True)

SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
WORKSHEET = os.getenv('WORKSHEET', 'catalog')


def row_to_product(row):
    sku = str(row['sku']).strip()
    title_ko = str(row['title_ko']).strip()
    title_ja = str(row.get('title_ja', '') or '').strip()
    title_fr = str(row.get('title_fr', '') or '').strip()
    source_country = str(row['source_country']).strip()

    # source_country에 따른 title_ko 자동 번역
    if not title_ko:
        if source_country == 'JP' and title_ja:
            title_ko = ja_to_ko(title_ja)
        elif source_country == 'FR' and title_fr:
            title_ko = fr_to_ko(title_fr)

    title_en = (str(row.get('title_en', '')).strip()) or ko_to_en_if_needed(title_ko)
    src_url = str(row['src_url']).strip()
    buy_currency = str(row['buy_currency']).strip()
    buy_price = Decimal(str(row['buy_price']).replace(',', ''))
    stock = int(row.get('stock', 0) or 0)
    tags = str(row.get('tags', '') or '')
    vendor = str(row.get('vendor', '') or '')

    image_urls = ensure_images(row)

    price_krw = calc_price(buy_price, buy_currency, FX_USDKRW, MARGIN, 'KRW', fx_rates=FX_RATES)
    price_usd = calc_price(buy_price, buy_currency, FX_USDKRW, MARGIN, 'USD', fx_rates=FX_RATES)

    body_html = f"""<p>원산지/소스: {source_country} | 원판매처: <a href='{src_url}' target='_blank'>링크</a></p>
<p>[배송/관세 안내] 국가에 따라 관세/부가세가 부과될 수 있습니다. 통관 지연 시 배송일이 추가될 수 있습니다.</p>
""".strip()

    shopify_prod = {
        'title': title_en if SECONDARY_LOCALE == 'en' else title_ko,
        'body_html': body_html,
        'tags': tags,
        'vendor': vendor,
        'images': [{'src': u} for u in image_urls],
        'variants': [{
            'sku': sku,
            'price': str(price_usd),
            'inventory_quantity': stock
        }]
    }

    woo_prod = {
        'name': title_ko,
        'type': 'simple',
        'regular_price': str(price_krw),
        'sku': sku,
        'manage_stock': True,
        'stock_quantity': stock,
        'images': [{'src': u} for u in image_urls],
        'description': body_html,
        'tags': [{'name': t.strip()} for t in tags.split(',') if t.strip()]
    }

    return shopify_prod, woo_prod


def sync_once():
    ws = open_sheet(SHEET_ID, WORKSHEET)
    rows = ws.get_all_records()
    active_rows = [r for r in rows if (str(r.get('status','')).strip().lower() == 'active')]
    for row in active_rows:
        s_prod, w_prod = row_to_product(row)
        # Shopify
        try:
            if os.getenv('SHOPIFY_ACCESS_TOKEN') and os.getenv('SHOPIFY_SHOP'):
                shopify_upsert(s_prod)
        except Exception as e:
            print('[Shopify upsert error]', e)
        # WooCommerce
        try:
            if os.getenv('WOO_CK') and os.getenv('WOO_CS') and os.getenv('WOO_BASE_URL'):
                woo_upsert(w_prod)
        except Exception as e:
            print('[Woo upsert error]', e)
        time.sleep(0.5)


def main():
    sync_once()

if __name__ == '__main__':
    main()
