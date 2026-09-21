"""계약이 **구조**를 보게 하는 도구 — 소스 문자열을 읽지 않는다.

## 왜 있나 (오너 지시 2026-09-21)

> 「소스 문자열·주석·줄번호 핀 금지」는 부트스트랩에 이미 있던 규칙인데 **한 세션에 7회** 재발했다.
> **고치는 방식을 바꿔라** — 사람의 다짐이 아니라 **CI가 잡게.**

문자열로 재면 세 가지가 한꺼번에 망가진다:

| | 어떻게 |
|---|---|
| **헛것을 잰다** | 독스트링·주석에 그 단어가 있으면 통과한다(F44-p·D3에서 실제로 그랬다) |
| **옳은 변경을 막는다** | 대입문 한 줄을 공용 함수로 빼면 터진다(F40-b) |
| **거짓을 지킨다** | 틀린 문장을 박아 두면 틀린 채로 굳는다(F45 `assert result is True`) |

그래서 **AST**를 본다. 「이 함수가 저 함수를 부르나」·「이 모듈이 저 모듈을 import 하나」는
**구조**이고, 주석을 고쳐도 바뀌지 않으며, 리팩터링에는 정직하게 따라온다.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Iterable, Set

ROOT = Path(__file__).resolve().parents[1]


def _tree_of(fn) -> ast.AST:
    src = inspect.getsource(fn)
    return ast.parse(_dedent(src))


def _dedent(src: str) -> str:
    import textwrap
    return textwrap.dedent(src)


def calls_in(fn) -> Set[str]:
    """그 함수가 **부르는 이름들**(`a.b()` → `b`와 `a.b` 둘 다).

    「이 라우트가 권한 검사를 부르나」를 문자열이 아니라 **호출 구조**로 잰다.
    """
    out: Set[str] = set()
    for n in ast.walk(_tree_of(fn)):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name):
            out.add(f.id)
        elif isinstance(f, ast.Attribute):
            out.add(f.attr)
            try:
                out.add(ast.unparse(f))
            except Exception:                            # pragma: no cover
                pass
    return out


def names_in(fn) -> Set[str]:
    """그 함수가 **쓰는 이름들**(변수·속성). 상수 이름을 확인할 때."""
    out: Set[str] = set()
    for n in ast.walk(_tree_of(fn)):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def string_constants_in(fn) -> Set[str]:
    """그 함수의 **문자열 리터럴**(독스트링 제외).

    ★ 이건 「소스를 읽는 것」이 아니다 — **코드가 실제로 쓰는 값**이다.
    화면에 나갈 문구나 전송할 코드처럼 **값 자체가 계약**일 때만 쓴다.
    """
    tree = _tree_of(fn)
    doc = ast.get_docstring(tree.body[0]) if tree.body else None
    out = {n.value for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    return out - ({doc} if doc else set())


def returns_in(fn) -> int:
    """`return` 개수 — 「한 자리에서만 돌려주나」를 볼 때."""
    return sum(1 for n in ast.walk(_tree_of(fn)) if isinstance(n, ast.Return))


def importers_of(module_name: str, *, allow: Iterable[str] = ()) -> list:
    """`src/` 안에서 그 모듈을 **실제로 import 하는** 파일들 (글자 일치 아님).

    「아직 연결하지 않았다」를 지키는 잣대. `allow`는 같은 트랙 안의 모듈이다.
    """
    skip = {f"{module_name}.py", *allow}
    hits = []
    for p in (ROOT / "src").rglob("*.py"):
        if p.name in skip:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:                              # pragma: no cover
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [f"{node.module or ''}.{a.name}"
                                               for a in node.names]
            if any(module_name == n.rsplit(".", 1)[-1] or n.endswith(f".{module_name}")
                   for n in names):
                hits.append(str(p.relative_to(ROOT)))
                break
    return sorted(set(hits))


def imports_in(module) -> Set[str]:
    """그 모듈이 **import 하는 이름들**(`from a.b import c` → `a.b`, `a.b.c`).

    「이 모듈이 공급사를 고르지 않는다」를 잴 때. 독스트링이 공급사 이름을 **설명**해도
    안 잡힌다 — 설명과 의존은 다른 사실이다.
    """
    out: Set[str] = set()
    for n in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            out.add(mod)
            out.update(f"{mod}.{a.name}" for a in n.names)
    return out


def callers_of(module, call_name: str) -> Set[str]:
    """그 모듈 안에서 `call_name(...)`을 부르는 **함수 이름들**.

    「등록 경로가 전부 빌더를 지나나」처럼 **경로를 열거**할 때 쓴다(F40-b).
    """
    tree = ast.parse(inspect.getsource(module))
    out: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                f = sub.func
                nm = getattr(f, "attr", None) or getattr(f, "id", None)
                if nm == call_name:
                    out.add(node.name)
                    break
    return out
