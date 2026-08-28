"""tests/test_session_repo_sync_guard.py — 세션 시작 레포 동기 확인(오너 2026-08-28).

컨테이너가 리포를 옛 커밋으로 되돌려 놓는 일이 이번 세션에만 3회. 모르고 작업하면
**이미 머지된 수리 위에 옛 코드를 얹고**, 전체 스위트 숫자도 무효가 된다.

계약: ①훅이 존재·실행 가능 ②SessionStart로 등록 ③**감지·보고만**(자동 reset 금지 —
미커밋 작업 소실 방지) ④CLAUDE.md 1단계 고정 ⑤역행 상황에서 실제로 경고를 낸다.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOK = Path(".claude/hooks/session_start_repo_sync.sh")


def test_hook_exists_and_executable():
    assert HOOK.exists(), "세션 시작 동기화 훅이 없다"
    assert os.access(HOOK, os.X_OK), "훅에 실행 권한이 없다"


def test_hook_registered_on_session_start():
    cfg = json.loads(Path(".claude/settings.json").read_text(encoding="utf-8"))
    entries = cfg["hooks"]["SessionStart"]
    cmds = [h["command"] for e in entries for h in e["hooks"]]
    assert any("session_start_repo_sync.sh" in c for c in cmds), cmds


def test_hook_detects_and_reports_only():
    """**자동 reset 금지** — 훅이 작업 트리를 건드리면 미커밋 작업이 날아간다.

    주석·`echo` 안내문에는 재동기화 명령이 **문자열로** 있어도 된다(사람이 읽고 판단할 몫).
    금지되는 건 **실행**이므로 실행되는 줄만 본다.
    """
    src = HOOK.read_text(encoding="utf-8")
    executed = [l for l in src.splitlines()
                if not l.lstrip().startswith(("#", "echo "))]
    code = "\n".join(executed)
    for destructive in ("reset --hard", "checkout -B", "clean -f", "stash"):
        assert destructive not in code, f"훅이 파괴적 명령을 실행한다: {destructive}"
    assert "git fetch origin main" in code and "rev-parse origin/main" in code
    # 안내문에는 있어야 한다 — 감지만 하고 다음 행동을 안 알려주면 반쪽이다.
    assert "reset --hard origin/main" in src


def test_hook_reports_mismatch(tmp_path):
    """역행 상황(HEAD != origin/main)에서 **경고를 낸다** — 조용히 통과하지 않는다."""
    repo = tmp_path / "r"
    run = lambda *a, **k: subprocess.run(a, cwd=k.pop("cwd", repo), check=True,
                                         capture_output=True, text=True, **k)
    (repo / "x").mkdir(parents=True)
    run("git", "init", "-q", "-b", "main", cwd=repo)
    run("git", "config", "user.email", "t@t"); run("git", "config", "user.name", "t")
    (repo / "a.txt").write_text("1")
    run("git", "add", "-A"); run("git", "commit", "-qm", "old")
    old = run("git", "rev-parse", "HEAD").stdout.strip()
    (repo / "a.txt").write_text("2")
    run("git", "add", "-A"); run("git", "commit", "-qm", "new")
    # origin/main = 최신, HEAD = 옛 커밋(= 컨테이너 역행 재현)
    run("git", "update-ref", "refs/remotes/origin/main", "HEAD")
    run("git", "remote", "add", "origin", str(repo))
    run("git", "checkout", "-q", "--detach", old)

    out = subprocess.run(["bash", str(HOOK.resolve())], cwd=repo, capture_output=True,
                         text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": str(repo)})
    assert "HEAD != origin/main" in out.stdout, out.stdout
    assert "재동기화" in out.stdout
    # 훅이 작업 트리를 바꾸지 않았다.
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                          text=True).stdout.strip() == old


def test_claude_md_pins_step_one():
    """상시 로드되는 CLAUDE.md에 **1단계**로 고정 — 훅이 없는 환경에서도 규율이 산다."""
    md = Path("CLAUDE.md").read_text(encoding="utf-8")
    assert "세션 시작 1단계 = 레포 동기 확인" in md
    assert "git fetch origin main" in md
    assert "HEAD == origin/main" in md
    assert "최근 머지한 파일·심볼이 없다" in md          # 사람 눈 감지법
