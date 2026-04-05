"""src/api/data_pipeline_api.py — 데이터 파이프라인 API Blueprint (Phase 100).

Blueprint: /api/v1/data-pipeline

엔드포인트:
  POST /pipelines                              — 파이프라인 생성
  GET  /pipelines                              — 파이프라인 목록
  GET  /pipelines/<pipeline_id>               — 파이프라인 상세
  PUT  /pipelines/<pipeline_id>               — 파이프라인 수정
  DELETE /pipelines/<pipeline_id>             — 파이프라인 삭제
  POST /pipelines/<pipeline_id>/run           — 파이프라인 실행
  GET  /pipelines/<pipeline_id>/history       — 실행 이력
  GET  /sources                               — 데이터 소스 목록
  GET  /warehouse/tables                      — 웨어하우스 테이블 목록
  GET  /warehouse/tables/<table_name>         — 테이블 상세
  POST /warehouse/query                       — 쿼리 실행
  GET  /quality/reports                       — 품질 리포트
  POST /quality/check                         — 품질 검사 실행
  GET  /views                                 — 분석 뷰 목록
  POST /views/<view_name>/refresh             — 뷰 새로고침
  GET  /dashboard                             — ETL 대시보드
  GET  /lineage/<table_name>                  — 데이터 리니지
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

data_pipeline_bp = Blueprint("data_pipeline", __name__, url_prefix="/api/v1/data-pipeline")

# ── 지연 초기화 싱글턴 ────────────────────────────────────────────────────

_engine = None
_warehouse = None
_source_registry = None
_quality_checker = None
_view_manager = None
_monitor = None
_dashboard = None
_lineage_tracker = None


def _get_services():
    global _engine, _warehouse, _source_registry, _quality_checker
    global _view_manager, _monitor, _dashboard, _lineage_tracker

    if _engine is None:
        from ..data_pipeline.etl_engine import ETLEngine
        from ..data_pipeline.data_warehouse import DataWarehouse
        from ..data_pipeline.data_sources import (
            SourceRegistry, InternalDBSource, APISource, FileSource, EventStreamSource,
        )
        from ..data_pipeline.data_quality import DataQualityChecker
        from ..data_pipeline.analytics_views import AnalyticsViewManager
        from ..data_pipeline.pipeline_monitor import PipelineMonitor, ETLDashboard, LineageTracker

        _engine = ETLEngine()
        _warehouse = DataWarehouse()
        _source_registry = SourceRegistry()
        _quality_checker = DataQualityChecker()
        _view_manager = AnalyticsViewManager(_warehouse)
        _monitor = PipelineMonitor()
        _dashboard = ETLDashboard(_engine, _warehouse, _monitor)
        _lineage_tracker = LineageTracker()

        # 기본 데이터 소스 등록
        _source_registry.register(InternalDBSource())
        _source_registry.register(APISource())
        _source_registry.register(FileSource())
        _source_registry.register(EventStreamSource())


# ── 파이프라인 관리 ───────────────────────────────────────────────────────

@data_pipeline_bp.post("/pipelines")
def create_pipeline():
    try:
        _get_services()
        data = request.get_json(force=True) or {}
        pipeline = _engine.create_pipeline(
            name=data.get("name", "unnamed"),
            source=data.get("source", "internal_db"),
            transforms=data.get("transforms", []),
            destination=data.get("destination", "dw_default"),
            schedule=data.get("schedule", ""),
            metadata=data.get("metadata", {}),
        )
        return jsonify(pipeline.to_dict()), 201
    except Exception as exc:
        logger.error("create_pipeline 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.get("/pipelines")
def list_pipelines():
    try:
        _get_services()
        pipelines = _engine.list_pipelines()
        return jsonify([p.to_dict() for p in pipelines]), 200
    except Exception as exc:
        logger.error("list_pipelines 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.get("/pipelines/<pipeline_id>")
def get_pipeline(pipeline_id: str):
    try:
        _get_services()
        pipeline = _engine.get_pipeline(pipeline_id)
        if pipeline is None:
            return jsonify({"error": "파이프라인을 찾을 수 없습니다"}), 404
        return jsonify(pipeline.to_dict()), 200
    except Exception as exc:
        logger.error("get_pipeline 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.put("/pipelines/<pipeline_id>")
def update_pipeline(pipeline_id: str):
    try:
        _get_services()
        data = request.get_json(force=True) or {}
        pipeline = _engine.update_pipeline(pipeline_id, **data)
        if pipeline is None:
            return jsonify({"error": "파이프라인을 찾을 수 없습니다"}), 404
        return jsonify(pipeline.to_dict()), 200
    except Exception as exc:
        logger.error("update_pipeline 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.delete("/pipelines/<pipeline_id>")
def delete_pipeline(pipeline_id: str):
    try:
        _get_services()
        deleted = _engine.delete_pipeline(pipeline_id)
        if not deleted:
            return jsonify({"error": "파이프라인을 찾을 수 없습니다"}), 404
        return jsonify({"deleted": pipeline_id}), 200
    except Exception as exc:
        logger.error("delete_pipeline 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.post("/pipelines/<pipeline_id>/run")
def run_pipeline(pipeline_id: str):
    try:
        _get_services()
        record = _engine.run_pipeline(pipeline_id)
        pipeline = _engine.get_pipeline(pipeline_id)
        if pipeline:
            _lineage_tracker.record_lineage(pipeline)
        _monitor.record_run(record, duration_sec=1.0)
        return jsonify(record.to_dict()), 200
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        logger.error("run_pipeline 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.get("/pipelines/<pipeline_id>/history")
def get_run_history(pipeline_id: str):
    try:
        _get_services()
        history = _engine.get_run_history(pipeline_id)
        return jsonify([r.to_dict() for r in history]), 200
    except Exception as exc:
        logger.error("get_run_history 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── 데이터 소스 ───────────────────────────────────────────────────────────

@data_pipeline_bp.get("/sources")
def list_sources():
    try:
        _get_services()
        return jsonify(_source_registry.list_sources()), 200
    except Exception as exc:
        logger.error("list_sources 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── 웨어하우스 ────────────────────────────────────────────────────────────

@data_pipeline_bp.get("/warehouse/tables")
def list_warehouse_tables():
    try:
        _get_services()
        tables = _warehouse.list_tables()
        return jsonify([t.to_dict() for t in tables]), 200
    except Exception as exc:
        logger.error("list_warehouse_tables 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.get("/warehouse/tables/<table_name>")
def get_warehouse_table(table_name: str):
    try:
        _get_services()
        table = _warehouse.get_table(table_name)
        if table is None:
            return jsonify({"error": "테이블을 찾을 수 없습니다"}), 404
        return jsonify({
            **table.to_dict(),
            "sample": _warehouse.get_sample(table_name, n=5),
        }), 200
    except Exception as exc:
        logger.error("get_warehouse_table 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.post("/warehouse/query")
def warehouse_query():
    try:
        _get_services()
        from ..data_pipeline.analytics_views import QueryEngine
        data = request.get_json(force=True) or {}
        engine = QueryEngine(_warehouse)
        result = engine.execute(data)
        return jsonify({"rows": result, "count": len(result)}), 200
    except Exception as exc:
        logger.error("warehouse_query 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── 데이터 품질 ───────────────────────────────────────────────────────────

@data_pipeline_bp.get("/quality/reports")
def get_quality_reports():
    try:
        _get_services()
        table_name = request.args.get("table")
        reports = _quality_checker.get_reports(table_name)
        return jsonify([r.to_dict() for r in reports]), 200
    except Exception as exc:
        logger.error("get_quality_reports 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.post("/quality/check")
def run_quality_check():
    try:
        _get_services()
        from ..data_pipeline.data_quality import NotNullRule, RangeRule
        req = request.get_json(force=True) or {}
        table_name = req.get("table", "")
        threshold = float(req.get("threshold", 80.0))

        data = _warehouse.query(table_name) if table_name else req.get("data", [])
        if not data:
            data = [{"id": str(i), "value": i} for i in range(10)]

        # 기본 규칙 추가
        checker_copy = _quality_checker
        report = checker_copy.check(data, table_name or "adhoc")
        alert = checker_copy.check_threshold(report, threshold)

        return jsonify({
            "report": report.to_dict(),
            "alert": alert.to_dict() if alert else None,
        }), 200
    except Exception as exc:
        logger.error("run_quality_check 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── 분석 뷰 ──────────────────────────────────────────────────────────────

@data_pipeline_bp.get("/views")
def list_views():
    try:
        _get_services()
        views = _view_manager.list_views()
        return jsonify([v.to_dict() for v in views]), 200
    except Exception as exc:
        logger.error("list_views 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.post("/views/<view_name>/refresh")
def refresh_view(view_name: str):
    try:
        _get_services()
        # 뷰가 없으면 빈 뷰 생성
        if _view_manager.get_view(view_name) is None:
            _view_manager.create_view(view_name, {"table": view_name})
        view = _view_manager.refresh_view(view_name)
        return jsonify(view.to_dict()), 200
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        logger.error("refresh_view 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── 대시보드 & 리니지 ─────────────────────────────────────────────────────

@data_pipeline_bp.get("/dashboard")
def get_dashboard():
    try:
        _get_services()
        return jsonify(_dashboard.get_summary()), 200
    except Exception as exc:
        logger.error("get_dashboard 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@data_pipeline_bp.get("/lineage/<table_name>")
def get_lineage(table_name: str):
    try:
        _get_services()
        lineage = _lineage_tracker.get_table_lineage(table_name)
        return jsonify({"table_name": table_name, "lineage": lineage}), 200
    except Exception as exc:
        logger.error("get_lineage 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500
