"""scripts/hygiene_report.py — v87-W1 정리 후보 3수치 리포트 (오너 실행용).

실유저 데이터(Supabase PG)는 오너만 접근한다. 이 스크립트는 **읽기 전용**으로
수집 이력을 스캔해 정리 후보 수치와 목록을 출력할 뿐, 삭제/보관을 하지 않는다.
(자동 삭제 절대 금지 — 실행은 화면에서 오너 클릭으로만.)

사용:
    python scripts/hygiene_report.py [--seller <seller_id>] [--days 3650] [--limit-samples 50]

출력: 전체 N · 정리 후보 C(=잡은 수) · 유지 N-C. 후보 샘플(url·점수·사유).
오너가 이 목록을 보고 '놓친/오탐'을 최종 판정한다(화면 '정리 후보' 탭과 동일 판별기).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.getcwd())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seller", default=None, help="특정 셀러만(미지정=전체 스캔)")
    ap.add_argument("--days", type=int, default=3650, help="조회 기간(일)")
    ap.add_argument("--limit-samples", type=int, default=50)
    args = ap.parse_args()

    from src.seller_console.collect_hygiene import summarize_candidates
    from src.seller_console import collect_history_store as store

    kwargs = {"days": args.days}
    if args.seller:
        kwargs["seller_id"] = args.seller
    rows = store.list_items(**kwargs)  # 읽기 전용
    rep = summarize_candidates(rows)

    print("=" * 60)
    print("v87-W1 수집 목록 위생 — 정리 후보 리포트 (읽기 전용)")
    print("=" * 60)
    print(f"전체 수집 행     : {rep['total']}")
    print(f"정리 후보(잡은 수): {rep['candidates']}")
    print(f"유지(상품 간주)  : {rep['kept']}")
    print("-" * 60)
    print(f"후보 샘플 (상위 {args.limit_samples}):")
    for s in rep["samples"][: args.limit_samples]:
        print(f"  [{s['score']:>3}] {s['url'][:70]}")
        print(f"        사유: {' · '.join(s['reasons'])}")
    print("-" * 60)
    print("※ 이 스크립트는 삭제/보관을 하지 않습니다. 실행은 화면 '정리 후보' 탭에서")
    print("  선택 후 '보관(복원 가능)'으로만. 영구 삭제는 보관 목록에서 2단 확인 후.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
