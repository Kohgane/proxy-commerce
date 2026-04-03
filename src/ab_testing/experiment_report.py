"""src/ab_testing/experiment_report.py — 실험 보고서 생성."""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class ExperimentReport:
    """실험 결과 보고서 생성."""

    def __init__(self):
        from .experiment_manager import ExperimentManager
        from .metrics_tracker import MetricsTracker
        from .statistical_analyzer import StatisticalAnalyzer
        self._exp_mgr = ExperimentManager()
        self._metrics = MetricsTracker()
        self._analyzer = StatisticalAnalyzer()

    def generate(self, experiment_id: str) -> Dict:
        exp = self._exp_mgr.get(experiment_id)
        if exp is None:
            return {'error': f'실험 없음: {experiment_id}'}
        metrics = self._metrics.get_metrics(experiment_id)
        significance = {}
        variants = exp.get('variants', [])
        control = variants[0] if variants else None
        for variant in variants[1:]:
            if control and control in metrics and variant in metrics:
                ctrl = metrics[control]
                treat = metrics[variant]
                sig = self._analyzer.z_test(
                    int(ctrl.get('conversions', 0)),
                    max(1, int(ctrl.get('impressions', 0))),
                    int(treat.get('conversions', 0)),
                    max(1, int(treat.get('impressions', 0))),
                )
                significance[variant] = sig
        return {
            'experiment_id': experiment_id,
            'experiment_name': exp.get('name'),
            'status': exp.get('status'),
            'metrics': metrics,
            'significance': significance,
        }
