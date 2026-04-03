"""tests/test_pipeline.py — Phase 58: 작업 파이프라인 테스트."""
from __future__ import annotations

import pytest
from src.pipeline.stage import Stage
from src.pipeline.stage_result import StageResult
from src.pipeline.pipeline import Pipeline
from src.pipeline.pipeline_builder import PipelineBuilder
from src.pipeline.pipeline_executor import PipelineExecutor
from src.pipeline.pipeline_monitor import PipelineMonitor
from src.pipeline.stages.collect_stage import CollectStage
from src.pipeline.stages.translate_stage import TranslateStage
from src.pipeline.stages.price_calculate_stage import PriceCalculateStage
from src.pipeline.stages.upload_stage import UploadStage


class SuccessStage(Stage):
    name = "success_stage"

    def process(self, context: dict) -> StageResult:
        context["success_stage_ran"] = True
        return StageResult(status="success", output="done")


class FailStage(Stage):
    name = "fail_stage"

    def process(self, context: dict) -> StageResult:
        return StageResult(status="failure", error_message="intentional failure")

    def rollback(self, context: dict) -> None:
        context["rolled_back"] = True


class SkipStage(Stage):
    name = "skip_stage"

    def validate(self, context: dict) -> bool:
        return False

    def process(self, context: dict) -> StageResult:
        return StageResult(status="success")


class TestStageResult:
    def test_success(self):
        result = StageResult(status="success")
        assert result.success is True
        assert result.failed is False

    def test_failure(self):
        result = StageResult(status="failure", error_message="oops")
        assert result.failed is True
        assert result.success is False

    def test_to_dict(self):
        result = StageResult(status="success", duration_ms=10.5, output="data")
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["duration_ms"] == 10.5


class TestPipeline:
    def test_run_success(self):
        pipeline = Pipeline(name="test", stages=[SuccessStage()])
        context = {}
        results = pipeline.run(context)
        assert results["success_stage"].status == "success"
        assert context.get("success_stage_ran") is True

    def test_run_failure_triggers_rollback(self):
        pipeline = Pipeline(name="test", stages=[SuccessStage(), FailStage()])
        context = {}
        results = pipeline.run(context)
        assert results["fail_stage"].status == "failure"

    def test_skip_stage(self):
        pipeline = Pipeline(name="test", stages=[SkipStage()])
        results = pipeline.run({})
        assert results["skip_stage"].status == "skipped"

    def test_multiple_stages(self):
        pipeline = Pipeline(name="test", stages=[SuccessStage(), SkipStage()])
        results = pipeline.run({})
        assert len(results) == 2


class TestPipelineBuilder:
    def test_build_pipeline(self):
        pipeline = (
            PipelineBuilder(name="my_pipeline")
            .add_stage(SuccessStage())
            .add_stage(SkipStage())
            .build()
        )
        assert pipeline.name == "my_pipeline"
        assert len(pipeline.stages) == 2

    def test_fluent_interface(self):
        builder = PipelineBuilder()
        result = builder.add_stage(SuccessStage())
        assert result is builder  # fluent returns self


class TestPipelineExecutor:
    def setup_method(self):
        self.executor = PipelineExecutor()

    def test_execute(self):
        pipeline = PipelineBuilder(name="p").add_stage(SuccessStage()).build()
        results = self.executor.execute(pipeline, {})
        assert "success_stage" in results

    def test_execute_async(self):
        pipeline = PipelineBuilder(name="p").add_stage(SuccessStage()).build()
        results = self.executor.execute_async(pipeline, {})
        assert "success_stage" in results

    def test_history_recorded(self):
        pipeline = PipelineBuilder(name="p").add_stage(SuccessStage()).build()
        self.executor.execute(pipeline, {})
        history = self.executor.get_execution_history()
        assert len(history) == 1
        assert history[0]["pipeline_name"] == "p"


class TestPipelineMonitor:
    def setup_method(self):
        self.monitor = PipelineMonitor()

    def test_record_and_get_stats(self):
        results = {"success_stage": StageResult(status="success", duration_ms=10)}
        self.monitor.record_execution("my_pipeline", results)
        stats = self.monitor.get_stats("my_pipeline")
        assert stats["runs"] == 1
        assert stats["successes"] == 1
        assert stats["success_rate"] == 100.0

    def test_failure_stats(self):
        results = {"fail": StageResult(status="failure", duration_ms=5)}
        self.monitor.record_execution("p", results)
        stats = self.monitor.get_stats("p")
        assert stats["failures"] == 1

    def test_get_all_stats(self):
        self.monitor.record_execution("p1", {"s": StageResult(status="success")})
        self.monitor.record_execution("p2", {"s": StageResult(status="failure")})
        all_stats = self.monitor.get_all_stats()
        assert len(all_stats) == 2


class TestBuiltinStages:
    def test_collect_stage(self):
        stage = CollectStage()
        ctx = {}
        result = stage.process(ctx)
        assert result.success
        assert "collected" in ctx

    def test_translate_stage(self):
        stage = TranslateStage()
        ctx = {"collected": [{"id": "1", "name": "product", "price": 1000}]}
        result = stage.process(ctx)
        assert result.success
        assert ctx["translated"][0]["name_translated"]

    def test_translate_stage_validate_false(self):
        stage = TranslateStage()
        assert stage.validate({}) is False
        assert stage.validate({"collected": [{"id": "1"}]}) is True

    def test_price_calculate_stage(self):
        stage = PriceCalculateStage(markup_rate=1.5)
        ctx = {"collected": [{"id": "1", "name": "p", "price": 1000}]}
        result = stage.process(ctx)
        assert result.success
        assert ctx["priced"][0]["final_price"] == 1500

    def test_upload_stage(self):
        stage = UploadStage()
        ctx = {"collected": [{"id": "1"}, {"id": "2"}]}
        result = stage.process(ctx)
        assert result.success
        assert len(ctx["uploaded_ids"]) == 2

    def test_full_pipeline(self):
        pipeline = (
            PipelineBuilder(name="full")
            .add_stage(CollectStage())
            .add_stage(TranslateStage())
            .add_stage(PriceCalculateStage())
            .add_stage(UploadStage())
            .build()
        )
        results = pipeline.run({})
        assert all(r.status == "success" for r in results.values())
