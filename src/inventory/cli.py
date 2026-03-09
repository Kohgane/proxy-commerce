"""재고 관리 CLI — 재고 확인 / 동기화 / 알림

사용법:
  python -m src.inventory.cli --action full-sync [--dry-run]
  python -m src.inventory.cli --action check --sku PTR-TNK-001
  python -m src.inventory.cli --action check-all [--vendor porter]
  python -m src.inventory.cli --action report
"""

import argparse
import json
import logging
import sys

from .inventory_sync import InventorySync
from .stock_checker import StockChecker

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def cmd_full_sync(args):
    syncer = InventorySync()
    result = syncer.full_sync(dry_run=args.dry_run, vendor_filter=args.vendor or None)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if result.get('errors'):
        sys.exit(1)


def cmd_check(args):
    if not args.sku:
        print("--sku is required for action 'check'", file=sys.stderr)
        sys.exit(1)
    syncer = InventorySync()
    result = syncer.sync_single(args.sku, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_check_all(args):
    from ..utils.sheets import open_sheet
    import os

    sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
    worksheet = os.getenv('WORKSHEET', 'catalog')
    ws = open_sheet(sheet_id, worksheet)
    rows = ws.get_all_records()
    active = [
        r for r in rows
        if str(r.get('status', '')).strip().lower() == 'active' and r.get('src_url')
    ]
    if args.vendor:
        active = [r for r in active if str(r.get('vendor', '')).lower() == args.vendor.lower()]

    checker = StockChecker()
    inputs = [{'sku': r['sku'], 'src_url': r['src_url'], 'vendor': r.get('vendor', '')} for r in active]
    results = checker.check_batch(inputs)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


def cmd_report(args):
    syncer = InventorySync()
    report = syncer.get_sync_report()
    if not report:
        print('No sync report available. Run full-sync first.')
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description='재고 관리 CLI')
    parser.add_argument('--action', required=True,
                        choices=['full-sync', 'check', 'check-all', 'report'],
                        help='실행할 액션')
    parser.add_argument('--sku', help='특정 SKU (action=check 시 필수)')
    parser.add_argument('--vendor', help='벤더 필터 (porter, memo_paris)')
    parser.add_argument('--dry-run', action='store_true', help='실제 업데이트 없이 변경사항만 확인')
    args = parser.parse_args()

    dispatch = {
        'full-sync': cmd_full_sync,
        'check': cmd_check,
        'check-all': cmd_check_all,
        'report': cmd_report,
    }
    dispatch[args.action](args)


if __name__ == '__main__':
    main()
