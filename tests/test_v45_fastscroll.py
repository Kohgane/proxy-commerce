"""tests/test_v45_fastscroll.py — 인덱스 패스트 스크롤(폰 앱서랍 방식).

이름순일 때만 초성/A-Z/# 그룹핑 + 우측 인덱스 레일. 컴포넌트 초성 분류(node 실행) +
템플릿 배선(catalog·collect_history) + CSS 토큰(하드코딩 색 0) 검증.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path("src/seller_console/static/kgp-fastscroll.js")
CSS = Path("src/static/app.css").read_text(encoding="utf-8")
CATALOG = Path("src/seller_console/templates/catalog.html").read_text(encoding="utf-8")
CH = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
        yield c


def test_component_file_exists():
    assert JS.exists()
    src = JS.read_text(encoding="utf-8")
    assert "KGPFastScroll" in src
    assert "bucketOf" in src and "scrollIntoView" in src   # 그룹핑 + 점프
    assert "touchstart" in src and "touchmove" in src      # 엄지 스크럽(터치)
    assert "kgp-fs-scrub" in src                           # 스크럽 오버레이


@pytest.mark.skipif(not shutil.which("node"), reason="node 미설치")
def test_choseong_bucketing_node():
    prog = (
        "const FS=require('./%s');"
        "const cs=[['가방','ㄱ'],['끈','ㄱ'],['뜨개','ㄷ'],['빵','ㅂ'],['싸움','ㅅ'],['옷','ㅇ'],"
        "['짜장','ㅈ'],['하늘','ㅎ'],['Apple','A'],['zoo','Z'],['3단','#'],['_','#']];"
        "let bad=[];for(const [k,e] of cs){if(FS.bucketOf(k)!==e)bad.push(k+'->'+FS.bucketOf(k));}"
        "console.log(JSON.stringify({buckets:FS.BUCKETS.length,bad}));"
    ) % JS.as_posix()
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["buckets"] == 41            # 14 초성 + 26 A-Z + #
    assert res["bad"] == []                # 전부 정확 분류


def test_catalog_rail_always_on_both_sorts(client):
    # 나이아: 레일은 항상 노출(정렬 무관). 이름순은 그룹핑(enabled true), 다른 정렬은 자동 전환.
    h_name = client.get("/seller/catalog?sort=title_asc").get_data(as_text=True)
    assert "data-fs-root" in h_name and "kgp-fastscroll.js" in h_name
    assert "enabled: true" in h_name
    h_recent = client.get("/seller/catalog?sort=last_synced_desc").get_data(as_text=True)
    assert "data-fs-root" in h_recent and "kgp-fastscroll.js" in h_recent   # 레일 여전히 노출
    assert "enabled: false" in h_recent and "switchUrl" in h_recent          # 조작 시 이름순 전환


def test_collect_history_rail_always_on(client):
    h_name = client.get("/seller/collect/history?sort=title").get_data(as_text=True)
    assert "data-fs-root" in h_name and "enabled: true" in h_name
    h_new = client.get("/seller/collect/history?sort=newest").get_data(as_text=True)
    assert "data-fs-root" in h_new and "enabled: false" in h_new and "switchUrl" in h_new


def test_template_wiring_source():
    # 속도: 행은 파셜(단일소스)로 분리 — 목록 컨테이너(data-fs-list)는 본문, data-fs-key는 파셜.
    CAT_ROWS = Path("src/seller_console/templates/catalog_rows.html").read_text(encoding="utf-8")
    CH_ROWS = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    for t in (CATALOG, CH):
        assert "data-fs-list" in t
    for t in (CAT_ROWS, CH_ROWS):
        assert "data-fs-key" in t
    # 이름순 전체 5000 로드 폐기 → 첫50 + 무한스크롤(fmt=rows) + 나이아 서버버킷 점프(onJump)
    for t in (CATALOG, CH):
        assert "fsInfiniteScroll" in t and "onJump" in t and "fmt=rows" in t


def test_component_naia_v2_behaviors():
    src = JS.read_text(encoding="utf-8")
    # v2 정답지: 토스트 폭탄 제거(전환 조용히), 스크럽 오버레이·레일 벤딩·해시 점프
    assert "이름순으로 전환됨" not in src and "pcToast" not in src   # 토스트 0
    assert "_showScrub" in src and "kgp-fs-scrub-items" in src        # 스크럽 모드(빈 화면+초성+항목)
    assert "_bend" in src and "translateX" in src and "scale(" in src  # 레일 벤딩
    assert "elementFromPoint" in src                                   # 정답지 스크럽 판정
    assert "switchUrl" in src and "kgpfs=" in src                      # 다른 정렬 조용히 전환 + 해시
    assert "아직 없어요" in src or "아직 없음" in src                   # 빈 초성/섹션


def test_css_uses_tokens_not_hardcoded():
    block = CSS[CSS.index("나이아 인덱스 레일"):]
    assert ".kgp-fs-rail" in block and ".kgp-fs-scrub" in block   # 레일 + 스크럽 오버레이
    # ★ 6-c(2026-09-03): 이 핀은 **선언부**의 하드코딩을 막는 것이다. 주석은 "옛 값 #xxx를
    #   토큰으로 바꿨다"처럼 근거로 값을 인용할 수 있고, 그건 문서지 선언이 아니다.
    import re as _re
    block = _re.sub(r"/\*.*?\*/", "", block, flags=_re.S)
    assert "var(--ink)" in block and "var(--teal)" in block and "var(--cream)" in block
    import re
    hexes = re.findall(r"#[0-9A-Fa-f]{3,6}\b", block)
    assert hexes == [], f"하드코딩 hex 발견: {hexes}"
    assert "content-visibility" in block and "prefers-reduced-motion" in block


def test_catalog_no_mock_sheets_banner():
    # 항목5: PG-only 후 Mock/Sheets 배너 제거, 실데이터 없을 때만 정직한 빈 상태
    assert "Mock 데이터" not in CATALOG and "Sheets에 저장" not in CATALOG
    assert "아직 수집된 상품이 없어요" in CATALOG
    # 항목4: 필터 접이식('필터 ▾')
    assert 'id="catalogFilters"' in CATALOG and "collapse" in CATALOG and "kgp-filter-toggle" in CATALOG
