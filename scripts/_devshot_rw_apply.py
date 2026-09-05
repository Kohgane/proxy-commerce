"""개발용 스크린샷 — T1 처방 실행 버튼 + R2 감시 재무장.

T1 3벌: 게이트 OFF(잠김) / 게이트 ON(실행 가능) / 확인 다이얼로그.
요점은 **게이트가 화면에서 실제로 갈리는지** — OFF에서 버튼이 눌리면 안 된다.
R2 2벌: 재무장 카드 / 확인 다이얼로그. 이건 마켓 호출이 0이라 성격이 다르다 —
화면이 그 사실을 말하는지까지 찍는다.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
BOOTSTRAP_JS = "/tmp/bsdl/node_modules/bootstrap/dist/js/bootstrap.bundle.min.js"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
OUT_DIR = "docs/screens/rw-apply"
SIZE = (1920, 940)

ROWS = [
    {"sid": "16369251981", "title": "ALPAKA 에어 슬링 크로스백", "comment": "임시저장",
     "kind": "saved_pending", "kind_ko": "임시저장(승인요청 누락)",
     "prescription": "request_approval", "prescription_ko": "승인 재요청(PUT approvals) — 재등록 아님"},
    {"sid": "16359486080", "title": "PopSockets 그립톡 스탠드", "comment": "대표이미지 최소 500*500 미달",
     "kind": "image_spec", "kind_ko": "이미지 규격", "prescription": "reupload",
     "prescription_ko": "이미지 재수집·교체 후 재제출"},
    {"sid": "16359486081", "title": "무명 파우치", "comment": "담당자 검토 결과 반려되었습니다.",
     "kind": "unknown", "kind_ko": "미분류", "prescription": "manual",
     "prescription_ko": "오너 확인 필요", "comment_is_status_only": True},
]


def _html(approved):
    from flask import render_template

    from src.order_webhook import app
    from src.pipeline import reject_watch as RW
    app.jinja_env.cache.clear()
    by_kind = {}
    for r in ROWS:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    scan = {"alert": f"반려·임시저장 {len(ROWS)}건", "rows": ROWS, "by_kind": by_kind,
            "scanned": len(ROWS)}
    with app.test_request_context("/seller/sourcing/reject-watch"):
        page = render_template("reject_watch.html", page="sourcing", scan=scan, account="gogane",
                               sids_text="", approved=approved, kinds=RW.REJECTION_KINDS,
                               watch={"connected": True, "note": "", "rows": []})
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += "<style>" + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            inline += "<style>" + open(extra, encoding="utf-8").read() + "</style>"
    if os.path.exists(BOOTSTRAP_JS):
        inline += "<script>" + open(BOOTSTRAP_JS, encoding="utf-8").read() + "</script>"
        inline += "<script>" + open("src/seller_console/static/seller.js", encoding="utf-8").read() + "</script>"
    return page.replace("</head>", inline + "</head>", 1)


AUDIT = """() => {
  const btns = [...document.querySelectorAll('.rw-apply')];
  const locked = [...document.querySelectorAll('button[disabled]')]
    .filter(b => (b.textContent || '').includes('게이트 잠김'));
  return {
    applyButtons: btns.length,
    rearmCard: !!document.getElementById('rearmBtn'),
    rearmSaysNoMarketCall: (document.body.textContent || '').includes('마켓에 아무것도 보내지 않아요'),
    lockedButtons: locked.length,
    disabledApply: btns.filter(b => b.disabled).length,
    resultRows: document.querySelectorAll('.rw-result-row').length,
    visibleResults: [...document.querySelectorAll('.rw-result-row')].filter(r => !r.hidden).length,
    bodyScrollX: document.documentElement.scrollWidth > innerWidth + 1,
  };
}"""


def main():
    from playwright.sync_api import sync_playwright

    os.makedirs(OUT_DIR, exist_ok=True)
    print("=== T1 처방 실행 버튼 실측 ===")
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for label, approved in (("게이트OFF", False), ("게이트ON", True)):
            path = f"/tmp/_rw_apply_{label}.html"
            open(path, "w", encoding="utf-8").write(_html(approved))
            pg = br.new_page(viewport={"width": SIZE[0], "height": SIZE[1]})
            pg.goto(f"file://{path}")
            pg.wait_for_timeout(700)
            a = pg.evaluate(AUDIT)
            pg.screenshot(path=f"{OUT_DIR}/rw-apply-{label}.png")
            print(f"  {label}: 실행버튼 {a['applyButtons']} · 잠김버튼 {a['lockedButtons']} · "
                  f"결과행 {a['resultRows']}(표시 {a['visibleResults']}) · 가로 스크롤 "
                  f"{'있음' if a['bodyScrollX'] else '없음 ✓'}")
            print(f"      재무장 카드 {a['rearmCard']} · '마켓 호출 0' 표기 {a['rearmSaysNoMarketCall']}")
            # 게이트 ON에서 확인 다이얼로그까지 — 클릭 한 번이 바로 실행되지 않는다는 증거.
            if approved:
                pg2 = br.new_page(viewport={"width": SIZE[0], "height": SIZE[1]})
                pg2.goto(f"file://{path}")
                pg2.wait_for_timeout(700)
                pg2.click(".rw-apply")
                pg2.wait_for_timeout(900)
                shown = pg2.evaluate(
                    "() => { const m = document.getElementById('pcConfirmModal');"
                    " return m ? { open: m.classList.contains('show'),"
                    " body: (document.getElementById('pcConfirmBody')||{}).textContent || '',"
                    " ok: (document.getElementById('pcConfirmOk')||{}).textContent || '' } : null; }")
                pg2.screenshot(path=f"{OUT_DIR}/rw-apply-다이얼로그.png")
                pg2.close()
                if shown:
                    print(f"  다이얼로그: 열림 {shown['open']} · 확인버튼 '{shown['ok']}'")
                    print(f"      본문: {' '.join((shown['body'] or '').split())[:90]}")
                else:
                    print("  다이얼로그: pcConfirmModal 없음 — 네이티브 confirm 폴백")
            pg.close()

        # R2 — 재무장 카드. 게이트와 무관하다(마켓 호출 0)라서 OFF 화면에서 찍는다.
        path = "/tmp/_rw_apply_게이트OFF.html"
        pg3 = br.new_page(viewport={"width": SIZE[0], "height": SIZE[1]})
        pg3.goto(f"file://{path}")
        pg3.wait_for_timeout(700)
        pg3.fill("#rearmSids", "16369251981")
        pg3.eval_on_selector("#rearmBtn", "el => el.scrollIntoView({block:'center'})")
        pg3.wait_for_timeout(300)
        pg3.screenshot(path=f"{OUT_DIR}/rw-rearm-카드.png")
        pg3.click("#rearmBtn")
        pg3.wait_for_timeout(900)
        d = pg3.evaluate(
            "() => { const m = document.getElementById('pcConfirmModal');"
            " return m ? { open: m.classList.contains('show'),"
            " body: (document.getElementById('pcConfirmBody')||{}).textContent || '',"
            " ok: (document.getElementById('pcConfirmOk')||{}).textContent || '' } : null; }")
        pg3.screenshot(path=f"{OUT_DIR}/rw-rearm-다이얼로그.png")
        pg3.close()
        if d:
            print(f"  재무장 다이얼로그: 열림 {d['open']} · 확인버튼 '{d['ok']}'")
            print(f"      본문: {' '.join((d['body'] or '').split())[:110]}")
        br.close()
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
