from __future__ import annotations

import pathlib
import py_compile


def test_all_python_files_compile():
    errors = []
    for path in pathlib.Path("src").rglob("*.py"):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{path}: {exc}")
    assert not errors, "Python syntax errors:\n" + "\n".join(errors)
