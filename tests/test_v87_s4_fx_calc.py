"""tests/test_v87_s4_fx_calc.py — v87-S4 #1: 환율·마진 '계산' 버튼 무동작 수리.

■ 실기기 증상(오너 확정)
'계산'을 눌러도 아무 일도 안 남. URL만 `/dashboard/fx?buy_price=&currency=USD&margin_pct=45` 로 바뀜.
→ **빈 매입가가 쿼리로 실려 GET 왕복만 하고**(검증 없음) 결과 렌더도 없었다.

■ 더 큰 문제 — 식이 두 벌이었다
이 화면은 `판매가 = 매입가 × 환율 ÷ (1 − 마진)` 이라는 **자체 식**을 들고 있었다. 가격 정책(S3)의
`compute_sell_price`(해외배송비·마켓수수료·카드수수료·올림 포함)와 갈라져 **같은 입력에 다른 답**을
내놓는 구조였다. 오너 지시대로 S3 미리보기 로직을 재사용한다 — 화면은 그리기만 한다.

■ 계약
- 매입가 100 USD · 마진 45 → 결과(분해표) 렌더.
- 빈 매입가 → 버튼 비활성 + 왜 못 누르는지 안내(죽은 버튼 금지).
- GET 쿼리 왕복 제거(폼 제출 없음).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path("src/dashboard/web_ui.py").read_text(encoding="utf-8")
FX_VIEW = SRC.split("def fx_view")[1].split("\ndef _fx_calc_script")[0]
CALC_JS = SRC.split("def _fx_calc_script")[1].split("\ndef _policy_section")[0]


@pytest.fixture()
def client():
    import os
    os.environ["DASHBOARD_UI_ENABLED"] = "1"
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"; s["user_email"] = "a@b.c"; s["user_role"] = "admin"
    return c


# ── GET 왕복 제거 ─────────────────────────────────────────────────────────────

def test_no_get_form_roundtrip(client):
    body = client.get("/dashboard/fx").get_data(as_text=True)
    assert 'method="get"' not in body, "폼 제출이 남아 빈 값이 쿼리로 실려 왕복한다"
    assert 'name="buy_price"' not in body
    assert 'type="submit"' not in body.split('<h2 class="kgp-h2">마진 계산기</h2>')[1][:2000]


def test_calc_button_is_not_a_dead_submit(client):
    body = client.get("/dashboard/fx").get_data(as_text=True)
    seg = body.split('<h2 class="kgp-h2">마진 계산기</h2>')[1][:2500]
    assert 'id="fxCalcBtn"' in seg and 'type="button"' in seg
    # 빈 매입가에서 처음부터 못 누른다 + 이유를 말한다.
    assert "disabled" in seg and 'aria-disabled="true"' in seg
    assert "매입가를 입력" in seg


def test_result_container_and_noscript_present(client):
    body = client.get("/dashboard/fx").get_data(as_text=True)
    assert 'id="fxCalcOut"' in body
    assert "<noscript>" in body, "JS 없으면 버튼이 조용히 죽는다 — 안내가 필요하다"


# ── 식은 한 벌 ────────────────────────────────────────────────────────────────

def test_screen_does_not_reimplement_the_formula():
    """★ 두 벌 금지 — 화면이 자체 판매가 식을 들고 있으면 정책과 갈라진다."""
    assert "1 - mp" not in FX_VIEW and "1-mp" not in FX_VIEW
    assert "sell_krw" not in FX_VIEW
    # 계산은 서버 엔드포인트(=compute_sell_price) 호출로만.
    assert "/dashboard/fx/policy/preview" in CALC_JS


def test_preview_endpoint_uses_the_single_pricing_function():
    seg = SRC.split("def fx_policy_preview")[1].split("\n@web_ui_bp")[0]
    assert "compute_sell_price" in seg


# ── 오너 지정 계약값: 100 USD · 마진 45 ───────────────────────────────────────

def test_owner_contract_100usd_margin45_renders_a_result(client):
    """매입가 100 USD, 마진 45 → 결과가 나온다(분해표 + 판매가)."""
    r = client.post("/dashboard/fx/policy/preview", data={
        "sample_price": "100", "sample_currency": "USD", "sample_rate": "1350",
        "sample_market": "coupang", "sample_country": "US", "percent_margin": "45",
    })
    assert r.status_code == 200
    after = r.get_json()["after"]
    assert after["ok"] is True, after
    assert after["sell_price"] and after["sell_price"] > 0
    labels = [s["label"] for s in after["steps"]]
    assert any("매입가" in x for x in labels) and any("퍼센트 마진" in x for x in labels)
    # 입력한 마진이 실제로 반영된다(정책 기본값을 그냥 되돌려주는 게 아님).
    assert any(str(s["value"]).startswith("45.") for s in after["steps"] if "퍼센트 마진" in s["label"])


def test_empty_buy_price_never_reaches_a_calculation(client):
    """빈 매입가로는 계산 자체를 시작하지 않는다(JS 가드) — 소스 계약으로 못박음."""
    assert "num(buy.value)!==null&&num(buy.value)>0" in CALC_JS
    assert "btn.disabled=!ok" in CALC_JS


def test_missing_rate_is_honest_not_silent():
    """환율이 없으면 임의 환산하지 않고 그렇게 말한다."""
    assert "환율이 아직 없어 계산할 수 없어요" in CALC_JS
    assert re.search(r"if\(!rate\)", CALC_JS)


def test_failure_is_not_disguised_as_success():
    assert "계산 요청이 실패했어요" in CALC_JS
    assert "a.ok" in CALC_JS, "서버가 ok=false로 준 걸 결과처럼 그리면 안 된다"
