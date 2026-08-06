"""tests/test_v60_hover_default.py — v60 STEP5: 디폴트 소싱처 버튼 결정성 + 호버 수집.

디폴트 소싱처(어댑터 등록 사이트)에서는 판정불능('unknown') 금지 — URL 패턴으로 결정적 판정
(상세패턴 /dp/·-g-{id}·/item/ → 단건 / 그 외 도메인 전체 → 벌크).
호버 수집(v42 E-3 기반): 목록 카드 우상단 소형 [수집] → 클릭 시 확장 큐(collectBulk)로 단건 수집 + '수집됨 ✓' 배지.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


# ── source-contract ──
def test_default_sourcing_deterministic():
    assert "function kgpIsDefaultSourcing" in CS
    assert "KGP_DEFAULT_SRC_RE" in CS
    # v71 STEP5: 디폴트 소싱처도 URL 명확할 때만 URL 판정(상세=single·목록=list), 애매하면 DOM 신호로 낙하
    #   (무조건 list 기본값 제거 — 라쿠텐/야후 상세 오판 방지). 결정 라인은 공통 하드매치.
    assert 'if (isDetail && !isList) return "single";' in CS
    assert 'if (isList && !isDetail) return "list";' in CS
    assert "애매하면 DOM 신호로 낙하" in CS
    for dom in ("amazon", "temu", "aliexpress", "yahoo", "taobao", "1688"):
        assert dom in CS


def test_hover_collect_uses_extension_queue_not_fetch():
    # 호버 수집은 백그라운드 fetch가 아니라 확장 큐(collectBulk 메시지)로.
    seg = CS.split("function kgpQuickCollect")[1].split("function kgpMarkExisting")[0]
    assert '"collectBulk"' in seg and "kgpSendMessage" in seg
    assert "fetch(" not in seg                                  # 페이지 직접 fetch 금지
    assert "kgpMarkQuickCollected" in seg                       # 수집됨 배지
    # v86-G: 집합 직접 조작(_kgpCollectedUrls.add)은 빈 키 오염 때문에 금지됐고, 가드 헬퍼를 거친다.
    #   계약의 뜻은 그대로 — "수집 성공 시 그 카드 URL을 수집됨으로 기록한다". 인자까지 못박아 완화 아님.
    assert "_kgpRememberCollected(card.url)" in seg


def test_hover_button_per_card_and_reuse():
    # v65 STEP3: 카드당 1개 — 버튼이 이미지 요소 부모에 앵커되어 카드 직속 자식이 아닐 수 있으므로
    #   중복 방지 셀렉터를 자손(.kgp-card-quick)으로. 스크롤 재사용(재스캔 시 기존 유지).
    # v77 STEP1: 멱등 — 타일당 .kgp-card-quick 최대 1개(자손 조회로 재사용 갱신·재생성 0).
    assert 'c.el.querySelectorAll(":scope .kgp-card-quick")' in CS
    assert "kgp-card-quick" in CS
    # 카드 감지: 아마존 어댑터 + 상세링크(/g-{id} 등 테무 그리드) 인식.
    assert "_kgpAmazonCards" in CS and "_kgpIsDetailHref" in CS


# ── behavioral: URL 결정성(node) ──
@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_default_sourcing_url_decisions_node():
    # content_script에서 정규식 2개 추출해 결정 로직 실증.
    src_re = re.search(r"const KGP_DEFAULT_SRC_RE = (/.*/i);", CS).group(1)
    det_re = re.search(r"const KGP_DETAIL_URL_RE = (/.*/i);", CS).group(1)
    list_re = re.search(r"const KGP_LIST_URL_RE = (/.*/i);", CS).group(1)
    # v71 STEP5: 디폴트 소싱처도 URL 명확할 때만 URL 판정, 애매하면 DOM 낙하('dom').
    harness = f"""
    const SRC={src_re}; const DET={det_re}; const LIST={list_re};
    function pt(host,href){{
      const isD=DET.test(href), isL=LIST.test(href);
      if(isD && !isL) return 'single';
      if(isL && !isD) return 'list';
      return 'dom';   // 애매 → DOM 신호(하네스 밖); 디폴트/비디폴트 동일
    }}
    const cases=[
      ['www.amazon.com','https://www.amazon.com/dp/B0XXXX','single'],
      ['www.amazon.com','https://www.amazon.com/s?k=phone','list'],
      ['www.temu.com','https://www.temu.com/x-g-601099.html','single'],
      ['www.temu.com','https://www.temu.com/','dom'],
      ['item.rakuten.co.jp','https://item.rakuten.co.jp/shop/abc123/','dom'],
      ['shop.example.com','https://shop.example.com/x','dom'],
    ];
    let ok=true; cases.forEach(c=>{{ if(pt(c[0],c[1])!==c[2]){{ok=false;console.log('FAIL',c,'→',pt(c[0],c[1]));}} }});
    console.log(ok?'ALL_OK':'FAIL');
    """
    r = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "ALL_OK", r.stdout
