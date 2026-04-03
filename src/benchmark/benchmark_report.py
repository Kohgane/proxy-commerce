"""src/benchmark/benchmark_report.py — 벤치마크 보고서."""
import logging

logger = logging.getLogger(__name__)


class BenchmarkReport:
    """벤치마크 결과 보고서 생성."""

    def generate(self, profile, analyzer_result: dict, errors: list) -> dict:
        profile_dict = profile.to_dict() if hasattr(profile, 'to_dict') else dict(profile)
        error_count = len(errors)
        total = analyzer_result.get('count', 0) + error_count
        error_rate = error_count / total if total > 0 else 0.0
        p95 = analyzer_result.get('p95', 0)
        mean = analyzer_result.get('mean', 0)
        summary = (
            f"요청 {total}건, P95={p95}ms, 평균={mean}ms, 오류율={error_rate:.1%}"
        )
        return {
            'profile': profile_dict,
            'stats': analyzer_result,
            'error_count': error_count,
            'error_rate': round(error_rate, 4),
            'summary_text': summary,
        }
