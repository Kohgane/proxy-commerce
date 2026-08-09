"""tests/test_v86_k_require_browser.py — v86-K: KGP_REQUIRE_BROWSER 게이트 자기검증.

플래그 OFF면 인프라 skip은 skip(로컬 편의). 플래그 ON이면 인프라 skip이 **실패**로 전환된다
(조용한 skip 금지 = v86-H2 사각의 구조적 봉인). 게이트가 실제로 무는지 서브프로세스로 실증.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


_DUMMY = textwrap.dedent(
    '''
    import pytest
    @pytest.mark.skipif(True, reason="Playwright/chromium 미설치")
    def test_browser_gated():
        assert True
    @pytest.mark.skipif(True, reason="의도적 로직 skip(품질 미달)")
    def test_logic_skip():
        assert True
    '''
)


def _run(env_flag):
    # conftest 훅은 tests/ 하위에서만 로드된다 → 프로브를 tests/ 안에 둔다(고유명, 실행 후 삭제).
    tests_dir = Path(__file__).resolve().parent
    probe = tests_dir / f"_gate_probe_{os.getpid()}.py"
    probe.write_text(_DUMMY, encoding="utf-8")
    env = dict(os.environ)
    if env_flag:
        env["KGP_REQUIRE_BROWSER"] = "1"
    else:
        env.pop("KGP_REQUIRE_BROWSER", None)
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(probe), "-q", "--no-header", "-p", "no:cacheprovider"],
            capture_output=True, text=True, cwd=str(tests_dir.parent), env=env,
        )
        return r.stdout + r.stderr
    finally:
        probe.unlink(missing_ok=True)


def test_flag_off_infra_skip_stays_skipped():
    out = _run(env_flag=False)
    assert "2 skipped" in out, out
    assert "failed" not in out.lower(), out


def test_flag_on_infra_skip_becomes_failure_but_logic_skip_stays():
    out = _run(env_flag=True)
    # 인프라 skip(Playwright) → 비-통과(setup-phase 전환은 error로 집계 = CI 차단), 의도적 로직 skip → skip 유지.
    assert ("1 failed" in out) or ("1 error" in out), ("인프라 skip이 비-통과로 전환 안 됨", out)
    assert "1 skipped" in out, ("의도적 로직 skip까지 전환됨(과잉)", out)
    assert "KGP_REQUIRE_BROWSER=1" in out, out
