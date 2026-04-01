"""수집 CLI 엔트리포인트.

Usage::

    # Amazon US에서 키워드 검색 수집
    python -m src.collectors.cli --marketplace amazon --country US \\
        --action search --keyword "wireless earbuds" --max 20

    # Amazon JP에서 키워드 검색 수집
    python -m src.collectors.cli --marketplace amazon --country JP \\
        --action search --keyword "ワイヤレスイヤホン" --max 20

    # 단일 상품 URL 수집
    python -m src.collectors.cli --action collect \\
        --url "https://www.amazon.com/dp/B09..."

    # URL 목록 파일에서 배치 수집
    python -m src.collectors.cli --action batch \\
        --file urls.txt --marketplace amazon --country US

    # 수집 현황 리포트
    python -m src.collectors.cli --action report

    # DRY_RUN (Sheets에 저장하지 않고 결과만 확인)
    python -m src.collectors.cli --action search --keyword "test" --dry-run
"""

import argparse
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def _build_collector(marketplace: str, country: str):
    """마켓플레이스/국가에 맞는 수집기를 생성한다."""
    if marketplace == 'amazon':
        from src.collectors.amazon_collector import AmazonCollector
        return AmazonCollector(country=country.upper())
    raise ValueError(f'Unsupported marketplace: {marketplace}')


def _action_search(args):
    """키워드 검색 수집."""
    collector = _build_collector(args.marketplace, args.country)
    products = collector.search_products(args.keyword, max_results=args.max)
    logger.info('Collected %d products for keyword "%s"', len(products), args.keyword)
    if args.dry_run:
        print(json.dumps(products, ensure_ascii=False, indent=2, default=str))
        return
    from src.collectors.collection_manager import CollectionManager
    mgr = CollectionManager()
    result = mgr.save_collected(products, dry_run=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _action_collect(args):
    """단일 URL 수집."""
    collector = _build_collector(args.marketplace, args.country)
    product = collector.collect_product(args.url)
    if product is None:
        logger.warning('Failed to collect product from URL: %s', args.url)
        sys.exit(1)
    if args.dry_run:
        print(json.dumps(product, ensure_ascii=False, indent=2, default=str))
        return
    from src.collectors.collection_manager import CollectionManager
    mgr = CollectionManager()
    result = mgr.save_collected([product], dry_run=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _action_batch(args):
    """URL 파일에서 배치 수집."""
    try:
        with open(args.file, encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
    except OSError as exc:
        logger.error('Cannot open file %s: %s', args.file, exc)
        sys.exit(1)
    collector = _build_collector(args.marketplace, args.country)
    products = collector.collect_batch(urls)
    logger.info('Collected %d / %d products from batch', len(products), len(urls))
    if args.dry_run:
        print(json.dumps(products, ensure_ascii=False, indent=2, default=str))
        return
    from src.collectors.collection_manager import CollectionManager
    mgr = CollectionManager()
    result = mgr.save_collected(products, dry_run=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _action_report(_args):
    """수집 현황 리포트 출력."""
    from src.collectors.collection_manager import CollectionManager
    mgr = CollectionManager()
    report = mgr.generate_report()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='proxy-commerce 상품 수집 CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--marketplace', default='amazon', help='수집 마켓플레이스 (amazon)')
    parser.add_argument('--country', default='US', help='국가 코드 (US, JP)')
    parser.add_argument(
        '--action', required=True,
        choices=['search', 'collect', 'batch', 'report'],
        help='실행할 액션',
    )
    parser.add_argument('--keyword', default='', help='검색 키워드 (search 액션)')
    parser.add_argument('--max', type=int, default=20, help='최대 수집 개수 (search 액션)')
    parser.add_argument('--url', default='', help='수집할 상품 URL (collect 액션)')
    parser.add_argument('--file', default='', help='URL 목록 파일 경로 (batch 액션)')
    parser.add_argument('--dry-run', action='store_true', help='저장 없이 결과만 출력')

    args = parser.parse_args(argv)

    if args.action == 'search':
        if not args.keyword:
            parser.error('--keyword is required for search action')
        _action_search(args)
    elif args.action == 'collect':
        if not args.url:
            parser.error('--url is required for collect action')
        _action_collect(args)
    elif args.action == 'batch':
        if not args.file:
            parser.error('--file is required for batch action')
        _action_batch(args)
    elif args.action == 'report':
        _action_report(args)


if __name__ == '__main__':
    main()
