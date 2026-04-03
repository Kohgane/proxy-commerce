"""src/pipeline/pipeline_builder.py — 파이프라인 빌더 (fluent interface)."""
from __future__ import annotations

from typing import List

from .stage import Stage
from .pipeline import Pipeline


class PipelineBuilder:
    """파이프라인을 단계적으로 조립하는 빌더."""

    def __init__(self, name: str = "pipeline") -> None:
        self._name = name
        self._stages: List[Stage] = []

    def add_stage(self, stage: Stage) -> "PipelineBuilder":
        self._stages.append(stage)
        return self

    def build(self) -> Pipeline:
        return Pipeline(name=self._name, stages=list(self._stages))
