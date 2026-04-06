"""src/bot/competitor_pricing_commands.py — 경쟁사 가격 모니터링 봇 커맨드 (Phase 111)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def cmd_competitors(sku: str) -> str:
    """/competitors <sku> — 특정 상품의 경쟁사 목록 + 가격 비교."""
    from .formatters import format_message

    sku = sku.strip()
    if not sku:
        return format_message('error', 'SKU를 입력해주세요.\n사용법: /competitors <sku>')
    try:
        from src.competitor_pricing.tracker import CompetitorTracker

        tracker = CompetitorTracker()
        competitors = tracker.get_competitors(my_product_id=sku)
        lines = [
            f'🏪 *경쟁사 목록: `{sku}`*\n',
            f'• 경쟁사 수: {len(competitors)}개',
        ]
        for cp in competitors[:10]:
            avail = '✅' if cp.is_available else '❌'
            lines.append(
                f'  {avail} [{cp.platform}] {cp.competitor_name}: {cp.price:,.0f}원'
            )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_competitors 오류: %s", exc)
        return format_message('error', f'경쟁사 조회 실패: {exc}')


def cmd_price_position(sku: str = '') -> str:
    """/price_position [sku] — 가격 포지션 분석."""
    from .formatters import format_message

    sku = sku.strip()
    try:
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer

        tracker = CompetitorTracker()
        analyzer = PricePositionAnalyzer(tracker)
        product_id = sku or 'ALL'

        if sku:
            pos = analyzer.analyze_position(sku)
            label_icon = {
                'cheapest': '🥇',
                'below_average': '🟢',
                'average': '🟡',
                'above_average': '🟠',
                'most_expensive': '🔴',
            }.get(pos.position_label.value if hasattr(pos.position_label, 'value') else pos.position_label, '⚪')
            lines = [
                f'📊 *가격 포지션: `{sku}`*\n',
                f'• 내 가격: {pos.my_price:,.0f}원',
                f'• 최저가: {pos.min_price:,.0f}원',
                f'• 평균가: {pos.avg_price:,.0f}원',
                f'• 최고가: {pos.max_price:,.0f}원',
                f'• 순위: {pos.my_rank}/{pos.total_competitors + 1}',
                f'• 포지션: {label_icon} {pos.position_label.value if hasattr(pos.position_label, "value") else pos.position_label}',
            ]
        else:
            summary = analyzer.get_position_summary()
            lines = [
                '📊 *전체 포지션 요약*\n',
                f'• 최저가: {summary.get("cheapest", 0)}개',
                f'• 평균이하: {summary.get("below_average", 0)}개',
                f'• 평균: {summary.get("average", 0)}개',
                f'• 평균이상: {summary.get("above_average", 0)}개',
                f'• 최고가: {summary.get("most_expensive", 0)}개',
            ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_price_position 오류: %s", exc)
        return format_message('error', f'포지션 분석 실패: {exc}')


def cmd_price_suggest(sku: str = '') -> str:
    """/price_suggest [sku] — 가격 조정 제안."""
    from .formatters import format_message

    try:
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer
        from src.competitor_pricing.adjuster import PriceAdjustmentSuggester

        tracker = CompetitorTracker()
        analyzer = PricePositionAnalyzer(tracker)
        adjuster = PriceAdjustmentSuggester(tracker, analyzer)

        if sku.strip():
            suggestion = adjuster.suggest_adjustment(sku.strip())
            if not suggestion:
                return format_message('info', f'`{sku}` 제안 없음')
            lines = [
                f'💡 *가격 조정 제안: `{sku}`*\n',
                f'• 현재가: {suggestion.current_price:,.0f}원',
                f'• 제안가: {suggestion.suggested_price:,.0f}원',
                f'• 전략: {suggestion.strategy.value if hasattr(suggestion.strategy, "value") else suggestion.strategy}',
                f'• 예상 마진율: {suggestion.estimated_margin_rate:.1f}%',
                f'• 신뢰도: {suggestion.confidence*100:.0f}%',
                f'• 사유: {suggestion.reason}',
            ]
        else:
            suggestions = adjuster.suggest_bulk_adjustments()
            lines = [
                '💡 *일괄 가격 조정 제안*\n',
                f'• 제안 수: {len(suggestions)}개',
            ]
            for s in suggestions[:5]:
                lines.append(
                    f'  • `{s.my_product_id}`: {s.current_price:,.0f}원 → {s.suggested_price:,.0f}원'
                )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_price_suggest 오류: %s", exc)
        return format_message('error', f'가격 제안 실패: {exc}')


def cmd_competitor_alerts() -> str:
    """/competitor_alerts — 경쟁사 알림 현황."""
    from .formatters import format_message

    try:
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.competitor_alerts import CompetitorAlertService

        svc = CompetitorAlertService(CompetitorTracker())
        svc.check_alerts()
        summary = svc.get_alert_summary()
        by_sev = summary.get('by_severity', {})
        lines = [
            '🔔 *경쟁사 알림 현황*\n',
            f'• 전체: {summary.get("total", 0)}건',
            f'• 미확인: {summary.get("unacknowledged", 0)}건',
            f'  🔴 critical: {by_sev.get("critical", 0)}건',
            f'  🟡 warning: {by_sev.get("warning", 0)}건',
            f'  🔵 info: {by_sev.get("info", 0)}건',
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_competitor_alerts 오류: %s", exc)
        return format_message('error', f'알림 조회 실패: {exc}')


def cmd_competitor_dashboard() -> str:
    """/competitor_dashboard — 경쟁사 대시보드 요약."""
    from .formatters import format_message

    try:
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer
        from src.competitor_pricing.adjuster import PriceAdjustmentSuggester
        from src.competitor_pricing.competitor_dashboard import CompetitorDashboard

        tracker = CompetitorTracker()
        analyzer = PricePositionAnalyzer(tracker)
        adjuster = PriceAdjustmentSuggester(tracker, analyzer)
        dashboard = CompetitorDashboard(tracker, analyzer, adjuster)
        data = dashboard.get_dashboard_data()
        stats = data.get('suggestion_stats', {})
        lines = [
            '📊 *경쟁사 대시보드*\n',
            f'• 전체 경쟁사: {data.get("total_competitors", 0)}개',
            f'• 상품당 평균 경쟁사: {data.get("avg_competitors_per_product", 0):.1f}개',
            f'• 독점 상품: {data.get("monopoly_products", 0)}개',
            f'• 경쟁 점수: {data.get("competition_score", 0):.1f}/100',
            f'• 가격 전쟁 상품: {len(data.get("price_war_products", []))}개',
            f'• 제안 (대기/적용/거부): {stats.get("pending", 0)}/{stats.get("applied", 0)}/{stats.get("rejected", 0)}',
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_competitor_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


def cmd_price_war() -> str:
    """/price_war — 가격 전쟁 감지."""
    from .formatters import format_message

    try:
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer

        tracker = CompetitorTracker()
        analyzer = PricePositionAnalyzer(tracker)
        war_products = analyzer.detect_price_war()
        lines = [
            '⚔️ *가격 전쟁 감지*\n',
            f'• 가격 전쟁 상품: {len(war_products)}개',
        ]
        for pid in war_products[:10]:
            lines.append(f'  • `{pid}`')
        if not war_products:
            lines.append('• 현재 가격 전쟁 없음 ✅')
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_price_war 오류: %s", exc)
        return format_message('error', f'가격 전쟁 감지 실패: {exc}')


def cmd_competitor_find(sku: str) -> str:
    """/competitor_find <sku> — 경쟁사 자동 검색."""
    from .formatters import format_message

    sku = sku.strip()
    if not sku:
        return format_message('error', 'SKU를 입력해주세요.\n사용법: /competitor_find <sku>')
    try:
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.matcher import CompetitorMatcher

        tracker = CompetitorTracker()
        matcher = CompetitorMatcher(tracker)
        matches = matcher.find_competitors(sku, my_product={'title': sku, 'price': 10000})
        lines = [
            f'🔍 *경쟁사 자동 검색: `{sku}`*\n',
            f'• 발견: {len(matches)}개',
        ]
        for m in matches:
            score = m.match_score
            mtype = m.match_type.value if hasattr(m.match_type, 'value') else m.match_type
            cp = m.competitor_product
            lines.append(
                f'  • [{cp.platform}] {cp.competitor_name}: {cp.price:,.0f}원 '
                f'(유사도 {score:.1f}점, {mtype})'
            )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_competitor_find 오류: %s", exc)
        return format_message('error', f'경쟁사 검색 실패: {exc}')


def cmd_price_rules() -> str:
    """/price_rules — 가격 규칙 목록."""
    from .formatters import format_message

    try:
        from src.competitor_pricing.price_rules import CompetitorPriceRules

        rules_svc = CompetitorPriceRules()
        rules = rules_svc.get_rules()
        lines = [
            '📋 *가격 규칙 목록*\n',
            f'• 전체: {len(rules)}개 규칙',
        ]
        for r in rules:
            active = '✅' if r.is_active else '❌'
            lines.append(
                f'  {active} [{r.priority}] {r.name}\n'
                f'      조건: {r.condition}\n'
                f'      액션: {r.action}'
            )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_price_rules 오류: %s", exc)
        return format_message('error', f'규칙 조회 실패: {exc}')
