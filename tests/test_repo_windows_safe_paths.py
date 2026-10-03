"""저장소 경로가 Windows에서 체크아웃 가능한지 지키는 가드.

배경(2026-10-04): 리다이렉션 대상에 정규식이 들어가 저장소 루트에 '고객\\s*만족도' 라는
파일이 커밋됐다(ko_polish_rules.json 의 옛 사본, 참조 0). Linux/macOS 는 그 이름을 허용하지만
Windows 는 역슬래시·별표를 만들 수 없어 `error: invalid path` 로 체크아웃이 통째로 막혔고,
그 PC 의 클론이 origin/main 보다 408커밋 뒤에 고정됐다. 같은 일이 다시 커밋되면 CI 에서 막는다.
"""
import os
import subprocess

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BAD_CHARS = set('\\:*?"<>|')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def _tracked_paths():
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=_REPO, capture_output=True, check=True, timeout=60
        ).stdout
    except Exception:  # git 없음 / 저장소 아님(이미지 안 등)
        pytest.skip("git 저장소가 아니어서 경로 검사를 건너뜀")
    return [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


def _problems(path):
    found = []
    for part in path.split("/"):
        bad = sorted(_BAD_CHARS & set(part))
        if bad:
            found.append(f"금지 문자 {''.join(bad)!r}")
        if any(ord(ch) < 32 for ch in part):
            found.append("제어 문자")
        if part != part.rstrip(" ."):
            found.append("끝이 공백/마침표")
        if part.split(".")[0].upper() in _RESERVED:
            found.append("예약 이름")
    return found


def test_tracked_paths_are_checkoutable_on_windows():
    offenders = {p: _problems(p) for p in _tracked_paths()}
    offenders = {p: why for p, why in offenders.items() if why}
    assert not offenders, "Windows 에서 만들 수 없는 경로가 커밋됨: " + "; ".join(
        f"{p!r} ({', '.join(why)})" for p, why in sorted(offenders.items())
    )


def test_guard_catches_the_original_offender():
    assert _problems("고객\\s*만족도")
    assert _problems("docs/aux.txt") and _problems("a/b. ")
    assert not _problems("src/collectors/ko_polish_rules.json")
