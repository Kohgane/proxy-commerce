"""src/benchmark/benchmark_report.py — 벤치마크 결과 리포트."""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class BenchmarkReport:
    """결과 리포트 생성 (JSON + 텍스트 요약)."""

    def generate(self, profile: dict, stats: dict, errors: int = 0) -> dict:
        """리포트 생성."""
        total = stats.get("count", 0)
        elapsed = profile.get("duration_seconds", 0)
        rps = round(total / elapsed, 2) if elapsed > 0 else 0.0

        return {
            "profile": profile,
            "stats": stats,
            "errors": errors,
            "error_rate": round(errors / total * 100, 2) if total > 0 else 0.0,
            "throughput_rps": rps,
            "generated_at": _now_iso(),
        }

    def to_json(self, report: dict) -> str:
        return json.dumps(report, ensure_ascii=False, indent=2)

    def to_text(self, report: dict) -> str:
        """텍스트 요약."""
        profile = report.get("profile", {})
        stats = report.get("stats", {})
        lines = [
            f"=== 벤치마크 리포트: {profile.get('name', 'unknown')} ===",
            f"URL: {profile.get('target_url', '-')} [{profile.get('method', 'GET')}]",
            f"동시 사용자: {profile.get('concurrent_users', 0)}",
            f"지속 시간: {profile.get('duration_seconds', 0)}초",
            "",
            "[ 응답 시간 (ms) ]",
            f"  총 요청: {stats.get('count', 0)}",
            f"  평균: {stats.get('mean', 0):.1f}",
            f"  최소: {stats.get('min', 0):.1f}",
            f"  최대: {stats.get('max', 0):.1f}",
            f"  p50: {stats.get('p50', 0):.1f}",
            f"  p95: {stats.get('p95', 0):.1f}",
            f"  p99: {stats.get('p99', 0):.1f}",
            f"  stddev: {stats.get('stddev', 0):.1f}",
            "",
            f"처리량: {report.get('throughput_rps', 0):.1f} RPS",
            f"에러율: {report.get('error_rate', 0):.1f}%",
        ]
        return "\n".join(lines)
