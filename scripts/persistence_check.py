#!/usr/bin/env python3
"""scripts/persistence_check.py — v87-W3 수집 이력 내구성 실증 (오너 운영 실증용).

배포마다 수집 이력이 소실되는지(컨테이너 로컬 휘발) 여부를 운영 컨테이너에서 직접 실증한다.
- `status`  : 저장 내구성 신호 출력(삭제/쓰기 없음).
- `seed`    : QA-TEST- 접두사 1건 시드(운영 코드와 같은 append 경로). 배포 전 실행.
- `verify`  : 그 시드가 아직 있는지 조회. 배포 **후** 실행 → 생존이면 durable 실증.
- `cleanup` : QA-TEST- 시드만 소프트삭제(그 외 절대 손대지 않음).

■ 안전장치 (실유저 데이터 절대 접촉 금지)
  - 시드 url/title이 반드시 `QA-TEST-`로 시작. verify/cleanup은 그 접두사만 대상.
  - 자동 삭제 없음(cleanup은 명시 호출 시 QA-TEST-만).

■ 사용 (Render Shell)
  python scripts/persistence_check.py status
  python scripts/persistence_check.py seed      # 배포 전
  #  ...배포...
  python scripts/persistence_check.py verify     # 배포 후 → 'SURVIVED'면 내구 실증
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

_QA_URL = "https://QA-TEST-persistence.example/collect/marker"
_QA_TITLE = "QA-TEST- 영속성 실증 마커"
_QA_SELLER = "QA-TEST-seller"


def _status() -> int:
    from src.db.pg import storage_status
    s = storage_status()
    print("=" * 56)
    print("v87-W3 저장 내구성 신호 (읽기 전용)")
    print("=" * 56)
    print(f"  durable(내구)          : {s['durable']}   (True=Supabase PG, False=in-memory 휘발)")
    print(f"  backend                : {s['backend']}")
    print(f"  DATABASE_URL 설정       : {s['url_set']}")
    print(f"  deployed(배포 컨테이너)  : {s['deployed']}")
    print(f"  volatile_in_production : {s['volatile_in_production']}   (True면 배포마다 소실 중)")
    if s["volatile_in_production"]:
        print("  → ⚠️ 배포인데 휘발 저장. DATABASE_URL(6543)·DATABASE_URL_DIRECT(5432) 설정 필요.")
    return 0


def _seed() -> int:
    from src.seller_console import collect_history_store as store
    iid = store.append(source="qa", url=_QA_URL, title=_QA_TITLE, seller_id=_QA_SELLER)
    if isinstance(iid, tuple):
        iid = iid[0]
    print(f"[seed] QA-TEST- 시드 저장: item_id={iid}")
    print("  배포 후 `python scripts/persistence_check.py verify` 로 생존 확인.")
    return 0


def _verify() -> int:
    from src.seller_console import collect_history_store as store
    rows = store.list_items(seller_ids={_QA_SELLER}, days=3650)
    hit = [r for r in rows if (r.get("url") or "").startswith("https://QA-TEST-persistence")]
    if hit:
        print(f"[verify] SURVIVED — QA-TEST- 시드 {len(hit)}건 생존. 저장이 배포에도 내구(Supabase PG).")
        return 0
    print("[verify] LOST — QA-TEST- 시드가 사라짐. 저장이 휘발(컨테이너 로컬) = 배포마다 소실.")
    return 2


def _cleanup() -> int:
    from src.seller_console import collect_history_store as store
    rows = store.list_items(seller_ids={_QA_SELLER}, days=3650)
    ids = [r.get("id") for r in rows if (r.get("url") or "").startswith("https://QA-TEST-persistence")]
    if not ids:
        print("[cleanup] 대상 QA-TEST- 시드 없음.")
        return 0
    gone = store.delete_ids(ids, seller_ids={_QA_SELLER})
    print(f"[cleanup] QA-TEST- 시드 {len(gone)}건 소프트삭제(그 외 미접촉).")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    return {"status": _status, "seed": _seed, "verify": _verify, "cleanup": _cleanup}.get(cmd, _status)()


if __name__ == "__main__":
    raise SystemExit(main())
