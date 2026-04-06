"""src/bot/discovery_commands.py — 소싱 발굴 봇 커맨드 (Phase 115)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _fmt(msg_type: str, text: str) -> str:
    from .formatters import format_message
    return format_message(msg_type, text)


def cmd_discover() -> str:
    """/discover — 소싱 발굴 파이프라인 실행."""
    from src.sourcing_discovery.discovery_pipeline import DiscoveryPipeline
    try:
        pipeline = DiscoveryPipeline()
        run = pipeline.run_pipeline()
        lines = [
            '🔍 *소싱 발굴 파이프라인 실행 완료*\n',
            f"📦 발굴된 기회: {run.opportunities_found}개",
            f"✅ 자동 승인: {run.opportunities_approved}개",
            f"❌ 자동 거절: {run.opportunities_rejected}개",
            f"⏱ 소요 시간: {run.duration_seconds:.2f}초",
            f"📊 상태: {run.status}",
        ]
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_discover 오류: %s", exc)
        return _fmt('error', f'파이프라인 실행 실패: {exc}')


def cmd_trending() -> str:
    """/trending — 상위 10 상승 트렌드 조회."""
    from src.sourcing_discovery.trend_analyzer import TrendAnalyzer
    try:
        analyzer = TrendAnalyzer()
        trends = analyzer.get_rising_trends(limit=10)
        lines = ['📈 *상승 트렌드 TOP 10*\n']
        for i, t in enumerate(trends, 1):
            lines.append(
                f"{i}. {t.keyword} | 성장률: +{t.growth_rate:.1f}% | {t.trend_direction.value}"
            )
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_trending 오류: %s", exc)
        return _fmt('error', f'트렌드 조회 실패: {exc}')


def cmd_opportunities(status: str = 'discovered') -> str:
    """/opportunities [status] — 소싱 기회 목록 조회."""
    from src.sourcing_discovery.opportunity_finder import SourcingOpportunityFinder
    try:
        finder = SourcingOpportunityFinder()
        finder.discover_opportunities(limit=10)
        opps = finder.get_opportunities(status=status if status != 'all' else None)
        lines = [f'💡 *소싱 기회 목록* ({status})\n']
        if not opps:
            lines.append('조회된 기회가 없습니다.')
        for opp in opps[:10]:
            lines.append(
                f"• {opp.product_name} | 점수: {opp.opportunity_score:.1f} | {opp.discovery_method.value}"
            )
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_opportunities 오류: %s", exc)
        return _fmt('error', f'기회 목록 조회 실패: {exc}')


def cmd_opportunity(opportunity_id: str) -> str:
    """/opportunity <id> — 단일 소싱 기회 상세 조회."""
    from src.sourcing_discovery.opportunity_finder import SourcingOpportunityFinder
    try:
        finder = SourcingOpportunityFinder()
        finder.discover_opportunities(limit=10)
        opp = finder.get_opportunity(opportunity_id)
        if opp is None:
            return _fmt('warning', f'기회를 찾을 수 없습니다: {opportunity_id}')
        lines = [
            f'📋 *소싱 기회 상세*\n',
            f"상품: {opp.product_name}",
            f"카테고리: {opp.category}",
            f"플랫폼: {opp.source_platform}",
            f"소싱가: {opp.source_price} {opp.source_currency}",
            f"예상 판매가: {opp.estimated_selling_price:,.0f}원",
            f"예상 마진율: {opp.estimated_margin_rate:.1f}%",
            f"기회 점수: {opp.opportunity_score:.1f}",
            f"상태: {opp.status.value}",
        ]
        if opp.risk_factors:
            lines.append(f"위험 요소: {', '.join(opp.risk_factors)}")
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_opportunity 오류: %s", exc)
        return _fmt('error', f'기회 조회 실패: {exc}')


def cmd_market_gaps() -> str:
    """/market_gaps — 마켓 갭 분석 목록."""
    from src.sourcing_discovery.market_gap_analyzer import MarketGapAnalyzer
    try:
        analyzer = MarketGapAnalyzer()
        gaps = analyzer.get_top_gaps(limit=5)
        lines = ['🔎 *주요 마켓 갭 TOP 5*\n']
        for i, gap in enumerate(gaps, 1):
            lines.append(
                f"{i}. [{gap.category}] {gap.description[:30]}... | 갭 점수: {gap.gap_score:.1f}"
            )
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_market_gaps 오류: %s", exc)
        return _fmt('error', f'마켓 갭 조회 실패: {exc}')


def cmd_scout_suppliers(category: str = '') -> str:
    """/scout_suppliers [category] — 공급사 탐색."""
    from src.sourcing_discovery.supplier_scout import SupplierScout
    try:
        scout = SupplierScout()
        candidates = scout.scout_suppliers(category=category or None)
        lines = [f'🏭 *공급사 탐색 결과* ({len(candidates)}개)\n']
        for c in candidates[:8]:
            lines.append(
                f"• {c.supplier_name} ({c.platform}) | 신뢰도: {c.estimated_reliability:.0f}%"
            )
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_scout_suppliers 오류: %s", exc)
        return _fmt('error', f'공급사 탐색 실패: {exc}')


def cmd_predict_profit(product_info: str) -> str:
    """/predict_profit name:price:currency — 수익성 예측."""
    from src.sourcing_discovery.profitability_predictor import ProfitabilityPredictor
    try:
        parts = product_info.split(':')
        name = parts[0] if len(parts) > 0 else '상품'
        price = float(parts[1]) if len(parts) > 1 else 10.0
        currency = parts[2].strip() if len(parts) > 2 else 'CNY'

        predictor = ProfitabilityPredictor()
        pred = predictor.predict_profitability({
            'product_name': name,
            'source_price': price,
            'source_currency': currency,
        })
        lines = [
            f'💰 *수익성 예측: {pred.product_name}*\n',
            f"소싱가: {pred.source_price} {pred.source_currency}",
            f"예상 판매가: {pred.estimated_selling_price:,.0f}원",
            f"예상 마진율: {pred.estimated_margin_rate:.1f}%",
            f"월 예상 수익: {pred.estimated_monthly_profit:,.0f}원",
            f"손익분기점: {pred.break_even_units}개",
            f"추천 모델: {pred.recommended_model}",
            f"신뢰도: {pred.confidence_score:.1f}%",
        ]
        if pred.risk_factors:
            lines.append(f"⚠️ 위험: {', '.join(pred.risk_factors)}")
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_predict_profit 오류: %s", exc)
        return _fmt('error', f'수익성 예측 실패: {exc}')


def cmd_seasonal_opportunities() -> str:
    """/seasonal — 현재 시즌 소싱 기회."""
    from src.sourcing_discovery.trend_analyzer import TrendAnalyzer
    try:
        analyzer = TrendAnalyzer()
        trends = analyzer.get_seasonal_opportunities()
        lines = ['🌸 *현재 시즌 소싱 기회*\n']
        if not trends:
            lines.append('현재 시즌 기회가 없습니다.')
        for t in trends[:8]:
            lines.append(
                f"• {t.keyword} ({t.category}) | 성수기: {t.peak_month}월 | 시즌성: {t.seasonality_score:.1f}"
            )
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_seasonal_opportunities 오류: %s", exc)
        return _fmt('error', f'시즌 기회 조회 실패: {exc}')


def cmd_discovery_alerts() -> str:
    """/discovery_alerts — 미확인 발굴 알림 조회."""
    from src.sourcing_discovery.discovery_alerts import DiscoveryAlertService
    try:
        service = DiscoveryAlertService()
        alerts = service.check_alerts()
        lines = [f'🔔 *발굴 알림* ({len(alerts)}개 미확인)\n']
        for alert in alerts[:8]:
            emoji = '🔴' if alert.severity == 'high' else '🟡' if alert.severity == 'medium' else '🟢'
            lines.append(f"{emoji} {alert.message}")
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_discovery_alerts 오류: %s", exc)
        return _fmt('error', f'알림 조회 실패: {exc}')


def cmd_discovery_dashboard() -> str:
    """/discovery_dashboard — 대시보드 요약."""
    from src.sourcing_discovery.discovery_dashboard import DiscoveryDashboard
    try:
        dashboard = DiscoveryDashboard()
        data = dashboard.get_dashboard_data()
        lines = [
            '📊 *소싱 발굴 대시보드*\n',
            f"📦 주간 발굴 기회: {data.get('weekly_opportunities_found', 0)}개",
            f"✅ 주간 승인: {data.get('weekly_approved', 0)}개",
            f"🏭 신규 공급사 후보: {data.get('new_supplier_candidates', 0)}개",
            f"🔄 파이프라인 상태: {data.get('pipeline_status', 'unknown')}",
        ]
        top_keywords = data.get('trend_keywords', [])[:3]
        if top_keywords:
            kws = ', '.join(t['keyword'] for t in top_keywords)
            lines.append(f"📈 주요 트렌드: {kws}")
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_discovery_dashboard 오류: %s", exc)
        return _fmt('error', f'대시보드 조회 실패: {exc}')


def cmd_discovery_pipeline() -> str:
    """/discovery_pipeline — 파이프라인 설정 조회."""
    from src.sourcing_discovery.discovery_pipeline import DiscoveryPipeline
    try:
        pipeline = DiscoveryPipeline()
        config = pipeline.get_pipeline_config()
        lines = [
            '⚙️ *파이프라인 설정*\n',
            f"자동 발굴 주기: {config.auto_discover_interval_hours}시간",
            f"최대 기회 수: {config.max_opportunities_per_run}개",
            f"최소 점수: {config.min_opportunity_score}점",
            f"자동 승인 임계값: {config.auto_approve_threshold}점",
            f"모니터링 카테고리: {', '.join(config.categories_to_monitor)}",
            f"스캔 플랫폼: {', '.join(config.platforms_to_scan)}",
        ]
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_discovery_pipeline 오류: %s", exc)
        return _fmt('error', f'파이프라인 설정 조회 실패: {exc}')
