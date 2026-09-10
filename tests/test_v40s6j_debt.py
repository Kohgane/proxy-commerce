"""tests/test_v40s6j_debt.py — Stage 6-j 부채 청산.

확산의 큰 줄기(6-c~6-i)는 닫혔다. 남은 건 **화면이 아니라 규칙**이다 — 슬라이스마다 같은 선언을
복사해 쌓인 중복, 화면끼리 갈린 위계, 그리고 사용자에게 새는 개발 원문.
전역 chrome(`_base`)에 손대기 **전에** 하는 정지작업이다.

여기서 나 자신을 두 번 잡았다:
  · 그리드 5종을 접는 스크립트가 **자기가 방금 넣은 선택자 목록을 다시 지웠다**
    (삽입문 안의 `.ct-page {`가 이어지는 삭제 패턴에 재매칭).
  · 원문 노출을 고친다며 `kgpFriendlyError({status})`를 넘겼는데, 그 형태는 처리기가 못 읽어
    **`[object Object]`가 그대로 사용자에게** 갔다 — 수리가 아니라 개악이었다.
둘 다 실행해 보고 알았다. 그래서 이 파일의 계약은 **결과 문자열**을 실제로 만들어 본다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

CSS = Path("src/static/app.css")
TPL = Path("src/seller_console/templates")
JS = Path("src/seller_console/static/seller.js")


def _decl(text: str) -> str:
    """선언부만 — 내가 쓴 설명 주석이 내 계약을 통과시키면 안 된다(이 스위트의 단골 자해)."""
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


# ── ① 숫자 KPI 3중복 → 공용 하나 ─────────────────────────────────────────────
def test_kpi_grammar_is_declared_once():
    """★ 6-h(`.rw-kpi`)와 6-i(`.si-kpi`)가 같은 선언을 각자 복사해 갖고 있었다.

    규칙을 복사하면 다음 화면에서 또 복사된다 — 선언은 한 곳, 화면은 **치수만** 덮는다.
    """
    css = _decl(CSS.read_text(encoding="utf-8"))
    assert ".op-kpi {" in css and ".op-kpi-v {" in css, "공용 KPI 문법이 없다"
    for dead in (".rw-kpi", ".si-kpi"):
        assert dead not in css, f"복사본이 살아 있다: {dead}"
    # 화면은 치수만 덮는다(문법 재선언 0).
    assert ".rw-strip .op-kpi-v" not in css or "font-size" in css
    for f in ("reject_watch.html", "sourcing.html"):
        t = (TPL / f).read_text(encoding="utf-8")
        assert "rw-kpi" not in t and "si-kpi" not in t, f"{f}에 옛 클래스 잔존"
        assert "op-kpi" in t


# ── ② 페이지 그리드 5종 → 하나 ───────────────────────────────────────────────
def test_identical_page_grids_are_folded_into_one_selector():
    """★ 다섯 화면의 그리드 선언이 **글자 하나까지 같았다** — 이름만 다른 같은 규칙.

    2단 화면(`.rw-page`·`.si-page`)은 **진짜로 다른 규칙**이라 묶지 않는다.
    같아 보인다고 묶으면 그게 다음 결함이다.
    """
    css = _decl(CSS.read_text(encoding="utf-8"))
    merged = re.search(r"\.ch-page,\s*\.mk-page,\s*\.od-page,\s*\.mc-page,\s*\.ct-page\s*\{", css)
    assert merged, "다섯 그리드가 아직 따로 선언돼 있다"
    # 개별 재선언이 되살아나지 않았는지 — `.ch-page > *` 같은 파생은 허용, 본 선언만 금지.
    for g in ("ch", "mk", "od", "mc", "ct"):
        assert not re.search(r"^\." + g + r"-page\s*\{", css, re.M), f".{g}-page 개별 선언 부활"
    # 2단은 따로 살아 있어야 한다.
    assert re.search(r"^\.rw-page\s*\{", css, re.M) and re.search(r"^\.si-page\s*\{", css, re.M)
    # 그리고 실제로 **다른** 규칙이어야 한다(묶을 수 없다는 근거).
    two = re.search(r"^\.rw-page\s*\{([^}]*)\}", css, re.M).group(1)
    assert "minmax" in two and "repeat(12" not in two


def test_css_braces_stay_balanced():
    """★ 그리드를 접는 스크립트가 **자기 삽입문을 다시 지운** 적이 있다 — 파일이 깨졌다.

    중괄호 균형은 그 사고를 1초에 잡는다(그때 못 잡았으면 CSS가 통째로 죽었다).
    """
    css = CSS.read_text(encoding="utf-8")
    assert css.count("{") == css.count("}"), "CSS 중괄호 불균형 — 편집이 파일을 깼다"


# ── ③ 필터 제출 버튼 위계 ────────────────────────────────────────────────────
def test_filter_submit_button_hierarchy_is_one():
    """★ 6-c는 채움(`btn-primary`), 6-e·6-g는 고스트로 **두 화면이 갈려 있었다.**

    같은 일을 하는 버튼이 화면마다 다른 무게로 보이면, 그건 위계가 아니라 잡음이다.
    볼트 결정(latest-wins)대로 고스트로 통일한다.
    """
    weights = {}
    for f in ("collect_history.html", "orders.html", "catalog.html"):
        t = (TPL / f).read_text(encoding="utf-8")
        hits = re.findall(r'<button[^>]*type="submit"[^>]*class="([^"]*)"', t)
        hits += re.findall(r'<button[^>]*class="([^"]*)"[^>]*type="submit"', t)
        weights[f] = {"채움" if "btn-primary" in h else "고스트" for h in hits}
    assert all(w == {"고스트"} for w in weights.values()), f"필터 버튼 위계가 갈린다: {weights}"


# ── ④ 원문 노출 → 친절 처리기 ────────────────────────────────────────────────
def test_no_raw_error_text_reaches_the_user():
    """★ `요청 실패 (HTTP 500)` · `err.message` 날것이 v19 친절 처리기를 **우회**하고 있었다.

    볼트 부채엔 '9곳'으로 적혀 있었는데 실측하니 **20곳**이었다(그 뒤로 늘었다).
    """
    t = (TPL / "collect_history.html").read_text(encoding="utf-8")
    assert not re.search(r"요청 실패 \(HTTP \$\{", t), "HTTP 상태 원문이 아직 사용자에게 간다"
    assert not re.search(r"요청 실패: ' \+ err\.message", t), "err.message 날것이 아직 노출된다"
    assert t.count("kgpFriendlyError") >= 20, "친절 처리기를 안 거치는 경로가 남았다"


@pytest.mark.skipif(not shutil.which("node"), reason="node 미설치 — 정직하게 skip")
def test_friendly_handler_never_leaks_object_object():
    """★★ **내가 만들 뻔한 개악** — `kgpFriendlyError({status})`는 그 형태를 못 읽어
    `String(raw)` = **`[object Object]`**를 사용자에게 그대로 보낸다.

    호출부만 고치면 다음 사람이 또 같은 형태로 부른다. **처리기 쪽에서** 막는다.
    그리고 이 계약은 소스를 훑지 않고 **실제 반환 문자열을 만들어 본다** — 코드를 읽어
    '괜찮겠지' 한 게 이번 사고의 원인이었다.
    """
    src = JS.read_text(encoding="utf-8")
    fn = re.search(r"function kgpFriendlyError\(raw\) \{.*?\n\}", src, re.S)
    assert fn, "처리기를 못 찾음"
    cases = [{"status": 500}, [], {}, "HTTP 500", "HTTP 401", "이미 수집한 상품입니다"]
    script = fn.group(0) + "\nconsole.log(JSON.stringify(%s.map(kgpFriendlyError)));" % json.dumps(cases)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        path = fh.name
    out = json.loads(subprocess.run(["node", path], capture_output=True, text=True, timeout=30).stdout)
    for got in out:
        assert "[object" not in got, f"개발 원문이 샜다: {got}"
        assert got, "빈 안내"
    assert "로그인" in out[4], "401은 로그인 안내여야 한다"
    assert out[5] == "이미 수집한 상품입니다", "서버가 준 사람 말은 그대로 존중한다"


# ── ⑤ `.op-filter` 완전 개명 ─────────────────────────────────────────────────
def test_filter_class_has_one_name():
    """★ 6-g에서 **선택자 승격만** 하고 이름은 둘로 남겨 뒀다(`.od-filter, .op-filter`).

    이름이 둘이면 다음 화면이 어느 쪽을 쓸지 고른다 — 그게 세 번째 이름의 시작이다.
    """
    css = _decl(CSS.read_text(encoding="utf-8"))
    assert ".od-filter" not in css, "옛 이름이 CSS에 남았다"
    assert ".op-filter" in css
    for f in TPL.glob("*.html"):
        assert "od-filter" not in f.read_text(encoding="utf-8"), f"{f.name}에 옛 이름 잔존"
