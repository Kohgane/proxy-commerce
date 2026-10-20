"""Y13-F — 캡처: ① 지우기 제안 「넘김」 즉시 갱신(U1) 전/후 ② 등록 결과 쿠팡 일일 옵션 한도·네이버 413 문구(F1·F2) 전/후
③ 사전검증 11번가 판매방식 보류(F3). 문구는 **이 PR 코드가 실제로 만든 값**(UploadDispatcher·NaverUploader·사전검증)을 화면 함수에 넣는다.
「전」 문구는 오너 화면(10-19 13:31~13:34 KST)에 찍힌 원문. 운영 주소는 막혀 있어(프록시 403) 인메모리로 로컬에서 그린다.
사용: python scripts/_devshot_y13f.py [OUT]"""
import dataclasses, glob, json, os, sys, threading, time
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/screens/y13f"
os.makedirs(OUT, exist_ok=True)
from src.db import image_translate_queue_pg as Q
Q.counts = lambda item_id="": {"queued": 0, "running": 0}
from src.db import market_registrations_pg as _L
_L.enabled = lambda: False
from src.seller_console import collect_history_store as ch
ch._pg_backend = lambda: None; ch._in_memory.clear()

# ① 지우기 제안 2장(정품 보장 · 무료 배송) — 넘김 전/후
def _photo(i, t):
    return {"idx": i, "kind": "gallery", "use": True, "status": "done", "url": f"https://res.cloudinary.com/x/g{i}-ko.png",
            "boxes": [{"x": 0, "y": 0, "w": 400, "h": 100}], "box_size": [1000, 1000],
            "polish": {"at": "2026-10-19T04:00:00+00:00", "version": "edit:1", "outbound": True, "suggest_erase": 1,
                       "rows": [{"id": "t0", "tgt": t, "ko": t, "from": "tencent", "suggest_erase": True}]}}
ex = {"title_ko": "1인용 소파 의자", "images": [f"https://img.alicdn.com/g{i}.jpg" for i in range(3)],
      "images_ko": [_photo(1, "정품 보장"), _photo(2, "무료 배송"),
                    dict(_photo(0, "- · __ · ____"), idx=0)]}       # U2: 기호뿐 상자 — 목록에 안 나와야 한다
iid = ch.append(source="share", url="https://item.taobao.com/item.htm?id=913", seller_id="u1", title="소파", price="10",
                currency="CNY", extra=ex)

# ② 등록 결과 — 이 PR 코드가 만든 문구
from src.channel_sync._channel_bridge import ChannelUploadError
from src.seller_console.upload_dispatcher import UploadDispatcher, DispatchResult, UploadResult
from src.services import coupang_option_quota as CQ
RAW = "[A01381223]가 오늘 등록할 수 있는 구매옵션 개수(5000)를 초과하였습니다. 현재까지 요청: 5000, 현재요청: 10"
exc = ChannelUploadError("쿠팡 업로드 실패: " + RAW, lines=[RAW]); exc.reason_code = CQ.CODE
fake = MagicMock(); fake.upload.side_effect = exc
with patch.dict("sys.modules", {"src.channel_sync.coupang_uploader": fake}):
    r_cq = UploadDispatcher()._upload_coupang({"title": "x", "price": 1000})
r_cq.market = "coupang:gogane"
from src.market_relay import RelayTooLarge
from src.collectors.image_norm import FetchedImage
from src.uploaders.naver_uploader import NaverSmartStoreUploader as NU
nu = NU.__new__(NU); nu.client_id, nu.account, nu.token_error = "cid", "", ""; nu._get_access_token = lambda: "tok"
with patch("src.uploaders.naver_uploader.relay_request", side_effect=RelayTooLarge("413")), patch("time.sleep"):
    up = nu._upload_parts([FetchedImage(b"x" * 412_000, "image/jpeg", "jpg"), FetchedImage(b"x" * 397_000, "image/jpeg", "jpg")], nos=[1, 2])
from src.seller_console.upload_dispatcher import lines_message
r_nv = UploadResult(market="smartstore:chezgoga", success=False, error_code="naver_image_too_large", details=["이미지 업로드 실패 — 등록 중단: " + up["reason"]],
                    message=lines_message("전송 전에 보류했습니다", ["이미지 업로드 실패 — 등록 중단: " + up["reason"]]))   # 디스패처 보류 분기와 같은 모양
after_up = {"ok": True, "result": DispatchResult(product_url="", total=2, failed=2, results=[r_cq, r_nv]).to_dict()}
before_up = {"ok": True, "result": DispatchResult(product_url="", total=2, failed=2, results=[
    UploadResult(market="coupang:gogane", success=False, message="쿠팡이 거부했습니다 — " + RAW, error_code="api_error"),
    UploadResult(market="smartstore:chezgoga", success=False, error_code="api_error",
                 message="이미지 업로드 실패(최대 3회, 전송 3633210B): 릴레이 오류: 릴레이가 HTTP 413")]).to_dict()}

# ③ 사전검증 11번가 — 이 PR의 판정 그대로(판매방식 02 = 11번가 거부 확인값)
os.environ["ELEVENST_SELL_METHOD"] = "02"; os.environ.setdefault("ELEVENST_API_KEY", "k")
import urllib.request as _ur
_ur.urlopen = lambda *a, **k: MagicMock()
from src.seller_console import upload_dispatcher as D
D.market_reach = lambda m: {"ok": True, "ms": 398, "detail": "도달"}
pv11 = dataclasses.asdict(D.UploadDispatcher()._prevalidate_market(
    {"title": "블랙홀 무드등", "price": 30000, "currency": "KRW", "sell_price_krw": 30000,
     "images": ["https://img.alicdn.com/a.jpg"], "description": "본문"}, "elevenst"))
pv11_before = {"market": "elevenst", "ok": True, "message": "사전검증 통과", "reach_ok": True, "reach_ms": 398, "reach_detail": "도달"}

from src.order_webhook import app
PORT = 5139
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start(); time.sleep(2)
cookie = app.session_interface.get_signing_serializer(app).dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_role": "admin"})
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
lines = []
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    opts = {'executable_path': exe}
    if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    c = b.new_context(viewport={'width': 1100, 'height': 1000})
    c.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    pg = c.new_page()
    pg.goto(f"http://127.0.0.1:{PORT}/seller/collect/preview/{iid}?drawer=1", wait_until="networkidle")
    bs = "/home/user/proxy-commerce/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(bs): pg.add_style_tag(path=bs)
    pg.wait_for_timeout(500)
    print("숨긴 조상:", pg.evaluate("""() => { let e = document.querySelector('[data-role=erase-suggest]'), out = [];
        while (e) { const cs = getComputedStyle(e); if (cs.display === 'none' || (e.tagName === 'DETAILS' && !e.open)) out.push(e.tagName + '.' + e.className + '#' + (e.dataset.role || '')); e = e.parentElement; }
        return out; }"""))
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    box = pg.locator("[data-role=erase-suggest]").first
    box.scroll_into_view_if_needed(); box.screenshot(path=os.path.join(OUT, "u1-skip-before.png"))
    lines.append("U1 전: " + box.inner_text().replace("\n", " / "))
    print("단계: 넘김 클릭")
    pg.locator("[data-role=erase-skip]").first.click(); pg.wait_for_timeout(1500)
    print("URL 그대로?", pg.url)
    box = pg.locator("[data-role=erase-suggest]").first
    box.scroll_into_view_if_needed(timeout=5000); box.screenshot(path=os.path.join(OUT, "u1-skip-after.png"), timeout=8000)
    lines.append("U1 후(새로고침 없음): " + box.inner_text().replace("\n", " / "))
    for tag, data in (("before", before_up), ("after", after_up)):
        print("단계: 등록 결과", tag)
        pg.evaluate("""(d) => { renderUploadResults(d); const el = document.getElementById('uploadResults');
                       el.style.cssText = 'background:#fff;padding:16px;width:900px'; document.body.prepend(el); window.scrollTo(0, 0); }""", data)
        pg.wait_for_timeout(300)
        el = pg.locator("#uploadResults")
        el.screenshot(path=os.path.join(OUT, f"f1f2-upload-{tag}.png"))
        lines.append(f"F1·F2 {tag}: " + el.inner_text().replace("\n", " / "))
    for tag, res in (("before", pv11_before), ("after", pv11)):
        print("단계: 사전검증", tag)
        pg.evaluate("""(r) => { renderPrevalidateResults([r], [], 'done'); const el = document.getElementById('prevalidateResults');
                       el.style.cssText = 'background:#fff;padding:16px;width:900px'; document.body.prepend(el); window.scrollTo(0, 0); }""", res)
        pg.wait_for_timeout(300)
        el = pg.locator("#prevalidateResults")
        el.screenshot(path=os.path.join(OUT, f"f3-elevenst-{tag}.png"))
        lines.append(f"F3 {tag}: " + el.inner_text().replace("\n", " / "))
    b.close()
open(os.path.join(OUT, "captions.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
os._exit(0)
