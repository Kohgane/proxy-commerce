"""src/seller_report/report_generator.py — PerformanceReportGenerator (Phase 114)."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReportType(str, Enum):
    daily = 'daily'
    weekly = 'weekly'
    monthly = 'monthly'


class ReportFormat(str, Enum):
    text = 'text'
    markdown = 'markdown'
    json = 'json'


class PerformanceReportGenerator:
    """자동 리포트 생성."""

    def __init__(self) -> None:
        self._report_history: List[Dict[str, Any]] = []

    # ── 공통 헬퍼 ─────────────────────────────────────────────────────────────

    def _get_metrics(self, period: str = 'daily') -> Any:
        from .metrics_engine import PerformanceMetricsEngine
        return PerformanceMetricsEngine().calculate_metrics(period)

    def _get_channel_data(self) -> Any:
        from .channel_performance import ChannelPerformanceAnalyzer
        return ChannelPerformanceAnalyzer().compare_channels()

    def _get_product_ranking(self, limit: int = 5) -> Any:
        from .product_performance import ProductPerformanceAnalyzer
        return ProductPerformanceAnalyzer().get_product_ranking(limit=limit)

    def _get_worst_products(self, limit: int = 5) -> Any:
        from .product_performance import ProductPerformanceAnalyzer
        analyzer = ProductPerformanceAnalyzer()
        return analyzer.get_product_ranking(sort_by='margin_rate', limit=200)[-limit:]

    def _get_hybrid_summary(self) -> Any:
        from .hybrid_model_advisor import HybridModelAdvisor
        return HybridModelAdvisor().get_hybrid_summary()

    def _get_source_ranking(self) -> Any:
        from .sourcing_performance import SourcingPerformanceAnalyzer
        return SourcingPerformanceAnalyzer().get_source_ranking()

    def _get_alerts(self) -> Any:
        from .performance_alerts import PerformanceAlertService
        return PerformanceAlertService().get_alerts()

    def _save_report(self, report_type: str, content: Any) -> str:
        report_id = str(uuid.uuid4())[:8]
        self._report_history.append({
            'report_id': report_id,
            'report_type': report_type,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'content': content,
        })
        return report_id

    # ── 리포트 생성 ──────────────────────────────────────────────────────────

    def generate_report(
        self,
        report_type: str,
        fmt: str = 'json',
    ) -> Dict[str, Any]:
        """리포트 생성."""
        if report_type == ReportType.daily:
            return self.generate_daily_report(fmt=fmt)
        elif report_type == ReportType.weekly:
            return self.generate_weekly_report(fmt=fmt)
        elif report_type == ReportType.monthly:
            return self.generate_monthly_report(fmt=fmt)
        else:
            return self.generate_daily_report(fmt=fmt)

    def generate_daily_report(self, fmt: str = 'json') -> Dict[str, Any]:
        """일간 리포트."""
        metrics = self._get_metrics('daily')
        top_products = self._get_product_ranking(5)
        worst_products = self._get_worst_products(5)
        alerts = self._get_alerts()

        report_data = {
            'report_type': 'daily',
            'date': date.today().isoformat(),
            'metrics': {
                'total_revenue': metrics.total_revenue,
                'total_orders': metrics.total_orders,
                'gross_margin_rate': metrics.gross_margin_rate,
                'avg_order_value': metrics.avg_order_value,
                'return_rate': metrics.return_rate,
                'fulfillment_rate': metrics.fulfillment_rate,
            },
            'top_products': [
                {'product_id': p.product_id, 'name': p.name, 'revenue': p.revenue}
                for p in top_products
            ],
            'worst_products': [
                {'product_id': p.product_id, 'name': p.name, 'margin_rate': p.margin_rate}
                for p in worst_products
            ],
            'fulfillment': {
                'rate': metrics.fulfillment_rate,
                'sla_compliance': metrics.sla_compliance_rate,
            },
            'alerts': [
                {'type': a.alert_type, 'severity': a.severity, 'message': a.message}
                for a in alerts[:5]
            ],
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

        self._save_report('daily', report_data)

        if fmt == 'markdown':
            return {'report_type': 'daily', 'format': 'markdown', 'content': self._daily_to_markdown(report_data)}
        return report_data

    def generate_weekly_report(self, fmt: str = 'json') -> Dict[str, Any]:
        """주간 리포트."""
        metrics = self._get_metrics('weekly')
        channels = self._get_channel_data()
        source_ranking = self._get_source_ranking()
        hybrid = self._get_hybrid_summary()

        today = date.today()
        week_start = today - timedelta(days=6)

        report_data = {
            'report_type': 'weekly',
            'period': {'start': week_start.isoformat(), 'end': today.isoformat()},
            'kpi_summary': {
                'total_revenue': metrics.total_revenue,
                'total_orders': metrics.total_orders,
                'gross_margin_rate': metrics.gross_margin_rate,
                'return_rate': metrics.return_rate,
                'fulfillment_rate': metrics.fulfillment_rate,
            },
            'channel_performance': [
                {
                    'channel': c.channel,
                    'revenue': c.revenue,
                    'orders': c.orders,
                    'margin_rate': c.margin_rate,
                    'growth_rate': c.growth_rate,
                }
                for c in channels
            ],
            'sourcing_ranking': [
                {
                    'source_id': s.source_id,
                    'source_name': s.source_name,
                    'success_rate': s.success_rate,
                    'avg_delivery_days': s.avg_delivery_days,
                }
                for s in source_ranking[:5]
            ],
            'hybrid_suggestion': {
                'convert_count': hybrid['convert_count'],
                'total_investment': hybrid['total_investment'],
                'summary': hybrid['summary_text'],
            },
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

        self._save_report('weekly', report_data)
        return report_data

    def generate_monthly_report(self, fmt: str = 'json') -> Dict[str, Any]:
        """월간 리포트."""
        metrics = self._get_metrics('monthly')
        channels = self._get_channel_data()
        hybrid = self._get_hybrid_summary()
        source_ranking = self._get_source_ranking()

        from .product_performance import ProductPerformanceAnalyzer
        pa = ProductPerformanceAnalyzer()
        matrix = pa.get_profitability_matrix()

        today = date.today()
        month_start = today.replace(day=1)

        report_data = {
            'report_type': 'monthly',
            'period': {'start': month_start.isoformat(), 'end': today.isoformat()},
            'overall_performance': {
                'total_revenue': metrics.total_revenue,
                'gross_profit': metrics.gross_profit,
                'net_profit': metrics.net_profit,
                'gross_margin_rate': metrics.gross_margin_rate,
                'net_margin_rate': metrics.net_margin_rate,
                'total_orders': metrics.total_orders,
                'unique_customers': metrics.unique_customers,
                'repeat_customer_rate': metrics.repeat_customer_rate,
            },
            'channel_performance': [
                {
                    'channel': c.channel,
                    'revenue': c.revenue,
                    'orders': c.orders,
                    'margin_rate': c.margin_rate,
                    'return_rate': c.return_rate,
                }
                for c in channels
            ],
            'profitability_matrix': {
                'stars_count': len(matrix['stars']),
                'hidden_gems_count': len(matrix['hidden_gems']),
                'volume_drivers_count': len(matrix['volume_drivers']),
                'dogs_count': len(matrix['dogs']),
            },
            'sourcing_evaluation': [
                {
                    'source_id': s.source_id,
                    'source_name': s.source_name,
                    'success_rate': s.success_rate,
                    'quality_score': s.quality_score,
                    'reliability_trend': s.reliability_trend,
                }
                for s in source_ranking[:10]
            ],
            'hybrid_model_analysis': hybrid,
            'next_month_targets': {
                'revenue_target': round(metrics.total_revenue * 1.10),
                'margin_target': round(metrics.gross_margin_rate + 1.0, 2),
                'order_target': round(metrics.total_orders * 1.10),
            },
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

        self._save_report('monthly', report_data)
        return report_data

    def _daily_to_markdown(self, data: Dict[str, Any]) -> str:
        m = data['metrics']
        lines = [
            f"# 📊 일간 리포트 — {data['date']}",
            "",
            "## 💰 오늘 성과",
            f"- 매출: {m['total_revenue']:,.0f}원",
            f"- 주문: {m['total_orders']}건",
            f"- 마진율: {m['gross_margin_rate']:.1f}%",
            f"- AOV: {m['avg_order_value']:,.0f}원",
            "",
            "## 🏆 베스트 상품 Top 5",
        ]
        for p in data.get('top_products', []):
            lines.append(f"- {p['name']}: {p['revenue']:,.0f}원")
        return '\n'.join(lines)

    def get_report_history(
        self,
        report_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """리포트 이력."""
        history = self._report_history
        if report_type:
            history = [r for r in history if r['report_type'] == report_type]
        return history[-limit:]

    def schedule_reports(self) -> Dict[str, Any]:
        """리포트 자동 스케줄 정보."""
        return {
            'daily': {'cron': '0 9 * * *', 'description': '매일 09:00 일간 리포트'},
            'weekly': {'cron': '0 9 * * 1', 'description': '매주 월요일 09:00 주간 리포트'},
            'monthly': {'cron': '0 9 1 * *', 'description': '매월 1일 09:00 월간 리포트'},
            'status': 'active',
        }
