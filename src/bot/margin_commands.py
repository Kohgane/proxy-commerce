"""src/bot/margin_commands.py — 마진 계산기 봇 커맨드 (Phase 110)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def cmd_margin(sku: str) -> str:
    """/margin <sku> — 상품 마진 계산 결과 (비용 항목별 분해 포함)."""
    sku = sku.strip()
    if not sku:
        return '❌ SKU를 입력해주세요.\n사용법: /margin <sku>'
    try:
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        calc = RealTimeMarginCalculator()
        result = calc.calculate_margin(sku)
        lines = [
            f'💰 *마진 계산: `{sku}`*\n',
            f'• 판매가: {result.selling_price:,.0f}원',
            f'• 원가(원화): {result.source_cost_krw:,.0f}원',
            f'• 해외배송비: {result.international_shipping:,.0f}원',
            f'• 관세: {result.customs_duty:,.0f}원',
            f'• 부가세: {result.vat:,.0f}원',
            f'• 국내배송비: {result.domestic_shipping:,.0f}원',
            f'• 플랫폼수수료: {result.platform_fee:,.0f}원',
            f'• 결제수수료: {result.payment_fee:,.0f}원',
            f'• 환율손실: {result.exchange_loss:,.0f}원',
            f'• 포장비: {result.packaging_cost:,.0f}원',
            f'• 라벨링비: {result.labeling_cost:,.0f}원',
            f'• 반품충당금: {result.return_reserve:,.0f}원',
            f'• 총비용: {result.total_cost:,.0f}원',
            f'\n*순이익: {result.net_profit:,.0f}원*',
            f'*마진율: {result.margin_rate:.1f}%*',
        ]
        icon = '🔴' if result.margin_rate < 0 else ('🟡' if result.margin_rate < 5 else '🟢')
        lines.append(f'{icon} {"적자" if result.margin_rate < 0 else ("저마진" if result.margin_rate < 5 else "정상")}')
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_margin 오류: %s", exc)
        return f'❌ 마진 계산 실패: {exc}'


def cmd_margin_alert() -> str:
    """/margin_alert — 현재 마진 알림 현황 (적자/저마진/정상 개수)."""
    try:
        from src.margin_calculator.margin_alerts import MarginAlertService, AlertSeverity
        svc = MarginAlertService()
        summary = svc.get_alert_summary()
        lines = [
            '🔔 *마진 알림 현황*\n',
            f'🔴 적자 (CRITICAL): {summary.get(AlertSeverity.CRITICAL.value, 0)}건',
            f'🟡 저마진 (WARNING): {summary.get(AlertSeverity.WARNING.value, 0)}건',
            f'🟠 목표미달 (INFO): {summary.get(AlertSeverity.INFO.value, 0)}건',
            f'🟢 정상 (GOOD): {summary.get(AlertSeverity.GOOD.value, 0)}건',
        ]
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_margin_alert 오류: %s", exc)
        return f'❌ 마진 알림 조회 실패: {exc}'


def cmd_profit_ranking(direction: str = 'top', n: int = 10) -> str:
    """/profit_ranking [top|bottom] [N] — 수익성 순위 (상위/하위 N개)."""
    try:
        from src.margin_calculator.profitability import ProfitabilityAnalyzer
        analyzer = ProfitabilityAnalyzer()
        reverse = direction.lower() != 'bottom'
        ranking = analyzer.get_profitability_ranking(limit=n, reverse=reverse)
        direction_str = '상위' if reverse else '하위'
        lines = [f'📊 *수익성 {direction_str} {n}개*\n']
        for item in ranking:
            icon = '🔴' if item['margin_rate'] < 0 else ('🟡' if item['margin_rate'] < 5 else '🟢')
            lines.append(
                f'{item["rank"]}. {icon} `{item["product_id"]}` '
                f'마진 {item["margin_rate"]:.1f}% | 이익 {item["net_profit"]:,.0f}원'
            )
        return '\n'.join(lines) if len(lines) > 1 else '상품 없음'
    except Exception as exc:
        logger.error("cmd_profit_ranking 오류: %s", exc)
        return f'❌ 수익성 순위 조회 실패: {exc}'


def cmd_loss_products() -> str:
    """/loss_products — 적자 상품 목록."""
    try:
        from src.margin_calculator.profitability import ProfitabilityAnalyzer
        analyzer = ProfitabilityAnalyzer()
        products = analyzer.get_loss_products()
        if not products:
            return '✅ 적자 상품 없음'
        lines = [f'🔴 *적자 상품 ({len(products)}개)*\n']
        for p in products[:20]:
            lines.append(
                f'• `{p["product_id"]}` 마진 {p["margin_rate"]:.1f}% '
                f'(손실 {abs(p["net_profit"]):,.0f}원)'
            )
        if len(products) > 20:
            lines.append(f'  ... 외 {len(products) - 20}개')
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_loss_products 오류: %s", exc)
        return f'❌ 적자 상품 조회 실패: {exc}'


def cmd_margin_simulate(sku: str, new_price: float) -> str:
    """/margin_simulate <sku> <new_price> — 가격 변경 시 마진 변화 시뮬레이션."""
    sku = sku.strip()
    if not sku:
        return '❌ SKU와 새 가격을 입력해주세요.\n사용법: /margin_simulate <sku> <new_price>'
    try:
        from src.margin_calculator.margin_simulator import MarginSimulator
        sim = MarginSimulator()
        result = sim.simulate_price_change(sku, new_price)
        before = result['before']
        after = result['after']
        delta_margin = result['delta_margin_rate']
        delta_profit = result['delta_net_profit']
        arrow = '↑' if delta_margin >= 0 else '↓'
        lines = [
            f'🔬 *가격 변경 시뮬레이션: `{sku}`*\n',
            f'• 현재 판매가: {before["selling_price"]:,.0f}원 → {after["selling_price"]:,.0f}원',
            f'• 마진율: {before["margin_rate"]:.1f}% → {after["margin_rate"]:.1f}% ({arrow}{abs(delta_margin):.1f}%p)',
            f'• 순이익: {before["net_profit"]:,.0f}원 → {after["net_profit"]:,.0f}원 ({arrow}{abs(delta_profit):,.0f}원)',
        ]
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_margin_simulate 오류: %s", exc)
        return f'❌ 시뮬레이션 실패: {exc}'


def cmd_break_even(sku: str) -> str:
    """/break_even <sku> — 손익분기 판매가 계산."""
    sku = sku.strip()
    if not sku:
        return '❌ SKU를 입력해주세요.\n사용법: /break_even <sku>'
    try:
        from src.margin_calculator.margin_simulator import MarginSimulator
        sim = MarginSimulator()
        result = sim.find_break_even_price(sku)
        lines = [
            f'⚖️ *손익분기 계산: `{sku}`*\n',
            f'• 손익분기 판매가: {result["break_even_price"]:,}원',
            f'• 해당 마진율: {result["margin_rate_at_break_even"]:.2f}%',
        ]
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_break_even 오류: %s", exc)
        return f'❌ 손익분기 계산 실패: {exc}'


def cmd_margin_trend(sku: str) -> str:
    """/margin_trend <sku> — 상품 마진 추이."""
    sku = sku.strip()
    if not sku:
        return '❌ SKU를 입력해주세요.\n사용법: /margin_trend <sku>'
    try:
        from src.margin_calculator.margin_trend import MarginTrendAnalyzer
        analyzer = MarginTrendAnalyzer()
        trend = analyzer.get_product_trend(sku)
        data = trend.get('data', [])
        if not data:
            return f'📈 *마진 추이: `{sku}`*\n데이터 없음'
        lines = [f'📈 *마진 추이: `{sku}`* (최근 {len(data)}개)\n']
        for pt in data[-5:]:
            lines.append(f'• {pt.get("timestamp", "")[:10]} 마진 {pt.get("margin_rate", 0):.1f}%')
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_margin_trend 오류: %s", exc)
        return f'❌ 마진 추이 조회 실패: {exc}'


def cmd_margin_dashboard() -> str:
    """/margin_dashboard — 마진 대시보드 요약."""
    try:
        from src.margin_calculator.profitability import ProfitabilityAnalyzer
        from src.margin_calculator.margin_alerts import MarginAlertService, AlertSeverity
        from src.margin_calculator.margin_trend import MarginTrendAnalyzer

        profitability = ProfitabilityAnalyzer()
        alert_svc = MarginAlertService()
        trend = MarginTrendAnalyzer()

        dist = profitability.get_profitability_distribution()
        alert_summary = alert_svc.get_alert_summary()
        trend_summary = trend.get_trend_summary()

        lines = [
            '📊 *마진 대시보드*\n',
            f'• 총 상품: {dist.get("total_products", 0)}개',
            f'• 평균 마진율: {dist.get("average_margin_rate", 0):.1f}%',
            f'\n*알림 현황:*',
            f'  🔴 적자: {alert_summary.get(AlertSeverity.CRITICAL.value, 0)}건',
            f'  🟡 저마진: {alert_summary.get(AlertSeverity.WARNING.value, 0)}건',
            f'\n*마진 추이:*',
            f'  📈 상승: {trend_summary.get("rising", 0)}개',
            f'  📉 하락: {trend_summary.get("declining", 0)}개',
            f'  ➡️ 안정: {trend_summary.get("stable", 0)}개',
        ]
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_margin_dashboard 오류: %s", exc)
        return f'❌ 대시보드 조회 실패: {exc}'


def cmd_platform_fees(channel: str = '') -> str:
    """/platform_fees [channel] — 플랫폼 수수료 정보."""
    try:
        from src.margin_calculator.platform_fees import PlatformFeeCalculator
        calc = PlatformFeeCalculator()
        if channel.strip():
            info = calc.get_fee_structure(channel.strip().lower())
            lines = [f'💳 *{channel} 수수료 구조*\n']
            for k, v in info.items():
                if k != 'channel':
                    lines.append(f'• {k}: {v}')
        else:
            all_fees = calc.get_all_fee_structures()
            lines = ['💳 *플랫폼 수수료 현황*\n']
            for ch, info in all_fees.items():
                desc = info.get('description', '')
                lines.append(f'*{ch}*: {desc}')
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_platform_fees 오류: %s", exc)
        return f'❌ 플랫폼 수수료 조회 실패: {exc}'


def cmd_margin_config() -> str:
    """/margin_config — 현재 마진 설정 조회."""
    try:
        from src.margin_calculator.margin_config import MarginConfig
        cfg = MarginConfig()
        config = cfg.get_config()
        lines = ['⚙️ *마진 설정*\n']
        for k, v in config.items():
            lines.append(f'• {k}: {v}')
        return '\n'.join(lines)
    except Exception as exc:
        logger.error("cmd_margin_config 오류: %s", exc)
        return f'❌ 설정 조회 실패: {exc}'
