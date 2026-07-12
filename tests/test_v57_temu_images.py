"""tests/test_v57_temu_images.py — v57 STEP3: 테무 상세이미지 전량('더보기' 접힘 대응).

Tier1 상세이미지 키 보강(decoration/bottom/richtext) + 상세이미지 갤러리 독립 수집 +
Tier2 '더보기' 접힘 펼침(클릭 → MutationObserver 대기, 최대 3s) + 정직 '일부만' 경고 +
드로어 '상세페이지' 탭이 detail_images 렌더. 서버가 detail_fold 영속.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
API = Path("src/api/extension_api.py").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


def test_tier1_detail_keys_broadened():
    # 테무 상세이미지 키(decoration/bottom/richtext/longimage/goodsdesc)를 detail 버킷으로 라우팅.
    assert "decoration" in EX and "bottomimage" in EX and "richtext" in EX
    seg = EX.split("var DET_KEY")[1].split("\n")[0]
    for k in ("detail", "desc", "content", "decoration"):
        assert k in seg, k


def test_detail_images_collected_independently_of_gallery():
    # 갤러리가 차 있어도 detail_images가 비면 DOM 상세 수집을 독립 실행(핵심 버그 수리).
    assert "if (detailImages.length === 0)" in EX
    assert "상세이미지는" in EX and "독립" in EX


def test_honest_partial_warning_and_fold_flag():
    assert "상세이미지 일부만" in EX
    assert "detail_fold: detailFold" in EX
    assert "function _hasDetailFold" in EX


def test_reveal_fold_function_exists():
    # '더보기' 클릭 + MutationObserver 대기(최대 3s) + 즉시 콜백(접힘 없으면 지연 0).
    assert "function kgpRevealDetailFolds" in EX
    assert "MutationObserver" in EX
    assert "setTimeout(stop, 3000)" in EX
    assert "global.kgpRevealDetailFolds = kgpRevealDetailFolds" in EX


def test_content_script_wires_reveal_before_extract():
    assert "kgpRevealDetailFolds" in CS
    assert "kgpRevealDetailFolds 콜백 닫기" in CS
    # 어느 월드든 접힘 감지 OR
    assert "out.detail_fold = !!(out.detail_fold || extra.detail_fold)" in CS


def test_server_persists_detail_fold():
    assert '"detail_fold": bool(payload.get("detail_fold"))' in API
    assert 'extra["detail_fold"] = bool(data.get("detail_fold"))' in VIEWS


def test_drawer_detail_tab_renders_detail_images():
    # 상세이미지 블록이 '상세페이지'(detail) 탭 + 정직 fold 안내.
    assert 'id="detailImagesBlock" data-etab="detail"' in PREVIEW
    assert "detailFoldNote" in PREVIEW
    assert "detail_fold" in PREVIEW


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_reveal_fold_behavioral():
    """mock DOM: 상세 컨테이너에 '더보기' 버튼 → kgpRevealDetailFolds가 클릭하고 cb 1회 호출."""
    # FOLD_RE + _foldButtons + _hasDetailFold 추출
    a = EX.index("var FOLD_RE =")
    b = EX.index("var OPT_LABEL")
    foldblock = EX[a:b]
    # kgpRevealDetailFolds 추출
    c = EX.index("function kgpRevealDetailFolds")
    d = EX.index("global.kgpExtractProduct = kgpExtractProduct")
    revealblock = EX[c:d]
    harness = foldblock + revealblock + r"""
    // mock DOM: 상세 컨테이너 안 '더보기' 버튼 1개
    var clicked = 0;
    var moreBtn = { innerText: '더보기', textContent: '더보기', getAttribute: function(){return null;},
                    scrollIntoView: function(){}, click: function(){ clicked++; } };
    var detailScope = { querySelectorAll: function(){ return [{}]; } };  // img 1개(고정)
    global.document = {
      querySelectorAll: function(sel){
        if (/button|a|role/i.test(sel)) return [moreBtn];
        return [];
      },
      querySelector: function(sel){ return detailScope; }
    };
    // MutationObserver mock — observe 후 아무 것도 안 함(타임아웃 경로 검증) → 3s는 테스트 느림.
    // 대신 즉시 mutation 발생시켜 조기 종료 경로 검증: observe 시 콜백 1회 호출(img 증가처럼).
    global.MutationObserver = function(cb){ this.cb = cb; };
    global.MutationObserver.prototype.observe = function(){ var self=this; setTimeout(function(){ self.cb([]); }, 5); };
    global.MutationObserver.prototype.disconnect = function(){};
    // 조기종료를 위해 img count 증가 시뮬: 첫 호출 1, 관찰 후 2
    var calls = 0;
    detailScope.querySelectorAll = function(){ calls++; return calls <= 1 ? [{}] : [{},{}]; };

    var foldPresent = _hasDetailFold();
    var cbCalled = 0;
    kgpRevealDetailFolds(function(){ cbCalled++; });
    setTimeout(function(){
      console.log(JSON.stringify({ foldPresent: foldPresent, clicked: clicked, cbCalled: cbCalled }));
    }, 60);
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    import json
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["foldPresent"] is True, "더보기 접힘 감지 실패"
    assert out["clicked"] >= 1, "더보기 버튼 클릭 안 함"
    assert out["cbCalled"] == 1, "콜백이 정확히 1회 호출돼야(중복/누락 금지)"
