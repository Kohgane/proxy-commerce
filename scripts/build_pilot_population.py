#!/usr/bin/env python3
"""scripts/build_pilot_population.py — v88-C: sourcing_map → 파일럿 모집단 396 산출(결정적).

원본 data/sourcing_map.json 불변(읽기전용). 산출 data/pilot_population.json + 감쇄 로그.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline.coupang_replicate import build_pilot_population

def main():
    sm = json.loads(Path("data/sourcing_map.json").read_text(encoding="utf-8"))
    res = build_pilot_population(sm)
    r = res["reduction"]
    print(f"모집단 감쇄: coupang_sid truthy {r['truthy']} → distinct sid {r['distinct_sid']} "
          f"(중복 sid 제거 {r['dropped_dup']}) = 대표 {res['count']}건")
    Path("data/pilot_population.json").write_text(
        json.dumps({"count": res["count"], "reduction": r, "population": res["population"]},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print("→ data/pilot_population.json 기록")
    # 재현성 검증: 두 번 돌려 동일 sid 시퀀스인지
    res2 = build_pilot_population(sm)
    same = [x["sid"] for x in res["population"]] == [x["sid"] for x in res2["population"]]
    print(f"재현성(2회 동일): {same}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
