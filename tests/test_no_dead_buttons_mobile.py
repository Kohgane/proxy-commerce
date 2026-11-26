"""폰 화면 죽은 버튼 계약(코파일럿 #1044 → 오너 11-26 오후 ③에서 바인딩 판정을 넓혀 받음).

폰 화면 템플릿(`_m5_flow`·`_risk_block`·`_coupang_exposure`·`mobile_*`)의 `<button data-role="…">`마다
눌림을 받는 코드가 있어야 한다. 바인딩으로 치는 것(실제로 쓰는 다섯 꼴):
  1) 선택자 `[data-role=R]`·`[data-role="R"]`  2) 비교 `=== 'R'`·`== "R"`·`case 'R'`  3) 처리표 키 `'R':`
  4) 버튼 id를 `getElementById('X')`·`#X`로 잡음  5) 버튼의 다른 속성·클래스로 잡음(`hasAttribute('data-view')` · `.cpx-vbtn`)
  6) 위임 속성(`data-act`·`data-override`·`data-market-status`) — 예외 목록으로 보고만
부분 템플릿(`_risk_block` 등)은 그것을 include하는 화면의 코드까지 본다(눌림은 들여놓은 화면이 받는다).
템플릿 안 JS 문자열로 그리는 버튼(`'<button … data-role="R"…'`)도 같은 잣대.
"""
from __future__ import annotations

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "src" / "seller_console" / "templates"
TARGET_NAMES = ("_m5_flow.html", "_risk_block.html", "_coupang_exposure.html")
_SHARED_JS = (Path(__file__).resolve().parents[1] / "src" / "seller_console" / "static" / "seller.js",
              Path(__file__).resolve().parents[1] / "src" / "static" / "m_shell.js")


def _targets():
    out = [TEMPLATE_DIR / n for n in TARGET_NAMES if (TEMPLATE_DIR / n).exists()]
    return out + sorted(TEMPLATE_DIR.glob("mobile_*.html"))


def _with_includes(text: str, seen=None) -> str:
    seen = seen or set()
    out = text
    for name in re.findall(r"{%\s*include\s+[\"']([^\"']+)[\"']", text):
        p = TEMPLATE_DIR / name
        if p.exists() and name not in seen:
            seen.add(name)
            out += "\n" + _with_includes(p.read_text(encoding="utf-8"), seen)
    return out


def _buttons(text: str):
    """(role, tag 문자열) — HTML 버튼과 JS 문자열 속 버튼 둘 다."""
    for m in re.finditer(r"<button\b[^>]*>", text, re.I):
        tag = m.group(0)
        r = re.search(r"\bdata-role\s*=\s*\\?[\"']([^\"'\\]+)", tag)
        if r:
            yield r.group(1), tag


def _bound(role: str, tag: str, text: str) -> str:
    e = re.escape(role)
    if re.search(r"\[data-role\s*=\s*\\?[\"']?" + e + r"\\?[\"']?\]", text):
        return "selector"
    if re.search(r"(?:===?|case)\s*[\"']" + e + r"[\"']", text):
        return "compare"
    if re.search(r"[\"']" + e + r"[\"']\s*:", text):
        return "map"
    bid = re.search(r"\bid\s*=\s*\\?[\"']([A-Za-z][\w-]*)", tag)
    if bid and (re.search(r"getElementById\(\s*[\"']" + re.escape(bid.group(1)) + r"[\"']", text)
                or re.search(r"[\"']#" + re.escape(bid.group(1)) + r"\b", text)):
        return "id"
    for attr in re.findall(r"\b(data-[a-z-]+)\s*=", tag):
        if attr != "data-role" and re.search(r"hasAttribute\(\s*[\"']" + re.escape(attr) + r"[\"']", text):
            return "attr"
    cls = re.search(r"\bclass\s*=\s*\\?[\"']([^\"'\\]+)", tag)
    for c in (cls.group(1).split() if cls else []):
        if c.startswith(("btn", "m5-btn", "kgp-risk-btn")):
            continue                                            # 공용 꾸밈 클래스는 바인딩 근거가 아니다
        if re.search(r"[\"'][^\"']*\." + re.escape(c) + r"(?![\w-])", text):
            return "class"
    return ""


def _includers(name: str) -> str:
    out = []
    for p in TEMPLATE_DIR.glob("*.html"):
        t = p.read_text(encoding="utf-8")
        if re.search(r"{%\s*include\s+[\"']" + re.escape(name) + r"[\"']", t):
            out.append(t)
    return "\n".join(out)


def test_mobile_template_buttons_have_handlers():
    shared = "\n".join(p.read_text(encoding="utf-8") for p in _SHARED_JS if p.exists())
    dead, delegated = [], []
    for path in _targets():
        text = _with_includes(path.read_text(encoding="utf-8")) + "\n" + shared + "\n" + _includers(path.name)
        for role, tag in sorted(set(_buttons(path.read_text(encoding="utf-8")))):
            if _bound(role, tag, text):
                continue
            marks = [m for m in ("data-act", "data-override", "data-market-status") if m in tag]
            (delegated if marks else dead).append(f"{path.name} · {role}" + (f" · 위임 {','.join(marks)}" if marks else ""))
    assert not dead, "눌림을 받는 코드가 없는 버튼:\n" + "\n".join(dead) + ("\n\n(위임 예외: " + "; ".join(delegated) + ")" if delegated else "")


def test_contract_still_catches_a_dead_button():
    """잣대가 너무 느슨해 다 통과시키지 않는지 — 아무도 안 받는 버튼은 걸려야 한다."""
    tag = '<button type="button" class="btn m5-btn" data-role="m5-ghost" id="m5Ghost">유령</button>'
    assert _bound("m5-ghost", tag, tag + "<script>document.getElementById('m5Other')</script>") == ""
    assert _bound("m5-ghost", tag, tag + "<script>q('[data-role=m5-ghost]')</script>") == "selector"
    assert _bound("m5-ghost", tag, tag + "<script>document.getElementById('m5Ghost')</script>") == "id"
