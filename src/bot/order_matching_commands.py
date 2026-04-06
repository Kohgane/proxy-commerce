"""src/bot/order_matching_commands.py — 주문 매칭 봇 커맨드 (Phase 112)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def cmd_match_order(order_id: str) -> str:
    """/match_order <order_id> — 주문 소싱처 매칭 실행."""
    from .formatters import format_message

    order_id = order_id.strip()
    if not order_id:
        return format_message('error', '주문 ID를 입력해주세요.\n사용법: /match_order <order_id>')
    try:
        from src.order_matching.matcher import OrderSourceMatcher

        matcher = OrderSourceMatcher()
        results = matcher.match_order(order_id)
        lines = [f'🔗 *주문 매칭 완료: `{order_id}`*\n', f'• 상품 수: {len(results)}개']
        for r in results:
            status_icon = {
                'fulfillable': '✅',
                'unfulfillable': '❌',
                'risky': '⚠️',
                'partially_fulfillable': '🟡',
                'pending_check': '⏳',
            }.get(r.fulfillment_status.value, '❓')
            lines.append(
                f'  {status_icon} [{r.product_id}] {r.fulfillment_status.value}'
                + (f' → {r.best_source}' if r.best_source else '')
            )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_match_order 오류: %s", exc)
        return format_message('error', f'매칭 실패: {exc}')


def cmd_match_status(order_id: str) -> str:
    """/match_status <order_id> — 주문 매칭 결과 조회."""
    from .formatters import format_message

    order_id = order_id.strip()
    if not order_id:
        return format_message('error', '주문 ID를 입력해주세요.\n사용법: /match_status <order_id>')
    try:
        from src.order_matching.matcher import OrderSourceMatcher

        matcher = OrderSourceMatcher()
        results = matcher.get_match_result(order_id)
        if not results:
            return format_message('warning', f'매칭 결과 없음: `{order_id}`')
        lines = [f'📋 *매칭 현황: `{order_id}`*\n']
        for r in results:
            lines.append(
                f'• [{r.product_id}] {r.fulfillment_status.value}'
                f' | 비용: {r.estimated_cost:,.0f}원'
                f' | 배송: {r.estimated_delivery_days}일'
                f' | 리스크: {r.risk_score:.0f}'
            )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_match_status 오류: %s", exc)
        return format_message('error', f'조회 실패: {exc}')


def cmd_fulfillment_check(order_id: str) -> str:
    """/fulfillment_check <order_id> — 이행 가능성 확인."""
    from .formatters import format_message

    order_id = order_id.strip()
    if not order_id:
        return format_message('error', '주문 ID를 입력해주세요.\n사용법: /fulfillment_check <order_id>')
    try:
        from src.order_matching.fulfillment_checker import FulfillmentChecker

        checker = FulfillmentChecker()
        results = checker.check_fulfillment(order_id)
        lines = [f'✅ *이행 확인: `{order_id}`*\n']
        for r in results:
            avail = '✅ 이행가능' if r.is_available else '❌ 이행불가'
            lines.append(f'• [{r.product_id}] {avail}')
            if r.issues:
                lines.append(f'  └ 사유: {", ".join(r.issues)}')
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_fulfillment_check 오류: %s", exc)
        return format_message('error', f'이행 확인 실패: {exc}')


def cmd_fulfillment_risk(order_id: str = '') -> str:
    """/fulfillment_risk [order_id] — 주문 리스크 평가."""
    from .formatters import format_message

    try:
        from src.order_matching.risk_assessor import OrderRiskAssessor, RiskLevel

        assessor = OrderRiskAssessor()
        if order_id.strip():
            assessment = assessor.assess_order_risk(order_id.strip())
            level_icon = {
                'low': '🟢', 'medium': '🟡', 'high': '🟠', 'critical': '🔴',
            }.get(assessment.risk_level.value, '❓')
            lines = [
                f'⚠️ *리스크 평가: `{order_id}`*\n',
                f'• 종합 점수: {assessment.overall_risk_score:.1f}/100',
                f'• 리스크 등급: {level_icon} {assessment.risk_level.value}',
            ]
            if assessment.recommendations:
                lines.append('• 권고사항:')
                for rec in assessment.recommendations:
                    lines.append(f'  - {rec}')
        else:
            summary = assessor.get_risk_summary()
            lines = [
                '⚠️ *리스크 현황 요약*\n',
                f'• 전체: {summary["total"]}건',
                f'• 🟢 낮음: {summary["low"]}건',
                f'• 🟡 중간: {summary["medium"]}건',
                f'• 🟠 높음: {summary["high"]}건',
                f'• 🔴 위험: {summary["critical"]}건',
            ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_fulfillment_risk 오류: %s", exc)
        return format_message('error', f'리스크 평가 실패: {exc}')


def cmd_sla_status(order_id: str = '') -> str:
    """/sla_status [order_id] — SLA 현황."""
    from .formatters import format_message

    try:
        from src.order_matching.sla_tracker import FulfillmentSLATracker

        tracker = FulfillmentSLATracker()
        if order_id.strip():
            status = tracker.get_sla_status(order_id.strip())
            if not status:
                return format_message('warning', f'SLA 추적 없음: `{order_id}`')
            overdue_icon = '🔴 초과' if status.is_overdue else '🟢 정상'
            lines = [
                f'⏱ *SLA 현황: `{order_id}`*\n',
                f'• 단계: {status.stage.value}',
                f'• 상태: {overdue_icon}',
                f'• 경과: {status.elapsed_hours:.1f}시간',
                f'• 남은: {status.remaining_hours:.1f}시간',
            ]
        else:
            perf = tracker.get_sla_performance()
            lines = [
                '⏱ *SLA 전체 현황*\n',
                f'• 전체: {perf["total"]}건',
                f'• 정상: {perf["on_time"]}건',
                f'• 초과: {perf["overdue"]}건',
                f'• 달성률: {perf["achievement_rate"]:.1f}%',
            ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_sla_status 오류: %s", exc)
        return format_message('error', f'SLA 조회 실패: {exc}')


def cmd_sla_overdue() -> str:
    """/sla_overdue — SLA 초과 주문 목록."""
    from .formatters import format_message

    try:
        from src.order_matching.sla_tracker import FulfillmentSLATracker

        tracker = FulfillmentSLATracker()
        overdue = tracker.get_overdue_orders()
        if not overdue:
            return format_message('info', '✅ SLA 초과 주문 없음')
        lines = [f'🔴 *SLA 초과 주문: {len(overdue)}건*\n']
        for s in overdue[:10]:
            lines.append(
                f'• [{s.order_id}] {s.stage.value} | 경과: {s.elapsed_hours:.1f}시간'
            )
        return format_message('warning', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_sla_overdue 오류: %s", exc)
        return format_message('error', f'SLA 초과 조회 실패: {exc}')


def cmd_source_priority(product_id: str) -> str:
    """/source_priority <product_id> — 소싱처 우선순위 조회."""
    from .formatters import format_message

    product_id = product_id.strip()
    if not product_id:
        return format_message('error', '상품 ID를 입력해주세요.\n사용법: /source_priority <product_id>')
    try:
        from src.order_matching.source_priority import SourcePriorityManager

        manager = SourcePriorityManager()
        priorities = manager.get_priorities(product_id)
        if not priorities:
            return format_message('warning', f'우선순위 없음: `{product_id}`')
        lines = [f'📊 *소싱처 우선순위: `{product_id}`*\n']
        for p in priorities:
            tag = '⭐ 주' if p.is_primary else '🔄 백업'
            lines.append(
                f'  {p.priority_rank}. {tag} {p.source_id} | 점수: {p.score:.1f}'
            )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_source_priority 오류: %s", exc)
        return format_message('error', f'우선순위 조회 실패: {exc}')


def cmd_matching_dashboard() -> str:
    """/matching_dashboard — 매칭 대시보드 요약."""
    from .formatters import format_message

    try:
        from src.order_matching.matcher import OrderSourceMatcher
        from src.order_matching.order_matching_dashboard import OrderMatchingDashboard

        dashboard = OrderMatchingDashboard(matcher=OrderSourceMatcher())
        data = dashboard.get_dashboard_data()
        ms = data.get('matching_summary', {})
        lines = [
            '📊 *주문 매칭 대시보드*\n',
            f'• 전체 매칭: {ms.get("total", 0)}건',
            f'• 이행가능: {ms.get("fulfillable", 0)}건',
            f'• 이행불가: {ms.get("unfulfillable", 0)}건',
            f'• 위험: {ms.get("risky", 0)}건',
            f'• 성공률: {ms.get("success_rate", 0.0):.1f}%',
        ]
        sla = data.get('sla_summary', {})
        perf = sla.get('performance', {})
        if perf:
            lines.append(
                f'\n• SLA 달성률: {perf.get("achievement_rate", 0.0):.1f}%'
                f' (초과: {sla.get("overdue_count", 0)}건)'
            )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_matching_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


def cmd_unfulfillable() -> str:
    """/unfulfillable — 이행 불가 상품 목록."""
    from .formatters import format_message

    try:
        from src.order_matching.fulfillment_checker import FulfillmentChecker

        checker = FulfillmentChecker()
        actions = checker.get_unfulfillable_actions()
        if not actions:
            return format_message('info', '✅ 이행 불가 상품 없음')
        lines = [f'❌ *이행 불가: {len(actions)}건*\n']
        by_reason: dict = {}
        for a in actions:
            r = a.get('reason', 'unknown')
            by_reason[r] = by_reason.get(r, 0) + 1
        for reason, count in by_reason.items():
            lines.append(f'• {reason}: {count}건')
        return format_message('warning', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_unfulfillable 오류: %s", exc)
        return format_message('error', f'이행 불가 조회 실패: {exc}')


def cmd_high_risk_orders() -> str:
    """/high_risk_orders — 고위험 주문 목록."""
    from .formatters import format_message

    try:
        from src.order_matching.risk_assessor import OrderRiskAssessor

        assessor = OrderRiskAssessor()
        high_risk = assessor.get_high_risk_orders()
        if not high_risk:
            return format_message('info', '✅ 고위험 주문 없음')
        lines = [f'🔴 *고위험 주문: {len(high_risk)}건*\n']
        for a in high_risk[:10]:
            lines.append(
                f'• [{a.order_id}] {a.risk_level.value} | 점수: {a.overall_risk_score:.0f}'
            )
        return format_message('warning', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_high_risk_orders 오류: %s", exc)
        return format_message('error', f'고위험 주문 조회 실패: {exc}')
