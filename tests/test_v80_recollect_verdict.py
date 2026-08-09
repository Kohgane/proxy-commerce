"""tests/test_v80_recollect_verdict.py — v80 STEP5: 실패 2건 재수집 검증(판별).

오너 진단(1.5.114): 목록의 '실패·추출 실패' 2건(아마존 스티머·테무 LED)을 [다시 수집]으로 세탁 → 성공 전환.
스티머 제목의 'Amazon.com:' 잔재가 **구수집분인지 새니타이저 회귀인지 재수집 결과로 판별**.

판별(코드 근거): 제목 새니타이저(_sanitizeTitle, v76 STEP1)가 'Amazon.com:' 접두를 **정상 제거**한다 →
새니타이저 회귀 아님 → 잔재는 **구수집분**(사니타이저 이전/미배포 시점 수집). 재수집(force 덮어쓰기)으로 세탁됨.
STEP5는 확장 런타임 무변경(재수집은 오너 기기 액션) — 이 가드가 '사니타이저 정상·재수집 경로 실존'을 못박음.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_unchanged():
    # STEP5는 검증(확장 런타임 무변경) → 버전 유지(1.5.120).
    assert MANIFEST["version"] == "1.5.142"


def test_recollect_force_flow_wired():
    """재수집([다시 수집] 덮어쓰기) 경로 실존 — force 플래그 → 서버 기존 레코드 덮어씀(신규 행 금지)."""
    assert "if (opts.force) meta.force = true;" in CS
    assert '"다시 수집(덮어쓰기)"' in CS
    assert "다시 수집 완료" in CS


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node 미설치")
def test_amazon_title_sanitizer_strips_prefix_verdict():
    """판별: 'Amazon.com:' 접두를 새니타이저가 제거 → 회귀 아님. 재수집 시 제목 세탁(구수집분 판정)."""
    brand = re.search(r"var _SITE_BRAND_RE = (/.*/i);", EX).group(1)
    # v83 STEP3: _sanitizeTitle이 참조하는 아마존 카테고리 꼬리 정규식도 주입.
    amz_tail = re.search(r"var _AMZ_CAT_TAIL_RE = new RegExp\([\s\S]*?, \"i\"\);", EX).group(0)
    bf = re.search(r"function _brandFromHost\(url\) \{.*?\n  \}", EX, re.S).group(0)
    st = re.search(r"function _sanitizeTitle\(t, url\) \{.*?\n  \}", EX, re.S).group(0)
    cases = [
        # 스티머 실기기 잔재 재현 — 재수집 결과 제목엔 'Amazon.com' 0.
        ["Amazon.com: OHSNAP Handheld Garment Steamer for Clothes",
         "https://www.amazon.com/dp/B0STEAM", "OHSNAP Handheld Garment Steamer for Clothes"],
        ["Amazon.com : Foldable Travel Steamer", "https://www.amazon.com/dp/B0X", "Foldable Travel Steamer"],
        ["OHSNAP Steamer - Amazon.com", "https://www.amazon.com/dp/B0X", "OHSNAP Steamer"],
    ]
    harness = (
        "var _SITE_BRAND_RE=" + brand + ";\n" + amz_tail + "\n" + bf + "\n" + st + "\n"
        + "var C=" + json.dumps(cases) + ";\n"
        + "process.stdout.write(JSON.stringify(C.map(function(c){return _sanitizeTitle(c[0],c[1]);}))+'\\n');"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        got = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    for (inp, _url, want), g in zip(cases, got):
        assert "Amazon.com" not in g and "amazon.com" not in g.lower(), ("사니타이저 회귀 — Amazon.com 잔존!", inp, g)
        assert g == want, ("제목 세탁 불일치", inp, g, want)
