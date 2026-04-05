"""src/data_pipeline/etl_engine.py — ETL 엔진 (Phase 100)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from .pipeline_models import ETLPipeline, PipelineStatus, RunRecord


class PipelineScheduler:
    """스케줄 기반 파이프라인 실행 스케줄러."""

    _INTERVALS = {
        "hourly": timedelta(hours=1),
        "daily": timedelta(days=1),
        "weekly": timedelta(weeks=1),
        "monthly": timedelta(days=30),
    }

    def next_run(self, schedule: str) -> str:
        """다음 실행 시간 계산 (ISO 문자열 반환)."""
        now = datetime.utcnow()
        delta = self._INTERVALS.get(schedule, timedelta(hours=1))
        return (now + delta).isoformat()

    def is_due(self, schedule: str, last_run: str) -> bool:
        """파이프라인 실행 예정 여부 확인."""
        if not schedule or not last_run:
            return bool(schedule)
        try:
            last = datetime.fromisoformat(last_run)
        except ValueError:
            return True
        delta = self._INTERVALS.get(schedule, timedelta(hours=1))
        return datetime.utcnow() >= last + delta

    def parse_cron(self, cron_expr: str) -> dict:
        """cron 표현식 파싱 (minute hour dom month dow)."""
        parts = cron_expr.strip().split()
        if len(parts) < 5:
            parts = parts + ["*"] * (5 - len(parts))
        return {
            "minute": parts[0],
            "hour": parts[1],
            "day_of_month": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }


class ETLEngine:
    """ETL 파이프라인 오케스트레이터."""

    def __init__(self) -> None:
        self._pipelines: dict[str, ETLPipeline] = {}
        self._run_history: dict[str, list[RunRecord]] = {}
        self._scheduler = PipelineScheduler()

    def create_pipeline(
        self,
        name: str,
        source: str,
        transforms: list,
        destination: str,
        schedule: str = "",
        metadata: dict | None = None,
    ) -> ETLPipeline:
        pipeline_id = str(uuid.uuid4())
        pipeline = ETLPipeline(
            pipeline_id=pipeline_id,
            name=name,
            source=source,
            transforms=list(transforms),
            destination=destination,
            schedule=schedule,
            status=PipelineStatus.idle,
            created_at=datetime.utcnow().isoformat(),
            metadata=metadata or {},
        )
        self._pipelines[pipeline_id] = pipeline
        self._run_history[pipeline_id] = []
        return pipeline

    def get_pipeline(self, pipeline_id: str) -> Optional[ETLPipeline]:
        return self._pipelines.get(pipeline_id)

    def list_pipelines(self) -> list[ETLPipeline]:
        return list(self._pipelines.values())

    def update_pipeline(self, pipeline_id: str, **kwargs) -> Optional[ETLPipeline]:
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            return None
        for key, value in kwargs.items():
            if hasattr(pipeline, key):
                setattr(pipeline, key, value)
        return pipeline

    def delete_pipeline(self, pipeline_id: str) -> bool:
        if pipeline_id not in self._pipelines:
            return False
        del self._pipelines[pipeline_id]
        self._run_history.pop(pipeline_id, None)
        return True

    def run_pipeline(self, pipeline_id: str) -> RunRecord:
        """파이프라인 동기 실행 및 실행 기록 저장."""
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            raise KeyError(f"파이프라인 없음: {pipeline_id}")

        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow().isoformat()
        pipeline.status = PipelineStatus.running

        rows, error = self._execute(pipeline)

        finished_at = datetime.utcnow().isoformat()
        status = "completed" if not error else "failed"
        pipeline.status = PipelineStatus(status)
        pipeline.last_run = finished_at

        record = RunRecord(
            run_id=run_id,
            pipeline_id=pipeline_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            rows_processed=rows,
            error=error,
            metrics={"rows_per_sec": rows / max(1, 1)},
        )
        self._run_history.setdefault(pipeline_id, []).append(record)
        return record

    def stop_pipeline(self, pipeline_id: str) -> bool:
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            return False
        pipeline.status = PipelineStatus.paused
        return True

    def get_run_history(self, pipeline_id: str) -> list[RunRecord]:
        return list(self._run_history.get(pipeline_id, []))

    def _execute(self, pipeline: ETLPipeline) -> tuple[int, str]:
        """파이프라인 실행 시뮬레이션 (추출 → 변환 → 적재)."""
        try:
            # 추출: 소스 유형별 모의 데이터 생성
            source = pipeline.source.lower()
            if "order" in source:
                data = [{"order_id": f"O{i}", "amount": 10000 + i * 500, "status": "completed"} for i in range(50)]
            elif "product" in source:
                data = [{"product_id": f"P{i}", "name": f"상품{i}", "price": 5000 + i * 100} for i in range(30)]
            elif "customer" in source:
                data = [{"customer_id": f"C{i}", "name": f"고객{i}", "grade": "vip" if i % 5 == 0 else "normal"} for i in range(40)]
            elif "event" in source:
                data = [{"event_id": f"E{i}", "type": "purchase", "timestamp": f"2024-01-{i % 28 + 1:02d}"} for i in range(60)]
            else:
                data = [{"id": f"R{i}", "value": i * 100} for i in range(20)]

            # 변환: transform 목록 처리
            for transform_cfg in pipeline.transforms:
                t_type = transform_cfg.get("type", "")
                if t_type == "filter":
                    field_name = transform_cfg.get("field", "")
                    value = transform_cfg.get("value")
                    if field_name:
                        data = [r for r in data if r.get(field_name) == value]
                elif t_type == "map":
                    field_map = transform_cfg.get("field_map", {})
                    mapped = []
                    for row in data:
                        new_row = dict(row)
                        for src_f, dst_f in field_map.items():
                            if src_f in new_row:
                                new_row[dst_f] = new_row.pop(src_f)
                        mapped.append(new_row)
                    data = mapped
                elif t_type == "deduplicate":
                    seen = set()
                    deduped = []
                    key_fields = transform_cfg.get("key_fields", ["id"])
                    for row in data:
                        key = tuple(row.get(k) for k in key_fields)
                        if key not in seen:
                            seen.add(key)
                            deduped.append(row)
                    data = deduped

            # 적재: 목적지별 처리
            dest = pipeline.destination.lower()
            if "warehouse" in dest or "dw_" in dest or dest.startswith("dw"):
                pass  # 인메모리 웨어하우스에 적재 (실제 적재는 DataWarehouse가 처리)

            return len(data), ""
        except Exception as exc:
            return 0, str(exc)
