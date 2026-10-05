"""R1-a(오너 2026-10-05 역직구) — 한국 소싱처(올리브영·스마트스토어·쿠팡): 원화 확정 · 확장 기본 소싱처 · 서버 레지스트리.

상세 추출 어댑터(R1-b)는 실페이지 스냅샷(확장 팝업 「진단 스냅샷 저장」 → fixtures/realpages/)이 온 뒤 —
이 컨테이너는 세 사이트에 못 나가고(연결 거부), 저장소 규칙상 추측 셀렉터로 추출을 바꾸지 않는다.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

KR = [("https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000184228", "KRW"),
      ("https://m.oliveyoung.co.kr/m/goods/getGoodsDetail.do?goodsNo=A1", "KRW"),
      ("https://smartstore.naver.com/somestore/products/1234567890", "KRW"),
      ("https://m.smartstore.naver.com/somestore/products/1", "KRW"),
      ("https://brand.naver.com/brandx/products/1", "KRW"),
      ("https://www.coupang.com/vp/products/7335597976?itemId=1", "KRW"),
      ("https://m.coupang.com/vm/products/1", "KRW"),
      # 다른 통화 — 패턴이 잡으면 안 된다(추측 금지)
      ("https://global.oliveyoung.com/product/detail?prdtNo=GA1", ""),
      ("https://tw.coupang.com/products/1", ""),
      ("https://shopping.naver.com/home", "")]


@pytest.mark.parametrize("url,cur", KR)
def test_server_domain_currency(url, cur):
    from src.collectors.collect_sanitize import domain_currency, check_currency_domain
    assert domain_currency(url) == cur
    if cur:
        assert check_currency_domain(url, "USD")                      # 원화 사이트에 USD로 오면 사유
        assert check_currency_domain(url, "KRW") == ""


def test_registry_has_three_kr_sources_needing_snapshots():
    from src.collectors.sourcing_registry import DEFAULT_SOURCING_SITES, registry_ids
    assert registry_ids()[-3:] == ["oliveyoung", "smartstore", "coupang"]
    for s in DEFAULT_SOURCING_SITES[-3:]:
        assert s["coverage"] == {"level": "unverified", "needs_snapshot": True} and s["adapter"] is False


_NODE = shutil.which("node")
_JS = r"""
const path = require('path');
const T = require(path.resolve('extensions/chrome-collector/kgp-extractor.js'))._test;
global.self = global;
require(path.resolve('extensions/chrome-collector/kgp-sources.js'));
const S = global.KGPSources;
const hosts = ['www.oliveyoung.co.kr','m.oliveyoung.co.kr','smartstore.naver.com','m.smartstore.naver.com','brand.naver.com',
               'www.coupang.com','m.coupang.com','global.oliveyoung.com','tw.coupang.com','shopping.naver.com','coupang.com.evil.io'];
const out = {};
for (const h of hosts) out[h] = {cur: T.domainCurrency(h, '/'), src: (S.matchHost(h, {}) || {}).id || ''};
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_extension_matches_and_prices_in_won():
    r = subprocess.run([_NODE, "-e", _JS], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    for h, src in (("www.oliveyoung.co.kr", "oliveyoung"), ("m.oliveyoung.co.kr", "oliveyoung"),
                   ("smartstore.naver.com", "smartstore"), ("m.smartstore.naver.com", "smartstore"),
                   ("brand.naver.com", "smartstore"), ("www.coupang.com", "coupang"), ("m.coupang.com", "coupang")):
        assert d[h] == {"cur": "KRW", "src": src}, (h, d[h])
    for h in ("global.oliveyoung.com", "tw.coupang.com", "shopping.naver.com", "coupang.com.evil.io"):
        assert d[h] == {"cur": "", "src": ""}, (h, d[h])               # 다른 통화·유사 도메인은 안 잡는다
