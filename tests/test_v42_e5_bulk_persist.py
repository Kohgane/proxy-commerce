"""tests/test_v42_e5_bulk_persist.py — v42 E-5: 벌크 수집 서버 커밋 후에만 성공 + 정직 요약/재시도/진행률.

증상: 전체수집 '수집됨' 표시 → 이력에 없음. 수리: 항목별 서버 커밋(d.ok, STEP 1-0 write-then-verify)
후에만 성공 카운트, 중복/실패 분리 집계, 실패 항목 재시도, 진행률 실시간.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_background_counts_commit_and_separates_duplicate_failed():
    # 서버 커밋(d.ok) 성공만 success, 중복은 별도, 실패는 failedItems로 반환.
    assert "d.ok && d.duplicate) duplicate++" in BG
    assert "else if (d && d.ok) success++" in BG
    assert "failedItems.push(meta)" in BG
    assert "failedItems" in BG and "duplicate" in BG


def test_background_sends_progress_and_honest_summary():
    assert 'action: "bulkProgress"' in BG          # 진행률 실시간
    assert "완료 ${success}" in BG                  # 정직 요약(완료 N)
    assert "sender && sender.tab && sender.tab.id" in BG   # 탭 id 전달


def test_content_script_has_runbulk_retry_and_progress():
    assert "function kgpRunBulk" in CS
    assert "function kgpRenderRetry" in CS
    assert 'msg.action === "bulkProgress"' in CS   # 진행률 수신
    assert "재시도" in CS
    # 정직 요약: 완료·중복·실패 분리 표기
    assert "완료 ${resp.success}" in CS
    assert "중복 ${dup}" in CS and "실패 ${fail}" in CS


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_render_retry_appends_button():
    """kgpRenderRetry가 실패 항목이 있으면 재시도 버튼을 만든다(정직: 실패 가시화)."""
    i = CS.index("function kgpRenderRetry")
    j = CS.index("\n}\n", i) + 2
    fn = CS[i:j]
    tid = "kgp-listing-toolbar"
    # v86 STEP2: 벌크바 내부가 shadowRoot로 들어가면서 kgpRenderRetry가 라이트 DOM 조회 대신
    #   shadow를 뚫는 `_kgpTbQ`를 쓴다. 스텁에 그 헬퍼가 없으면 ReferenceError로 죽어 계약이
    #   '깨진 것처럼' 보인다 → 실제 헬퍼(_kgpTbRoot/_kgpTbQ)를 그대로 주입해 진짜 경로를 태운다.
    hi = CS.index("function _kgpTbRoot")
    hj = CS.index("function _kgpTbAll")
    helpers = CS[hi:hj]
    script = f"""
    const KGP_TOOLBAR_ID = "{tid}";
    global.document = null;
    // 최소 DOM 스텁
    const btns = [];
    const toolbar = {{ appendChild: (b) => btns.push(b), querySelector: () => null }};
    const removed = [];
    global.document = {{
      getElementById: (id) => id === KGP_TOOLBAR_ID ? toolbar : null,
      createElement: () => ({{ style: {{}}, attrs: {{}}, addEventListener: () => {{}},
        setAttribute(k, v){{ this.attrs[k] = v; }}, getAttribute(k){{ return this.attrs[k]; }},
        set textContent(v){{this._t=v;}}, get textContent(){{return this._t;}} }}),
    }};
    {helpers}
    {fn}
    kgpRenderRetry([{{url:'a'}},{{url:'b'}}]);
    console.log(JSON.stringify({{ made: btns.length, label: btns[0] && btns[0].textContent }}));
    """
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    import json
    o = json.loads(res.stdout.strip())
    assert o["made"] == 1
    assert "재시도" in (o["label"] or "")
