#!/usr/bin/env python3
"""C-F14 이관 — `enrich_state`가 지고 있던 **두 뜻**을 두 필드로 나눈다.

## 왜

F11이 가격 확보 시 `enrich_state="done"`을 세웠다. 그 뜻은 「등록 게이트 열림」이었는데,
목록 화면은 같은 필드를 「보강 완료」로 읽어 **이미지 0장 + done = 추출 실패**로 표시했다.
그래서 제목·상품번호·가격이 다 담긴 행이 「실패」로, 아무것도 없는 행이 「대기」로 뒤집혔다.

## 무엇을 하나

`images`가 비어 있는데 `enrich_state == "done"`인 행:
  · `gate_ready`  ← 가격이 있으면 True(원래 의도한 뜻을 이쪽으로 옮긴다)
  · `enrich_state` ← `pending`(보강은 실제로 안 됐으니까)

**되돌릴 수 있게** 이관 전 상태를 `f14_backup`에 통째로 적어 둔다(행마다).
드라이런이 기본 — `--apply`를 줘야 쓴다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def scan(rows):
    """이관 대상과 사유를 고른다. **판단 근거를 함께 돌려준다**(숫자만 믿지 않게)."""
    targets, skipped = [], []
    for row in rows:
        try:
            ex = json.loads(row.get("extra_json") or "{}") or {}
        except Exception:
            skipped.append((row.get("id"), "extra_json 파손"))
            continue
        state = str(ex.get("enrich_state") or "")
        images = ex.get("images") or []
        if state == "done" and not images:
            targets.append({
                "id": row.get("id"),
                "title": (row.get("title") or "")[:40],
                "price": str(ex.get("price") or ""),
                "before": {"enrich_state": state, "gate_ready": ex.get("gate_ready"),
                           "images": len(images)},
            })
    return targets, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다(기본은 드라이런)")
    ap.add_argument("--seller", default="", help="특정 셀러만")
    args = ap.parse_args()

    from src.seller_console.collect_history_store import list_items, update

    ids = {args.seller} if args.seller else None
    rows = list_items(seller_ids=ids, days=3650, limit=5000)
    targets, skipped = scan(rows)

    print(f"전체 {len(rows)}행 · 이관 대상 {len(targets)}행 · 건너뜀 {len(skipped)}행")
    for t in targets:
        print(f"  {t['id']}  {t['title']!r}  가격={t['price'] or '-'}  "
              f"이전={t['before']}")
    if skipped:
        print("건너뜀:", skipped)
    if not args.apply:
        print("\n드라이런입니다. 실제로 쓰려면 --apply 를 주세요.")
        return 0

    done = 0
    for t in targets:
        row = next((r for r in rows if r.get("id") == t["id"]), None)
        if not row:
            continue
        ex = json.loads(row.get("extra_json") or "{}") or {}
        # 되돌릴 수 있게 **이관 전 상태를 통째로** 남긴다.
        ex["f14_backup"] = t["before"]
        ex["gate_ready"] = bool(str(ex.get("price") or "").strip())
        ex["enrich_state"] = "pending"
        update(t["id"], extra_json=json.dumps(ex, ensure_ascii=False))
        done += 1
    print(f"\n이관 완료 {done}행. 되돌리려면 각 행의 `f14_backup`을 보세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
