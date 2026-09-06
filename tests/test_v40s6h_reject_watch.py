"""tests/test_v40s6h_reject_watch.py — 디자인 v3 Stage 6-h: 반려 감시 뷰포트 고정.

합격 기준이 **"1920×940에 들어간다"**라서, 이 슬라이스는 문법 승계보다
"무엇을 세로로 쌓지 않을 것인가"가 본론이었다.

수리 전 실측: `scrollHeight 1760` — 뷰포트를 **820px** 넘겼다. 카드 5장 + 배너 3장이 전부 세로였다.
수리 후: 0건·실데이터·많은 행 **전부 940**(내부 스크롤 2곳으로 흡수).

로직 변경 0. 라우트·id·data-* 훅은 그대로다 — 유일한 구조 변경은 **입력칸 둘을 하나로 합친 것**이고,
그건 오너 지시(H2)다.
"""
from __future__ import annotations

import glob
import os
import re
import tempfile
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/reject_watch.html")
CSS = Path("src/static/app.css")
VIEWPORT = (1920, 940)


def _body(p: Path) -> str:
    s = p.read_text(encoding="utf-8")
    s = re.sub(r"<script.*?</script>", "", s, flags=re.S)
    return re.sub(r"\{#.*?#\}|<!--.*?-->", "", s, flags=re.S)


def _js(p: Path) -> str:
    js = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", p.read_text(encoding="utf-8"), re.S))
    return re.sub(r"^\s*//.*$", "", re.sub(r"/\*.*?\*/", "", js, flags=re.S), flags=re.M)


# ── H2 구조: 입력은 하나, 분기는 버튼이 진다 ─────────────────────────────────
def test_one_input_two_buttons():
    """★ 같은 번호를 두 번 치게 하지 않는다 — 입력칸 둘을 하나로 합쳤다(오너 H2).

    합칠 수 있었던 이유: 갈리는 건 **'비웠을 때'뿐**이고 그 분기는 이미 버튼이 지고 있었다.
    조회는 비우면 감시 대상 전부, 다시 지켜보기는 전부에 걸지 않는다(상태를 되돌리는 조작이라
    대상이 명시돼야 한다). 그래서 못 합칠 이유가 없었다.
    """
    b = _body(TPL)
    assert b.count("<textarea") == 1, "입력칸이 아직 둘이다"
    assert 'id="sids"' in b and 'name="sids"' in b
    assert 'id="rearmSids"' not in b, "합치기 전 입력이 남았다"
    # 두 버튼이 같은 폼 안에서 같은 입력을 본다.
    assert 'id="rearmBtn"' in b and 'type="submit"' in b
    assert "document.getElementById('sids')" in _js(TPL)


def test_empty_input_means_different_things_and_says_so():
    """★ 비웠을 때 의미가 갈린다 — 화면이 그걸 **말한다**(가짜 일괄 실행 0)."""
    b, js = _body(TPL), _js(TPL)
    assert "비워 두면 <strong>감시 대상 전부</strong>를 조회합니다." in b
    assert "번호를 적었을 때만 실행돼요" in b
    # 코드도 같은 약속을 지킨다: 비면 전부가 아니라 **차단**이다.
    guard = js.split("if (!sids.length)")[1][:200]
    assert "전부에 대해 실행하지 않아요" in guard and "return" in guard


# ── H1 합격 기준: 한 화면 ────────────────────────────────────────────────────
def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    if glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"):
        return True
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
    return cache.is_dir() and any(cache.glob("chromium-*"))


# 부트스트랩은 앱이 CDN으로 싣는 **실제 스타일시트**다. 없이 재면 다른 화면을 재는 것이고,
# 그 숫자로 "한 화면에 들어간다"를 말할 수 없다(CI 실측: 없으면 940 대신 1161).
# 그래서 **조용히 넘어가지 않고** 못 찾으면 그 사실이 실패로 드러나게 한다.
_BS_CANDIDATES = ("node_modules/bootstrap/dist/css/bootstrap.min.css",
                  "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css")
BOOTSTRAP = next((p for p in _BS_CANDIDATES if Path(p).exists()), None)
CSS_FILES = tuple(x for x in (BOOTSTRAP, "src/static/app.css",
                              "src/seller_console/static/seller.css",
                              "src/seller_console/static/console.css") if x)

PROBE = """() => {
  const scrollers = [];
  document.querySelectorAll('.rw-page *').forEach(function (e) {
    const s = getComputedStyle(e);
    if (/(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 4) scrollers.push(1);
  });
  // scrollHeight는 뷰포트보다 작아지지 않는다(clamp) — 그래서 '넘쳤나'만 알려주고 **여유는 못 보여준다.**
  //   여유를 재려면 콘텐츠의 실제 바닥을 봐야 한다. CI엔 우리 웹폰트가 없어 글자 높이가 미세하게
  //   다르니, 로컬에서 딱 맞춘 값은 CI에서 넘칠 수 있다(6-h에서 실제로 그렇게 깨졌다).
  const main = document.querySelector('main').getBoundingClientRect();
  return {total: document.documentElement.scrollHeight, vh: window.innerHeight,
          contentBottom: Math.round(main.bottom), scrollers: scrollers.length,
          cols: document.querySelectorAll('.rw-page > .rw-col').length};
}"""


def _rows(n):
    base = [
        {"sid": "16369251981", "title": "ALPAKA 에어 슬링 크로스백", "comment": "임시저장",
         "kind": "saved_pending", "kind_ko": "임시저장(승인요청 누락)", "wing_state": "saved",
         "prescription": "request_approval", "prescription_ko": "승인 재요청(PUT approvals) — 재등록 아님"},
        {"sid": "16359486080", "title": "PopSockets 그립톡 스탠드", "comment": "대표이미지 최소 500*500 미달",
         "kind": "image_spec", "kind_ko": "이미지 규격", "prescription": "reupload",
         "prescription_ko": "이미지 재수집·교체 후 재제출", "wing_state": "rejected"},
        {"sid": "16359486081", "title": "무명 파우치", "comment": "담당자 검토 결과 반려되었습니다.",
         "kind": "unknown", "kind_ko": "미분류", "prescription": "manual",
         "prescription_ko": "오너 확인 필요", "comment_is_status_only": True, "wing_state": "rejected"},
    ]
    return (base * ((n // 3) + 1))[:n]


def _render(n_scan, n_watch):
    from flask import render_template

    from src.order_webhook import app
    from src.pipeline import reject_watch as RW
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    app.jinja_env.cache.clear()
    rows = _rows(n_scan)
    sc = None
    if n_scan:
        by_kind, by_state = {}, {}
        for r in rows:
            by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
            by_state[r["wing_state"]] = by_state.get(r["wing_state"], 0) + 1
        sc = {"alert": f"반려·임시저장 {n_scan}건", "rows": rows, "by_kind": by_kind, "scanned": n_scan,
              "needs_manual": sum(1 for r in rows if r["kind"] == "unknown"), "by_state": by_state,
              "labels": {"rejected": "반려", "saved": "임시저장"},
              "actionable": sum(1 for r in rows if r["kind"] != "unknown"),
              "info_only": sum(1 for r in rows if r["kind"] == "unknown"), "error": None}
    watch = [{"sid": f"1636925{1900 + i}", "title": "감시 대상 상품", "account": "gogane",
              "market_url": "https://www.coupang.com/vp/products/1"} for i in range(n_watch)]
    with app.test_request_context("/seller/sourcing/reject-watch"):
        html = render_template("reject_watch.html", page="sourcing", scan=sc, account="gogane",
                               sids_text="", approved=True, kinds=RW.REJECTION_KINDS,
                               watch={"connected": True, "note": "", "rows": watch})
    style = "".join(f"<style>{Path(p).read_text(encoding='utf-8')}</style>"
                    for p in CSS_FILES if Path(p).exists())
    return html.replace("</head>", style + "</head>", 1)


def _measure(n_scan, n_watch):
    from playwright.sync_api import sync_playwright
    exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome") or [None])[0]
    tmp = Path(tempfile.gettempdir()) / f"kgp6h_{n_scan}_{n_watch}.html"
    tmp.write_text(_render(n_scan, n_watch), encoding="utf-8")
    with sync_playwright() as pw:
        br = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = br.new_page(viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]})
        pg.set_default_timeout(15000)
        pg.route("**/*", lambda r: (r.continue_() if r.request.url.startswith("file://") else r.abort()))
        pg.goto(tmp.as_uri(), wait_until="domcontentloaded")
        pg.wait_for_timeout(400)
        r = pg.evaluate(PROBE)
        br.close()
    return r


@pytest.mark.skipif(not _pw_ok(), reason="크로미움 없음 — 정직하게 skip")
@pytest.mark.parametrize("n_scan,n_watch,label", [(0, 0, "0건"), (3, 3, "실데이터"), (18, 6, "많은 행")])
def test_fits_one_viewport(n_scan, n_watch, label):
    """★ 1920×940에서 **body 스크롤바 0**(오너 H1). 데이터가 늘어도 넘치지 않는다.

    행이 늘 때 페이지가 자라면 상한이 무는 게 아니라 '지금 데이터에서만 맞는' 레이아웃이다.
    그래서 18행짜리도 같이 잰다 — 상한이 실제로 무는지가 이 계약의 값어치다.
    """
    assert BOOTSTRAP, ("부트스트랩 CSS를 못 찾았다 — 라이브와 **다른 화면**을 재게 된다. "
                       f"찾은 자리: {_BS_CANDIDATES}")
    r = _measure(n_scan, n_watch)
    assert r["cols"] == 2, "2단이 아니다"
    assert r["total"] <= r["vh"], f"{label}: scrollHeight {r['total']} > 뷰포트 {r['vh']}"
    # 여유도 함께 못 박는다 — 0px로 맞추면 폰트가 다른 환경에서 바로 넘친다(그게 CI를 깨뜨렸다).
    assert r["contentBottom"] <= r["vh"] - 20, \
        f"{label}: 콘텐츠 바닥 {r['contentBottom']} — 여유 20px 미만이면 다른 환경에서 넘친다"


@pytest.mark.skipif(not _pw_ok(), reason="크로미움 없음 — 정직하게 skip")
def test_internal_scroll_is_exactly_two_places():
    """★ 세로 스크롤은 **감시 대상 · 분류표 안에서만**(오너 H1). 셋째가 생기면 실패한다."""
    assert _measure(18, 6)["scrollers"] == 2
    # 분류표가 없는 0건 화면에선 하나뿐이다 — 없는 스크롤을 만들지도 않는다.
    assert _measure(0, 6)["scrollers"] <= 1


def test_caps_are_measured_not_guessed():
    """상한은 실측으로 정했다 — 주석이 그 근거를 들고 있어야 다음 사람이 함부로 못 키운다."""
    css = CSS.read_text(encoding="utf-8")
    slice_ = css.split("Stage 6-h")[1]
    assert ".rw-card-watch" in slice_ and ".rw-card-table" in slice_
    assert "1760" in slice_, "수리 전 실측치가 주석에 없다"
    # 뷰포트를 dvh로 잠그지 않았다 — 상단 배너 유무로 어긋나기 때문이다(그 판단도 남긴다).
    assert "dvh" in slice_


# ── H3 배너 3장 다이어트: 자리만 바꾼다, 정보는 0 손실 ───────────────────────
BANNER_SENTENCES = [
    "반려된 쿠팡 상품의 <strong>실제 사유(이력 comment)</strong>",          # ① 상단 설명
    "재등록·삭제 실행은 오너 승인 뒤",
    "마켓에는 아무것도 보내지 않아요",
    "심사 결과를 다시 확인하고 싶은 상품",
    "2시간마다 자동 점검",                                                  # 감시 대상 푸터
    "쿠팡에 실제 사유를 물어보는",
    "POST /admin/reject-watch/apply",                                       # ③ 하단 요약
    "브랜드 수정요청·증빙 필요는 자동 조치하지 않습니다",
]


@pytest.mark.parametrize("sentence", BANNER_SENTENCES)
def test_no_information_was_dropped(sentence):
    """★ 배너를 접었지 **지우지 않았다**(오너 H3: 없앤 정보 0).

    자리를 옮기는 수리에서 가장 흔한 사고가 '줄이다가 문장을 잃는 것'이다. 문장 단위로 못 박는다.
    """
    assert sentence in _body(TPL), f"배너 다이어트에서 사라진 문장: {sentence}"


def test_gate_banner_became_one_badge():
    """★ 게이트 노랑 배너 → 자물쇠 뱃지 하나. 상태는 한눈에, 사유는 뱃지가 물고 있는다."""
    b = _body(TPL)
    # 남은 `pc-status` 배너는 **조회 실패(scan.error)** 하나뿐이다 — 그건 배너가 맞다(진짜 경보).
    assert b.count("pc-status ") == 1 and "{{ scan.error }}" in b, "배너가 더 남았다"
    assert "처방 실행 <strong>보류</strong>" not in b, "게이트가 아직 배너 문장이다"
    assert "bi-lock" in b and "bi-{% if approved %}unlock{% else %}lock{% endif %}" in b
    assert "실행 승인됨" in b and "실행 보류" in b
    # 왜 잠겼는지는 title이 들고 있다(정보 0 손실).
    assert "REJECT_WATCH_APPROVED" in b


def test_intro_banner_is_folded_not_deleted():
    """★ 상단 설명 배너 → 1줄 + 접힘. 요약 줄은 접혀 있어도 읽힌다."""
    b = _body(TPL)
    assert '<details class="rw-note">' in b and "<summary>" in b
    assert "반려 사유를 조회해 유형별로 분류하고 처방을 붙이는 화면이에요" in b


def test_summary_banner_moved_into_the_table_foot():
    """★ 하단 요약 배너 → 분류표 카드 푸터 **한 줄**로 흡수(카드 경계 하나가 줄었다)."""
    b = _body(TPL)
    foot = b.split("rw-card-table")[1].split("op-card-foot")[1].split("</div>")[0]
    assert "{{ scan.alert }}" in foot and "조치 대상" in foot
    assert foot.count("<span") <= 2, "푸터가 다시 여러 줄이 됐다"


# ── 로직 변경 0 (훅 계약) ────────────────────────────────────────────────────
HOOKS = ('id="account"', 'id="sids"', 'id="rearmBtn"', 'id="rearmResult"', "/admin/reject-watch/rearm",
         "/admin/reject-watch/apply", "rw-apply", 'id="rwResult-', "rw-result", "rwRender(",
         "RW_ACTION_KO", "RW_TONE_ICON", "pcConfirm(", 'action="/seller/sourcing/reject-watch"')


@pytest.mark.parametrize("hook", HOOKS)
def test_hooks_survive(hook):
    assert hook in TPL.read_text(encoding="utf-8"), hook


def test_apply_button_still_gated():
    """게이트가 잠겨 있으면 실행 버튼은 비활성 + 사유 표기(비가역 방어는 디자인보다 위)."""
    b = _body(TPL)
    assert "게이트 잠김" in b and "disabled" in b
    assert "REJECT_WATCH_APPROVED가 꺼져 있어" in b


def test_code_color_is_a_token_now():
    """★ 6-g에서 SKU 하나만 잡고 지나간 유형이 여기서 또 나왔다(감시 대상 상품번호).

    화면마다 클래스를 붙이면 다음 화면에서 또 만난다 — 부트스트랩 변수를 우리 토큰으로 덮어 끝냈다.
    """
    css = CSS.read_text(encoding="utf-8")
    assert "--bs-code-color: var(--text-muted)" in css


def test_screen_renders():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    assert app.test_client().get("/seller/sourcing/reject-watch").status_code == 200
