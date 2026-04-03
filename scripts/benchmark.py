#!/usr/bin/env python3
"""scripts/benchmark.py — CLI 벤치마크 도구 (Phase 54)."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Proxy Commerce 성능 벤치마크 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="대상 URL (예: http://localhost:8000/health)")
    parser.add_argument("-c", "--concurrency", type=int, default=10,
                        help="동시 사용자 수 (기본: 10)")
    parser.add_argument("-d", "--duration", type=int, default=10,
                        help="테스트 지속 시간 초 (기본: 10)")
    parser.add_argument("-r", "--ramp-up", type=int, default=2,
                        help="램프업 시간 초 (기본: 2)")
    parser.add_argument("-X", "--method", default="GET",
                        help="HTTP 메서드 (기본: GET)")
    parser.add_argument("--mock", action="store_true",
                        help="실제 요청 없이 모의 실행")
    parser.add_argument("-o", "--output", choices=["text", "json"], default="text",
                        help="출력 형식 (기본: text)")
    parser.add_argument("-n", "--name", default="cli_benchmark",
                        help="벤치마크 이름")

    args = parser.parse_args()

    from src.benchmark.load_profile import LoadProfile
    from src.benchmark.benchmark_runner import BenchmarkRunner
    from src.benchmark.benchmark_report import BenchmarkReport

    profile = LoadProfile(
        name=args.name,
        concurrent_users=args.concurrency,
        duration_seconds=args.duration,
        ramp_up_seconds=args.ramp_up,
        target_url=args.url,
        method=args.method.upper(),
    )

    runner = BenchmarkRunner()
    reporter = BenchmarkReport()

    print(f"🚀 벤치마크 시작: {args.url}", file=sys.stderr)
    print(f"   동시 사용자: {args.concurrency}, 지속 시간: {args.duration}초", file=sys.stderr)

    if args.mock:
        report = runner.run_mock(profile)
    else:
        try:
            report = runner.run(profile)
        except Exception as exc:
            print(f"❌ 오류: {exc}", file=sys.stderr)
            return 1

    if args.output == "json":
        print(reporter.to_json(report))
    else:
        print(reporter.to_text(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
