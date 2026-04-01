"""마진 계산기 CLI 엔트리포인트.

Usage::

    # 단일 상품 마진 계산
    python -m src.margin.cli calculate \\
        --price 29.99 --currency USD --sale-price 55000 \\
        --marketplace amazon_us --platform coupang

    # 목표 마진율로 역계산
    python -m src.margin.cli calculate \\
        --price 29.99 --currency USD --target-margin 20 \\
        --marketplace amazon_us --platform coupang

    # 리포트 생성 (JSON 파일 기반)
    python -m src.margin.cli report --input products.json --output report.json
"""

import argparse
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def _build_calculator(use_live_fx: bool = False):
    """마진 계산기 생성.

    Args:
        use_live_fx: 실시간 환율 사용 여부

    Returns:
        MarginCalculator 인스턴스
    """
    from .calculator import MarginCalculator
    fx_service = None
    if use_live_fx:
        try:
            from ..fx.realtime_rates import RealtimeRates
            fx_service = RealtimeRates()
        except Exception as exc:
            logger.warning("실시간 환율 서비스 초기화 실패: %s — 기본 환율 사용", exc)
    return MarginCalculator(fx_service=fx_service)


def _cmd_calculate(args):
    """단일 상품 마진 계산 또는 역계산."""
    calc = _build_calculator(use_live_fx=getattr(args, 'live_fx', False))

    if args.target_margin is not None:
        # 역계산
        result = calc.reverse_calculate(
            foreign_price=args.price,
            target_margin_rate=args.target_margin,
            currency=args.currency,
            marketplace=args.marketplace,
            platform=args.platform,
            category=args.category,
            weight_kg=args.weight,
        )
        print(f"\n역계산 결과 (목표 마진율: {args.target_margin}%)")
        print("-" * 60)
        print(f"  최적 판매가:    {int(result['optimal_sale_price']):,}원")
        print(f"  추천 판매가:    {int(result['rounded_sale_price']):,}원 (100원 단위 올림)")
        print(f"  원가:           {int(result['cost_krw']):,}원")
        print(f"  총비용:         {int(result['total_cost']):,}원")
        print(f"  수수료율:       {result['fee_rate']:.1f}%")
        print(f"  실제 마진율:    {result['actual_margin_rate']:.1f}%")
    else:
        # 마진 계산
        if not args.sale_price:
            print("오류: --sale-price 또는 --target-margin 중 하나를 지정하세요.")
            sys.exit(1)

        result = calc.calculate(
            foreign_price=args.price,
            sale_price_krw=args.sale_price,
            currency=args.currency,
            marketplace=args.marketplace,
            platform=args.platform,
            category=args.category,
            weight_kg=args.weight,
        )
        profit_mark = '✅' if result['is_profitable'] else '❌'
        print(f"\n마진 계산 결과 {profit_mark}")
        print("-" * 60)
        print(f"  해외가격:       {args.price} {args.currency}")
        print(f"  적용 환율:      {result['exchange_rate']:,.1f}원/{args.currency}")
        print(f"  원가:           {int(result['cost_krw']):,}원")
        print(f"  국제배송비:     {int(result['international_shipping']):,}원")
        print(f"  통관비:         {int(result['customs_total']):,}원")
        print(f"  국내배송비:     {int(result['domestic_shipping']):,}원")
        print(f"  총비용:         {int(result['total_cost']):,}원")
        print(f"  판매가:         {int(result['sale_price_krw']):,}원")
        print(f"  수수료율:       {result['fee_rate']:.1f}%")
        print(f"  수수료 금액:    {int(result['fee_amount']):,}원")
        print(f"  순수익:         {int(result['net_revenue']):,}원")
        print(f"  마진율:         {result['margin_rate']:.1f}%")

    if getattr(args, 'json', False):
        print("\n--- JSON ---")
        print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_bulk_calculate(args):
    """일괄 마진 계산."""
    if not os.path.exists(args.input):
        print(f"파일을 찾을 수 없습니다: {args.input}")
        sys.exit(1)

    with open(args.input, 'r', encoding='utf-8') as f:
        products = json.load(f)

    calc = _build_calculator(use_live_fx=getattr(args, 'live_fx', False))
    results = calc.bulk_calculate(products)

    successful = [r for r in results if r.get('success')]
    profitable = [r for r in successful if r.get('is_profitable')]

    print("\n일괄 마진 계산 완료")
    print(f"  전체: {len(products)}개 / 성공: {len(successful)}개 / 수익: {len(profitable)}개")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  결과 저장: {args.output}")
    else:
        for result in results:
            if result.get('success'):
                idx = result.get('product_index', '')
                margin = result.get('margin_rate', 0)
                mark = '✅' if result.get('is_profitable') else '❌'
                print(f"  [{idx}] 마진율: {margin:.1f}% {mark}")


def _cmd_report(args):
    """마진 리포트 생성."""
    if not os.path.exists(args.input):
        print(f"파일을 찾을 수 없습니다: {args.input}")
        sys.exit(1)

    with open(args.input, 'r', encoding='utf-8') as f:
        products = json.load(f)

    calc = _build_calculator(use_live_fx=getattr(args, 'live_fx', False))
    report = calc.generate_report(products)

    print("\n마진 리포트")
    print("=" * 60)
    print(f"  전체 상품:      {report['total_products']}개")
    print(f"  계산 성공:      {report['successful_count']}개")
    print(f"  수익 상품:      {report['profitable_count']}개")
    print(f"  평균 마진율:    {report['avg_margin_rate']:.1f}%")
    print(f"  최고 마진율:    {report['max_margin_rate']:.1f}%")
    print(f"  최저 마진율:    {report['min_margin_rate']:.1f}%")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n리포트 저장: {args.output}")


def main():
    """CLI 메인 엔트리포인트."""
    parser = argparse.ArgumentParser(
        prog='margin',
        description='수입 구매대행 마진 계산기',
    )
    parser.add_argument('--live-fx', action='store_true', help='실시간 환율 사용')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # calculate 서브커맨드
    calc_parser = subparsers.add_parser('calculate', help='마진 계산')
    calc_parser.add_argument('--price', type=float, required=True, help='해외 상품가격')
    calc_parser.add_argument('--currency', default='USD', help='통화 코드 (기본: USD)')
    calc_parser.add_argument('--sale-price', type=float, default=None, help='국내 판매가 (KRW)')
    calc_parser.add_argument('--target-margin', type=float, default=None, help='목표 마진율 (%)')
    calc_parser.add_argument('--marketplace', default='amazon_us', help='마켓플레이스 (기본: amazon_us)')
    calc_parser.add_argument('--platform', default='coupang', choices=['coupang', 'naver'], help='판매 플랫폼')
    calc_parser.add_argument('--category', default='default', help='상품 카테고리')
    calc_parser.add_argument('--weight', type=float, default=0.5, help='무게(kg, 기본 0.5)')
    calc_parser.add_argument('--json', action='store_true', help='JSON 형식 추가 출력')

    # bulk-calculate 서브커맨드
    bulk_parser = subparsers.add_parser('bulk-calculate', help='일괄 마진 계산')
    bulk_parser.add_argument('--input', required=True, help='상품 목록 JSON 파일 경로')
    bulk_parser.add_argument('--output', help='결과 저장 파일 경로')

    # report 서브커맨드
    report_parser = subparsers.add_parser('report', help='마진 리포트 생성')
    report_parser.add_argument('--input', required=True, help='상품 목록 JSON 파일 경로')
    report_parser.add_argument('--output', help='리포트 저장 파일 경로')

    args = parser.parse_args()

    if args.command == 'calculate':
        _cmd_calculate(args)
    elif args.command == 'bulk-calculate':
        _cmd_bulk_calculate(args)
    elif args.command == 'report':
        _cmd_report(args)


if __name__ == '__main__':
    main()
