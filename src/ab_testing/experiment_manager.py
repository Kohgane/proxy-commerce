"""src/ab_testing/experiment_manager.py — 실험 CRUD."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ExperimentManager:
    """A/B 실험 생성/조회/시작/중지."""

    def __init__(self):
        self._experiments: Dict[str, dict] = {}

    def create(self, name: str, variants: List[str]) -> dict:
        exp_id = str(uuid.uuid4())[:8]
        exp = {
            'id': exp_id,
            'name': name,
            'status': 'draft',
            'variants': variants,
            'start_time': None,
            'end_time': None,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._experiments[exp_id] = exp
        logger.info("실험 생성: %s (%s)", exp_id, name)
        return exp

    def get(self, experiment_id: str) -> Optional[dict]:
        return self._experiments.get(experiment_id)

    def start(self, experiment_id: str) -> dict:
        exp = self._experiments.get(experiment_id)
        if exp is None:
            raise KeyError(f"실험 없음: {experiment_id}")
        exp['status'] = 'running'
        exp['start_time'] = datetime.now(timezone.utc).isoformat()
        return exp

    def stop(self, experiment_id: str) -> dict:
        exp = self._experiments.get(experiment_id)
        if exp is None:
            raise KeyError(f"실험 없음: {experiment_id}")
        exp['status'] = 'stopped'
        exp['end_time'] = datetime.now(timezone.utc).isoformat()
        return exp

    def list_experiments(self) -> List[dict]:
        return list(self._experiments.values())
