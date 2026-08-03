"""tests/test_v87_s2_pcc_column.py — v87 STEP2 후속: PCC·국가를 실재하는 필드로 만든다.

■ 무엇이 문제였나 (검수 발견)
드로어 [상세]는 `개인통관고유부호(PCC)`를 `o.get("pcc") or o.get("personal_customs_code")`로 읽는데,
`src/` 전체에서 그 키의 **유일한 등장이 그 읽는 줄 하나**였다. `_pg_order_rows()`도 `orders` 스키마도
값을 만들지 않았으므로 실서비스에서 이 칸은 **영원히 빈 값**이었고, 드로어 JS가 빈 값 행을 렌더하지
않기 때문에 화면에서 **통째로 사라져** "원래 그런 필드는 없다"처럼 보였다. 도달 불가능한 죽은 필드.

■ 왜 기존 드로어 테스트가 못 잡았나 (이 파일이 존재하는 이유)
`test_v87_s2_orders_drawer.py`의 픽스처가 `pcc`/`country`를 **직접 넣은 평면 dict**를 주입한다.
그래서 "값을 주면 드로어가 렌더한다"는 증명은 됐지만, **아무도 그 값을 주지 않는다**는 사실은
가려졌다. 소비자만 테스트하고 생산자를 테스트하지 않으면 이렇게 조용히 죽는다.
→ 여기서는 **생산 경로(`orders_pg` 컬럼 → `_pg_order_rows` 매핑 → 드로어)** 를 끝까지 잇고,
   값이 없을 때 **자리가 남는지**(미수신)를 못박는다.

■ 화면 수 동결
신규 라우트 0. 컬럼 2개 + 매핑 + 표기 규칙만.
"""
from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path

import pytest

SCHEMA3 = Path("src/db/schema_stage3.sql").read_text(encoding="utf-8")

# _pg_order_rows가 받는 것과 같은 모양(ORDERS_HEADERS 키)의 PG 행.
_PG_ROW = {
    "order_id": "ORD-PG-1", "marketplace": "coupang", "status": "paid",
    "placed_at": "2026-08-01 10:00:00", "paid_at": "2026-08-01 10:00:00",
    "buyer_name_masked": "홍*동", "buyer_phone_masked": "", "buyer_address_masked": "",
    "total_krw": "39000", "shipping_fee_krw": "3000",
    "items_json": json.dumps([{"sku": "SKU-1", "title": "접이식 차량용 책상", "qty": 2,
                              "options": {"색상": "블랙"}}], ensure_ascii=False),
    "courier": "cj", "tracking_no": "999", "shipped_at": "",
    "landed_cost_krw": "24000", "margin_krw": "12000", "margin_pct": "31",
    "last_synced_at": "", "notes": "",
    "pcc": "P123456789012", "country": "KR",
}


def _pg_rows(monkeypatch, row):
    from src.db import orders_pg
    from src.dashboard import web_ui
    monkeypatch.setattr(orders_pg, "all_row_dicts", lambda: [dict(row)])
    return web_ui._pg_order_rows()


@pytest.fixture()
def drawer_of(monkeypatch):
    """주문 행 dict → 드로어 페이로드(화면이 실제로 렌더하는 그 JSON)."""
    import os
    os.environ["DASHBOARD_UI_ENABLED"] = "1"
    from src.dashboard import web_ui
    from src.order_webhook import app

    def _go(order_row):
        monkeypatch.setattr(web_ui, "_load_orders", lambda: [dict(order_row)])
        c = app.test_client()
        with c.session_transaction() as s:
            s["user_id"] = "u1"; s["user_email"] = "a@b.c"; s["user_role"] = "admin"
        body = c.get("/dashboard/orders").get_data(as_text=True)
        m = re.search(r"data-order='([^']+)'", body) or re.search(r'data-order="([^"]+)"', body)
        assert m, "행에 드로어 페이로드가 없다"
        return json.loads(_html.unescape(m.group(1)))
    return _go


# ── 저장 계층: 컬럼이 실재하는가 ────────────────────────────────────────────────

def test_orders_schema_adds_pcc_and_country_idempotently():
    # 이미 만들어진 orders 테이블에는 CREATE TABLE IF NOT EXISTS가 컬럼을 못 붙인다 →
    # 기존 배포에도 적용되려면 ALTER ... ADD COLUMN IF NOT EXISTS 여야 한다.
    for col in ("pcc", "country"):
        assert re.search(
            r"ALTER\s+TABLE\s+orders\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+%s\s" % col,
            SCHEMA3, re.I), f"{col} idempotent ALTER 없음"


def test_orders_pg_persists_pcc_and_country():
    from src.db import orders_pg
    assert "pcc" in orders_pg._COLS and "country" in orders_pg._COLS


def test_qa_seed_row_matches_orders_columns_and_fills_pcc():
    """검수용 시드가 새 컬럼을 실제로 태워야 화면 검수가 성립한다."""
    import importlib.util
    from src.db import orders_pg
    spec = importlib.util.spec_from_file_location("qa", "scripts/qa_test_order.py")
    qa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qa)
    row = qa.qa_row()
    assert sorted(row) == sorted(orders_pg._COLS), "시드 행 키가 저장 컬럼과 어긋남"
    from src.seller_console.pccc_store import is_valid_pccc
    assert is_valid_pccc(row["pcc"]), "시드 PCC가 형식조차 안 맞으면 화면 검수가 안 된다"
    assert row["country"]


# ── 매핑 계층: 값을 만드는 곳이 있는가 (죽은 필드였던 지점) ──────────────────────

def test_pg_order_rows_produces_pcc_and_country(monkeypatch):
    got = _pg_rows(monkeypatch, _PG_ROW)[0]
    assert got["pcc"] == "P123456789012"
    assert got["country"] == "KR"


def test_pcc_has_a_producer_not_only_a_reader():
    """읽는 줄만 있고 만드는 곳이 없으면 그 필드는 죽어 있다 — 회귀 시 여기서 걸린다."""
    src = Path("src/dashboard/web_ui.py").read_text(encoding="utf-8")
    produced = re.search(r'"pcc":\s*r\.get\(', src)
    assert produced, "_pg_order_rows가 pcc를 만들지 않는다(읽기 전용 죽은 필드로 회귀)"


# ── 표기 계층: 비어 있으면 자리가 남는가 ────────────────────────────────────────

def test_drawer_shows_pcc_and_country_when_present(drawer_of):
    d = drawer_of({**_PG_ROW, "market": "coupang", "order_date": "2026-08-01 10:00:00",
                   "pcc": "P123456789012", "country": "KR"})
    assert d["상세"]["개인통관고유부호(PCC)"] == "P123456789012"
    assert d["상세"]["국가"] == "KR"


def test_drawer_keeps_the_slot_when_pcc_missing(drawer_of):
    """★ 이 계약이 이번 발견의 핵심 — 빈 값을 숨겨 필드가 없는 척하지 않는다."""
    d = drawer_of({**_PG_ROW, "market": "coupang", "order_date": "2026-08-01 10:00:00",
                   "pcc": "", "country": ""})
    # 드로어 JS는 빈 문자열 행을 렌더하지 않으므로, 빈칸으로 두면 화면에서 사라진다.
    assert d["상세"]["개인통관고유부호(PCC)"] == "미수신"
    assert d["상세"]["국가"] == "미수신"


def test_missing_marker_is_not_faked_into_a_real_value(monkeypatch):
    """'미수신'은 표기일 뿐 저장값이 아니다 — 없는 PCC를 있는 것처럼 만들지 않는다.

    ※ 여기서 `pytest.MonkeyPatch()`를 직접 만들면 undo가 안 돼 `all_row_dicts` 패치가
      다음 테스트로 새어나간다(실제로 test_v87_s2s3_followup을 깨뜨렸다). 픽스처를 쓴다.
    """
    rows = _pg_rows(monkeypatch, {**_PG_ROW, "pcc": "", "country": ""})
    assert rows[0]["pcc"] == "" and rows[0]["country"] == ""


def test_only_the_customs_axis_gets_the_missing_marker(drawer_of):
    """전 필드에 '미수신'을 뿌리면 드로어가 잡동사니가 된다 — 통관 축에만 적용."""
    d = drawer_of({**_PG_ROW, "market": "coupang", "order_date": "2026-08-01 10:00:00",
                   "pcc": "", "country": "", "margin_pct": ""})
    assert d["상세"].get("마진", "") == "", "마진 빈 값까지 '미수신'으로 채우면 안 된다"
