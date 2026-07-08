"""tests/test_v47_mainworld_extract.py — v47 STEP4: MAIN world 주입으로 상세·이미지 전수 수집(근본).

근본: content_script는 격리월드라 Temu 등 XHR로 렌더 후 채우는 live 전역(window.rawData)을 못 읽어
'부분 수집'이 났다(v46 실기기 실패). 수리: manifest "world":"MAIN"으로 페이지 월드에 kgp-main.js 주입 →
거기서 kgpExtractProduct() 실행(초기상태 JSON 접근) → 결과만 postMessage로 격리월드에 넘겨 병합.
추가 API 호출 없음. 병합: 빈 필드 채우고 배열(이미지·옵션·리뷰·상세)은 더 완전한 쪽 채택, 가격·이미지
확보되면 partial 해제. STEP2 상태 컬럼과 연동.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import os
from pathlib import Path

MANIFEST = Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MAIN = Path("extensions/chrome-collector/kgp-main.js").read_text(encoding="utf-8")


def test_manifest_has_main_world_content_script():
    import json
    m = json.loads(MANIFEST)
    worlds = [cs for cs in m["content_scripts"] if cs.get("world") == "MAIN"]
    assert worlds, "MAIN world content script 항목이 없음"
    js = worlds[0]["js"]
    assert "kgp-extractor.js" in js and "kgp-main.js" in js   # 추출기 + 브릿지 둘 다 MAIN에


def test_main_bridge_posts_extraction_result():
    # kgp-main.js: __kgpReq 수신 → kgpExtractProduct 실행 → __kgpRes 로 결과 postMessage
    assert "__kgpReq" in MAIN and "__kgpRes" in MAIN
    assert "kgpExtractProduct" in MAIN
    assert "postMessage" in MAIN
    assert "__kgpMainBound" in MAIN                            # 중복 주입 방지


def test_content_script_requests_and_merges():
    assert "kgpExtractMerged" in CS and "kgpMergeMeta" in CS
    assert "__kgpReq" in CS and "__kgpRes" in CS               # 요청/응답 채널
    assert "postMessage" in CS
    # handleFabClick이 병합 추출을 쓴다(단순 extractProductMeta 직접 호출 대체)
    assert "kgpExtractMerged(function" in CS


def test_merge_logic_executes():
    # 실제 kgpMergeMeta를 node로 실행: 격리 부분 + MAIN 완전 → 완전 병합, partial 해제.
    i = CS.index("function kgpMergeMeta")
    depth = 0; started = False; end = None
    for j in range(i, len(CS)):
        c = CS[j]
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                end = j + 1; break
    fn = CS[i:end]
    script = fn + """
var isolated={url:'u',title:'',price:'',currency:'',images:[],gallery_images:[],detail_images:[],options:[],reviews:[],partial:true,field_sources:{price:'none',images:'none'}};
var main={title:'상품',price:'20605',currency:'KRW',images:['a','b','c'],gallery_images:['a','b','c'],detail_images:['d'],options:[{name:'옵션',values:['x','y']}],reviews:[{text:'g'}],rating:'4.8',review_count:'120',partial:false,field_sources:{price:'json',images:'json'}};
var m=kgpMergeMeta(isolated,main);
var ok=(m.price==='20605'&&m.images.length===3&&m.partial===false&&m.image==='a'&&m.field_sources.price==='json'&&m.rating==='4.8');
console.log(ok?'OK':'FAIL:'+JSON.stringify(m));
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(script); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=20)
        assert r.stdout.strip() == "OK", (r.stdout, r.stderr)
    finally:
        os.unlink(f.name)


def test_no_extra_api_calls():
    # Temu 추가 API 호출 금지(오너 금지사항) — MAIN 브릿지는 추출만, fetch/XHR 없음.
    assert "fetch(" not in MAIN and "XMLHttpRequest" not in MAIN


def test_download_zip_includes_main_bridge():
    # 확장 다운로드 ZIP에 kgp-main.js 포함(빠지면 MAIN world 미주입 → 근본 수리 무효).
    VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    m = re.search(r"include = \[(.*?)\]", VIEWS, re.S)
    assert m and '"kgp-main.js"' in m.group(1)
