"""tests/test_v86_g_rest_key.py — v86-G(수리): rest가 사이트별로 갈리는 **구조적 분기** 하나를 봉인.

■ 판독 전제(v86-G 계측에서 확정)
`KGP_QUICK_REST_OPACITY`는 전역 0이고, rest에서 [수집]이 보이는 **유일한** 경로는
`dataset.collected === "1"`('수집됨 ✓'는 v86-C 설계상 상시 노출)이다. 즉 "아마존만 rest=1"은
= "아마존 타일들이 수집됨으로 켜져 있다"와 동치다.

■ 그 켜짐이 잘못 일어날 수 있는 지점(이 파일이 막는 것)
타일의 collected 판정은 `_kgpCollectedUrls` 집합 조회다. 그런데 URL이 안 잡히는 타일(홈 캐러셀처럼
href 해석이 실패하는 경로)이 섞이면 `""`·`"undefined"` 같은 **빈 키가 집합에 들어갈 수 있고**, 그
순간 같은 처지의 **모든 타일이 한꺼번에 '수집됨'으로 켜져 rest가 통째로 1**이 된다. 목록 페이지
(알리·라쿠텐)는 href가 또렷해 이 함정을 안 밟고, 홈/캐러셀 경로만 밟는다 — 사이트별 불일치의 모양 그대로다.

빈 키는 **어떤 경우에도** 수집 여부의 근거가 아니다. 그래서 조회·기록을 가드 헬퍼 한 쌍으로 좁히고,
직접 접근이 되살아나면 이 파일이 잡는다.

※ 정직 표기: 이 봉인은 "빈 키 오염으로는 더 이상 rest가 새지 않는다"를 보증한다. 오너 실기기의
   아마존 홈 rest=1이 **실제로** 이 원인이었는지는 1.5.137에 실린 `rest_state{collected, rest_violations}`
   판독으로 확정한다(수집됨 타일이면 위반 아님). 원인 단정 대신 분기를 막고 계측을 남기는 순서.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

CS_PATH = Path("extensions/chrome-collector/content_script.js")
CS = CS_PATH.read_text(encoding="utf-8")


def _node_or_skip():
    if not shutil.which("node"):
        pytest.skip("node 미설치 — 실행 계약 검증 불가")


def _helpers_src() -> str:
    """가드 헬퍼 3종(_kgpUrlKey/_kgpRememberCollected/_kgpIsCollectedUrl) 원본을 그대로 떼어 온다."""
    i = CS.index("let _kgpCollectedUrls")
    j = CS.index("function _kgpIsCollectedUrl")
    end = CS.index("\n", CS.index("}", j))
    src = CS[i:end]
    assert "_kgpUrlKey" in src and "_kgpRememberCollected" in src, "가드 헬퍼를 못 찾았다"
    return src


def _run_node(script: str) -> dict:
    f = tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False, encoding="utf-8")
    f.write(script)
    f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        assert r.returncode == 0, r.stderr
        return json.loads([ln for ln in r.stdout.splitlines() if ln.strip()][-1])
    finally:
        Path(f.name).unlink(missing_ok=True)


_PROBE = """
%(SRC)s
const BAD = ["", "   ", undefined, null, "undefined", "null"];
const out = { poisoned: [], realHit: false, realMiss: false };
BAD.forEach((b) => _kgpRememberCollected(b));
out.setSize = _kgpCollectedUrls.size;                       // 가드가 붙으면 0
BAD.forEach((b) => { if (_kgpIsCollectedUrl(b)) out.poisoned.push(String(b)); });
// 정상 URL은 그대로 동작해야 한다(가드가 기능을 죽이면 '수집됨 ✓'가 사라진다).
_kgpRememberCollected("https://www.amazon.com/dp/B0TEST0001");
out.realHit = _kgpIsCollectedUrl("https://www.amazon.com/dp/B0TEST0001");
out.realMiss = _kgpIsCollectedUrl("https://www.amazon.com/dp/B0OTHER999");
console.log(JSON.stringify(out));
"""


def test_empty_url_key_cannot_mark_tiles_collected():
    """★빈 키는 집합에 들어가지도, 매칭되지도 않는다 — rest 통째 노출의 씨앗 제거."""
    _node_or_skip()
    got = _run_node(_PROBE % {"SRC": _helpers_src()})
    assert got["setSize"] == 0, ("빈 키가 수집됨 집합에 들어갔다 — 한 타일 오염이 전 타일로 번진다", got)
    assert not got["poisoned"], ("빈 키가 '수집됨'으로 매칭된다", got)
    assert got["realHit"], ("정상 URL이 매칭되지 않는다 — '수집됨 ✓' 표시가 죽는다", got)
    assert not got["realMiss"], ("다른 URL이 수집됨으로 잘못 매칭된다", got)


def test_unguarded_version_actually_leaks():
    """인위회귀 — 가드를 뺀 종전 방식이면 빈 키 오염이 **실제로** 일어난다(계약이 공허하지 않음)."""
    _node_or_skip()
    naive = """
    const _kgpCollectedUrls = new Set();
    const _kgpRememberCollected = (u) => _kgpCollectedUrls.add(u);
    const _kgpIsCollectedUrl = (u) => _kgpCollectedUrls.has(u);
    """
    got = _run_node(_PROBE % {"SRC": naive})
    assert got["setSize"] > 0 and got["poisoned"], \
        ("가드 없이도 오염이 안 난다 — 재현 조건이 틀렸고 이 봉인은 지키는 게 없다", got)


def test_all_access_goes_through_guards():
    """직접 접근 금지 — `_kgpCollectedUrls`의 add/has는 가드 헬퍼 안에서만.

    이 단언이 없으면 다음 리팩터가 `_kgpCollectedUrls.add(x)` 한 줄을 되살려 조용히 봉인을 푼다.
    """
    body = CS.split("function _kgpIsCollectedUrl", 1)[1]
    body = body[body.index("\n"):]                       # 헬퍼 정의부 이후 전 코드
    leaks = re.findall(r"_kgpCollectedUrls\.(add|has)\(", body)
    assert not leaks, f"가드를 우회한 직접 접근 {leaks} — 빈 키 오염 경로가 되살아난다"


def test_rest_opacity_constant_is_zero_and_single_source():
    """rest 투명도는 여전히 0 단일 상수 — 사이트별 분기(예외 도메인)가 끼어들지 않았다."""
    assert "var KGP_QUICK_REST_OPACITY = 0;" in CS, "rest 상수가 0이 아니거나 이름이 바뀌었다"
    assert len(re.findall(r"KGP_QUICK_REST_OPACITY\s*=", CS)) == 1, \
        "rest 상수를 여러 곳에서 대입한다 — 사이트별로 갈릴 여지"
    # 호버 토글·초기 스타일 두 곳 모두 이 상수를 쓴다(하드코딩 0.85 등 재등장 금지).
    assert CS.count("KGP_QUICK_REST_OPACITY") >= 3, "rest 상수를 안 쓰는 경로가 생겼다"
