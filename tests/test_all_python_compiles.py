from __future__ import annotations

import pathlib
import py_compile


def test_all_python_compiles():
    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    errors: list[str] = []
    for path in root.rglob("*.py"):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{path}: {exc}")
    assert not errors, "python compile errors:\n" + "\n".join(errors)
