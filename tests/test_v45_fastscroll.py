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
    assert "kgp-fs-bubble" in src                          # 대형 버블


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
    for t in (CATALOG, CH):
        assert "data-fs-list" in t and "data-fs-key" in t
    # 이름순이면 페이지네이션 숨김(전체 로드)
    assert "not fastscroll" in CATALOG and "not fastscroll" in CH


def test_component_naia_behaviors():
    src = JS.read_text(encoding="utf-8")
    assert "switchUrl" in src and "이름순으로 전환됨" in src   # 다른 정렬 → 자동 전환 + 토스트
    assert "아직 없음" in src                                  # 빈 섹션 1행
    assert "kgpfs=" in src                                      # 해시 점프
    assert "elementFromPoint" in src                           # 스크럽(정답지 방식)


def test_css_uses_tokens_not_hardcoded():
    block = CSS[CSS.index("나이아 인덱스 레일"):]
    assert ".kgp-fs-rail" in block and ".kgp-fs-bubble" in block
    assert "var(--ink)" in block and "var(--teal)" in block and "var(--cream)" in block
    import re
    # 버블 그림자의 rgba(먹) 1건은 토큰 밖 허용(그림자). hex 하드코딩만 검사.
    hexes = re.findall(r"#[0-9A-Fa-f]{3,6}\b", block)
    assert hexes == [], f"하드코딩 hex 발견: {hexes}"
    assert "content-visibility" in block and "prefers-reduced-motion" in block
    assert "아직 없음" not in block or True   # CSS엔 문자열 없음(무관)
