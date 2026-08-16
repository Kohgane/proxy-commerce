"""tests/test_v86_l_payload_echo.py — v86-L: payload_echo=null 배선 결함 봉인.

오너 실기기(테무 갤럭시 프로젝터, 1.5.140, 04:05:18Z): 수집 클릭 → 진단 payload_echo=null
(tier1_diag·bar_collapsed는 정상). 4-지점 추적(a 월드분리 b 경로분기 c 타이밍 d 페이지재렌더)
결과 = **경로분기(b)**: echo는 FAB(handleFabClick)만 기록하고, 호버 단건(kgpQuickCollect)·벌크
(kgpRunBulk)의 collectBulk 경로는 `_kgpMetaStore.echo`를 아예 안 남겼다. 테무 목록에서 호버/벌크로
수집하면 echo는 초기 null 그대로 → payload_echo=null.
  (a 월드분리 배제: _kgpMetaStore·진단·recorder 전부 content_script 같은 world. tier1은 MAIN이지만
   payload_echo는 tier1을 안 읽는다. c 타이밍·d 재렌더 배제: 벌크 경로는 애초에 기록 지점이 없어
   재렌더·대기와 무관하게 null.)

수리: echo 기록 단일 관문 `_kgpRecordEcho(meta, path, extra)` — 모든 전송 경로(FAB·호버·벌크)가
경유. path enum("fab"|"hover"|"bulk"|"bulk-retry")로 '어느 버튼이 보냈나', echoed_at으로 '언제'를
진단 파일 하나로 판독. 어느 경로로 보냈든 payload_echo는 non-null.

금지 준수: 추출기·tier1 선택 로직·kgp-net.js 스코프 무변경(이 변경은 content_script 전송 계측만).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))

_ECHO_ENUMS = ("fab", "hover", "bulk", "bulk-retry")


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.145"


# ── source-contract: echo가 모든 수집 경로에 배선됐는가(FAB-only 회귀 금지) ──
def test_echo_recorder_defined_with_path_and_echoed_at():
    assert "function _kgpRecordEcho(meta, path, extra)" in CS, "echo 기록 단일 관문 없음"
    body = CS.split("function _kgpRecordEcho(meta, path, extra)")[1].split("\n}")[0]
    assert "e.path = path" in body, "path enum 미기록"
    assert "e.echoed_at" in body, "echoed_at 미기록"
    assert "_kgpMetaStore.echo = e" in body, "스토어에 echo 미반영"


def test_echo_wired_in_all_three_collect_paths():
    # FAB 단건 + 호버 단건 + 벌크 — 세 경로 모두 recorder 경유(종전 결함=FAB만).
    assert '_kgpRecordEcho(meta, "fab")' in CS, "FAB 경로 echo 미배선"
    assert '_kgpRecordEcho(meta, "hover")' in CS, "호버 경로 echo 미배선(오너 결함 지점)"
    assert '_kgpRecordEcho(items[0] || {}' in CS, "벌크 경로 echo 미배선"
    # 진단 export가 그 스토어를 읽는 계약은 유지.
    assert "payload_echo: (_kgpMetaStore && _kgpMetaStore.echo) || null," in CS
    # 낡은 FAB-only 직접대입이 남아 다시 갈라지지 않게(단일 관문 강제).
    assert "_kgpMetaStore.echo = _kgpPayloadEcho(meta);" not in CS, \
        "FAB 직접대입 잔존 — 단일 관문(_kgpRecordEcho) 우회"


# ── node 하네스: 경로별 echo가 6필드 non-null + path/echoed_at 실증 ──
@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_echo_records_nonnull_for_every_path():
    pe = re.search(r"function _kgpPayloadEcho\(meta\) \{[\s\S]*?\n\}", CS)
    re_ = re.search(r"function _kgpRecordEcho\(meta, path, extra\) \{[\s\S]*?\n\}", CS)
    assert pe and re_, "함수 추출 실패"
    harness = (
        "var _kgpMetaStore = { echo: null };\n"
        + pe.group(0) + "\n" + re_.group(0) + "\n"
        + r"""
    var richMeta = { title:"갤럭시 프로젝터", price:"61144", currency:"KRW", currency_source:"domain",
      images:["a","b"], options:[], reviews:[], skus:[], mode:"full", field_sources:{price:"tier1"} };
    function record(meta, path, extra){ _kgpMetaStore.echo=null; _kgpRecordEcho(meta, path, extra); return _kgpMetaStore.echo; }
    var out = {
      fab:   record(richMeta, "fab"),
      hover: record(richMeta, "hover"),
      bulk:  record(richMeta, "bulk", {items_n: 3}),
      empty: record({}, "hover"),   // 값이 빈약해도 echo 자체는 non-null이어야(경로가 돌면 기록됨)
    };
    console.log(JSON.stringify(out));
    """
    )
    r = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=15)
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout.strip())

    def nonnull_count(e):
        return sum(1 for v in e.values() if v is not None and v != "")

    # 경로별: echo non-null + path enum 일치 + echoed_at ISO + 6필드 이상 non-null.
    for path in ("fab", "hover", "bulk"):
        e = o[path]
        assert e is not None, f"{path}: echo가 null(배선 결함 재현)"
        assert e["path"] == path, f"{path}: path enum 불일치({e.get('path')})"
        assert e["path"] in _ECHO_ENUMS
        assert isinstance(e.get("echoed_at"), str) and e["echoed_at"], f"{path}: echoed_at 없음"
        assert "T" in e["echoed_at"] and e["echoed_at"].endswith("Z"), "echoed_at ISO 아님"
        assert nonnull_count(e) >= 6, f"{path}: non-null 필드 6 미만({nonnull_count(e)})"
    # 벌크는 items_n 동봉(무엇을 보냈나).
    assert o["bulk"]["items_n"] == 3
    # 값이 빈 meta여도 경로가 돌면 echo는 non-null(path/echoed_at/at은 항상 채워짐) — payload_echo=null 박멸.
    assert o["empty"] is not None and o["empty"]["path"] == "hover"
    assert isinstance(o["empty"]["echoed_at"], str) and o["empty"]["echoed_at"]
