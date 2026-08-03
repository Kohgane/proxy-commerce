#!/usr/bin/env python3
"""scripts/qa_test_order.py — QA 검수용 테스트 주문 시드/삭제/카운트.

왜 스크립트인가: 수동 INSERT는 재현이 안 되고, 지울 때 무엇을 지워야 하는지도 남지 않는다.
시드와 삭제를 **쌍으로** 두고 재사용 자산으로 만든다.

■ 안전장치 (실유저 데이터 절대 접촉 금지)
  - 시드 주문은 `order_id`가 반드시 `QA-TEST-` 로 시작한다.
  - `delete`는 **그 접두사에 해당하는 행만** 소프트삭제한다(그 외는 어떤 경우에도 손대지 않는다).
  - 실 주문과 눈으로도 구분되게 주문자명이 `[TEST] 검수용`이다.

■ 쓰기는 재구현하지 않는다
  INSERT를 여기서 다시 짜면 `orders_pg.upsert_rows`와 두 벌이 되어 한쪽만 낡는다.
  시드는 **운영 코드와 같은 경로**(`orders_pg.upsert_rows`, ON CONFLICT upsert)로 쓴다 —
  그래야 이 시드가 통과했다는 사실이 실제 주문 저장 경로의 증거도 된다. 멱등(재실행 안전).

■ 스코프 주의
  `orders`에 `user_id` 컬럼이 있지만 **읽기 경로(`orders_pg.all_row_dicts`)는 이를 쓰지 않는다**
  (스키마 주석대로 "향후 멀티테넌시(현재 단일 스코프)"). 그래서 `--user` 같은 스코프 인자를 받으면
  있지도 않은 격리를 있는 척하게 된다 — 받지 않는다. 대신 QA 접두사가 유일한 식별·회수 기준이다.

■ 사용 (Render Shell — DATABASE_URL 이 있는 환경)
    python scripts/qa_test_order.py count
    python scripts/qa_test_order.py seed
    python scripts/qa_test_order.py delete
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")

QA_PREFIX = "QA-TEST-"
QA_ORDER_ID = QA_PREFIX + "0001"
QA_MARKETPLACE = "coupang"
QA_BUYER = "[TEST] 검수용"


def _require_pg():
    from src.db.pg import pg_enabled
    if not pg_enabled():
        print("DATABASE_URL(또는 SUPABASE_DB_URL)이 없습니다. 프로덕션 셸에서 실행하세요.")
        raise SystemExit(2)


def cmd_count(_args) -> int:
    """실카운트 — 전체 / QA / 실데이터를 나눠 센다(실데이터가 몇 건인지 정직하게)."""
    _require_pg()
    from src.db import pg

    with pg.query() as cur:
        cur.execute(
            "SELECT count(*) FILTER (WHERE deleted_at IS NULL),"
            "       count(*) FILTER (WHERE deleted_at IS NULL AND order_id LIKE %s),"
            "       count(*) FILTER (WHERE deleted_at IS NOT NULL)"
            "  FROM orders",
            (QA_PREFIX + "%",))
        live, qa, soft = (int(v) for v in cur.fetchone())
    print(f"orders 실카운트(활성): {live}")
    print(f"  └ QA 테스트 주문   : {qa}")
    print(f"  └ 실데이터          : {live - qa}")
    print(f"소프트삭제(비활성)   : {soft}")
    return 0


def qa_row() -> dict:
    """실사형 1건 — 마켓·상품·금액·배송 필드를 전부 채운다(빈칸 화면은 검수가 안 된다).

    키는 ORDERS_HEADERS(= `orders_pg._COLS`)와 1:1. 스키마에 없는 칸은 **만들지 않는다**
    (가짜 컬럼 날조 금지). 주문 화면 드로어의 '개인통관고유부호(PCC)'·'국가'는 현재
    코드베이스 어디에도 값을 넣는 곳이 없어 빈 값으로 남고, 드로어는 빈 값을 렌더하지 않는다.
    """
    now = datetime.now()
    placed = (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    items = [{
        "sku": "QA-SKU-001",
        "title": "[TEST] 접이식 차량용 컵홀더 트레이",
        "qty": 2,
        "options": {"색상": "블랙", "크기": "L"},
    }]
    return {
        "order_id": QA_ORDER_ID,
        "marketplace": QA_MARKETPLACE,
        "status": "paid",
        "placed_at": placed,
        "paid_at": placed,
        "buyer_name_masked": QA_BUYER,
        "buyer_phone_masked": "010-****-1234",
        "buyer_address_masked": "서울 ****구 ****로 12",
        "total_krw": "39000",
        "shipping_fee_krw": "3000",
        "items_json": json.dumps(items, ensure_ascii=False),
        "courier": "cj",
        "tracking_no": "QA0000000001",
        "shipped_at": "",
        "landed_cost_krw": "24000",
        "margin_krw": "12000",
        "margin_pct": "31",
        "last_synced_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "notes": "QA 검수용 시드 — scripts/qa_test_order.py delete 로 제거",
    }


def cmd_seed(_args) -> int:
    _require_pg()
    from src.db import orders_pg, pg

    orders_pg.upsert_rows([qa_row()])
    with pg.query() as cur:
        cur.execute(
            "SELECT count(*) FROM orders WHERE deleted_at IS NULL AND order_id = %s",
            (QA_ORDER_ID,))
        n = int(cur.fetchone()[0])
    if n != 1:
        print(f"시드 실패: {QA_ORDER_ID} 활성 행이 {n}건입니다(1이어야 함).")
        return 1
    print(f"시드 완료: {QA_ORDER_ID} / {QA_MARKETPLACE}")
    print("화면에서 확인: /dashboard/orders 전체 탭 → '상세' 클릭")
    print("제거: python scripts/qa_test_order.py delete")
    return 0


def cmd_delete(_args) -> int:
    """QA 접두사에 해당하는 행만 소프트삭제. 실데이터는 어떤 경우에도 건드리지 않는다."""
    _require_pg()
    from src.db import pg

    with pg.tx() as cur:
        cur.execute(
            "UPDATE orders SET deleted_at = now() "
            "WHERE deleted_at IS NULL AND order_id LIKE %s",
            (QA_PREFIX + "%",))
        removed = cur.rowcount
        cur.execute(
            "SELECT count(*) FROM orders WHERE deleted_at IS NULL AND order_id LIKE %s",
            (QA_PREFIX + "%",))
        left = int(cur.fetchone()[0])
    print(f"삭제(소프트) {removed}건 — 남은 QA 주문 {left}건")
    return 0 if left == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="QA 검수용 테스트 주문 시드/삭제/카운트")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, help_text in (
        ("count", cmd_count, "orders 실카운트(전체/QA/실데이터)"),
        ("seed", cmd_seed, "QA 테스트 주문 1건 시드(멱등)"),
        ("delete", cmd_delete, "QA 테스트 주문만 소프트삭제"),
    ):
        sub.add_parser(name, help=help_text).set_defaults(func=fn)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
