"""F51-b-2·3 / F48-d 검증 캡처 — 수행방패(ICE SKU 10) 편집 화면.

① 쿠팡 필수 옵션 블록(열자마자 불러온 결과): 적용모델 「제목에서 추출 — 확인」 · SKU 10줄 「용어집」 · 환율 줄
② 사전검증 결과(실제 `/seller/collect/prevalidate` 응답을 화면 렌더러로)
쿠팡 API는 `_api_request`만 목(카테고리·메타[색상·수량·적용모델]·출고지). 용어집은 **실제**(정본 10줄).
환율: 이 샌드박스는 환율 API가 막혀 있다 → 표기는 정직하게 「앱 기본값(고정)」(프로덕션 확인은 오너 캐너리).
사용: python scripts/_devshot_f51b2.py <before|after> <out_dir>
"""
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ.pop("FX_USE_LIVE", None)          # 운영과 같은 경로(실시간 시도 → 실패하면 고정값으로 정직 표기)
sys.argv = [sys.argv[0], TAG, OUT]
import scripts._devshot_f51 as base  # noqa: E402

base.META["attributes"].append({"attributeTypeName": "적용모델", "required": "MANDATORY", "dataType": "STRING",
                                "exposed": "EXPOSED", "groupNumber": "NONE"})


def main():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.uploaders.coupang_uploader import CoupangUploader
    os.makedirs(OUT, exist_ok=True)
    prod = base._product()
    iid = S.append(url="https://detail.tmall.com/item.htm?id=617129397971", title=prod["title"], price="29.90",
                   currency="CNY", source="extension", seller_id="u-shot-b2",
                   extra={"options": prod["options"], "images": prod["images"], "skus": prod["skus"]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    st = lambda *a, **k: {"missing": [], "account": "", "source": ""}  # noqa: E731
    with patch.object(CoupangUploader, "_api_request", base._api), \
            patch("src.seller_console.market_cred_view.resolve_upload_account", lambda: ""), \
            patch("src.seller_console.market_cred_view.coupang_api_state", st), \
            patch("src.seller_console.market_cred_view.coupang_shipping_state", st), \
            patch("urllib.request.urlopen", lambda *a, **k: __import__("contextlib").nullcontext()):
        # ↑ 이미지 공개 URL 확인(HEAD)은 이 샌드박스에서 외부망이 막혀 실패한다 — 계약 테스트와 같은 자리만 목.
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "u-shot-b2"
            html = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
            d = c.post("/seller/collect/coupang/options", json={"product": prod}).get_json()
            pv = c.post("/seller/collect/prevalidate", json={"product": prod, "markets": ["coupang"]}).get_json()
    r0 = (pv.get("results") or [{}])[0]
    print(f"[{TAG}] 옵션 보류:", d.get("holds"), "· SKU:", len(d.get("items") or []),
          "· 적용모델:", next((f.get("value"), f.get("source")) for f in d.get("fields") or [] if f["name"] == "적용모델"))
    print(f"[{TAG}] 사전검증 ok:", r0.get("ok"), "· hint:", r0.get("hint"), "· error:", r0.get("error"))
    print(f"[{TAG}] 환율:", d.get("fx"))
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=base.CHROME)
        open(f"/tmp/_b2_{TAG}.html", "w").write(base._inline(html).replace(
            "document.addEventListener('DOMContentLoaded', function () {\n  if (!document.getElementById('coupangOptionsBody')) return;",
            "document.addEventListener('DOMContentLoaded', function () {\n  return;"))  # 정적 파일 — 서버 호출 대신 응답 주입
        pg = br.new_page(viewport={"width": 760, "height": 1400})
        pg.goto(f"file:///tmp/_b2_{TAG}.html")
        pg.wait_for_timeout(300)
        pg.evaluate("() => { if (typeof kgpEtab === 'function') kgpEtab('options'); }")
        pg.evaluate("(d) => kgpRenderCoupangOptions(d)", d)
        pg.wait_for_timeout(200)
        pg.locator('[data-role="coupang-options"]').screenshot(path=f"{OUT}/f51b2-options-{TAG}.png")
        pg.evaluate("(r) => { const m = document.getElementById('prevalidateResults'); m.closest('.modal') && "
                    "(m.closest('.modal').style.display='block', m.closest('.modal').classList.add('show')); "
                    "document.querySelectorAll('[id^=step]').forEach(e => e.style.display='none'); "
                    "const st = document.getElementById('stepPrevalidate'); if (st) { st.classList.remove('d-none'); st.style.display='block'; } "
                    "renderPrevalidateResults(r); }", pv.get("results") or [])
        pg.wait_for_timeout(200)
        pg.locator('#prevalidateResults').screenshot(path=f"{OUT}/f51b2-prevalidate-{TAG}.png")
        br.close()
    print(f"[{TAG}] saved")


if __name__ == "__main__":
    main()
