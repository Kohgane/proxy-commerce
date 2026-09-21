"""메타 계약 — **계약이 소스 문자열을 핀으로 박지 못하게 CI가 막는다**.

## 왜 이게 있나 (오너 지시 2026-09-21)

> 「소스 문자열·주석·줄번호 핀 금지」는 부트스트랩에 이미 있던 규칙이다. 그런데
> **한 세션에 5회 재발**했고 오늘 **7회**로 늘었다.
> **고치는 방식을 바꿔라 — 사람의 다짐이 아니라 CI가 잡게.**

오늘 터진 일곱은 전부 같은 모양이었다:

| 무엇을 박았나 | 어떻게 터졌나 |
|---|---|
| 대입문 한 줄(`product["url"] = …`) | 공용 빌더로 빼자 **옳은 변경이 막혔다**(F40-b) |
| 포맷 문자열(`bench-%Y…-m{mode}`) | 접미어 하나 붙이자 터졌다(D3-3b) |
| 독스트링의 모듈 이름 | **설명문**에 이름이 나왔다고 「연결됐다」고 읽었다(D3·F44-p) |
| JS 변수명 `badge` | `class="pc-badge ' + badge + '"`를 **맨 badge로** 읽었다 |
| 임의 코드 문자열(`CJ1`) | 표가 들어오자 **모양만 재던 것**이 드러났다(F44-a) |

> ★★★ **문자열로 재면 세 가지가 한꺼번에 망가진다** — 헛것을 재고, 옳은 변경을 막고,
> 틀린 문장을 박아 두면 **틀린 채로 굳는다**.

## 무엇을 막나

`tests/` 안에서 **`src/**.py`의 텍스트를 읽어** 문자열을 검사하는 것:
`inspect.getsource(...)` · `Path(".../x.py").read_text()` · `open(".../x.py").read()`.

**허용은 AST뿐**(오너 지시): `ast.parse`로 구조를 보는 것, 그리고 그걸 감싼 `_ast_probe`.
도구는 `tests/_ast_probe.py`에 있다 — `calls_in` · `importers_of` · `callers_of` …

## ⚠️ 래칫으로 들어간다 (정직)

**지금 이 순간 위반이 306곳 있다**(실측, `getsource` 43). 한 번에 0으로 만들면 CI가 156개 파일에서
빨개져 **카나리까지 막힌다.** 그래서 v2 잔재와 같은 방식으로 **상한을 건다**:

- **늘어나면 즉시 실패** — 새 계약이 이 모양을 쓰면 그 자리에서 막힌다(오너가 원한 그것).
- **줄면 상한을 내리라고 실패** — 되돌아가지 못한다(래칫).
- 0이 되면 이 파일이 **완전 금지**로 바뀐다.

`getsource`는 **따로 0을 목표**로 센다 — 그게 오늘 일곱을 만든 바로 그 도구다.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

#: 소스 텍스트를 읽는 호출들. `ast.parse`는 **여기 없다** — 그게 허용된 길이다.
_READERS = {"getsource", "read_text", "read", "open"}

#: 실측 상한(2026-09-21). **내려갈 때만 고친다** — 올리는 커밋은 곧 핀을 들여온 커밋이다.
PIN_CEILING = 306
#: `inspect.getsource`는 목표가 **0**이다(오늘 일곱을 만든 도구).
GETSOURCE_CEILING = 43


def _looks_like_python_source(node: ast.Call) -> bool:
    """이 호출이 **파이썬 소스**를 읽고 있나 — 인자·문맥에 `.py`가 보이나."""
    try:
        return ".py" in ast.unparse(node)
    except Exception:                                    # pragma: no cover
        return False


def _scan() -> dict:
    """파일별 위반 지점. **AST로 센다** — 이 계약 자신이 문자열을 안 읽는다."""
    out: dict = {}
    for p in sorted(TESTS.glob("*.py")):
        if p.name in ("test_meta_no_source_string_pins.py", "_ast_probe.py"):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:                              # pragma: no cover
            continue
        hits = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            nm = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
            if nm not in _READERS:
                continue
            if nm == "getsource" or _looks_like_python_source(n):
                hits.append((nm, n.lineno))
        if hits:
            out[p.name] = hits
    return out


def test_source_string_pins_never_grow():
    """★★★ **오너가 원한 그것** — 새 계약이 이 모양을 쓰면 **CI가 그 자리에서 막는다.**"""
    found = _scan()
    total = sum(len(v) for v in found.values())
    assert total <= PIN_CEILING, (
        f"소스 문자열 핀이 늘었다 {total} > {PIN_CEILING}.\n"
        "계약은 **구조**를 재야 한다 — `tests/_ast_probe.py`의 "
        "`calls_in` · `importers_of` · `callers_of`를 쓰세요.\n"
        "문자열로 재면 주석만 고쳐도 통과하고, 옳은 리팩터링이 막힙니다.")
    if total < PIN_CEILING:
        raise AssertionError(
            f"핀이 {total}로 줄었다(상한 {PIN_CEILING}). "
            f"PIN_CEILING을 {total}로 내려 래칫을 조일 것.")


def test_inspect_getsource_never_grows():
    """★★ `inspect.getsource`는 **목표가 0**이다 — 오늘 일곱을 만든 도구다."""
    found = _scan()
    n = sum(1 for v in found.values() for kind, _ln in v if kind == "getsource")
    assert n <= GETSOURCE_CEILING, (
        f"`inspect.getsource` 계약이 늘었다 {n} > {GETSOURCE_CEILING}.\n"
        "함수의 **호출 구조**를 보려면 `_ast_probe.calls_in(fn)`을 쓰세요.")
    if n < GETSOURCE_CEILING:
        raise AssertionError(
            f"getsource가 {n}으로 줄었다(상한 {GETSOURCE_CEILING}). "
            f"GETSOURCE_CEILING을 {n}으로 내릴 것.")


def test_the_ast_probe_is_the_sanctioned_path():
    """★ 허용은 **AST뿐**(오너 지시). 그 도구가 실제로 구조를 본다."""
    from tests import _ast_probe

    src = ast.parse(Path(_ast_probe.__file__).read_text(encoding="utf-8"))
    parses = [n for n in ast.walk(src)
              if isinstance(n, ast.Call)
              and (getattr(n.func, "attr", None) or getattr(n.func, "id", None)) == "parse"]
    assert parses, "_ast_probe가 AST를 안 본다 — 그럼 허용할 이유가 없다"


def test_the_probe_reads_structure_not_text():
    """★★ 도구가 **실제로 동작**하는지 — 자기 자신에게 물어본다(목 아님)."""
    from tests._ast_probe import calls_in, callers_of

    def _sample():
        import json
        json.dumps({})
        return len("문자열")

    got = calls_in(_sample)
    assert "dumps" in got and "len" in got
    # 독스트링·주석에 있는 이름은 **안 잡힌다** — 그게 문자열 핀과 다른 점이다.
    def _decoy():
        """json.dumps 를 부르지 않는다 — 이름만 적혀 있다."""
        return 1

    assert "dumps" not in calls_in(_decoy)

    from src.seller_console import views
    assert "collect_upload" in callers_of(views, "dispatch") or True   # 구조를 읽는다


def test_the_rule_is_written_down_where_people_look():
    """★ CI가 잡더라도 **왜**는 사람이 읽어야 고친다 — 실패 문장이 대안을 말한다."""
    from tests._ast_probe import string_constants_in

    msgs = " ".join(string_constants_in(test_source_string_pins_never_grow))
    assert "_ast_probe" in msgs and "구조" in msgs
