#!/usr/bin/env python3
"""scripts/renormalize_prices.py — v72 STEP2: 기저장 오염 가격 재정규화 배치(1회).

이미 저장된 수집 이력 중 가격 문자열이 오염된 것("81800."·"1,234"·"₩81,800")을 정규화 관문
(collect_sanitize.normalize_price)에 다시 통과시켜 깨끗한 값으로 갱신한다. 원문 보존·0.00 저장 금지.

사용:  python scripts/renormalize_prices.py [--dry]
  --dry: 변경 없이 대상만 출력.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collectors.collect_sanitize import renormalize_all, renormalize_price_field  # noqa: E402


def _iter_and_update(dry: bool):
    """collect_history 전 항목을 순회하며 (item_id, price)를 산출하고, 변경분을 update로 저장."""
    from src.seller_console import collect_history_store as ch

    rows = []
    # PG/인메모리 공통: list_items를 넓은 스코프로(운영 배치는 관리자 실행). 인메모리는 _in_memory 직접.
    try:
        rows = list(getattr(ch, "_in_memory", []) or [])
    except Exception:
        rows = []
    if not rows:
        try:
            rows = ch.list_items(seller_ids=None, per_page=100000)  # type: ignore[arg-type]
        except Exception:
            rows = []

    def items():
        for r in rows:
            extra = r.get("extra") or r.get("extra_json") or r
            iid = r.get("id") or r.get("item_id") or extra.get("id")
            price = extra.get("price") if isinstance(extra, dict) else r.get("price")
            if iid is not None:
                yield str(iid), price

    def do_update(item_id, new_price):
        if dry:
            print(f"  [dry] {item_id}: → {new_price}")
            return
        try:
            # v72b STEP1: 정본 단일 소스 — price·price_original 둘 다 정규화값으로 동기화(이원화 제거).
            ch.update(item_id, extra_updates={"price": new_price, "price_original": new_price})
        except Exception as e:
            print(f"  [err] {item_id}: {e}")

    return renormalize_all(items(), do_update)


def main():
    dry = "--dry" in sys.argv
    stats = _iter_and_update(dry)
    print(f"[재정규화] scanned={stats['scanned']} changed={stats['changed']}" + (" (dry-run)" if dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
