"""V41-3(오너 2026-10-28 15:32 「아직 지저분」) — 수집한 상품 목록: 데스크톱에서 마켓 뱃지 = 글자 하나 원 4개, 마지막 동작 = 시각 + 한 단어.
CSS 계약(토큰만·기하 문자열 금지) + 렌더 계약(마크업 훅이 실제로 나온다)."""
from __future__ import annotations

import json
import os
import re

import pytest

APP_CSS = open("src/static/app.css", encoding="utf-8").read()
BLOCK = APP_CSS[APP_CSS.index("V41-3 수집한 상품 목록"):]


@pytest.fixture()
def client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-v413"; s["user_email"] = "v413@test.local"; s["user_role"] = "seller"
        yield c


def _seed(uid="u-v413"):
    from src.seller_console import collect_history_store as CH
    iid = CH.append(source="extension", url="https://item.taobao.com/item.htm?id=94130", title="V41-3 상품", image="https://x.test/a.jpg",
                    price="10", currency="CNY", seller_id=uid)
    iid = iid[0] if isinstance(iid, tuple) else iid
    CH.update(iid, seller_ids={uid}, extra_json=json.dumps({
        "uploaded": [{"market": "coupang:gogane", "account": "gogane", "success": True, "at": "2026-10-28T10:00:00+09:00", "url": "https://c.test/1"}]}))
    return iid


def _rule(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", BLOCK)
    assert m, f"{selector} 규칙이 V41-3 블록에 없음"
    return m.group(1)


def test_badge_is_letter_circle_desktop_only():
    body = _rule(".mk-badge")
    assert "width: 32px" in body and "height: 32px" in body
    assert "border-radius: var(--radius-pill)" in body
    assert "display: none" in _rule(".mk-badge .mk-full") and "display: inline" in _rule(".mk-badge .mk-short")
    # 전부 데스크톱 미디어 안에만 — 모바일(카드형)은 글자 뱃지 그대로
    assert BLOCK.count("@media (min-width: 768px)") >= 1
    assert not re.search(r"^\.mk-badge", BLOCK, re.M)                         # 미디어 밖 최상위 .mk-badge 규칙 0


def test_badge_states_use_tokens_only():
    assert "var(--teal)" in _rule(".mk-badge.kind-done")                       # 등록 = 청록 채움
    assert "var(--danger)" in _rule(".mk-badge.kind-bad")                      # 반려 = 신호 유지
    assert "dashed" in _rule(".mk-badge.kind-none")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", BLOCK)                        # 하드코딩 hex 0
    assert "border-radius: 50%" not in BLOCK and "clip-path" not in BLOCK      # Stage 5 기하 금지 계약


def test_when_column_short_word_only():
    assert "display: none" in _rule(".ch-c-when .ch-when-short")      # short = 짧은 시각(모바일용) — 데스크톱에선 시각 중복
    assert "display: inline" in _rule(".ch-c-when .ch-when-text")     # 「10-28 18:38 · 쿠팡 등록」
    assert '" · "' in _rule(".ch-c-when .ch-when-text::before")


def test_rows_render_hooks(client):
    _seed()
    html = client.get("/seller/collect/history").get_data(as_text=True)
    assert 'class="ch-thumb ch-thumb-lg"' in html
    assert 'class="kgp-open-drawer ch-title-1"' in html
    row = html[html.index('data-role="mk-chips"'):]
    assert re.search(r'class="mk-chip mk-badge kind-(done|wait)" data-role="mk-chip"', row)   # 등록 기록 = 뱃지 하나(심사 중이면 wait)
    assert '<span class="mk-short">고</span>' in row and '<span class="mk-full">고가네 등록됨</span>' in row   # 글자 하나 + 전문(툴팁/모바일)
    assert 'data-role="mk-slot-empty"' in row                                   # 빈 자리도 원으로 유지(순서 고정)
    assert 'class="ch-when-short"' in html and 'class="ch-when-text"' in html
