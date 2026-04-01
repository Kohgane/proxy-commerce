"""CLI 엔트리포인트 — 상품 상세페이지 편집기.

Usage::

    # 상품 편집 모드
    python -m src.editor.cli --action edit --sku PTR-TNK-001

    # 미리보기 (럭셔리 템플릿)
    python -m src.editor.cli --action preview --sku PTR-TNK-001 --template luxury

    # 마켓별 내보내기
    python -m src.editor.cli --action export --sku PTR-TNK-001 --market coupang

    # 전체 상품 일괄 내보내기
    python -m src.editor.cli --action batch-export --market smartstore

    # 사용 가능한 템플릿 목록
    python -m src.editor.cli --action list-templates
"""

import argparse
import json
import logging

PREVIEW_TRUNCATE_LENGTH = 500

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def _action_list_templates(args):
    """사용 가능한 템플릿 목록 출력."""
    from src.editor.template_engine import TemplateEngine
    engine = TemplateEngine()
    templates = engine.list_templates()
    print('사용 가능한 템플릿:')
    for t in templates:
        print(f'  - {t}')


def _action_edit(args):
    """상품 편집 모드."""
    from src.editor.editor import ProductEditor
    editor = ProductEditor()
    product = editor.load_product(args.sku)
    print(json.dumps(product, ensure_ascii=False, indent=2))


def _action_preview(args):
    """상품 미리보기 HTML 생성."""
    from src.editor.editor import ProductEditor
    editor = ProductEditor()
    product = editor.load_product(args.sku)
    template = args.template or 'default'
    html = editor.generate_detail_page(product, template=template)
    standalone = editor.preview(html)

    output_file = f'{args.sku}_{template}_preview.html'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(standalone)
    logger.info('미리보기 파일 생성: %s', output_file)
    print(standalone[:PREVIEW_TRUNCATE_LENGTH] + '...' if len(standalone) > PREVIEW_TRUNCATE_LENGTH else standalone)


def _action_export(args):
    """마켓별 내보내기."""
    from src.editor.editor import ProductEditor
    editor = ProductEditor()
    product = editor.load_product(args.sku)
    result = editor.export_for_market(product, args.market)

    output_file = f'{args.sku}_{args.market}_export.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info('내보내기 파일 생성: %s', output_file)

    validation = result['validation']
    if validation['passed']:
        logger.info('유효성 검사 통과')
    else:
        logger.warning('유효성 검사 경고: %s', validation['warnings'])


def _action_batch_export(args):
    """전체 상품 일괄 내보내기."""
    from src.editor.editor import ProductEditor
    from src.collectors.collection_manager import CollectionManager

    editor = ProductEditor()
    try:
        manager = CollectionManager()
        products = manager.list_products()
    except Exception as exc:
        logger.warning('CollectionManager 로드 실패: %s', exc)
        products = []

    if not products:
        logger.warning('내보낼 상품이 없습니다.')
        return

    results = []
    for product in products:
        try:
            result = editor.export_for_market(product, args.market)
            results.append(result)
        except Exception as exc:
            logger.error('상품 내보내기 실패 (sku=%s): %s', product.get('sku'), exc)

    output_file = f'batch_export_{args.market}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info('일괄 내보내기 완료: %d개 → %s', len(results), output_file)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='상품 상세페이지 편집기 CLI',
        prog='python -m src.editor.cli',
    )
    parser.add_argument(
        '--action',
        required=True,
        choices=['edit', 'preview', 'export', 'batch-export', 'list-templates'],
        help='실행할 액션',
    )
    parser.add_argument('--sku', help='상품 SKU (예: PTR-TNK-001)')
    parser.add_argument('--template', help='템플릿명 (default/luxury/cosmetic/electronics)')
    parser.add_argument(
        '--market',
        choices=['coupang', 'smartstore', 'shopify'],
        help='마켓명',
    )
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    action_map = {
        'list-templates': _action_list_templates,
        'edit': _action_edit,
        'preview': _action_preview,
        'export': _action_export,
        'batch-export': _action_batch_export,
    }

    handler = action_map[args.action]

    # sku가 필요한 액션 검증
    if args.action in ('edit', 'preview', 'export') and not args.sku:
        parser.error(f'--action {args.action}에는 --sku가 필요합니다.')

    if args.action in ('export', 'batch-export') and not args.market:
        parser.error(f'--action {args.action}에는 --market이 필요합니다.')

    handler(args)


if __name__ == '__main__':
    main()
