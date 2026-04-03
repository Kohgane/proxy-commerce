"""src/benchmark/benchmark_runner.py — 부하 테스트 실행."""
from __future__ import annotations

import time
import threading
import urllib.error
import urllib.request
import json
from typing import List, Optional

from .load_profile import LoadProfile
from .response_analyzer import ResponseAnalyzer
from .benchmark_report import BenchmarkReport
from .regression_detector import RegressionDetector


class BenchmarkRunner:
    """엔드포인트별 부하 테스트 실행 (concurrent requests)."""

    def __init__(self,
                 analyzer: Optional[ResponseAnalyzer] = None,
                 reporter: Optional[BenchmarkReport] = None,
                 detector: Optional[RegressionDetector] = None) -> None:
        self.analyzer = analyzer or ResponseAnalyzer()
        self.reporter = reporter or BenchmarkReport()
        self.detector = detector or RegressionDetector()

    def run(self, profile: LoadProfile) -> dict:
        """부하 테스트 실행."""
        profile.validate()
        response_times: List[float] = []
        errors = 0
        lock = threading.Lock()
        stop_event = threading.Event()

        def worker():
            nonlocal errors
            while not stop_event.is_set():
                start = time.time()
                try:
                    req_kwargs = {}
                    if profile.body:
                        body_bytes = json.dumps(profile.body).encode()
                        req = urllib.request.Request(
                            profile.target_url,
                            data=body_bytes,
                            headers={**profile.headers, "Content-Type": "application/json"},
                            method=profile.method,
                        )
                    else:
                        req = urllib.request.Request(
                            profile.target_url,
                            headers=profile.headers,
                            method=profile.method,
                        )
                    with urllib.request.urlopen(req, timeout=10):
                        pass
                except Exception:
                    with lock:
                        errors += 1
                elapsed_ms = (time.time() - start) * 1000
                with lock:
                    response_times.append(elapsed_ms)

                if profile.requests_per_second:
                    time.sleep(1.0 / profile.requests_per_second)

        # 스레드 생성
        threads = [
            threading.Thread(target=worker, daemon=True)
            for _ in range(profile.concurrent_users)
        ]
        for t in threads:
            t.start()

        time.sleep(profile.duration_seconds)
        stop_event.set()
        for t in threads:
            t.join(timeout=2)

        stats = self.analyzer.analyze(response_times)
        report = self.reporter.generate(profile.to_dict(), stats, errors)
        self.detector.add_result(report)
        return report

    def run_mock(self, profile: LoadProfile,
                 response_times_ms: List[float] = None) -> dict:
        """테스트용 모의 실행 (실제 HTTP 요청 없음)."""
        profile.validate()
        times = response_times_ms or [50.0, 60.0, 45.0, 70.0, 55.0]
        stats = self.analyzer.analyze(times)
        report = self.reporter.generate(profile.to_dict(), stats, errors=0)
        self.detector.add_result(report)
        return report
