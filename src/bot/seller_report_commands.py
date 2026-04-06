"""src/bot/seller_report_commands.py — 셀러 성과 리포트 봇 커맨드 (Phase 114)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _fmt(msg_type: str, text: str) -> str:
    from .formatters import format_message
    return format_message(msg_type, text)


# ── 리포트 ────────────────────────────────────────────────────────────────────

def cmd_my_report(report_type: str = 'daily') -> str:
    """/my_report [daily|weekly|monthly] — 리포트 생성."""
    from src.seller_report.report_generator import PerformanceReportGenerator
    try:
        gen = PerformanceReportGenerator()
        report = gen.generate_report(report_type)
        r_type = report.get('report_type', report_type)
        lines = [f'📊 *{r_type.upper()} 리포트*\n']

        if r_type == 'daily':
            m = report.get('metrics', {})
            lines += [
                f"💰 매출: {m.get('total_revenue', 0):,.0f}원",
                f"📦 주문: {m.get('total_orders', 0)}건",
                f"📈 마진율: {m.get('gross_margin_rate', 0):.1f}%",
                f"🔄 반품률: {m.get('return_rate', 0):.1f}%",
                f"✅ 이행률: {m.get('fulfillment_rate', 0):.1f}%",
            ]
        elif r_type == 'weekly':
            k = report.get('kpi_summary', {})
            lines += [
                f"💰 매출: {k.get('total_revenue', 0):,.0f}원",
                f"📦 주문: {k.get('total_orders', 0)}건",
                f"📈 마진율: {k.get('gross_margin_rate', 0):.1f}%",
            ]
            hs = report.get('hybrid_suggestion', {})
            if hs:
                lines.append(f"\n⭐ 사입 전환 제안: {hs.get('convert_count', 0)}개 상품")
        elif r_type == 'monthly':
            op = report.get('overall_performance', {})
            lines += [
                f"💰 매출: {op.get('total_revenue', 0):,.0f}원",
                f"📦 주문: {op.get('total_orders', 0)}건",
                f"📈 총마진율: {op.get('gross_margin_rate', 0):.1f}%",
                f"💵 순이익: {op.get('net_profit', 0):,.0f}원",
            ]
            ha = report.get('hybrid_model_analysis', {})
            if ha:
                lines.append(f"\n⭐ {ha.get('summary_text', '')}")

        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_my_report 오류: %s", exc)
        return _fmt('error', f'리포트 생성 실패: {exc}')


def cmd_daily_summary() -> str:
    """/daily_summary — 오늘 매출/주문/마진 요약."""
    from src.seller_report.metrics_engine import PerformanceMetricsEngine
    try:
        engine = PerformanceMetricsEngine()
        kpi = engine.get_kpi_summary()

        def _fmt_change(rate: float) -> str:
            arrow = '▲' if rate >= 0 else '▼'
            return f"{arrow}{abs(rate):.1f}%"

        lines = [
            '📊 *오늘 요약*\n',
            f"💰 매출: {kpi['revenue']['value']:,.0f}원 ({_fmt_change(kpi['revenue']['change_rate'])})",
            f"📦 주문: {kpi['orders']['value']}건 ({_fmt_change(kpi['orders']['change_rate'])})",
            f"📈 마진율: {kpi['gross_margin_rate']['value']:.1f}% ({_fmt_change(kpi['gross_margin_rate']['change_rate'])})",
            f"💳 AOV: {kpi['avg_order_value']['value']:,.0f}원",
            f"🔄 반품률: {kpi['return_rate']['value']:.1f}%",
            f"✅ SLA: {kpi['sla_compliance_rate']['value']:.1f}%",
        ]
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_daily_summary 오류: %s", exc)
        return _fmt('error', f'일간 요약 실패: {exc}')


# ── 상품 ──────────────────────────────────────────────────────────────────────

def cmd_product_rank(direction: str = 'top', n: int = 5) -> str:
    """/product_rank [top|bottom] [N] — 상품 수익성 순위."""
    from src.seller_report.product_performance import ProductPerformanceAnalyzer
    try:
        analyzer = ProductPerformanceAnalyzer()
        products = analyzer.get_product_ranking(limit=max(n, 5))
        if direction == 'bottom':
            products = sorted(products, key=lambda p: p.margin_rate)[:n]
        else:
            products = products[:n]

        title = '🏆 TOP' if direction == 'top' else '📉 BOTTOM'
        lines = [f'{title} {n} 상품 순위\n']
        for i, p in enumerate(products, 1):
            lines.append(
                f"{i}. {p.name}\n"
                f"   매출: {p.revenue:,.0f}원 | 마진: {p.margin_rate:.1f}% | 등급: {p.grade.value}"
            )
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_product_rank 오류: %s", exc)
        return _fmt('error', f'상품 순위 조회 실패: {exc}')


def cmd_dead_stock() -> str:
    """/dead_stock — 장기 미판매 상품."""
    from src.seller_report.product_performance import ProductPerformanceAnalyzer
    try:
        analyzer = ProductPerformanceAnalyzer()
        dead = analyzer.get_dead_stock()
        if not dead:
            return _fmt('info', '✅ 30일 이상 미판매 상품 없음')
        lines = [f'🚫 *장기 미판매 상품 ({len(dead)}개)*\n']
        for p in dead[:10]:
            lines.append(f"• {p.name} ({p.product_id}) — 재고: {p.days_of_stock}일치")
        return _fmt('warning', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_dead_stock 오류: %s", exc)
        return _fmt('error', f'장기 미판매 조회 실패: {exc}')


def cmd_trending_products() -> str:
    """/trending_products — 판매 급상승 상품."""
    from src.seller_report.product_performance import ProductPerformanceAnalyzer
    try:
        analyzer = ProductPerformanceAnalyzer()
        trending = analyzer.get_trending_products(limit=10)
        lines = ['🚀 *판매 급상승 상품 Top 10*\n']
        for i, p in enumerate(trending, 1):
            lines.append(f"{i}. {p.name} — 일평균 {p.avg_daily_sales:.1f}개 | 마진: {p.margin_rate:.1f}%")
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_trending_products 오류: %s", exc)
        return _fmt('error', f'급상승 상품 조회 실패: {exc}')


# ── 채널 ──────────────────────────────────────────────────────────────────────

def cmd_channel_compare() -> str:
    """/channel_compare — 채널별 성과 비교."""
    from src.seller_report.channel_performance import ChannelPerformanceAnalyzer
    try:
        analyzer = ChannelPerformanceAnalyzer()
        channels = analyzer.compare_channels()
        lines = ['📊 *채널별 성과 비교*\n']
        for c in sorted(channels, key=lambda x: x.revenue, reverse=True):
            lines.append(
                f"📌 {c.channel.upper()}\n"
                f"   매출: {c.revenue:,.0f}원 | 주문: {c.orders}건\n"
                f"   마진: {c.margin_rate:.1f}% | 반품: {c.return_rate:.1f}%\n"
                f"   성장: {c.growth_rate:+.1f}%"
            )
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_channel_compare 오류: %s", exc)
        return _fmt('error', f'채널 비교 실패: {exc}')


# ── 소싱처 ────────────────────────────────────────────────────────────────────

def cmd_source_rank() -> str:
    """/source_rank — 소싱처 성과 순위."""
    from src.seller_report.sourcing_performance import SourcingPerformanceAnalyzer
    try:
        analyzer = SourcingPerformanceAnalyzer()
        ranking = analyzer.get_source_ranking()[:10]
        lines = ['🏭 *소싱처 성과 순위 Top 10*\n']
        for i, s in enumerate(ranking, 1):
            trend_emoji = '📈' if s.reliability_trend == 'improving' else ('📉' if s.reliability_trend == 'declining' else '➡️')
            lines.append(
                f"{i}. {s.source_name} ({s.platform})\n"
                f"   성공률: {s.success_rate:.1f}% | 배송: {s.avg_delivery_days:.1f}일 {trend_emoji}"
            )
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_source_rank 오류: %s", exc)
        return _fmt('error', f'소싱처 순위 조회 실패: {exc}')


# ── 하이브리드 모델 ────────────────────────────────────────────────────────────

def cmd_hybrid_suggest() -> str:
    """/hybrid_suggest — 사입 전환 추천 상품."""
    from src.seller_report.hybrid_model_advisor import HybridModelAdvisor
    try:
        advisor = HybridModelAdvisor()
        recs = advisor.get_stock_recommendations()
        full = [r for r in recs if r.recommended_model.value == 'full_stock']
        semi = [r for r in recs if r.recommended_model.value == 'semi_stock']

        lines = [
            f'⭐ *사입 전환 추천 ({len(recs)}개 상품)*\n',
            f'🏭 대량 사입 (A급): {len(full)}개',
            f'📦 소량 사입 (B급): {len(semi)}개\n',
        ]

        lines.append('── 대량 사입 추천 (상위 5개) ──')
        for r in sorted(full, key=lambda x: x.monthly_sales, reverse=True)[:5]:
            lines.append(
                f"• {r.name}: 월 {r.monthly_sales}개\n"
                f"  배송: {advisor.CURRENT_DELIVERY_DAYS:.0f}일→{advisor.FULL_STOCK_DELIVERY_DAYS:.0f}일 | "
                f"투자: {r.estimated_investment:,.0f}원"
            )

        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_hybrid_suggest 오류: %s", exc)
        return _fmt('error', f'사입 추천 조회 실패: {exc}')


def cmd_hybrid_invest() -> str:
    """/hybrid_invest — 사입 전환 투자금 추정."""
    from src.seller_report.hybrid_model_advisor import HybridModelAdvisor
    try:
        advisor = HybridModelAdvisor()
        est = advisor.get_investment_estimate()
        delivery = advisor.get_delivery_improvement_estimate()

        lines = [
            '💰 *사입 전환 투자금 분석*\n',
            f"전환 대상: {est['total_products_to_convert']}개 상품",
            f"  • 대량 사입 (A급): {est['full_stock_count']}개 — {est['full_stock_investment']:,.0f}원",
            f"  • 소량 사입 (B급): {est['semi_stock_count']}개 — {est['semi_stock_investment']:,.0f}원",
            f"\n💵 총 투자금: {est['total_investment']:,.0f}원",
            f"📉 월 절감 예상: {est['estimated_monthly_savings']:,.0f}원",
        ]
        if est['payback_months']:
            lines.append(f"📅 투자 회수 기간: {est['payback_months']:.1f}개월")

        lines += [
            f"\n🚚 배송 개선:",
            f"  현재: {delivery['avg_delivery_before_days']:.0f}일 → 전환 후: {delivery['avg_delivery_after_days']:.1f}일",
            f"  평균 {delivery['avg_improvement_days']:.1f}일 단축",
        ]
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_hybrid_invest 오류: %s", exc)
        return _fmt('error', f'투자금 추정 실패: {exc}')


# ── 알림/목표/대시보드 ────────────────────────────────────────────────────────

def cmd_performance_alerts() -> str:
    """/performance_alerts — 성과 알림 현황."""
    from src.seller_report.performance_alerts import PerformanceAlertService
    try:
        svc = PerformanceAlertService()
        summary = svc.get_alert_summary()
        alerts = svc.get_alerts(acknowledged=False)

        lines = [
            f'🔔 *성과 알림 현황*\n',
            f"전체: {summary['total']}건 (미확인: {summary['unacknowledged']}건)",
            f"🚨 CRITICAL: {summary['critical']}건",
            f"⚠️ WARNING: {summary['warning']}건",
            f"ℹ️ INFO: {summary['info']}건\n",
        ]
        for a in alerts[:5]:
            emoji = '🚨' if a.severity == 'critical' else ('⚠️' if a.severity == 'warning' else 'ℹ️')
            lines.append(f"{emoji} {a.message}")

        return _fmt('warning' if summary['critical'] > 0 else 'info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_performance_alerts 오류: %s", exc)
        return _fmt('error', f'알림 조회 실패: {exc}')


def cmd_my_goals() -> str:
    """/my_goals — 목표 진행률."""
    from src.seller_report.goal_manager import PerformanceGoalManager
    try:
        mgr = PerformanceGoalManager()
        dashboard = mgr.get_goal_dashboard()
        summary = dashboard.get('summary', {})
        goals = dashboard.get('goals', [])

        lines = [f'🎯 *목표 진행률 ({summary.get("total", 0)}개)*\n']
        if not goals:
            lines.append('설정된 목표가 없습니다. /set_goal로 목표를 설정하세요.')
        else:
            for g in goals:
                status_emoji = {'on_track': '✅', 'at_risk': '⚠️', 'behind': '📉', 'achieved': '🏆', 'failed': '❌'}.get(g['status'], '•')
                lines.append(
                    f"{status_emoji} {g['metric_name']}: {g['progress_bar']}\n"
                    f"   현재: {g['current']:.1f} / 목표: {g['target']:.1f}"
                )
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_my_goals 오류: %s", exc)
        return _fmt('error', f'목표 조회 실패: {exc}')


def cmd_seller_dashboard() -> str:
    """/seller_dashboard — 종합 대시보드 요약."""
    from src.seller_report.metrics_engine import PerformanceMetricsEngine
    from src.seller_report.channel_performance import ChannelPerformanceAnalyzer
    from src.seller_report.hybrid_model_advisor import HybridModelAdvisor
    from src.seller_report.performance_alerts import PerformanceAlertService
    try:
        engine = PerformanceMetricsEngine()
        metrics = engine.calculate_metrics('daily')

        channel_analyzer = ChannelPerformanceAnalyzer()
        best_channel = channel_analyzer.get_best_channel()

        advisor = HybridModelAdvisor()
        hybrid = advisor.get_hybrid_summary()

        alert_svc = PerformanceAlertService()
        alert_summary = alert_svc.get_alert_summary()

        lines = [
            '📊 *셀러 종합 대시보드*\n',
            '── 오늘 성과 ──',
            f"💰 매출: {metrics.total_revenue:,.0f}원",
            f"📦 주문: {metrics.total_orders}건 | AOV: {metrics.avg_order_value:,.0f}원",
            f"📈 마진: {metrics.gross_margin_rate:.1f}% | 반품: {metrics.return_rate:.1f}%",
            f"\n── 채널 ──",
            f"🏆 베스트: {best_channel.channel} ({best_channel.revenue:,.0f}원)",
            f"\n── 하이브리드 전환 ──",
            f"⭐ {hybrid['summary_text']}",
            f"\n── 알림 ──",
            f"🔔 미확인: {alert_summary['unacknowledged']}건 (CRITICAL: {alert_summary['critical']}건)",
        ]
        return _fmt('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_seller_dashboard 오류: %s", exc)
        return _fmt('error', f'대시보드 조회 실패: {exc}')
