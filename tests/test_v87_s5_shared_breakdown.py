"""tests/test_v87_s5_shared_breakdown.py — v87-S5: 분해표 컴포넌트 단일화 + 로고 홈링크.

■ 오너 캡처 채점
1. 계산 버튼은 실동작(242,600 렌더 확인). 단 **결과 카드가 S3 미리보기와 다른 저밀도 마크업** —
   "매입가 × 환율86616.6"처럼 레이블과 값이 붙어 찍혔다. 계산기만 `div` 두 개를 나란히 두는
   드로어 행(`kgp-oc-row`)을 썼고, 정책 미리보기는 표(`kgp-table`)를 썼다 — **마크업이 두 벌**.
2. 헤더 '고가브릿지' 로고가 클릭 무반응으로 보였다.

■ 이번 계약
- 식을 `compute_sell_price` 한 벌로 만든 것과 **같은 이유로 마크업도 한 벌**. 두 화면이 같은
  컴포넌트(`window.kgpBreakdown`)를 렌더한다 — 정의는 소스에 **하나**, 호출은 둘.
- 두 셸 로고가 홈으로 가는 anchor이고, 누를 수 있게 보인다(cursor + hover 반응).

※ 이 대시보드는 Jinja 파셜이 아니라 `render_template_string` 단일 파일이라, '같은 파셜'의 실체는
  `_BREAKDOWN_COMPONENT_JS` 상수 하나를 두 호출자가 함께 쓰는 것이다(경로 = 그 단일 정의).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

SRC = Path("src/dashboard/web_ui.py").read_text(encoding="utf-8")
CONSOLE_CSS = Path("src/seller_console/static/console.css").read_text(encoding="utf-8")
SELLER_BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")


@pytest.fixture()
def client():
    import os
    os.environ["DASHBOARD_UI_ENABLED"] = "1"
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"; s["user_email"] = "a@b.c"; s["user_role"] = "admin"
    return c


# ── 컴포넌트가 한 벌인가 ──────────────────────────────────────────────────────

def test_breakdown_component_is_defined_exactly_once_in_source():
    assert SRC.count("_BREAKDOWN_COMPONENT_JS = ") == 1
    assert SRC.count("window.kgpBreakdown = function") == 1, "분해표 렌더러가 두 벌이다"
    assert SRC.count("window.kgpWon = function") == 1, "금액 표기가 두 벌이다"


def test_page_ships_the_component_once_and_both_screens_call_it(client):
    body = client.get("/dashboard/fx").get_data(as_text=True)
    assert body.count("window.kgpBreakdown = function") == 1, "컴포넌트가 페이지에 두 번 실렸다"
    assert body.count("kgpBreakdown(") == 2, "두 화면이 같은 컴포넌트를 부르지 않는다"


def test_neither_screen_reimplements_the_row_markup():
    """★ 두 벌 금지 — 자체 행/금액 빌더가 남아 있으면 또 갈라진다."""
    calc = SRC.split("def _fx_calc_script")[1].split("\ndef _policy_section")[0]
    policy = SRC.split("def _policy_section")[1]
    assert "kgp-oc-row" not in calc, "계산기가 드로어 행 마크업을 다시 쓴다(붙어 찍히는 원인)"
    assert "function row(k,v)" not in calc and "function won(n)" not in calc
    assert "function money(n)" not in policy, "정책 미리보기가 자체 금액 표기를 쓴다"


def test_component_uses_a_table_not_side_by_side_divs():
    seg = SRC.split("_BREAKDOWN_COMPONENT_JS = ")[1].split('"""', 2)[1]
    assert "kgp-table" in seg and "<td" in seg
    assert "kgp-kpi-value" in seg, "판매가 강조가 없다"


# ── 실행 증명: 두 화면이 정말 같은 것을 그리는가 ──────────────────────────────

_HARNESS = r"""
import fs from 'fs';
import { JSDOM } from 'jsdom';
const js = fs.readFileSync(process.argv[2], 'utf8');
const dom = new JSDOM(`<body><form id="kgpPolicyForm"></form><div id="kgpPolicyPreview"></div>
<input id="fxBuy"><select id="fxCur"><option value="USD" selected>USD</option></select>
<input id="fxMargin" value="20"><button id="fxCalcBtn" disabled>x</button>
<p id="fxCalcHint"></p><div id="fxCalcOut"></div></body>`, {runScripts:'outside-only'});
const w = dom.window;
w.fetch = () => Promise.resolve({json: () => Promise.resolve({ok:true,
  before:{ok:true,sell_price:200000,steps:[]},
  after: {ok:true, sell_price: 242600, formula:'f',
    steps:[{label:'매입가 × 환율', value:86616.6},{label:'퍼센트 마진', value:'45.00%'}]}})});
w.eval(js);
const btn = w.document.getElementById('fxCalcBtn'), buy = w.document.getElementById('fxBuy');
buy.value='100'; buy.dispatchEvent(new w.Event('input'));
w.document.getElementById('fxMargin').value='45';
btn.dispatchEvent(new w.Event('click'));
setTimeout(()=>{
  const calc = w.document.getElementById('fxCalcOut');
  const pol  = w.document.getElementById('kgpPolicyPreview');
  const cr = calc.querySelectorAll('table.kgp-table tbody tr');
  const pr = pol.querySelectorAll('table.kgp-table tbody tr');
  console.log(JSON.stringify({
    calcRows: cr.length, polRows: pr.length,
    calcCells: cr.length ? cr[0].querySelectorAll('td').length : 0,
    polCells: pr.length ? pr[0].querySelectorAll('td').length : 0,
    calcLabel: cr.length ? cr[0].querySelectorAll('td')[0].textContent : '',
    calcValue: cr.length ? cr[0].querySelectorAll('td')[1].textContent : '',
    calcPrice: (calc.querySelector('.kgp-kpi-value')||{}).textContent || '',
    polPrice: (pol.querySelector('.kgp-kpi-value')||{}).textContent || ''
  }));
}, 150);
"""


def _jsdom_ok() -> bool:
    return Path("node_modules/jsdom/package.json").exists()


@pytest.mark.skipif(not _jsdom_ok(), reason="jsdom 미설치(npm i -D jsdom)")
def test_both_screens_render_the_identical_structure(client, tmp_path):
    """★ 오너 증상 재현 방지 — 레이블과 값이 **분리된 칸**에 들어간다."""
    body = client.get("/dashboard/fx").get_data(as_text=True)
    js_file = tmp_path / "fx.js"
    js_file.write_text("\n;\n".join(re.findall(r"<script>(.*?)</script>", body, re.S)), encoding="utf-8")
    runner = Path("fxrun.v87s5.mjs")            # jsdom 해석을 위해 레포 루트에서 실행
    runner.write_text(_HARNESS, encoding="utf-8")
    try:
        out = subprocess.run(["node", str(runner), str(js_file)], capture_output=True, timeout=90)
        assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
        r = json.loads(out.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
    finally:
        runner.unlink(missing_ok=True)

    assert r["calcRows"] == 2 and r["polRows"] == 2, r
    # 붙어 찍히던 원인 = 한 칸에 레이블+값. 이제 각자 칸을 갖는다.
    assert r["calcCells"] == 2 and r["polCells"] == 2, r
    assert r["calcLabel"] == "매입가 × 환율" and r["calcValue"] == "86616.6", r
    # 두 화면의 금액 표기가 같은 함수에서 나온다.
    assert r["calcPrice"] == r["polPrice"] == "₩242,600", r


# ── 로고 = 홈 링크 ────────────────────────────────────────────────────────────

def test_dashboard_shell_logo_links_landing(client):
    """v87-S6: 로고=사이트 정문(랜딩 "/"). 콘솔 홈(/dashboard/)이 아니다(오너 확정)."""
    body = client.get("/dashboard/fx").get_data(as_text=True)
    assert re.search(r'<a class="kgp-brand" href="/"', body), "대시보드 로고가 랜딩 링크가 아니다"
    assert not re.search(r'<a class="kgp-brand" href="/dashboard/"', body), "콘솔 홈으로 되돌아갔다"


def test_seller_shell_logo_links_landing():
    assert re.search(r'<a href="/"[^>]*class="[^"]*console-brand', SELLER_BASE), \
        "셀러 콘솔 사이드바 로고가 랜딩 링크가 아니다"
    assert re.search(r'<a href="/"[^>]*class="[^"]*console-topbar-brand', SELLER_BASE), \
        "셀러 콘솔 탑바 로고가 랜딩 링크가 아니다"
    assert not re.search(r'<a href="/seller/"[^>]*class="[^"]*console-(topbar-)?brand', SELLER_BASE), \
        "셀러 셸 로고가 콘솔 홈으로 되돌아갔다"


def test_both_logos_look_clickable():
    """anchor만 있고 반응이 없으면 '비링크'로 읽힌다 — 오너가 본 상태가 정확히 그것이었다."""
    dash = SRC.split(".kgp-brand{")[1].split("\n.kgp-nav")[0]
    assert "cursor:pointer" in dash
    assert re.search(r"\.kgp-brand:hover\{[^}]*opacity", SRC), "hover 반응이 없다"
    assert "cursor: pointer" in CONSOLE_CSS.split(".console-brand {")[1].split("}")[0]
    assert re.search(r"\.console-brand:hover\s*\{[^}]*opacity", CONSOLE_CSS)


def test_logo_is_keyboard_reachable():
    assert re.search(r"\.kgp-brand:focus-visible\{", SRC)
    assert re.search(r"\.console-brand:focus-visible\s*\{", CONSOLE_CSS)
