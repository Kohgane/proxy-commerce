"""src/api/finance_automation_api.py — Phase 119: 정산/회계 자동화 API.

Blueprint: /api/v1/finance

엔드포인트:
  POST /revenue/recognize            — 매출 인식
  POST /cost/record                  — 매입 원가 기록
  GET  /ledger                       — 원장 조회 (?account=&from=&to=)
  GET  /settlements                  — 정산 배치 목록 (?channel=)
  POST /settlements/<batch_id>/finalize — 정산 확정
  POST /period/close                 — 기간 마감 ({type, date})
  GET  /period/<type>/<key>          — 마감 레코드 조회
  GET  /statements                   — 재무제표 (?type=pnl|bs|cf&period=)
  GET  /tax-report                   — 세무 리포트 (?period=&format=json|csv)
  GET  /anomalies                    — 이상 감지 결과
  GET  /fx-pnl                       — FX 손익 목록 (?period=)
  GET  /metrics                      — 자동화 메트릭
"""
from __future__ import annotations

import logging

from flask import Blueprint, Response, jsonify, request

logger = logging.getLogger(__name__)

finance_automation_bp = Blueprint(
    'finance_automation',
    __name__,
    url_prefix='/api/v1/finance',
)

# 싱글톤 매니저 (지연 초기화)
_manager = None


def _get_manager():
    """FinanceAutomationManager 싱글톤 반환."""
    global _manager
    if _manager is None:
        from ..finance_automation.automation_manager import FinanceAutomationManager
        _manager = FinanceAutomationManager()
    return _manager


# ─── 매출 인식 ──────────────────────────────────────────────────────────────

@finance_automation_bp.post('/revenue/recognize')
def recognize_revenue():
    """POST /api/v1/finance/revenue/recognize — 매출 인식."""
    data = request.get_json(force=True, silent=True) or {}
    if not data.get('order_id'):
        return jsonify({'error': 'order_id는 필수입니다.'}), 400
    try:
        mgr = _get_manager()
        record = mgr._recognizer.recognize(data)
        mgr._revenue_records.append(record)
        return jsonify({
            'order_id': record.order_id,
            'channel': record.channel,
            'gross_amount': str(record.gross_amount),
            'net_amount': str(record.net_amount),
            'currency': record.currency,
            'recognized_at': record.recognized_at,
        }), 201
    except Exception as exc:
        logger.error("매출 인식 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 매입 원가 기록 ─────────────────────────────────────────────────────────

@finance_automation_bp.post('/cost/record')
def record_cost():
    """POST /api/v1/finance/cost/record — 매입 원가 기록."""
    data = request.get_json(force=True, silent=True) or {}
    if not data.get('purchase_id'):
        return jsonify({'error': 'purchase_id는 필수입니다.'}), 400
    try:
        mgr = _get_manager()
        record = mgr.record_cost(data)
        return jsonify({
            'purchase_id': record.purchase_id,
            'source': record.source,
            'cogs': str(record.cogs),
            'shipping': str(record.shipping),
            'customs': str(record.customs),
            'currency': record.currency,
        }), 201
    except Exception as exc:
        logger.error("매입 기록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 원장 조회 ───────────────────────────────────────────────────────────────

@finance_automation_bp.get('/ledger')
def get_ledger():
    """GET /api/v1/finance/ledger — 원장 조회 (?account=&from=&to=)."""
    account = request.args.get('account', '')
    from_date = request.args.get('from', '')
    to_date = request.args.get('to', '')
    try:
        mgr = _get_manager()
        entries = mgr.get_ledger_entries(account, from_date, to_date)
        return jsonify({
            'entries': [
                {
                    'entry_id': e.entry_id,
                    'date': e.date,
                    'account': e.account,
                    'debit': str(e.debit),
                    'credit': str(e.credit),
                    'currency': e.currency,
                    'memo': e.memo,
                    'locked': e.locked,
                }
                for e in entries
            ],
            'total': len(entries),
        }), 200
    except Exception as exc:
        logger.error("원장 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 정산 목록 ───────────────────────────────────────────────────────────────

@finance_automation_bp.get('/settlements')
def list_settlements():
    """GET /api/v1/finance/settlements — 정산 배치 목록 (?channel=)."""
    channel = request.args.get('channel', '')
    try:
        mgr = _get_manager()
        batches = mgr.get_settlements(channel)
        return jsonify({
            'batches': [
                {
                    'batch_id': b.batch_id,
                    'channel': b.channel,
                    'period_start': b.period_start,
                    'period_end': b.period_end,
                    'gross': str(b.gross),
                    'fees': str(b.fees),
                    'net': str(b.net),
                    'status': b.status,
                }
                for b in batches
            ],
            'total': len(batches),
        }), 200
    except Exception as exc:
        logger.error("정산 목록 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 정산 확정 ───────────────────────────────────────────────────────────────

@finance_automation_bp.post('/settlements/<batch_id>/finalize')
def finalize_settlement(batch_id: str):
    """POST /api/v1/finance/settlements/<batch_id>/finalize — 정산 확정."""
    try:
        mgr = _get_manager()
        batch = mgr._settlement.finalize_batch(batch_id)
        return jsonify({
            'batch_id': batch.batch_id,
            'status': batch.status,
            'net': str(batch.net),
        }), 200
    except KeyError:
        return jsonify({'error': '정산 배치를 찾을 수 없습니다.'}), 404
    except Exception as exc:
        logger.error("정산 확정 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 기간 마감 ───────────────────────────────────────────────────────────────

@finance_automation_bp.post('/period/close')
def close_period():
    """POST /api/v1/finance/period/close — 기간 마감 ({type, date})."""
    data = request.get_json(force=True, silent=True) or {}
    period_type = data.get('type', 'daily')
    date_key = data.get('date', '')
    if not date_key:
        return jsonify({'error': 'date는 필수입니다.'}), 400
    try:
        mgr = _get_manager()
        if period_type == 'daily':
            close = mgr.run_daily_close(date_key)
        elif period_type == 'weekly':
            close = mgr.run_weekly_close(date_key)
        elif period_type == 'monthly':
            close = mgr.run_monthly_close(date_key)
        else:
            return jsonify({'error': f'지원하지 않는 기간 유형: {period_type}'}), 400
        return jsonify({
            'period': close.period,
            'type': close.type,
            'status': close.status,
            'closed_at': close.closed_at,
            'totals': close.totals,
        }), 200
    except Exception as exc:
        logger.error("기간 마감 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 기간 마감 조회 ──────────────────────────────────────────────────────────

@finance_automation_bp.get('/period/<period_type>/<key>')
def get_period_close(period_type: str, key: str):
    """GET /api/v1/finance/period/<type>/<key> — 마감 레코드 조회."""
    try:
        mgr = _get_manager()
        close = mgr._period_closer.get_close(period_type, key)
        if close is None:
            return jsonify({'error': '마감 레코드를 찾을 수 없습니다.'}), 404
        return jsonify({
            'period': close.period,
            'type': close.type,
            'status': close.status,
            'closed_at': close.closed_at,
            'totals': close.totals,
        }), 200
    except Exception as exc:
        logger.error("마감 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 재무제표 ────────────────────────────────────────────────────────────────

@finance_automation_bp.get('/statements')
def get_statement():
    """GET /api/v1/finance/statements — 재무제표 (?type=pnl|bs|cf&period=)."""
    stmt_type = request.args.get('type', 'pnl')
    period = request.args.get('period', '')
    if not period:
        return jsonify({'error': 'period는 필수입니다.'}), 400
    try:
        mgr = _get_manager()
        stmt = mgr.generate_statement(stmt_type, period)
        return jsonify({
            'type': stmt.type,
            'period': stmt.period,
            'line_items': stmt.line_items,
            'totals': stmt.totals,
        }), 200
    except ValueError:
        return jsonify({'error': '지원하지 않는 재무제표 유형입니다.'}), 400
    except Exception as exc:
        logger.error("재무제표 생성 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 세무 리포트 ─────────────────────────────────────────────────────────────

@finance_automation_bp.get('/tax-report')
def get_tax_report():
    """GET /api/v1/finance/tax-report — 세무 리포트 (?period=&format=json|csv)."""
    period = request.args.get('period', '')
    fmt = request.args.get('format', 'json')
    if not period:
        return jsonify({'error': 'period는 필수입니다.'}), 400
    try:
        mgr = _get_manager()
        report = mgr.generate_tax_report(period)
        if fmt == 'csv':
            csv_str = mgr._tax_reporter.export_csv(report)
            return Response(csv_str, mimetype='text/csv'), 200
        json_str = mgr._tax_reporter.export_json(report)
        return Response(json_str, mimetype='application/json'), 200
    except Exception as exc:
        logger.error("세무 리포트 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 이상 감지 ───────────────────────────────────────────────────────────────

@finance_automation_bp.get('/anomalies')
def get_anomalies():
    """GET /api/v1/finance/anomalies — 이상 감지 결과."""
    try:
        mgr = _get_manager()
        anomalies = mgr.get_anomalies()
        return jsonify({
            'anomalies': [
                {
                    'type': a.type,
                    'severity': a.severity,
                    'reference': a.reference,
                    'detected_at': a.detected_at,
                    'detail': a.detail,
                }
                for a in anomalies
            ],
            'total': len(anomalies),
        }), 200
    except Exception as exc:
        logger.error("이상 감지 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── FX 손익 ─────────────────────────────────────────────────────────────────

@finance_automation_bp.get('/fx-pnl')
def get_fx_pnl():
    """GET /api/v1/finance/fx-pnl — FX 손익 목록 (?period=)."""
    period = request.args.get('period', '')
    try:
        mgr = _get_manager()
        pnls = mgr.get_fx_pnls(period)
        return jsonify({
            'fx_pnls': [
                {
                    'purchase_id': p.purchase_id,
                    'fx_at_purchase': str(p.fx_at_purchase),
                    'fx_at_settlement': str(p.fx_at_settlement),
                    'realized_pnl_krw': str(p.realized_pnl_krw),
                }
                for p in pnls
            ],
            'total': len(pnls),
        }), 200
    except Exception as exc:
        logger.error("FX 손익 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 메트릭 ──────────────────────────────────────────────────────────────────

@finance_automation_bp.get('/metrics')
def get_metrics():
    """GET /api/v1/finance/metrics — 자동화 메트릭."""
    try:
        mgr = _get_manager()
        return jsonify(mgr.metrics()), 200
    except Exception as exc:
        logger.error("메트릭 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
