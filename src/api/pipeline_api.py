"""src/api/pipeline_api.py — 작업 파이프라인 API Blueprint (Phase 58)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

pipeline_bp = Blueprint("pipeline", __name__, url_prefix="/api/v1/pipelines")

_executor = None
_monitor = None
_pipelines: dict = {}


def _get_services():
    global _executor, _monitor
    if _executor is None:
        from ..pipeline.pipeline_executor import PipelineExecutor
        from ..pipeline.pipeline_monitor import PipelineMonitor
        _executor = PipelineExecutor()
        _monitor = PipelineMonitor()
    return _executor, _monitor


@pipeline_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "pipeline"})


@pipeline_bp.post("/create")
def create_pipeline():
    data = request.get_json(force=True) or {}
    name = data.get("name", "")
    stage_names = data.get("stages", [])
    if not name:
        return jsonify({"error": "파이프라인 이름 필요"}), 400

    from ..pipeline.pipeline_builder import PipelineBuilder
    from ..pipeline.stages.collect_stage import CollectStage
    from ..pipeline.stages.translate_stage import TranslateStage
    from ..pipeline.stages.price_calculate_stage import PriceCalculateStage
    from ..pipeline.stages.upload_stage import UploadStage

    stage_map = {
        "collect": CollectStage,
        "translate": TranslateStage,
        "price_calculate": PriceCalculateStage,
        "upload": UploadStage,
    }
    builder = PipelineBuilder(name=name)
    for s in (stage_names or list(stage_map.keys())):
        if s in stage_map:
            builder.add_stage(stage_map[s]())
    pipeline = builder.build()
    _pipelines[name] = pipeline
    return jsonify({"created": name, "stages": [s.name for s in pipeline.stages]}), 201


@pipeline_bp.post("/run")
def run_pipeline():
    executor, monitor = _get_services()
    data = request.get_json(force=True) or {}
    name = data.get("name", "")
    context = data.get("context", {})

    if name not in _pipelines:
        # Auto-create default pipeline
        from ..pipeline.pipeline_builder import PipelineBuilder
        from ..pipeline.stages.collect_stage import CollectStage
        from ..pipeline.stages.translate_stage import TranslateStage
        from ..pipeline.stages.price_calculate_stage import PriceCalculateStage
        from ..pipeline.stages.upload_stage import UploadStage
        builder = PipelineBuilder(name=name or "default")
        for s in [CollectStage(), TranslateStage(), PriceCalculateStage(), UploadStage()]:
            builder.add_stage(s)
        _pipelines[name or "default"] = builder.build()

    pipeline = _pipelines.get(name) or _pipelines.get("default")
    results = executor.execute(pipeline, context)
    monitor.record_execution(pipeline.name, results)
    return jsonify({
        "pipeline": pipeline.name,
        "results": {k: v.to_dict() for k, v in results.items()},
    })


@pipeline_bp.get("/status/<name>")
def get_status(name: str):
    _, monitor = _get_services()
    return jsonify(monitor.get_stats(name))


@pipeline_bp.get("/history")
def get_history():
    executor, _ = _get_services()
    return jsonify({"history": executor.get_execution_history()})
