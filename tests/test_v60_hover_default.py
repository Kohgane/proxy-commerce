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
    # 디폴트 소싱처는 상세패턴=single, 그 외=list (unknown 금지).
    assert 'if (kgpIsDefaultSourcing()) return isDetail ? "single" : "list";' in CS
    for dom in ("amazon", "temu", "aliexpress", "yahoo", "taobao", "1688"):
        assert dom in CS


def test_hover_collect_uses_extension_queue_not_fetch():
    # 호버 수집은 백그라운드 fetch가 아니라 확장 큐(collectBulk 메시지)로.
    seg = CS.split("function kgpQuickCollect")[1].split("function kgpMarkExisting")[0]
    assert '"collectBulk"' in seg and "kgpSendMessage" in seg
    assert "fetch(" not in seg                                  # 페이지 직접 fetch 금지
    assert "kgpMarkQuickCollected" in seg                       # 수집됨 배지
    assert "_kgpCollectedUrls.add" in seg


def test_hover_button_per_card_and_reuse():
    # 카드당 1개(:scope > .kgp-card-quick 중복방지) + 스크롤 재사용(재스캔 시 기존 유지).
    assert ":scope > .kgp-card-quick" in CS
    assert "kgp-card-quick" in CS
    # 카드 감지: 아마존 어댑터 + 상세링크(/g-{id} 등 테무 그리드) 인식.
    assert "_kgpAmazonCards" in CS and "_kgpIsDetailHref" in CS


# ── behavioral: URL 결정성(node) ──
@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_default_sourcing_url_decisions_node():
    # content_script에서 정규식 2개 추출해 결정 로직 실증.
    src_re = re.search(r"const KGP_DEFAULT_SRC_RE = (/.*/i);", CS).group(1)
    det_re = re.search(r"const KGP_DETAIL_URL_RE = (/.*/i);", CS).group(1)
    harness = f"""
    const SRC={src_re}; const DET={det_re};
    function pt(host,href){{ if(SRC.test(host)) return DET.test(href)?'single':'list'; return 'heuristic'; }}
    const cases=[
      ['www.amazon.com','https://www.amazon.com/dp/B0XXXX','single'],
      ['www.amazon.com','https://www.amazon.com/s?k=phone','list'],
      ['www.temu.com','https://www.temu.com/x-g-601099.html','single'],
      ['www.temu.com','https://www.temu.com/','list'],
      ['shop.example.com','https://shop.example.com/x','heuristic'],
    ];
    let ok=true; cases.forEach(c=>{{ if(pt(c[0],c[1])!==c[2]){{ok=false;console.log('FAIL',c,'→',pt(c[0],c[1]));}} }});
    console.log(ok?'ALL_OK':'FAIL');
    """
    r = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "ALL_OK", r.stdout
