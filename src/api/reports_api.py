"""src/api/reports_api.py — 리포트 API.

Flask Blueprint 기반 리포트 생성 API.

엔드포인트:
  GET  /api/reports/sales       — 매출 리포트
  GET  /api/reports/inventory   — 재고 리포트
  GET  /api/reports/customers   — 고객 리포트
  GET  /api/reports/marketing   — 마케팅 리포트
  POST /api/reports/generate    — 리포트 생성

환경변수:
  DASHBOARD_API_KEY  — API 인증 키
"""

import logging

from flask import Blueprint, jsonify, request

from .auth_middleware import require_api_key

logger = logging.getLogger(__name__)

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


def _get_builder():
    """ReportBuilder 인스턴스를 반환한다."""
    from ..reporting.report_builder import ReportBuilder
    return ReportBuilder()


@reports_bp.get("/sales")
@require_api_key
def get_sales_report():
    """매출 리포트를 반환한다.

    쿼리 파라미터:
      start — 시작일 (YYYY-MM-DD)
      end   — 종료일 (YYYY-MM-DD)
    """
    start = request.args.get("start")
    end = request.args.get("end")
    builder = _get_builder()
    try:
        report = builder.generate_report("sales", start_date=start, end_date=end)
    except Exception as exc:
        logger.warning("매출 리포트 생성 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify(report)


@reports_bp.get("/inventory")
@require_api_key
def get_inventory_report():
    """재고 리포트를 반환한다."""
    builder = _get_builder()
    try:
        report = builder.generate_report("inventory")
    except Exception as exc:
        logger.warning("재고 리포트 생성 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify(report)


@reports_bp.get("/customers")
@require_api_key
def get_customer_report():
    """고객 리포트를 반환한다."""
    builder = _get_builder()
    try:
        report = builder.generate_report("customers")
    except Exception as exc:
        logger.warning("고객 리포트 생성 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify(report)


@reports_bp.get("/marketing")
@require_api_key
def get_marketing_report():
    """마케팅 리포트를 반환한다."""
    builder = _get_builder()
    try:
        report = builder.generate_report("marketing")
    except Exception as exc:
        logger.warning("마케팅 리포트 생성 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify(report)


@reports_bp.post("/generate")
@require_api_key
def generate_report():
    """지정된 타입의 리포트를 생성한다.

    body: {
      "report_type": "sales" | "inventory" | "customers" | "marketing",
      "start_date": "YYYY-MM-DD" (선택),
      "end_date": "YYYY-MM-DD" (선택)
    }
    """
    data = request.get_json(silent=True) or {}
    report_type = data.get("report_type", "sales")
    start_date = data.get("start_date")
    end_date = data.get("end_date")

    builder = _get_builder()
    try:
        report = builder.generate_report(report_type, start_date=start_date, end_date=end_date)
    except Exception as exc:
        logger.warning("리포트 생성 실패 (%s): %s", report_type, exc)
        return jsonify({"error": str(exc)}), 500

    if "error" in report:
        return jsonify(report), 400
    return jsonify(report)
