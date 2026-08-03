"""tests/test_v87_s2s3_followup.py — 오너 실배포 채점 후속 2건.

■ STEP2 "전체 탭 0건" — 회귀가 아니라 **죽은 소스**
`_load_orders`는 Phase 20(54aa70db) 이후 한 번도 안 바뀌었고 #560도 안 건드렸다. 진짜 원인은
이 화면이 Google Sheets `orders` 워크시트만 읽는데, 주문은 #421에서 PG로 이관됐고 #422 백업은
`_backup_orders`에 쓴다 — **`orders` 시트엔 아무도 쓰지 않는다.** 그래서 PG에 주문이 있어도
이 화면만 0건이었다(셀러 콘솔은 OrderSyncService→PG라 정상). 소스를 PG로 통일했다.

■ S3 낙관잠금 오탐 — 오너가 지목한 갈래는 아니었다
"클라이언트 보유 버전 vs 서버 시드 버전" 대조 결과: `get_policy`는 행이 없으면 version 0을 주고
폼도 0을 싣는다. 스키마의 `version DEFAULT 1`은 **죽은 기본값**이다(유일한 INSERT가 항상 version을
명시). 인메모리 재현에서도 첫 저장은 무충돌로 통과한다.
남는 설명은 **같은 저장의 이중 도착**(더블 클릭·재전송) — 두 번째가 낡은 base_version을 들고 간다.
수리: 저장된 정책이 지금 보내는 것과 **같으면** 덮어쓸 남의 변경이 없으므로 충돌이 아니라 중복으로
본다 + 제출 버튼 이중 클릭 차단. 충돌 배너는 '남이 바꾼 걸 밀어낼 뻔했다'일 때만 뜬다.
"""
from __future__ import annotations

import re

import pytest

SRC = open("src/dashboard/web_ui.py", encoding="utf-8").read()

_PG_ROWS = [
    {"order_id": "ORD-1", "marketplace": "coupang", "status": "paid",
     "placed_at": "2026-08-01 10:00:00", "buyer_name_masked": "홍*동",
     "total_krw": "39000", "landed_cost_krw": "12000", "margin_pct": "31",
     "tracking_no": "999", "courier": "cj", "notes": "",
     "items_json": '[{"sku":"SKU-1","title":"접이식 차량용 책상","qty":2,'
                   '"options":{"색상":"블랙","크기":"L"}}]'},
    {"order_id": "ORD-2", "marketplace": "smartstore", "status": "shipped",
     "placed_at": "2026-08-01 11:00:00", "buyer_name_masked": "김*수",
     "total_krw": "12000", "items_json": "[]"},
]


@pytest.fixture()
def client():
    import os
    os.environ["DASHBOARD_UI_ENABLED"] = "1"
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"; s["user_email"] = "a@b.c"; s["user_role"] = "admin"
    return c


# ── STEP2: 주문 소스 ─────────────────────────────────────────────────────────

def test_orders_read_pg_not_dead_sheet_source():
    """소스가 PG로 통일됐다. Sheets는 PG 미설정(개발/테스트) 폴백으로만 남는다."""
    seg = SRC.split("def _load_orders")[1].split("\ndef ")[0]
    assert "pg_enabled()" in seg, "PG 위임이 없다 — 죽은 Sheets 소스로 되돌아갔다"
    assert "_pg_order_rows()" in seg
    # 폴백은 남기되(개발/테스트), PG 실패를 조용히 0건으로 위장하지 않는다.
    assert "logger.warning" in seg, "PG 조회 실패를 빈 목록으로 위장한다"


def test_pg_rows_mapped_to_screen_vocabulary(monkeypatch):
    """PG 어휘(marketplace/placed_at/total_krw/items_json) → 화면 어휘로 옮겨진다."""
    from src.db import orders_pg
    from src.dashboard import web_ui
    # `sys.modules`를 갈아끼우던 종전 방식은 **이 테스트가 먼저 돌 때만** 통했다.
    #   `_pg_order_rows`는 `from src.db import orders_pg`로 패키지 속성을 읽는데, 다른 테스트가
    #   그 모듈을 한 번이라도 임포트해 두면 속성이 이미 실모듈로 묶여 있어 sys.modules 패치가
    #   무시되고 실제 psycopg 연결로 새어나간다(실측: PCC 테스트와 같이 돌리면 깨졌다).
    #   실행 순서에 기대지 않도록 모듈 속성을 직접 패치한다.
    monkeypatch.setattr(orders_pg, "all_row_dicts", lambda: list(_PG_ROWS))
    rows = web_ui._pg_order_rows()
    assert len(rows) == 2, rows
    a = rows[0]
    assert a["market"] == "coupang" and a["order_date"] == "2026-08-01 10:00:00"
    assert a["sell_price_krw"] == "39000" and a["customer_name"] == "홍*동"
    # items_json 첫 건이 평면 상품 필드로 펼쳐진다.
    assert a["sku"] == "SKU-1" and a["title_ko"] == "접이식 차량용 책상" and a["quantity"] == 2
    assert "색상:블랙" in a["option"] and "크기:L" in a["option"]
    # 아이템이 없는 주문도 떨어지지 않는다(주문 자체는 존재한다).
    assert rows[1]["order_id"] == "ORD-2" and rows[1]["sku"] == ""


def test_existing_orders_never_render_zero(client, monkeypatch):
    """★ 오너 지정 계약 — 존재하는 주문이 전체 탭·무필터에서 0건이면 red."""
    from src.dashboard import web_ui
    monkeypatch.setattr(web_ui, "_load_orders", lambda: [
        {"order_id": r["order_id"], "market": r["marketplace"], "status": r["status"],
         "order_date": r["placed_at"], "customer_name": r["buyer_name_masked"],
         "sell_price_krw": r["total_krw"], "title_ko": "x", "quantity": 1}
        for r in _PG_ROWS])
    body = client.get("/dashboard/orders").get_data(as_text=True)
    assert "전체 2건" in body, ("존재하는 주문이 전체 카운트에 안 잡힌다",
                              re.findall(r"표시 \d+건 · 전체 \d+건", body))
    assert "표시 2건" in body, ("기본 필터가 존재하는 주문을 전량 거른다",
                              re.findall(r"표시 \d+건 · 전체 \d+건", body))
    assert "해당 조건의 주문이 없어요" not in body, "빈 상태로 렌더됐다"
    for oid in ("ORD-1", "ORD-2"):
        assert oid in body, f"{oid} 행이 없다"


def test_orders_json_reflects_pg_rows(client, monkeypatch):
    """JSON 응답도 같은 소스를 본다(화면만 고치고 API가 0이면 반쪽)."""
    from src.dashboard import web_ui
    monkeypatch.setattr(web_ui, "_load_orders", lambda: [{"order_id": "ORD-1"}])
    data = client.get("/dashboard/orders?format=json").get_json()
    assert data["count"] == 1, data


# ── S3: 낙관잠금 오탐 ─────────────────────────────────────────────────────────

@pytest.fixture()
def fresh_settings():
    from src.db import settings_pg
    settings_pg._MEM.clear()
    yield settings_pg
    settings_pg._MEM.clear()


def test_new_user_first_save_has_no_conflict(client, fresh_settings):
    """★ 오너 지정 계약 — 초기 정책 없던 유저의 첫 저장은 무충돌."""
    with client.session_transaction() as s:
        s["user_id"] = "newbie-1"
    body = client.get("/dashboard/fx").get_data(as_text=True)
    m = re.search(r'name="base_version" value="(\d+)"', body)
    assert m, "폼에 base_version이 없다"
    assert m.group(1) == "0", ("신규 유저인데 폼이 0이 아닌 버전을 싣는다(서버 시드 누출)", m.group(1))

    form = {"base_version": m.group(1), "percent_margin": "30", "plus_margin_krw": "0",
            "intl_ship_krw": "5000", "market_pct": "10", "round_unit": "100",
            "pccc_required": "0", "fx_source": "auto"}
    r = client.post("/dashboard/fx/policy", data=form)
    assert r.status_code == 302, r.status_code
    assert "policy_error" not in (r.headers.get("Location") or ""), \
        ("첫 저장에 오류 배너", r.headers.get("Location"))
    assert [h["version"] for h in fresh_settings.list_history("newbie-1", 5)] == [1]


def test_duplicate_identical_save_is_not_a_conflict(client, fresh_settings):
    """같은 저장이 두 번 도착해도 충돌이 아니다(더블 클릭·재전송) — 이력도 안 늘어난다."""
    with client.session_transaction() as s:
        s["user_id"] = "dup-1"
    form = {"base_version": "0", "percent_margin": "30", "plus_margin_krw": "0",
            "intl_ship_krw": "5000", "market_pct": "10", "round_unit": "100",
            "pccc_required": "0", "fx_source": "auto"}
    first = client.post("/dashboard/fx/policy", data=form)
    assert "policy_error" not in (first.headers.get("Location") or "")
    # 두 번째: 같은 낡은 base_version(0) + 같은 정책 → 덮어쓸 남의 변경이 없다.
    second = client.post("/dashboard/fx/policy", data=form)
    loc = second.headers.get("Location") or ""
    assert "policy_error" not in loc, ("중복 저장이 충돌로 오탐", loc)
    assert [h["version"] for h in fresh_settings.list_history("dup-1", 5)] == [1], \
        "중복 저장이 이력을 부풀린다"


def test_real_conflict_still_reported(client, fresh_settings):
    """반-공허: **다른** 정책이 낡은 버전으로 오면 여전히 충돌이어야 한다."""
    with client.session_transaction() as s:
        s["user_id"] = "conf-1"
    base = {"base_version": "0", "percent_margin": "30", "plus_margin_krw": "0",
            "intl_ship_krw": "5000", "market_pct": "10", "round_unit": "100",
            "pccc_required": "0", "fx_source": "auto"}
    client.post("/dashboard/fx/policy", data=base)
    other = dict(base, percent_margin="45")          # 남이 바꾼 값을 밀어내려는 시도
    r = client.post("/dashboard/fx/policy", data=other)
    loc = r.headers.get("Location") or ""
    assert "policy_error" in loc, ("진짜 충돌을 놓친다 — 남의 변경이 조용히 덮인다", loc)


def test_double_submit_guard_in_form():
    """이중 제출 자체를 막는다(오탐의 발생원)."""
    seg = SRC.split("_POLICY_PREVIEW_JS = ")[1]
    assert "addEventListener('submit'" in seg, "제출 가드가 없다"
    assert "b.disabled = true" in seg
    assert "b.disabled = false" in seg, "실패로 페이지에 머물면 버튼이 영영 죽는다"
