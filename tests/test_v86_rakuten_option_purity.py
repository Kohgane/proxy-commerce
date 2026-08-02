"""tests/test_v86_rakuten_option_purity.py — v86 마감: 라쿠텐 옵션 정제 실효.

오너 지시: tsumugi 실측 픽스처에서 추출 옵션이 **[ブラウン, ブラック] 정확 일치**여야 한다
(제조사·품번·국가가 섞이면 red).

수리 전 실측(kgp-snapshot-item-rakuten-co-jp-receno-tsumugi-tama-s-…):
    [{"name": "옵션", "values": ["TSUMUGI 汁椀", "我戸幹男商店", "tsumugi-tama", "日本", "ブラウン", "ブラック"]}]
시리즈명·제조사·품번·원산국이 색상값과 한 축에 뭉쳐 있었다.

근본: JSON-LD가 **축명 없이** sku별 스펙 문자열만 준다 → 전부 무명 축('옵션') 한 바구니에 쌓이는데,
그 축은 이름이 없어 `_isBadOptAxis`(원산지·브랜드·품번 배제) 방어를 못 받는다. sku 2건의 spec은
    ["TSUMUGI 汁椀","我戸幹男商店","tsumugi-tama","日本","ブラウン"]
    ["TSUMUGI 汁椀","我戸幹男商店","tsumugi-tama","日本","ブラック"]
로 **앞 4자리가 그대로 반복**된다.

수리: 값 블랙리스트를 늘리는 대신 **구분력**이라는 구조적 근거로 거른다 — 옵션 축은 정의상 sku를
구분하므로, 전 sku에 공통인 값은 변형이 아니다. sku가 1개면 가를 근거가 없어 손대지 않는다(추측 금지).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import _pw

EXT = Path("extensions/chrome-collector")
EX = (EXT / "kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
_SNAP = Path("fixtures/realpages/diag/"
             "kgp-snapshot-item-rakuten-co-jp-receno-tsumugi-tama-s-id-pc-shop-recommen.html")
_URL = "https://item.rakuten.co.jp/receno/tsumugi-tama-s/"

# 오너가 지정한 정답 — 이 상품의 실제 변형은 색 2종뿐이다.
EXPECTED = ["ブラウン", "ブラック"]
# 혼입되면 안 되는 것들(수리 전 실제로 섞여 있던 값).
CONTAMINANTS = ["TSUMUGI 汁椀", "我戸幹男商店", "tsumugi-tama", "日本"]


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.136"


def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


def _extract(source: str):
    """오너 실측 스냅샷을 실브라우저에 띄워 추출기를 그대로 돌린다(합성 픽스처 금지)."""
    from playwright.sync_api import sync_playwright

    if not _SNAP.exists():
        pytest.skip(f"스냅샷 미커밋: {_SNAP.name}")
    body = _SNAP.read_text(encoding="utf-8", errors="ignore")
    opts = _pw.launch_opts()
    with sync_playwright() as pw:
        b = pw.chromium.launch(**opts)
        page = b.new_context().new_page()

        def route(r):
            if r.request.url.split("#")[0] == _URL:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            else:
                r.abort()
        page.route("**/*", route)
        page.goto(_URL, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", source)
        b.close()
    return res


def test_common_value_filter_source():
    """구분력 기준이 소스에 존재한다(값 블랙리스트로 때우지 않았음을 못박는다)."""
    assert "function _dropCommonSkuValues" in EX
    seg = EX.split("function _dropCommonSkuValues")[1].split("\n  }")[0]
    assert "hits < n" in seg, "전 sku 공통값을 거르는 판정이 없다"
    assert "if (n < 2) return values;" in seg, "sku 1개일 때 손대지 않는 정직 가드가 없다"


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_tsumugi_options_are_exactly_two_colors():
    """실측 스냅샷 — 옵션값이 [ブラウン, ブラック] **정확 일치**."""
    res = _extract(EX)
    opts = res.get("options") or []
    vals = [v for o in opts for v in (o.get("values") or [])]
    assert vals == EXPECTED, ("옵션값이 정답과 다르다", opts)
    for bad in CONTAMINANTS:
        assert bad not in vals, (f"공통 스펙 '{bad}'이 옵션값으로 혼입", opts)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_option_fix_does_not_break_other_fields():
    """옵션 정제가 가격·통화·제목을 건드리지 않는다(곁가지 회귀 차단)."""
    res = _extract(EX)
    assert res.get("price") == "7480", res.get("price")
    assert res.get("currency") == "JPY", res.get("currency")
    assert "TSUMUGI" in (res.get("title") or ""), res.get("title")


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_contract_fails_without_common_value_filter():
    """인위회귀 — 구분력 필터를 무력화하면 오염값이 되돌아와야 한다(게이트가 실제로 잡는지)."""
    anchor = "      var vals = (axis === _ANON_AXIS) ? _dropCommonSkuValues(a.order, skus) : a.order;"
    assert anchor in EX, "회귀 주입 지점을 찾지 못했다"
    broken = EX.replace(anchor, "      var vals = a.order;", 1)
    res = _extract(broken)
    vals = [v for o in (res.get("options") or []) for v in (o.get("values") or [])]
    assert vals != EXPECTED, ("필터를 껐는데도 정답이 나온다 = 게이트가 무의미", vals)
    assert any(b in vals for b in CONTAMINANTS), ("필터를 껐는데 오염이 안 돌아온다", vals)
