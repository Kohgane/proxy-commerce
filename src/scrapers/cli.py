"""
src/scrapers/cli.py
Listly 크롤링 데이터를 Google Sheets 카탈로그에 적재하는 CLI 엔트리포인트.

사용 예:
    python -m src.scrapers.cli --vendor porter --file data/porter_raw.csv
    python -m src.scrapers.cli --vendor memo_paris --file data/memo_raw.csv --dry-run
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
        description='Listly 크롤링 데이터를 Google Sheets 카탈로그에 적재',
    )
    parser.add_argument(
        '--vendor',
        required=True,
        choices=['porter', 'memo_paris'],
        help='벤더 이름 (porter / memo_paris)',
    )
    parser.add_argument(
        '--file',
        required=True,
        help='Listly 내보내기 파일 경로 (CSV 또는 JSON)',
    )
    parser.add_argument(
        '--sheet-id',
        default=None,
        help='Google Sheets 파일 ID (기본: GOOGLE_SHEET_ID 환경변수)',
    )
    parser.add_argument(
        '--worksheet',
        default='catalog',
        help='워크시트 이름 (기본: catalog)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='DRY_RUN 모드: 시트에 실제 쓰지 않고 결과만 출력',
    )
    return parser.parse_args(argv)


def _dry_run(file_path: str, vendor_name: str) -> dict:
    """DRY_RUN 모드: 파일 로드 및 정규화만 수행하고 결과 미리 보기."""
    from .listly_client import ListlyLoader
    from .sheet_importer import get_vendor_normalizer

    loader = ListlyLoader()
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.json':
        raw_rows = loader.load_json(file_path)
    else:
        raw_rows = loader.load_csv(file_path)
    raw_rows = loader.clean_raw_data(raw_rows)

    normalizer = get_vendor_normalizer(vendor_name)
    normalized = []
    errors = []
    for i, row in enumerate(raw_rows):
        try:
            normalized.append(normalizer(row))
        except Exception as e:
            errors.append(f'행 {i} 정규화 오류: {e}')

    print(f'\n[DRY-RUN] 벤더: {vendor_name}  파일: {file_path}')
    print(f'  로드된 행: {len(raw_rows)}')
    print(f'  정규화 성공: {len(normalized)}')
    print(f'  오류: {len(errors)}')
    if normalized:
        print('\n  샘플 (최대 3행):')
        for row in normalized[:3]:
            print(f'    SKU={row.get("sku")} | 통화={row.get("buy_currency")} '
                  f'| 가격={row.get("buy_price")} | 벤더={row.get("vendor")}')
    if errors:
        print('\n  오류 목록:')
        for err in errors:
            print(f'    - {err}')
    print()
    return {'added': 0, 'updated': 0, 'skipped': len(errors), 'errors': errors}


def main(argv=None):
    args = _parse_args(argv)

    # Google Sheets ID 결정
    sheet_id = args.sheet_id or os.getenv('GOOGLE_SHEET_ID')

    if args.dry_run:
        result = _dry_run(args.file, args.vendor)
        sys.exit(0)

    if not sheet_id:
        logger.error(
            'Google Sheets ID가 필요합니다. --sheet-id 옵션 또는 '
            'GOOGLE_SHEET_ID 환경변수를 설정하세요.'
        )
        sys.exit(1)

    from .sheet_importer import SheetImporter

    logger.info('적재 시작: 벤더=%s, 파일=%s, 시트=%s', args.vendor, args.file, sheet_id)
    importer = SheetImporter(sheet_id=sheet_id, worksheet_name=args.worksheet)
    result = importer.import_from_file(file_path=args.file, vendor_name=args.vendor)

    print('\n──────────────────────────────')
    print(f'  적재 완료 [{args.vendor}]')
    print(f'  추가(added):   {result["added"]}')
    print(f'  업데이트:      {result["updated"]}')
    print(f'  스킵(skipped): {result["skipped"]}')
    print(f'  오류(errors):  {len(result["errors"])}')
    if result['errors']:
        print('  오류 목록:')
        for err in result['errors']:
            print(f'    - {err}')
    print('──────────────────────────────\n')

    sys.exit(0 if not result['errors'] else 1)


if __name__ == '__main__':
    main()
