"""src/benchmark/benchmark_runner.py — 벤치마크 실행기."""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """ThreadPoolExecutor 기반 부하 테스트 실행."""

    def __init__(self, request_func: Optional[Callable] = None):
        self._request_func = request_func or self._default_request

    def _default_request(self, url: str, method: str = 'GET', body=None) -> float:
        import urllib.request
        import json
        start = time.time()
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        return (time.time() - start) * 1000

    def run(self, profile) -> dict:
        from .response_analyzer import ResponseAnalyzer
        from .benchmark_report import BenchmarkReport

        response_times = []
        errors = []
        total_requests = profile.concurrent_users * max(1, profile.duration_seconds)

        def make_request():
            try:
                elapsed = self._request_func(profile.target_url, profile.method, profile.body)
                return elapsed, None
            except Exception as exc:
                return None, str(exc)

        with ThreadPoolExecutor(max_workers=profile.concurrent_users) as executor:
            futures = [executor.submit(make_request) for _ in range(total_requests)]
            for future in as_completed(futures):
                elapsed, error = future.result()
                if error:
                    errors.append(error)
                elif elapsed is not None:
                    response_times.append(elapsed)

        analyzer = ResponseAnalyzer()
        stats = analyzer.analyze(response_times)
        report = BenchmarkReport()
        return report.generate(profile, stats, errors)
