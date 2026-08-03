"""tests/test_v87_s2_drawer_dead_chips.py — v87 STEP2 후속: 드로어 상단 칩 죽은 버튼 계약.

■ 오너 지정 계약
드로어 상단 [수집처][판매마켓][상세페이지] 칩은
  - 대상 링크가 **있으면** 실제로 열린다(새 탭).
  - **없으면** 비활성 스타일 + 툴팁으로 *왜* 못 여는지 말한다.
"링크가 없는데 눌리는 것처럼 보이고 클릭하면 아무 일도 안 남" 상태가 red다.

■ 왜 pointer-events:none 이 답이 아니었나
종전 `--off` 칩은 `pointer-events:none` 이었다. 눌리지 않는 건 맞지만 **커서도 툴팁도 안 뜬다** —
사용자에겐 "회색이고 아무 반응 없음"만 남아, 죽은 버튼과 구분이 안 된다. 포인터 이벤트를 살리고
(span이라 애초에 이동할 곳이 없다) not-allowed 커서 + title 툴팁으로 사유를 먼저 알린다.

■ 재현
검수 시드 주문(QA-TEST-0001)은 수집처/마켓/상세 링크가 모두 없다 → 세 칩이 전부 비활성.
그래서 이 계약은 시드만 있으면 화면에서 그대로 재현된다.
"""
from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path

import pytest

SRC = Path("src/dashboard/web_ui.py").read_text(encoding="utf-8")
# 칩을 그리는 JS 조각만 떼어내 판정한다(파일 전체 grep은 다른 곳의 문자열에 오탐한다).
CHIP_JS = SRC.split("var defs=")[1].split(".join('');")[0]
CHIP_CSS = SRC.split(".kgp-oc-dbtn--off{")[1].split("\n.kgp-oc-dbody")[0]


# ── 링크가 있을 때: 진짜로 열린다 ──────────────────────────────────────────────

def test_linked_chip_is_a_real_anchor():
    live = CHIP_JS.split("if(d[1])")[1].split("return '<span")[0]
    assert "<a class=" in live, "링크 있는 칩이 실제 앵커가 아니다"
    assert "href=" in live and "esc(d[1])" in live, "앵커에 대상 주소가 안 실린다"
    assert 'target="_blank"' in live and 'rel="noopener"' in live


# ── 링크가 없을 때: 비활성 + 사유 ──────────────────────────────────────────────

def test_unlinked_chip_is_disabled_with_a_reason_tooltip():
    dead = CHIP_JS.split("return '<span")[1]
    assert "kgp-oc-dbtn--off" in dead, "비활성 스타일이 없다"
    assert 'aria-disabled="true"' in dead, "보조기술에 비활성이 전달되지 않는다"
    assert "title=" in dead, "왜 못 누르는지 말해주지 않는다(죽은 버튼과 구분 불가)"
    assert "esc(d[3])" in dead, "툴팁 문구가 이스케이프 없이 들어간다"


def test_unlinked_chip_is_never_rendered_as_an_anchor():
    """href 없는 <a>는 눌리는 것처럼 보이면서 아무 일도 안 하는 정확히 그 상태다."""
    dead = CHIP_JS.split("return '<span")[1]
    assert "<a " not in dead and "<a>" not in dead


@pytest.mark.parametrize("chip", ["수집처", "판매마켓", "상세페이지"])
def test_every_chip_declares_its_own_reason(chip):
    """칩마다 사유 문구가 붙어 있다(v87-S4: 오너 재확인분 — 세 칩 공통 '원본 미연결').

    새 칩을 추가하면서 사유를 빠뜨리면 여기서 걸린다(툴팁이 undefined로 뜨는 회귀 방지).
    """
    # 엔트리 모양: ['수집처',L['수집처'],'◈','원본 미연결'] — 안쪽 L[...] 대괄호를 건너뛴다.
    m = re.search(r"\['{0}',L\['{0}'\],[^\]]*\]".format(chip), CHIP_JS)
    assert m, f"{chip} 칩 정의를 못 찾았다"
    entry = m.group(0)
    assert entry.count(",") >= 3, f"{chip} 칩에 사유 문구가 없다"
    assert "미연결" in entry, f"{chip} 사유가 '왜 못 여는지'를 말하지 않는다"


# ── 스타일 계약: 툴팁이 실제로 뜰 수 있어야 한다 ────────────────────────────────

def test_disabled_chip_style_does_not_kill_its_own_tooltip():
    assert "pointer-events:none" not in CHIP_CSS, \
        "pointer-events:none 이면 title 툴팁이 안 뜬다 — 사유를 못 알린다"
    assert "cursor:not-allowed" in CHIP_CSS, "커서로도 '못 누른다'를 알려야 한다"


def test_disabled_chip_has_no_hover_affordance():
    """호버에 반응하면 '눌리는 버튼'으로 읽힌다."""
    assert re.search(r"\.kgp-oc-dbtn--off:hover\{background:transparent\}", SRC)
    assert re.search(r"\.kgp-oc-dbtn--off:active\{transform:none\}", SRC)


# ── 시드 주문으로 재현되는가 ───────────────────────────────────────────────────

def _seed_links(monkeypatch):
    import importlib.util
    import os
    os.environ["DASHBOARD_UI_ENABLED"] = "1"
    from src.db import orders_pg
    from src.dashboard import web_ui
    from src.order_webhook import app

    spec = importlib.util.spec_from_file_location("qa", "scripts/qa_test_order.py")
    qa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qa)
    monkeypatch.setattr(orders_pg, "all_row_dicts", lambda: [qa.qa_row()])
    monkeypatch.setattr(web_ui, "_load_orders", lambda: web_ui._pg_order_rows())

    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"; s["user_email"] = "a@b.c"; s["user_role"] = "admin"
    body = c.get("/dashboard/orders").get_data(as_text=True)
    m = re.search(r"data-order='([^']+)'", body) or re.search(r'data-order="([^"]+)"', body)
    assert m, "행에 드로어 페이로드가 없다"
    return json.loads(_html.unescape(m.group(1)))["links"]


def test_seed_order_shows_both_chip_states_in_one_capture(monkeypatch):
    """v87-S4: 시드가 링크를 **일부러 2/3만** 채운다.

    전부 채우면 비활성 상태를 못 보고, 전부 비우면 동작을 못 본다. 2/3이어야 캡처 한 장으로
    '되는 칩'과 '안 되는 칩'을 나란히 판정할 수 있다 — 죽은 버튼 계약의 재현 픽스처.
    """
    links = _seed_links(monkeypatch)
    assert set(links) == {"수집처", "판매마켓", "상세페이지"}
    assert links["수집처"].startswith("http"), "수집처 칩이 열릴 대상이 없다"
    assert links["상세페이지"].startswith("http"), "상세페이지 칩이 열릴 대상이 없다"
    assert links["판매마켓"] == "", "비활성 상태를 보여줄 칩이 남아 있어야 한다"


def test_drawer_links_have_a_producer_not_only_a_reader():
    """★ v87-S4 실기기 결함의 뿌리 — 세 링크는 만드는 곳이 없어 **영구 비활성**이었다(PCC와 동일 계열)."""
    src = Path("src/dashboard/web_ui.py").read_text(encoding="utf-8")
    seg = src.split("def _pg_order_rows")[1].split("\ndef ")[0]
    for key in ("source_url", "market_url", "detail_url"):
        assert re.search(r'"%s":\s*r\.get\(' % key, seg), f"_pg_order_rows가 {key}를 만들지 않는다"


def test_link_columns_are_persisted():
    from src.db import orders_pg
    for c in ("source_url", "market_url", "detail_url"):
        assert c in orders_pg._COLS
    schema = Path("src/db/schema_stage3.sql").read_text(encoding="utf-8")
    for c in ("source_url", "market_url", "detail_url"):
        assert re.search(r"ALTER\s+TABLE\s+orders\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+%s\s" % c,
                         schema, re.I), f"{c} idempotent ALTER 없음"
