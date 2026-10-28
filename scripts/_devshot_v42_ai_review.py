"""V42-1 캡처 — 드로어 사전검증 카드의 AI 검수 블록(수락·편집·기각). 인자: 접두. 390 모바일."""
import sys, os, threading, time, glob, json
sys.path.insert(0, os.getcwd()); os.environ["SELLER_CONSOLE_AUTH"] = "0"; os.environ["SECRET_KEY"] = "devshot"
pre = sys.argv[1]
from src.order_webhook import app
from src.seller_console import collect_history_store as CH
iid = CH.append(source="extension", url="https://item.taobao.com/item.htm?id=4211", title="t", image="https://picsum.photos/seed/9/300",
                price="1849", currency="CNY", seller_id="default")
iid = iid[0] if isinstance(iid, tuple) else iid
CH.update(iid, seller_ids={"default"}, extra_json=json.dumps({"title_ko": "전기 스쿠터 전기자전거 접이식 36V",
    "ai_review": {"status": "done", "at": "2026-10-28T11:00:00+00:00",
      "items": [{"issue": "상품명에 '전기자전거'와 '전기 스쿠터'가 혼용됨 — 어느 제품인지 불명확", "field": "title", "fix": "접이식 전기자전거 36V 리튬배터리"},
                {"issue": "옵션에 '전압 36V'만 있고 배터리 용량(Ah)·주행거리·최고속도가 없음", "field": "option", "fix": None},
                {"issue": "상세 사진 글자에 중국 매장 안내가 남아 있음", "field": "description", "fix": None}]}}, ensure_ascii=False))
threading.Thread(target=lambda: app.run(port=5421, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]; bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=exe)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True); p = ctx.new_page()
    p.goto(f"http://127.0.0.1:5421/seller/collect/preview/{iid}?drawer=1", wait_until="networkidle")
    if os.path.exists(bs): p.add_style_tag(path=bs)
    p.evaluate("""() => { const box = document.querySelector('.kgp-esec:not(.kgp-etab-hide)') || document.querySelector('main') || document.body;
      window._kgpAiReview = %s; const d = document.createElement('div'); d.innerHTML = window.kgpAiReviewHtml(window._kgpAiReview, %r); box.prepend(d); }""" % (
        json.dumps({"status": "done", "items": [{"issue": "상품명에 '전기자전거'와 '전기 스쿠터'가 혼용됨 — 어느 제품인지 불명확", "field": "title", "fix": "접이식 전기자전거 36V 리튬배터리"},
                                                {"issue": "옵션에 '전압 36V'만 있고 배터리 용량(Ah)·주행거리·최고속도가 없음", "field": "option", "fix": None},
                                                {"issue": "상세 사진 글자에 중국 매장 안내가 남아 있음", "field": "description", "fix": None}]}, ensure_ascii=False), iid))
    p.wait_for_timeout(400)
    el = p.query_selector('[data-role="ai-review"]'); el.scroll_into_view_if_needed(); p.wait_for_timeout(200)
    el.screenshot(path=f"docs/screens/v42_1/{pre}-m-ai-review.png")
    # 수락 눌러 본다(실제 라우트 → 저장) → 다시 그려진 블록
    p.click('[data-role="ai-review-act"][data-action="accept"]'); p.wait_for_timeout(1200)
    el = p.query_selector('[data-role="ai-review"]'); el.screenshot(path=f"docs/screens/v42_1/{pre}-m-ai-review-accepted.png")
    print("title now:", p.eval_on_selector('#editTitle', 'e => e.value'))
    b.close()
