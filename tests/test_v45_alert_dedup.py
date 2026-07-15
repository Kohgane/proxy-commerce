"""tests/test_v45_alert_dedup.py — 알럿 중복 방지(수집완료 토스트 건당 1회, corr-id dedupe).

증상(오너): 수집완료 토스트가 같은 건으로 여러 번. 원인 두 갈래:
 (1) background가 매 수집마다 OS 알림 + content가 인페이지 토스트 = 이중 알럿.
 (2) 콜백 이중 발화 등으로 같은 요청이 여러 번 알럿.
수리: content는 요청마다 corr-id 부여 + kgpAlertOnce로 건당 1회, background는 content 경로
(sendResponse 있음)에선 OS 알림 생략.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")


def test_source_contract():
    # corr-id 부여 + 건당 1회 헬퍼 + FAB/호버가 사용
    assert "function kgpAlertOnce" in CS and "_kgpCorrDone" in CS
    assert "meta.corr_id = corr" in CS          # FAB
    assert "corr_id: corr" in CS                # 호버
    assert "kgpAlertOnce(corr" in CS
    # background: content 경로(sendResponse)에선 OS 알림 생략(이중 알럿 제거)
    assert "if (!sendResponse) {" in BG
    assert BG.count("chrome.notifications.create") >= 2   # 여전히 context-menu/무-content 경로엔 존재


def test_alertonce_dedupes_same_corr(tmp_path):
    # 실제 kgpNewCorr/kgpAlertOnce를 추출해 실행: 같은 corr 두 번 → fn 1회, 다른 corr → 각 1회.
    import re
    m = re.search(r"(let _kgpCorrSeq[\s\S]*?\n\}\n)\n", CS)
    assert m, "corr 헬퍼 블록을 찾지 못함"
    block = m.group(1)
    harness = block + """
let calls = 0;
const c1 = kgpNewCorr();
kgpAlertOnce(c1, () => calls++);
kgpAlertOnce(c1, () => calls++);   // 같은 corr → 무시
const c2 = kgpNewCorr();
kgpAlertOnce(c2, () => calls++);   // 다른 corr → 실행
if (calls !== 2) { console.error("FAIL calls=" + calls); process.exit(1); }
console.log("OK");
"""
    f = tmp_path / "h.js"
    f.write_text(harness, encoding="utf-8")
    out = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, f"node dedup 실패: {out.stdout}{out.stderr}"
    assert "OK" in out.stdout


def test_manifest_bumped():
    assert '"version": "1.5.87"' in Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8")
