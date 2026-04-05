"""src/data_pipeline/pipeline_models.py — 파이프라인 데이터 모델 (Phase 100)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class PipelineStatus(Enum):
    idle = "idle"
    running = "running"
    completed = "completed"
    failed = "failed"
    paused = "paused"


@dataclass
class ETLPipeline:
    pipeline_id: str
    name: str
    source: str
    transforms: list
    destination: str
    schedule: str = ""
    status: PipelineStatus = PipelineStatus.idle
    created_at: str = ""
    last_run: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "pipeline_id": self.pipeline_id,
            "name": self.name,
            "source": self.source,
            "transforms": self.transforms,
            "destination": self.destination,
            "schedule": self.schedule,
            "status": self.status.value,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "metadata": self.metadata,
        }


@dataclass
class WarehouseSchema:
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "nullable": self.nullable,
            "primary_key": self.primary_key,
            "description": self.description,
        }


@dataclass
class WarehouseTable:
    table_name: str
    schema: list
    row_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    partitions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "table_name": self.table_name,
            "schema": [s.to_dict() if hasattr(s, "to_dict") else s for s in self.schema],
            "row_count": self.row_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "partitions": self.partitions,
        }


@dataclass
class RunRecord:
    run_id: str
    pipeline_id: str
    status: str
    started_at: str
    finished_at: str = ""
    rows_processed: int = 0
    error: str = ""
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "pipeline_id": self.pipeline_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "rows_processed": self.rows_processed,
            "error": self.error,
            "metrics": self.metrics,
        }
