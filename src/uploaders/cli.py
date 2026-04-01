"""업로드 CLI 엔트리포인트.

Usage::

    # 특정 SKU를 Coupang에 업로드
    python -m src.uploaders.cli --market coupang --skus AMZ-US-ELC-001,TAO-BTY-001

    # 특정 SKU를 Naver SmartStore에 업로드
    python -m src.uploaders.cli --market naver --skus AMZ-JP-BTY-001

    # 미업로드 상품 일괄 업로드
    python -m src.uploaders.cli --market coupang --action upload-pending

    # 가격 일괄 동기화
    python -m src.uploaders.cli --market coupang --action sync-prices

    # 업로드 현황 리포트 출력
    python -m src.uploaders.cli --action report

    # dry-run 모드 (실제 업로드 없이 결과만 확인)
    python -m src.uploaders.cli --market coupang --action upload-pending --dry-run
"""

import argparse
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def _action_upload(args):
    """특정 SKU 목록을 업로드한다."""
    if not args.market:
        logger.error('--market is required for upload action')
        sys.exit(1)
    if not args.skus:
        logger.error('--skus is required for upload action')
        sys.exit(1)
    skus = [s.strip() for s in args.skus.split(',') if s.strip()]
    if not skus:
        logger.error('No valid SKUs provided in --skus')
        sys.exit(1)
    from src.uploaders.upload_manager import UploadManager
    mgr = UploadManager()
    result = mgr.upload_to_market(skus, args.market, dry_run=args.dry_run)
    logger.info(
        'Upload complete: total=%d success=%d failed=%d',
        result['total'], result['success'], result['failed'],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def _action_upload_pending(args):
    """미업로드 상품을 일괄 업로드한다."""
    if not args.market:
        logger.error('--market is required for upload-pending action')
        sys.exit(1)
    from src.uploaders.upload_manager import UploadManager
    mgr = UploadManager()
    result = mgr.upload_all_pending(args.market, dry_run=args.dry_run)
    logger.info(
        'Upload pending complete: total=%d success=%d failed=%d',
        result['total'], result['success'], result['failed'],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def _action_sync_prices(args):
    """업로드된 상품의 가격을 동기화한다."""
    if not args.market:
        logger.error('--market is required for sync-prices action')
        sys.exit(1)
    from src.uploaders.upload_manager import UploadManager
    mgr = UploadManager()
    result = mgr.sync_prices(args.market, dry_run=args.dry_run)
    logger.info(
        'Sync prices complete: total=%d success=%d failed=%d',
        result['total'], result['success'], result['failed'],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def _action_report(_args):
    """업로드 현황 리포트를 출력한다."""
    from src.uploaders.upload_manager import UploadManager
    mgr = UploadManager()
    report = mgr.generate_report()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='proxy-commerce 상품 업로드 CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--market', default='', help='대상 마켓플레이스 (coupang, naver)')
    parser.add_argument(
        '--action', default='upload',
        choices=['upload', 'upload-pending', 'sync-prices', 'report'],
        help='실행할 액션 (기본: upload)',
    )
    parser.add_argument('--skus', default='', help='업로드할 SKU 목록, 쉼표 구분 (upload 액션)')
    parser.add_argument('--dry-run', action='store_true', help='실제 업로드 없이 결과만 출력')

    args = parser.parse_args(argv)

    if args.action == 'upload':
        _action_upload(args)
    elif args.action == 'upload-pending':
        _action_upload_pending(args)
    elif args.action == 'sync-prices':
        _action_sync_prices(args)
    elif args.action == 'report':
        _action_report(args)


if __name__ == '__main__':
    main()
