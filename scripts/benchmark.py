#!/usr/bin/env python3
"""scripts/benchmark.py — 벤치마크 CLI 도구."""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.benchmark.load_profile import LoadProfile
from src.benchmark.benchmark_runner import BenchmarkRunner
from src.benchmark.regression_detector import RegressionDetector


def main():
    parser = argparse.ArgumentParser(description='Proxy Commerce 벤치마크 도구')
    parser.add_argument('url', help='대상 URL')
    parser.add_argument('--users', type=int, default=10, help='동시 사용자 수')
    parser.add_argument('--duration', type=int, default=10, help='실행 시간 (초)')
    parser.add_argument('--ramp-up', type=int, default=2, help='램프업 시간 (초)')
    parser.add_argument('--method', default='GET', help='HTTP 메서드')
    parser.add_argument('--name', default='', help='결과 저장 이름')
    args = parser.parse_args()

    profile = LoadProfile(
        concurrent_users=args.users,
        duration_seconds=args.duration,
        ramp_up_seconds=args.ramp_up,
        target_url=args.url,
        method=args.method,
    )

    print(f"벤치마크 시작: {args.url} ({args.users} users, {args.duration}s)")
    runner = BenchmarkRunner()
    result = runner.run(profile)

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.name:
        detector = RegressionDetector()
        detector.store_result(args.name, result)
        print(f"결과 저장: {args.name}")


if __name__ == '__main__':
    main()
