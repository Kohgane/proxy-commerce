#!/usr/bin/env python3
"""F44 선행 실측 — TrackingMore가 우리가 쓰는 택배사를 **판별하는가**.

## 무엇을 정하려고 재나 (오너 결정 2026-09-21)

> 택배사 자동판별 공급사는 **하나만**. 먼저 `TrackingMore.detect_courier`가
> 한국 5대(CJ·롯데·한진·우체국·로젠) + 국제(EMS·DHL·FedEx·UPS)를 판별하는지 실측.
> 되면 TrackingMore 유지, **17TRACK 안 붙인다.** 안 되면 17TRACK으로 **통째 교체**(둘 병존 금지).

## 쓰는 법

    TRACKINGMORE_API_KEY=... python scripts/courier_detect_probe.py 송장번호파일.tsv

`송장번호파일.tsv` = 한 줄에 `택배사이름<TAB>송장번호`. **실제 송장번호여야 한다** —
번호를 지어내면 판별 결과도 지어낸 것이 된다(형식만 맞는 번호는 형식만 재는 것이다).
파일 없이 돌리면 **카탈로그 커버리지만** 잰다(그 택배사가 목록에 있기는 한가).

## 무엇이 결과인가

각 택배사마다 세 값 중 하나:

| 값 | 뜻 |
|---|---|
| `판별` | detect가 그 택배사를 **1순위로** 지목했다 |
| `후보` | 후보에 있지만 1순위가 아니다 |
| `못함` | 후보에 없다 |

**`못함`이 하나라도 있으면 TrackingMore는 이 일을 다 못 하는 것**이고, 그때 17TRACK 교체를
검토한다. 부분 통과를 「통과」로 읽지 않는다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

# 오너가 지목한 9곳. 이름은 우리 카탈로그(`courier_catalog`) 표기와 맞춘다.
TARGETS = [
    ("CJ대한통운", "국내"), ("롯데택배", "국내"), ("한진택배", "국내"),
    ("우체국택배", "국내"), ("로젠택배", "국내"),
    ("EMS", "국제"), ("DHL", "국제"), ("FedEx", "국제"), ("UPS", "국제"),
]


def _load_numbers(path: str) -> dict:
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t") if "\t" in line else line.split(None, 1)
            if len(parts) == 2:
                out[parts[0].strip()] = parts[1].strip()
    return out


def main() -> int:
    if not (os.getenv("TRACKINGMORE_API_KEY") or "").strip():
        print("TRACKINGMORE_API_KEY가 없습니다 — 판별을 잴 수 없습니다.")
        print("키 없이 카탈로그만 보려면 키를 넣고 다시 실행하세요(카탈로그도 키가 필요합니다).")
        return 2

    from src.seller_console.orders.courier_catalog import get_courier_catalog
    from src.seller_console.orders.tracking_trackingmore import TrackingMoreClient

    catalog = get_courier_catalog(include_dynamic=True)
    by_term = {}
    for row in catalog:
        for term in row.get("search_terms", []):
            by_term.setdefault(str(term).lower(), row)

    numbers = _load_numbers(sys.argv[1]) if len(sys.argv) > 1 else {}
    client = TrackingMoreClient()

    print(f"카탈로그 {len(catalog)}곳 · 송장번호 {len(numbers)}건 · 대상 {len(TARGETS)}곳\n")
    print(f"{'택배사':<12} {'구분':<5} {'카탈로그':<8} {'판별':<6} 비고")
    print("-" * 68)

    missing = []
    for name, kind in TARGETS:
        row = by_term.get(name.lower())
        in_catalog = "있음" if row else "없음"
        code = (row or {}).get("trackingmore_code", "")

        verdict, note = "미측정", "송장번호 없음"
        num = numbers.get(name)
        if num:
            got = client.detect_courier(num)
            if not got:
                verdict, note = "못함", "detect가 빈 목록을 냈다"
            elif code and got[0] == code:
                verdict, note = "판별", f"1순위={got[0]}"
            elif code and code in got:
                verdict, note = "후보", f"1순위={got[0]} (우리 코드는 {code})"
            else:
                verdict, note = "못함", f"후보={got[:3]}"
        if verdict in ("못함",) or in_catalog == "없음":
            missing.append(name)
        print(f"{name:<12} {kind:<5} {in_catalog:<8} {verdict:<6} {note}")

    print()
    if missing:
        print(f"★ 못 다루는 곳 {len(missing)}: {', '.join(missing)}")
        print("  → TrackingMore 단독으로는 부족하다. 17TRACK 교체를 검토한다(둘 병존 금지).")
        return 1
    print("★ 9곳 전부 다룬다 → TrackingMore 유지, 17TRACK 안 붙인다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
