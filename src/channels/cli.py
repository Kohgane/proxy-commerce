"""
src/channels/cli.py
판매 채널 내보내기 CLI 엔트리포인트.

사용 예:
    # 퍼센티용 CSV (전체)
    python -m src.channels.cli --channel percenty --output data/exports/

    # 쿠팡 전용 CSV
    python -m src.channels.cli --channel percenty --market coupang --output data/exports/

    # Shopify 동기화
    python -m src.channels.cli --channel shopify --sync

    # DRY_RUN
    python -m src.channels.cli --channel percenty --output data/exports/ --dry-run
"""

import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='판매 채널 내보내기 CLI',
    )
    parser.add_argument(
        '--channel',
        required=True,
        choices=['percenty', 'shopify', 'woocommerce', 'shopify_markets'],
        help='대상 채널 이름',
    )
    parser.add_argument(
        '--market',
        default=None,
        choices=['coupang', 'smartstore', '11st', 'all'],
        help='퍼센티 전용: 대상 마켓 (기본: all)',
    )
    parser.add_argument(
        '--output',
        default='data/exports/',
        help='출력 디렉토리 (기본: data/exports/)',
    )
    parser.add_argument(
        '--sync',
        action='store_true',
        help='Shopify/WooCommerce: API 직접 동기화',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='파일 생성만 수행하고 업로드/API 호출 안 함',
    )
    parser.add_argument(
        '--sheet-id',
        default=None,
        help='Google Sheets ID (기본: GOOGLE_SHEET_ID 환경변수)',
    )
    return parser.parse_args(argv)


def _load_catalog(sheet_id: str, worksheet: str = 'catalog') -> list:
    """Google Sheets에서 카탈로그를 읽어 dict 리스트로 반환한다."""
    from src.utils.sheets import open_sheet

    ws = open_sheet(sheet_id, worksheet)
    rows = ws.get_all_records()
    logger.info('카탈로그 로드 완료: %d개', len(rows))
    return rows


def _build_sell_price(row: dict) -> float:
    """카탈로그 행에서 KRW 판매가를 계산한다 (calc_landed_cost 사용)."""
    from src.price import calc_landed_cost, _build_fx_rates

    fx_rates = _build_fx_rates()
    margin_pct = float(os.getenv('TARGET_MARGIN_PCT', '22'))

    try:
        price = calc_landed_cost(
            buy_price=float(row.get('buy_price', 0)),
            buy_currency=row.get('buy_currency', 'KRW'),
            margin_pct=margin_pct,
            fx_rates=fx_rates,
        )
        return float(price)
    except Exception as exc:
        logger.warning('가격 계산 실패 SKU=%s: %s', row.get('sku', '?'), exc)
        return 0.0


def _run_percenty(args, catalog: list, dry_run: bool):
    """퍼센티 CSV 생성 실행."""
    from .percenty import PercentyExporter

    exporter = PercentyExporter()
    os.makedirs(args.output, exist_ok=True)

    # 상품 변환
    products = []
    for row in catalog:
        if row.get('status', 'active') != 'active':
            continue
        sell_price = _build_sell_price(row)
        products.append(exporter.prepare_product(row, sell_price))

    if not products:
        logger.warning('내보낼 활성 상품이 없습니다.')
        return

    market = args.market or 'all'

    if dry_run:
        logger.info('[DRY-RUN] 채널=percenty, 마켓=%s, 상품수=%d (파일 미저장)', market, len(products))
        print(f'\n[DRY-RUN] percenty / market={market}')
        print(f'  변환된 상품 수: {len(products)}')
        if products:
            sample = products[0]
            print(f'  샘플: {sample.get("상품명")} / {sample.get("판매가")}원 / {sample.get("카테고리")}')
        return

    if market == 'all':
        for mkt in exporter.supported_markets:
            out = os.path.join(args.output, f'percenty_{mkt}.csv')
            path = exporter.export_for_market(products, mkt, out)
            print(f'  [{mkt}] → {path}')
    else:
        out = os.path.join(args.output, f'percenty_{market}.csv')
        path = exporter.export_for_market(products, market, out)
        print(f'  [{market}] → {path}')


def _run_shopify(args, catalog: list, dry_run: bool):
    """Shopify 동기화 실행."""
    from .shopify_global import ShopifyGlobalChannel
    from src.price import calc_price, _build_fx_rates

    channel = ShopifyGlobalChannel()
    fx_rates = _build_fx_rates()
    margin_pct = float(os.getenv('TARGET_MARGIN_PCT', '22'))

    products = []
    for row in catalog:
        if row.get('status', 'active') != 'active':
            continue
        try:
            usd_price = calc_price(
                buy_price=float(row.get('buy_price', 0)),
                buy_currency=row.get('buy_currency', 'USD'),
                fx_usdkrw=float(fx_rates['USDKRW']),
                margin_pct=margin_pct,
                target_currency='USD',
                fx_rates=fx_rates,
            )
        except Exception as exc:
            logger.warning('USD 가격 계산 실패: %s', exc)
            usd_price = 0.0

        products.append(channel.prepare_product(row, float(usd_price)))

    if dry_run:
        logger.info('[DRY-RUN] 채널=shopify, 상품수=%d (API 미호출)', len(products))
        print('\n[DRY-RUN] shopify')
        print(f'  변환된 상품 수: {len(products)}')
        return

    if args.sync:
        channel.export_batch(products, '')
    else:
        logger.info('--sync 플래그 없음: Shopify API 호출 생략')


def _run_woocommerce(args, catalog: list, dry_run: bool):
    """WooCommerce 동기화 실행."""
    from .woo_domestic import WooDomesticChannel

    channel = WooDomesticChannel()

    products = []
    for row in catalog:
        if row.get('status', 'active') != 'active':
            continue
        sell_price = _build_sell_price(row)
        products.append(channel.prepare_product(row, sell_price))

    if dry_run:
        logger.info('[DRY-RUN] 채널=woocommerce, 상품수=%d (API 미호출)', len(products))
        print('\n[DRY-RUN] woocommerce')
        print(f'  변환된 상품 수: {len(products)}')
        return

    if args.sync:
        channel.export_batch(products, '')
    else:
        logger.info('--sync 플래그 없음: WooCommerce API 호출 생략')


def _run_shopify_markets(args, catalog: list, dry_run: bool):
    """Shopify Markets 다통화 동기화 실행."""
    from .shopify_markets import ShopifyMarketsChannel
    from src.price import calc_price, _build_fx_rates

    channel = ShopifyMarketsChannel()
    fx_rates = _build_fx_rates()
    margin_pct = float(os.getenv('TARGET_MARGIN_PCT', '22'))

    products = []
    for row in catalog:
        if row.get('status', 'active') != 'active':
            continue
        try:
            usd_price = calc_price(
                buy_price=float(row.get('buy_price', 0)),
                buy_currency=row.get('buy_currency', 'USD'),
                fx_usdkrw=float(fx_rates['USDKRW']),
                margin_pct=margin_pct,
                target_currency='USD',
                fx_rates=fx_rates,
            )
        except Exception as exc:
            logger.warning('USD 가격 계산 실패: %s', exc)
            usd_price = 0.0

        products.append(channel.prepare_product(row, float(usd_price)))

    if dry_run:
        logger.info('[DRY-RUN] 채널=shopify_markets, 상품수=%d (API 미호출)', len(products))
        print('\n[DRY-RUN] shopify_markets')
        print(f'  변환된 상품 수: {len(products)}')
        if products:
            cp = products[0].get('country_prices', {})
            print(f'  샘플 국가별 가격: {list(cp.keys())}')
        return

    if args.sync:
        channel.export_batch(products, '')
    else:
        logger.info('--sync 플래그 없음: Shopify Markets API 호출 생략')


def main(argv=None):
    args = _parse_args(argv)
    dry_run = args.dry_run

    # Google Sheets ID 결정
    sheet_id = args.sheet_id or os.getenv('GOOGLE_SHEET_ID')

    if not sheet_id:
        logger.error(
            'Google Sheets ID가 필요합니다. '
            '--sheet-id 옵션 또는 GOOGLE_SHEET_ID 환경변수를 설정하세요.'
        )
        sys.exit(1)

    catalog = _load_catalog(sheet_id)
    active = [r for r in catalog if r.get('status', 'active') == 'active']
    logger.info('활성 상품: %d개 / 전체: %d개', len(active), len(catalog))

    if args.channel == 'percenty':
        _run_percenty(args, active, dry_run)
    elif args.channel == 'shopify':
        _run_shopify(args, active, dry_run)
    elif args.channel == 'woocommerce':
        _run_woocommerce(args, active, dry_run)
    elif args.channel == 'shopify_markets':
        _run_shopify_markets(args, active, dry_run)

    logger.info('내보내기 완료')


if __name__ == '__main__':
    main()
