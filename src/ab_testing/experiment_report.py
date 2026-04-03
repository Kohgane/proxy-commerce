"""src/ab_testing/experiment_report.py — 실험 결과 리포트 생성."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


class ExperimentReport:
    """실험 결과 리포트 생성."""

    def generate(self, experiment: dict, metrics: dict, analysis: dict = None) -> dict:
        """실험 결과 리포트 생성."""
        exp_id = experiment.get("experiment_id", "unknown")
        name = experiment.get("name", "unknown")
        variants = experiment.get("variants", [])

        variant_summaries = []
        for v in variants:
            m = metrics.get(v, {})
            variant_summaries.append({
                "variant": v,
                "impressions": m.get("impressions", 0),
                "conversions": m.get("conversions", 0),
                "cvr": m.get("cvr", 0.0),
                "ctr": m.get("ctr", 0.0),
                "revenue": m.get("revenue", 0.0),
            })

        report = {
            "experiment_id": exp_id,
            "name": name,
            "status": experiment.get("status"),
            "created_at": experiment.get("created_at"),
            "started_at": experiment.get("started_at"),
            "stopped_at": experiment.get("stopped_at"),
            "variants": variant_summaries,
            "analysis": analysis or {},
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        # 승자 결정
        if variant_summaries:
            winner = max(variant_summaries, key=lambda x: x["cvr"])
            report["winner"] = winner["variant"]
            report["winner_cvr"] = winner["cvr"]
        else:
            report["winner"] = None

        return report

    def to_text(self, report: dict) -> str:
        """텍스트 요약."""
        lines = [
            f"=== 실험 리포트: {report.get('name')} ===",
            f"ID: {report.get('experiment_id')}",
            f"상태: {report.get('status')}",
            f"생성: {report.get('generated_at', '')[:10]}",
            "",
            "[ 변형별 성과 ]",
        ]
        for v in report.get("variants", []):
            lines.append(
                f"  {v['variant']}: 노출 {v['impressions']}, "
                f"전환 {v['conversions']}, CVR {v['cvr']:.2%}"
            )
        winner = report.get("winner")
        if winner:
            lines.append(f"\n🏆 승자: {winner} (CVR {report.get('winner_cvr', 0):.2%})")
        analysis = report.get("analysis", {})
        if analysis:
            sig = "✅ 유의" if analysis.get("significant") else "❌ 미유의"
            lines.append(f"통계 검정: {sig} (p={analysis.get('p_value', 'N/A')})")
        return "\n".join(lines)
