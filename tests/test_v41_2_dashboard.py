"""V41-2(오너 2026-10-28 15:32 「간결·임팩트」) — 대시보드 첫 화면 = 세리프 큰 숫자 하나 + 할 일 셋 + CTA 하나, 나머지는 접힘."""
from __future__ import annotations

import json
import os
import re

import pytest

APP_CSS = open("src/static/app.css", encoding="utf-8").read()
TPL = open("src/seller_console/templates/dashboard.html", encoding="utf-8").read()


@pytest.fixture()
def client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-v412"; s["user_email"] = "v412@test.local"; s["user_role"] = "seller"
        yield c


def _seed(n: int, uid="u-v412"):
    from src.seller_console import collect_history_store as CH
    ids = []
    for i in range(n):
        iid = CH.append(source="extension", url=f"https://item.taobao.com/item.htm?id=9412{i}", title=f"상품 {i}", image="", price="10", currency="CNY", seller_id=uid)
        iid = iid[0] if isinstance(iid, tuple) else iid
        CH.update(iid, seller_ids={uid}, extra_json=json.dumps({"price_status": "needs_check"}))
        ids.append(iid)
    return ids


def test_hero_number_and_single_cta(client):
    _seed(5)
    html = client.get("/seller/dashboard").get_data(as_text=True)
    a = html[html.index('data-role="hb-attention"'):]
    assert re.search(r'class="hb-hero-num" data-role="hb-attention-n">5<', a)       # 큰 숫자 = 오늘 할 일
    assert a.count('data-role="hb-hero-cta"') == 1 and 'href="/seller/manual-collect"' in a   # CTA 하나(주황)
    assert 'class="hb-todo hb-todo-fold"' in a and 'data-role="hb-todo-more"' in a and "할 일 2줄 더 보기" in a
    assert a.count('class="hb-todo-row" data-kind=') == 5                            # 줄은 전부 DOM에(접힘만)


def test_zero_todo_says_so(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert 'data-role="hb-attention-none">없음' in html and "hb-hero-zero" in html


def test_folds_wrap_secondary_sections(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    for cls, role in (("hb-d-fold", "hb-recent"), ("hb-e-fold", "hb-today")):
        i = html.index(f'class="hb-fold {cls}"'); j = html.index("</details>", i)
        assert f'data-role="{role}"' in html[i:j], role                              # 접힌 안에 그대로 있다
    assert "<details" not in html[html.index('data-role="hb-attention"'):html.index("</section>", html.index('data-role="hb-attention"'))]


def test_css_single_accent_and_min_font():
    assert ".hb-todo-fold:not(.is-open) > .hb-todo-row:nth-child(n+4) { display: none; }" in APP_CSS
    assert ".hb-grid .hb-tile.is-alert .hb-tile-v { color: var(--text-strong); }" in APP_CSS   # 숫자 주황 금지(CTA만)
    assert ".hb-grid { font-size: var(--body-lg); }" in APP_CSS
    block = APP_CSS[APP_CSS.index("V41-2 대시보드"):]
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", block)                                # 하드코딩 hex 0
    for cls in ("hb-hero", "hb-hero-num", "hb-hero-cta", "hb-todo-more", "hb-fold", "hb-fold-sum", "hb-dot"):
        assert f".{cls}" in APP_CSS, cls
