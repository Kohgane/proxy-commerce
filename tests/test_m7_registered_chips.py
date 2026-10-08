"""M7(오너 2026-10-08) — 「실제 등록된 제품은 조그맣게 표시 — 중복등록·시간낭비 방지」.

- 수집 목록 각 행에 등록된 마켓만 소형 칩(쿠팡·고가네 / 쿠팡·우주대행 / 셰고가 / 고코스모스 / 11번가 / 멀티샵),
  색 = 마지막으로 알려진 상태(승인대기 회색·승인완료 초록·반려 빨강·실패 주황). 목록을 그릴 땐 마켓에 묻지 않는다.
- 과거 등록분은 기록에 번호(또는 주소)가 있으면 소급 표시.
- 등록 모달(데스크톱·폰 카드): 이미 등록된 마켓은 기본 체크 해제 + 「이미 등록됨 (ID, 날짜) — 다시 올리면 중복 상품」,
  체크하면 「중복 등록」 확인 **한 번**.
- 목록 상단 「미등록만」「등록됨만」.
"""
from __future__ import annotations

import os

import pytest

from src.seller_console import listing_status as MS

FAM = "fam-m7@example.com"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("FAMILY_EMAILS", FAM)
    MS.reset_cache()
    # 목록·카드를 그릴 땐 마켓에 묻지 않는다 — 부르면 실패
    monkeypatch.setattr(MS, "query", lambda *a, **k: pytest.fail("목록 렌더가 마켓에 물었다"))
    yield


UPLOADED = [
    {"market": "coupang:woojoo", "market_label": "쿠팡 — 우주대행", "product_id": "16407690349", "account": "woojoo",
     "at": "2026-10-08T07:26:18+00:00", "review": {"state": "approved", "label": "승인"}},
    {"market": "coupang:gogane", "market_label": "쿠팡 — 고가네", "product_id": "16400000001", "account": "gogane",
     "at": "2026-10-07T01:00:00+00:00", "review": {"state": "rejected", "label": "반려"}},
    {"market": "smartstore:chezgoga", "market_label": "스마트스토어 — 셰고가", "product_id": "5551", "at": "2026-10-08T08:00:00+00:00"},
    {"market": "smartstore:gocosmos", "market_label": "스마트스토어 — 고코스모스", "product_id": "5552", "at": "2026-10-08T08:00:00+00:00",
     "review": {"state": "unknown", "label": "확인 못 함"}},
    {"market": "elevenst", "market_label": "11번가", "product_id": "9001", "at": "2026-10-08T08:00:00+00:00"},
    {"market": "woocommerce", "market_label": "코가네멀티샵", "external_url": "https://kohganemultishop.org/products/321",
     "at": "2026-09-01T00:00:00+00:00"},
]


def _item(seller, uploaded=None, title="플리츠 미니멀 여성 여름 세트"):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": title, "price": "168", "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"]}
    if uploaded is not None:
        ex["uploaded"] = uploaded
    return S.append(source="share", url=f"https://item.taobao.com/item.htm?id={abs(hash(title)) % 10**9}", seller_id=seller,
                    title=title, price="168", currency="CNY", extra=ex)


def _client(uid, email=None, role="seller"):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=email or f"{uid}@example.com", user_role=role)
    return c


def test_chip_labels_tones_and_backfill():
    recs = MS.records({"uploaded": UPLOADED})
    assert [r["chip"] for r in recs] == ["쿠팡·고가네", "쿠팡·우주대행", "셰고가", "고코스모스", "11번가", "멀티샵"]
    assert [r["tone"] for r in recs] == ["bad", "ok", "wait", "fail", "wait", "wait"]
    assert recs[-1]["product_id"] == "321"                                   # 옛 기록 — 주소에서 번호(소급)


def test_list_rows_render_chips_without_asking_markets():
    iid = _item("m7-own", UPLOADED)
    none = _item("m7-own", None, title="아직 안 올린 상품")
    h = _client("m7-own").get("/seller/collect/history").get_data(as_text=True)
    row = h.split(f'value="{iid}"')[1].split("</tr>")[0]
    for chip in ("쿠팡·고가네", "쿠팡·우주대행", "셰고가", "고코스모스", "11번가", "멀티샵"):
        assert f">{chip}</button>" in row, chip
    assert row.count('data-role="mk-chip"') == 6 and f'data-item="{iid}"' in row
    assert 'data-tone="ok"' in row and 'data-tone="bad"' in row and 'data-tone="fail"' in row
    other = h.split(f'value="{none}"')[1].split("</tr>")[0]
    assert 'data-role="mk-chip"' not in other                                 # 등록 안 한 상품엔 칩 없음


def test_filter_registered_and_unregistered():
    iid = _item("m7-flt", UPLOADED[:1])
    none = _item("m7-flt", None, title="미등록 상품")
    c = _client("m7-flt")
    done = c.get("/seller/collect/history?reg=done").get_data(as_text=True)
    assert f'value="{iid}"' in done and f'value="{none}"' not in done
    und = c.get("/seller/collect/history?reg=none").get_data(as_text=True)
    assert f'value="{none}"' in und and f'value="{iid}"' not in und
    assert 'data-reg="none"' in und and 'class="is-on" data-reg="none"' in und


def test_phone_card_unchecks_registered_and_warns(monkeypatch):
    """가족(공유 마켓) 폰 카드: 우주대행에 이미 올렸으면 그 줄은 처음 체크 해제 + 「이미 등록됨 (번호, 날짜)」 + 칩.
    대조: 등록 기록이 없는 상품은 같은 줄이 기본(우주대행 묶음)으로 체크된다."""
    for k, v in {"COUPANG_WOOJOO_ACCESS_KEY": "a", "COUPANG_WOOJOO_SECRET_KEY": "s", "COUPANG_WOOJOO_VENDOR_ID": "A0"}.items():
        monkeypatch.setenv(k, v)
    c = _client("fam-m7", email=FAM)
    iid = _item("fam-m7", UPLOADED[:1])
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="mk-chips"' in h and ">쿠팡·우주대행</button>" in h
    box = h.split('value="coupang:woojoo"')[1].split(">")[0]
    assert "checked" not in box and 'data-registered="1"' in box
    assert "이미 등록됨 (16407690349, 10-08) — 다시 올리면 중복 상품" in h
    fresh = _item("fam-m7", None, title="아직 안 올린 세트")
    hf = c.get(f"/seller/m/item/{fresh}").get_data(as_text=True)
    fbox = hf.split('value="coupang:woojoo"')[1].split(">")[0]
    assert "checked" in fbox and 'data-registered' not in fbox and 'data-role="mk-chips"' not in hf


def test_mark_registered_unchecks_rows():
    from src.seller_console.views import _mark_registered
    rows = [{"code": "coupang:woojoo", "checked": True}, {"code": "smartstore:gocosmos", "checked": True}]
    reg = _mark_registered(rows, {"uploaded": UPLOADED[:1]})
    assert rows[0]["checked"] is False and rows[0]["registered"]["line"] == "이미 등록됨 (16407690349, 10-08) — 다시 올리면 중복 상품"
    assert rows[1]["checked"] is True and "registered" not in rows[1] and list(reg) == ["coupang:woojoo"]


def test_desktop_modal_unchecks_registered_tile():
    iid = _item("m7-desk", [UPLOADED[-2]])                                    # 11번가에 이미 등록
    h = _client("m7-desk").get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    box = h.split('id="chkElevenst"')[0].rsplit("<input", 1)[1] + h.split('id="chkElevenst"')[1].split(">")[0]
    assert "checked" not in box and 'data-registered="1"' in box
    assert "이미 등록됨 (9001, 10-08) — 다시 올리면 중복 상품" in h


BROWSER = pytest.mark.skipif(not os.path.exists("/opt/pw-browsers/chromium") and not os.environ.get("KGP_REQUIRE_BROWSER"),
                             reason="브라우저 없음")


def _browser(page_html, path, client, act):
    pytest.importorskip("playwright.sync_api")
    from urllib.parse import urlparse
    from playwright.sync_api import sync_playwright
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = b.new_page(viewport={"width": 390, "height": 900})

        def handle(route):
            u = route.request.url
            if (urlparse(u).hostname or "") != "kgp.test":
                return route.fulfill(status=200, body=b"")
            pth = u.split("kgp.test", 1)[-1]
            if pth == path:
                return route.fulfill(status=200, content_type="text/html", body=page_html)
            r = client.open(pth, method=route.request.method)
            return route.fulfill(status=r.status_code, content_type=r.content_type or "text/plain", body=r.get_data())
        pg.route("**/*", handle)
        pg.goto("http://kgp.test" + path)
        try:
            return act(pg)
        finally:
            b.close()


@BROWSER
def test_chips_wrap_at_390px_without_overflow():
    iid = _item("m7-390", UPLOADED)
    c = _client("m7-390")
    html = c.get("/seller/collect/history").get_data(as_text=True)

    def act(pg):
        sel = f'[data-role=mk-chip][data-item="{iid}"]'
        tops = pg.eval_on_selector_all(sel, "els => els.map(e => Math.round(e.getBoundingClientRect().top))")
        box = pg.eval_on_selector(f'[data-role=mk-chips]:has({sel})', "e => [e.scrollWidth, e.clientWidth, e.getBoundingClientRect().right]")
        heights = pg.eval_on_selector_all(sel, "els => els.map(e => Math.round(e.getBoundingClientRect().height))")
        # 같은 유형: 목록 머리줄 글자(「수집 목록」·「총 n건」)가 두 줄로 쪼개지지 않는다(main 실측: 정리 후보 52px)
        head = pg.eval_on_selector_all('.ch-card-table .op-card-head > span',
                                       "els => els.map(e => Math.round(e.getBoundingClientRect().height))")
        return tops, box, heights, head
    tops, (sw, cw, right), heights, head = _browser(html, "/seller/collect/history", c, act)
    assert head and max(head) <= 26, head
    assert len(set(tops)) >= 2                                                  # 여섯 칩이 두 줄 이상으로 줄바꿈
    assert sw <= cw and right <= 390                                            # 가로 넘침 0
    assert max(heights) <= 32                                                   # 칩 글자가 세로로 쪼개지지 않는다


@BROWSER
def test_duplicate_confirm_once():
    """이미 등록된 11번가 타일을 체크하면 확인 한 줄 → 「중복 등록」으로 체크 → 다시 체크할 땐 묻지 않는다."""
    iid = _item("m7-dup", [UPLOADED[-2]])
    c = _client("m7-dup")
    path = f"/seller/collect/preview/{iid}"
    html = c.get(path).get_data(as_text=True)

    def act(pg):
        pg.evaluate("() => { const b = document.getElementById('chkElevenst'); b.click(); }")
        first = (pg.evaluate("() => document.getElementById('chkElevenst').checked"),
                 pg.locator('[data-role=dup-confirm]').count())
        pg.evaluate("() => document.querySelector('[data-role=dup-yes]').click()")
        after_yes = pg.evaluate("() => document.getElementById('chkElevenst').checked")
        pg.evaluate("() => { const b = document.getElementById('chkElevenst'); b.click(); b.click(); }")
        again = (pg.evaluate("() => document.getElementById('chkElevenst').checked"), pg.locator('[data-role=dup-confirm]').count())
        return first, after_yes, again
    first, after_yes, again = _browser(html, path, c, act)
    assert first == (False, 1)                                                  # 체크가 바로 안 켜지고 확인 줄
    assert after_yes is True
    assert again == (True, 0)                                                   # 한 번 확인하면 다시 묻지 않는다
