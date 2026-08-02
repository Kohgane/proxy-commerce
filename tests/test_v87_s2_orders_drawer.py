"""tests/test_v87_s2_orders_drawer.py — v87 STEP2: 주문 상세 드로어 3섹션 + PCC + v56 원클릭 재사용.

■ 무엇을 바꿨나
#549(v82 STEP5)가 세운 주문 화면 위에 **드로어만** 재편했다. 상태탭바·기간칩·마켓칩·테이블은 그대로다.
종전 드로어는 [주문정보][상품정보][배송정보] = **정보 유형 축**이었다. 구매대행의 작업 단위는
"이 주문을 어디서 사서 어디에 팔았나"라서, 셀러가 실제로 오가는 **출처 축**으로 바꿨다:
[수집처][판매마켓][상세].

■ v56 재사용(재구현 금지 — 브리프 명시)
소싱처 역참조(sku→카탈로그→src_url)와 주문서 복사텍스트 조립은 이미 `_order_source_info`에 있다.
대시보드 행은 평면 dict라 모양이 안 맞을 뿐이므로 **어댑터로 모양만 맞춰** 그 함수를 부른다.
두 벌로 갈라지면 한쪽만 고쳐지고 다른 쪽이 조용히 낡는다 — 그래서 호출을 소스 계약으로 못박는다.

■ 화면 수 동결
신규 라우트 0. 드로어는 같은 페이지 오버레이이므로 화면이 늘지 않는다.
"""
from __future__ import annotations

import html as _html
import json
import re

import pytest

SRC = open("src/dashboard/web_ui.py", encoding="utf-8").read()

_ORDER = {
    "order_id": "ORD-1", "order_number": "N-1", "customer_name": "홍*동",
    "sku": "SKU-1", "title_ko": "접이식 차량용 책상", "option": "블랙 / L",
    "market": "coupang", "quantity": 2, "status": "paid",
    "order_date": "2026-08-01 10:00:00", "sell_price_krw": "39000",
    "buy_price": "12000", "margin_pct": "31",
    "pcc": "P123456789012", "country": "KR", "tracking_no": "999",
    "market_url": "https://coupang.example/p/1",
    "source_url": "https://item.rakuten.co.jp/shop/abc/",
}


@pytest.fixture()
def client(monkeypatch):
    import os
    os.environ["DASHBOARD_UI_ENABLED"] = "1"
    from src.dashboard import web_ui
    from src.order_webhook import app
    monkeypatch.setattr(web_ui, "_load_orders", lambda: [dict(_ORDER)])
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"; s["user_email"] = "a@b.c"; s["user_role"] = "admin"
    return c


def _drawer(client):
    """행에 실린 data-order JSON을 그대로 판정한다(드로어가 이 값을 렌더한다)."""
    body = client.get("/dashboard/orders").get_data(as_text=True)
    m = re.search(r"data-order='([^']+)'", body) or re.search(r'data-order="([^"]+)"', body)
    assert m, "행에 드로어 페이로드가 없다"
    return json.loads(_html.unescape(m.group(1))), body


# ── v56 재사용 ────────────────────────────────────────────────────────────────

def test_reuses_v56_source_info_not_reimplemented():
    """카탈로그 역참조·복사텍스트를 **v56 함수 호출**로 쓴다(복붙 재구현이면 red)."""
    assert "from src.seller_console.views import _order_source_info" in SRC
    seg = SRC.split("def _order_sourcing")[1].split("\ndef ")[0]
    assert "_order_source_info(shaped)" in seg, "v56 함수를 실제로 호출하지 않는다"
    # 재구현 흔적: 여기서 카탈로그를 직접 뒤지면 두 벌이 된다.
    assert "CatalogLookup" not in seg, "카탈로그 조회를 대시보드에서 재구현했다"
    assert "lookup_by_sku" not in seg, "sku 역참조를 재구현했다"


def test_sourcing_failure_is_honest_not_faked():
    """모듈 부재·미매칭이면 지어내지 않고 linked=False로 떨어진다(정직 데이터)."""
    seg = SRC.split("def _order_sourcing")[1].split("\ndef ")[0]
    assert 'fallback = {"source_url": "", "product_title": "", "copy_text": "", "linked": False' in seg
    assert seg.count("return fallback") >= 2, "실패 경로가 조용히 통과한다"


# ── 드로어 3섹션 ──────────────────────────────────────────────────────────────

def test_drawer_has_three_origin_axis_sections(client):
    """[수집처][판매마켓][상세] — 출처 축. 옛 정보유형 축 잔존이면 red."""
    d, _ = _drawer(client)
    assert [k for k in d if k != "links"] == ["수집처", "판매마켓", "상세"], list(d)
    for old in ("주문정보", "상품정보", "배송정보"):
        assert old not in d, f"옛 섹션 '{old}'이 남아 있다"


def test_pcc_rendered_in_detail_section(client):
    """PCC 표기 — 통관고유부호는 [상세]에 실린다."""
    d, _ = _drawer(client)
    assert d["상세"]["개인통관고유부호(PCC)"] == "P123456789012", d["상세"]


def test_sourcing_section_carries_link_and_paste_text(client):
    """[수집처]는 원본 주소 + 소싱 상태 + 주문서 붙여넣기 텍스트를 담는다."""
    src = _drawer(client)[0]["수집처"]
    assert src["원본 주소"] == _ORDER["source_url"], src
    assert src["소싱 상태"] in ("연결됨", "소싱완료"), src
    # 복사텍스트는 v56이 조립한다 — 상품명·수량·수취인이 들어간다.
    paste = src["주문서 붙여넣기"]
    assert "접이식 차량용 책상" in paste and "x2" in paste, paste
    assert "홍*동" in paste, ("마스킹된 수취인이 빠졌다", paste)


def test_unlinked_order_says_so_instead_of_guessing(client, monkeypatch):
    """원본이 없으면 '원본 미연결' — 빈칸이나 추측값으로 때우지 않는다."""
    from src.dashboard import web_ui
    row = dict(_ORDER); row.pop("source_url"); row.pop("sku")
    monkeypatch.setattr(web_ui, "_load_orders", lambda: [row])
    src = _drawer(client)[0]["수집처"]
    assert src["소싱 상태"] == "원본 미연결", src
    assert src.get("원본 주소", "") == "", ("없는 원본 주소를 지어냈다", src)


# ── 복사 버튼 ────────────────────────────────────────────────────────────────

def test_copy_button_rendered_and_failure_is_honest(client):
    """붙여넣기 값은 복사 블록 + 버튼. 클립보드가 막히면 '복사됨' 거짓 표시 금지."""
    body = _drawer(client)[1]
    assert "ocCopy" in body and "oc-pre" in body
    seg = body.split("window.ocCopy")[1].split("window.ocClose")[0]
    assert "'복사 실패'" in seg, "실패를 성공으로 위장한다(가짜 성공)"
    assert "selectNodeContents" in seg, "실패 시 직접 고를 수 있게 선택해 주지 않는다"


def test_copy_block_uses_tokens_not_hardcoded_colors():
    """하드코딩 hex/px 금지 — 토큰만(app.css 단일 소스)."""
    # `.oc-copy`는 규칙이 둘이라 maxsplit=1로 블록 **전체**를 잡는다(첫 줄만 보면 공허하다).
    seg = SRC.split(".kgp-oc-row.oc-copy", 1)[1].split(".kgp-oc-x{")[0]
    assert ".oc-pre" in seg, "복사 블록 CSS를 통째로 못 잡았다 — 계약이 헛돈다"
    assert re.search(r"#[0-9a-fA-F]{3,6}\b", seg) is None, ("하드코딩 색", seg)
    for tok in ("var(--hanji)", "var(--line)", "var(--r-sm)", "var(--ink)"):
        assert tok in seg, tok


# ── 화면 수 동결 · 회귀 ───────────────────────────────────────────────────────

def test_no_new_screen_added():
    """드로어는 같은 페이지 오버레이 — 신규 라우트 0(브리프: 화면 수 동결)."""
    from src.order_webhook import app
    rules = {str(r.rule) for r in app.url_map.iter_rules()}
    assert "/dashboard/orders" in rules
    for banned in ("/dashboard/orders/detail", "/dashboard/orders/<", "/dashboard/sourcing"):
        assert not any(r.startswith(banned) for r in rules), f"신규 화면 {banned}"


def test_status_tabs_and_period_chips_unchanged(client):
    """#549가 세운 상태탭바·기간칩은 현행 유지(이번 변경 범위 밖)."""
    body = client.get("/dashboard/orders").get_data(as_text=True)
    for label in ("전체", "결제완료", "배송준비중", "배송중", "배송완료", "취소", "반품", "교환"):
        assert label in body, f"상태 탭 '{label}' 소실"
    for chip in ("오늘", "3일", "1주", "2주", "1개월"):
        assert ">" + chip + "<" in body, f"기간칩 '{chip}' 소실"


def test_orders_json_response_unchanged(client):
    """JSON 응답은 드로어 재편과 무관해야 한다(외부 계약 불변)."""
    r = client.get("/dashboard/orders?format=json")
    assert r.status_code == 200
    data = r.get_json()
    assert data["count"] == 1 and data["orders"][0]["order_id"] == "ORD-1", data
