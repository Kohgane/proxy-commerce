"""src/data_pipeline/pipeline_monitor.py — 파이프라인 모니터링 (Phase 100)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .pipeline_models import ETLPipeline, RunRecord


@dataclass
class LineageNode:
    node_id: str
    node_type: str  # source / transform / destination
    name: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "metadata": self.metadata,
        }


@dataclass
class LineageEdge:
    from_node: str
    to_node: str
    columns: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "from_node": self.from_node,
            "to_node": self.to_node,
            "columns": self.columns,
        }


class LineageTracker:
    """데이터 리니지 추적기."""

    def __init__(self) -> None:
        self._lineages: dict[str, dict] = {}

    def record_lineage(self, pipeline: ETLPipeline) -> None:
        nodes = []
        edges = []

        # 소스 노드
        src_node = LineageNode(
            node_id=f"src_{pipeline.pipeline_id}",
            node_type="source",
            name=pipeline.source,
        )
        nodes.append(src_node)
        prev_id = src_node.node_id

        # 변환 노드들
        for i, t in enumerate(pipeline.transforms):
            t_name = t.get("type", f"transform_{i}") if isinstance(t, dict) else str(t)
            t_node = LineageNode(
                node_id=f"t{i}_{pipeline.pipeline_id}",
                node_type="transform",
                name=t_name,
            )
            nodes.append(t_node)
            edges.append(LineageEdge(from_node=prev_id, to_node=t_node.node_id))
            prev_id = t_node.node_id

        # 목적지 노드
        dst_node = LineageNode(
            node_id=f"dst_{pipeline.pipeline_id}",
            node_type="destination",
            name=pipeline.destination,
        )
        nodes.append(dst_node)
        edges.append(LineageEdge(from_node=prev_id, to_node=dst_node.node_id))

        self._lineages[pipeline.pipeline_id] = {
            "nodes": [n.to_dict() for n in nodes],
            "edges": [e.to_dict() for e in edges],
            "pipeline_id": pipeline.pipeline_id,
            "pipeline_name": pipeline.name,
        }

    def get_lineage(self, pipeline_id: str) -> dict:
        return dict(self._lineages.get(pipeline_id, {}))

    def get_table_lineage(self, table_name: str) -> list[dict]:
        """특정 테이블에 데이터를 로드하는 모든 파이프라인 리니지 반환."""
        result = []
        for pipeline_id, lineage in self._lineages.items():
            nodes = lineage.get("nodes", [])
            for node in nodes:
                if node.get("node_type") == "destination" and table_name in node.get("name", ""):
                    result.append({"pipeline_id": pipeline_id, **lineage})
                    break
        return result


class PipelineMonitor:
    """파이프라인 실행 모니터링."""

    def __init__(self) -> None:
        self._metrics: dict[str, list[dict]] = {}

    def record_run(self, run_record: RunRecord, duration_sec: float) -> None:
        entry = {
            "run_id": run_record.run_id,
            "status": run_record.status,
            "rows_processed": run_record.rows_processed,
            "duration_sec": duration_sec,
            "started_at": run_record.started_at,
        }
        self._metrics.setdefault(run_record.pipeline_id, []).append(entry)

    def get_metrics(self, pipeline_id: str) -> dict:
        runs = self._metrics.get(pipeline_id, [])
        if not runs:
            return {
                "avg_duration": 0.0,
                "total_runs": 0,
                "success_rate": 0.0,
                "avg_rows": 0.0,
                "last_run": "",
            }
        total = len(runs)
        successful = sum(1 for r in runs if r["status"] == "completed")
        avg_duration = sum(r["duration_sec"] for r in runs) / total
        avg_rows = sum(r["rows_processed"] for r in runs) / total
        last_run = runs[-1]["started_at"] if runs else ""
        return {
            "avg_duration": round(avg_duration, 3),
            "total_runs": total,
            "success_rate": round(successful / total, 4),
            "avg_rows": round(avg_rows, 1),
            "last_run": last_run,
        }

    def get_throughput(self, pipeline_id: str) -> float:
        """rows/sec 처리량 반환."""
        runs = self._metrics.get(pipeline_id, [])
        if not runs:
            return 0.0
        completed = [r for r in runs if r["status"] == "completed" and r["duration_sec"] > 0]
        if not completed:
            return 0.0
        throughputs = [r["rows_processed"] / r["duration_sec"] for r in completed]
        return round(sum(throughputs) / len(throughputs), 2)

    def get_error_rate(self, pipeline_id: str) -> float:
        """에러율 반환 (0.0–1.0)."""
        runs = self._metrics.get(pipeline_id, [])
        if not runs:
            return 0.0
        failed = sum(1 for r in runs if r["status"] == "failed")
        return round(failed / len(runs), 4)


class ETLDashboard:
    """ETL 대시보드."""

    def __init__(self, engine, warehouse: "DataWarehouse", monitor: PipelineMonitor) -> None:
        self._engine = engine
        self._warehouse = warehouse
        self._monitor = monitor

    def get_summary(self) -> dict:
        pipelines = self._engine.list_pipelines()
        active = [p for p in pipelines if p.status.value == "running"]
        all_runs: list[dict] = []
        for p in pipelines:
            all_runs.extend([r.to_dict() for r in self._engine.get_run_history(p.pipeline_id)])

        completed = sum(1 for r in all_runs if r["status"] == "completed")
        total_runs = len(all_runs)

        return {
            "pipeline_count": len(pipelines),
            "active_pipelines": len(active),
            "total_runs": total_runs,
            "success_rate": round(completed / max(1, total_runs), 4),
            "warehouse_stats": self._warehouse.get_stats(),
        }

    def get_pipeline_statuses(self) -> list[dict]:
        return [
            {
                "pipeline_id": p.pipeline_id,
                "name": p.name,
                "status": p.status.value,
                "last_run": p.last_run,
                "schedule": p.schedule,
            }
            for p in self._engine.list_pipelines()
        ]

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        all_runs: list[dict] = []
        for p in self._engine.list_pipelines():
            for r in self._engine.get_run_history(p.pipeline_id):
                all_runs.append(r.to_dict())
        # started_at 기준 내림차순 정렬
        all_runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return all_runs[:limit]

    def get_quality_summary(self) -> dict:
        return {
            "status": "placeholder",
            "message": "DataQualityChecker 연동 필요",
            "checked_tables": 0,
            "avg_score": 0.0,
        }

    def get_warehouse_stats(self) -> dict:
        return self._warehouse.get_stats()
