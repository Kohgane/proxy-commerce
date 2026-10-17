"""Y12-C(오너 2026-10-18, 캡처 02:31) — 대시보드 채우기(Wing·퍼센티 식 밀도) + 버그 4 계약.

버그:
1. 「마켓 상태 마지막 조회 기록 없음」 거짓 — 따로 적는 칸(`market_status:last_check`)은 상태 팝업만 적었다(일회성 조회·감시 조회는 빠짐).
   이제 등록 기록 `review.checked_at` 중 가장 늦은 것을 그대로 읽는다.
2. 뱃지 = 계정별 고정 자리 고·우·셰·코(항상 이 순서) · 미등록 계정은 빈 테두리로 자리 유지 ·
   플리츠 「쿠」 = 계정이 안 적힌 옛 쿠팡 기록(10-02, 2계정 전) — W0 무접두 키 = 고가네 → 고 자리.
3. 목록 제목도 `unbrace_title`.
4. 「상품」 밑 「자세히」(계정 안내 한 줄) 삭제.
구성: A 오늘 할 일(줄 + [보기]) · B 마켓별 현황 표 4행 · C 상품 현황 타일 4(누르면 그 필터) · D 최근 동작 10줄 · E 오늘 쓴 것.
주문·매출 타일은 운영 DB에 실주문이 없어 만들지 않는다(빈 약속 타일 금지).
"""
from __future__ import annotations

import json
import re

import pytest

from src.seller_console import collect_history_store as S
from src.seller_console import home_bundles as H
from src.seller_console import listing_status as MS


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    monkeypatch.setattr(MS, "query", lambda *a, **k: pytest.fail("대시보드·목록이 마켓에 물었다"))
    S._in_memory.clear()
    yield
    S._in_memory.clear()


def _client(uid):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=f"{uid}@example.com", user_role="seller")
    return c


# 운영 DB 10-18 실측 모양 — 플리츠: 옛 `coupang`(고가네 16401838524) · 우주대행 · 셰고가 · 고코스모스(조회 기록 없음)
PLEATS = [{"market": "coupang", "market_label": "쿠팡", "product_id": "16401838524", "at": "2026-10-02T09:54:59+00:00",
           "review": {"state": "approved", "checked_at": "2026-10-08T07:26:33+00:00"}},
          {"market": "coupang:woojoo", "market_label": "쿠팡 — 우주대행", "account": "woojoo", "product_id": "16407690349",
           "at": "2026-10-08T07:26:18+00:00",
           "review": {"state": "approved", "status_raw": "승인완료", "checked_at": "2026-10-10T13:57:15+00:00"}},
          {"market": "smartstore:chezgoga", "account": "chezgoga", "product_id": "13742149801", "channel_product_no": "1",
           "at": "2026-10-10T09:09:11+00:00",
           "review": {"state": "approved", "status_raw": "SALE", "checked_at": "2026-10-10T15:33:01+00:00"}},
          {"market": "smartstore:gocosmos", "account": "gocosmos", "product_id": "13742367344", "at": "2026-10-10T12:11:33+00:00"}]
VRSUK = [{"market": "coupang:gogane", "account": "gogane", "product_id": "16415921785", "at": "2026-10-15T15:38:55+00:00",
          "review": {"state": "approved", "status_raw": "승인완료", "checked_at": "2026-10-17T12:55:18+00:00"}},
         {"market": "coupang:woojoo", "account": "woojoo", "product_id": "16415921921", "at": "2026-10-15T15:38:55+00:00",
          "review": {"state": "approved", "status_raw": "승인완료", "checked_at": "2026-10-17T17:10:20+00:00"}}]


def _add(uid, title, uploaded=None, extra=None, url="https://item.taobao.com/item.htm?id=1"):
    ex = {"title_ko": title, "price": "10", "images": ["https://img.alicdn.com/a.jpg"]}
    if uploaded:
        ex["uploaded"] = uploaded
    ex.update(extra or {})
    iid = S.append(source="share", url=url, seller_id=uid, title=title, price="10", currency="CNY", extra=ex)
    for r in S._in_memory:                                       # 수집은 9월(운영 VRSUK) — 최근 동작 맨 위가 「수집」이 되지 않게
        if r.get("id") == iid:
            r["collected_at"] = "2026-09-27T11:05:20+00:00"
    return iid


# ── 버그 1 — 마지막 조회 ─────────────────────────────────────────────────────────────────────────────
def test_last_check_reads_records_not_side_key():
    """반례(실측): 우주대행 17:10 UTC 일회성 조회는 기록에만 남고 옛 칸은 안 적었다 → 「기록 없음」. 이제 기록을 읽는다."""
    uid = "u-y12c-last"
    _add(uid, "VRSUK 리클라이너", VRSUK)
    out = H.build({uid})
    assert out["last_check"] in ("02:10", "10-18 02:10")             # 17:10 UTC = 10-18 02:10 KST
    assert not hasattr(H, "mark_status_checked") and not hasattr(H, "STATUS_KEY")   # 옛 칸 자체를 없앴다
    html = _client(uid).get("/seller/").get_data(as_text=True)
    assert "마켓 상태 마지막 조회 기록 없음" not in html and "02:10" in html


def test_last_check_empty_only_when_no_record():
    html = _client("u-y12c-empty").get("/seller/").get_data(as_text=True)
    assert "마켓 상태 마지막 조회 기록 없음" in html                     # 정말 기록이 없을 때만


# ── 버그 2 — 뱃지 고정 자리 ───────────────────────────────────────────────────────────────────────────
def test_badge_slots_fixed_order_legacy_coupang_is_gogane_and_empty_kept():
    slots = MS.badge_slots({"uploaded": [PLEATS[3], PLEATS[1], PLEATS[0]]})          # 순서를 섞어 넣어도
    assert [s["short"] for s in slots] == ["고", "우", "셰", "코"]
    assert [bool(s.get("empty")) for s in slots] == [False, False, True, False]      # 셰고가 미등록 = 빈 자리
    assert slots[0]["product_id"] == "16401838524" and slots[0]["name"] == "고가네"   # 「쿠」 → 고가네 자리
    both = MS.badge_slots({"uploaded": [PLEATS[0], VRSUK[0]]})
    assert both[0]["product_id"] == "16415921785" and both[0]["dup_count"] == 2      # 같은 자리 2건 = 중복


def test_list_row_badges_render_slots_and_unbraced_title():
    uid = "u-y12c-row"
    iid = _add(uid, "플리츠{미니멀} 여성 세트", [PLEATS[0], PLEATS[1], PLEATS[3]])
    html = _client(uid).get("/seller/collect/history").get_data(as_text=True)
    row = html[html.index(f'data-item-id="{iid}"'):]
    row = row[:row.index("</tr>")]
    assert re.findall(r'<span class="mk-short">([^<]*)</span>', row) == ["고", "우", "", "코"]
    assert 'data-role="mk-slot-empty" data-slot="smartstore:chezgoga"' in row
    assert ">쿠<" not in row
    text = re.sub(r"<[^>]+>", "", row)
    assert "{" not in text and "플리츠 미니멀 여성 세트" in text                     # 버그 3


# ── 버그 4 — 「자세히」 ──────────────────────────────────────────────────────────────────────────────
def test_list_header_has_no_account_details():
    uid = "u-y12c-head"
    _add(uid, "아무 상품")
    html = _client(uid).get("/seller/collect/history").get_data(as_text=True)
    head = html[html.index('class="ch-head"'):]
    head = head[:head.index("</header>")]
    assert "자세히" not in head and 'data-role="ch-account"' not in html


# ── A 오늘 할 일 ────────────────────────────────────────────────────────────────────────────────────
def _erase_extra():
    return {"detail_images_ko": [{"idx": 21, "use": True, "status": "done", "url": "https://x/21.png",
                                  "polish": {"at": "2026-10-16T16:39:43+00:00", "version": "edit:1", "outbound": True, "suggest_erase": 1,
                                             "rows": [{"id": "t0", "tgt": "는", "suggest_erase": True}]}}]}


def test_todo_lines_with_view_link_and_none_when_zero():
    uid = "u-y12c-todo"
    iid = _add(uid, "VRSUK{비즈니스 시리즈} 리클라이너", VRSUK, _erase_extra())
    html = _client(uid).get("/seller/").get_data(as_text=True)
    a = html[html.index('data-role="hb-attention"'):]
    a = a[:a.index("</section>")]
    assert 'data-role="hb-attention-n">1<' in a
    assert "VRSUK 비즈니스 시리즈 리클라이너" in a and "지우기 제안 사진 1장" in a
    assert f'href="/seller/collect/history?open={iid}"' in a and ">보기<" in a
    none = _client("u-y12c-todo0").get("/seller/").get_data(as_text=True)
    assert 'data-role="hb-attention-none">없음' in none


def test_list_page_opens_drawer_from_open_param():
    html = _client("u-y12c-open").get("/seller/collect/history?open=abc").get_data(as_text=True)
    assert "new URLSearchParams(location.search).get('open')" in html and "openItemDrawer(_o" in html


# ── B 마켓별 현황 ───────────────────────────────────────────────────────────────────────────────────
def test_market_table_four_rows_counts_and_ledger(monkeypatch):
    uid = "u-y12c-mk"
    _add(uid, "플리츠", PLEATS, url="https://item.taobao.com/item.htm?id=2")
    _add(uid, "VRSUK", VRSUK, url="https://item.taobao.com/item.htm?id=3")
    rej = dict(VRSUK[1], review={"state": "rejected", "status_raw": "승인반려", "checked_at": "2026-10-16T01:00:00+00:00"})
    _add(uid, "반려 상품", [rej], url="https://item.taobao.com/item.htm?id=4")
    from src.db import market_registrations_pg as L
    monkeypatch.setattr(L, "enabled", lambda: True)
    monkeypatch.setattr(L, "recent_rejected", lambda **k: [])
    monkeypatch.setattr(L, "account_counts", lambda **k: [
        {"account": "gogane", "status": "approved", "held": False, "n": 1, "checked_at": "2026-09-08T09:00:40+00:00"},
        {"account": "gogane", "status": "rejected", "held": True, "n": 1, "checked_at": "2026-08-29T17:03:13+00:00"}])
    m = H._markets(S.dashboard_rows(seller_ids={uid}))
    rows = {r["slot"]: r for r in m["rows"]}
    assert [r["name"] for r in m["rows"]] == ["고가네", "우주대행", "셰고가", "고코스모스"]
    assert (rows["coupang:gogane"]["sale"], rows["coupang:gogane"]["rejected"]) == (3, 0)   # 플리츠 옛 쿠팡 + VRSUK + 대장 andobil · Stagg(임시저장) 안 셈
    assert (rows["coupang:woojoo"]["sale"], rows["coupang:woojoo"]["rejected"]) == (2, 1)
    assert rows["smartstore:gocosmos"]["wait"] == 1 and rows["smartstore:gocosmos"]["last_check"] == ""
    assert rows["coupang:woojoo"]["last_check"] in ("02:10", "10-18 02:10")
    html = _client(uid).get("/seller/").get_data(as_text=True)
    t = html[html.index('data-role="hb-markets"'):]
    assert t.count('data-role="hb-market-row"') == 4 and "판매중" in t and "승인대기" in t and "마지막 조회" in t


# ── C 상품 현황 ─────────────────────────────────────────────────────────────────────────────────────
def test_product_tiles_count_and_link_to_matching_filters():
    uid = "u-y12c-tile"
    _add(uid, "등록 상품", VRSUK, _erase_extra(), url="https://item.taobao.com/item.htm?id=5")
    _add(uid, "미등록 1", url="https://item.taobao.com/item.htm?id=6")
    _add(uid, "미등록 2", url="https://item.taobao.com/item.htm?id=7")
    c = _client(uid)
    html = c.get("/seller/").get_data(as_text=True)
    tiles = {k: (u, int(n)) for k, u, n in re.findall(
        r'data-role="hb-tile-(\w+)" href="([^"]+)">\s*<span class="hb-tile-k">[^<]*</span><b class="hb-tile-v">(\d+)<', html)}
    assert {k: v[1] for k, v in tiles.items()} == {"collected": 3, "registered": 1, "unregistered": 2, "attn": 1}
    for k, (url, n) in tiles.items():                             # 누르면 그 필터 목록 — 건수가 같다
        page = c.get(url.replace("&amp;", "&")).get_data(as_text=True)
        assert page.count('class="ch-row') == n, (k, url)


# ── D 최근 동작 ─────────────────────────────────────────────────────────────────────────────────────
def test_recent_actions_kst_sorted_status_and_grouped_polish():
    uid = "u-y12c-recent"
    ex = {"detail_images_ko": [{"idx": i, "polish": {"at": f"2026-10-15T06:39:{10 + i:02d}+00:00", "version": "edit:1"}}
                               for i in range(3)],
          "coupang_detail_sync": {"coupang:gogane": {"at": "2026-10-17T05:10:21+00:00", "ok": True}}}
    _add(uid, "VRSUK", VRSUK, ex)
    rec = H._recent(S.dashboard_rows(seller_ids={uid}))
    lines = [f"{r['at']} {r['text']}" for r in rec]
    assert lines[0] == "10-18 02:10 우주대행 상태 조회 → 승인완료"
    assert "10-17 21:55 고가네 상태 조회 → 승인완료" in lines
    assert "10-17 14:10 쿠팡 상세 보냄" in lines
    assert "10-15 15:39 다듬기 완료 · 3장" in lines and sum("다듬기" in x for x in lines) == 1   # 장마다가 아니라 한 번에 한 줄
    assert "10-16 00:38 고가네 등록" in lines and len(rec) <= 10
    ats = [r["at"] for r in rec]
    assert ats == sorted(ats, reverse=True)


# ── E 오늘 쓴 것 · 주문 타일 없음 ─────────────────────────────────────────────────────────────────────
def test_today_has_translate_and_polish_caps_and_no_order_tiles():
    html = _client("u-y12c-today").get("/seller/").get_data(as_text=True)
    t = html[html.index('data-role="hb-today"'):]
    t = t[:t.index("</section>")]
    assert "이미지 번역" in t and "다듬기" in t and "/400" in t
    board = html[html.index('data-role="home-bundles"'):]
    board = re.sub(r"<[^>]+>", " ", board[:board.index("</section>", board.index('data-role="hb-today"'))])
    assert "주문" not in board and "매출" not in board                  # 실주문 없음 — 빈 약속 타일 금지


def test_dashboard_one_store_read(monkeypatch):
    """대시보드는 상품을 **한 번** 읽는다(묶음마다 다시 읽지 않는다 — VRSUK 한 행 500KB라 큰 칸은 안 끈다)."""
    calls = []
    real = S.dashboard_rows
    monkeypatch.setattr(S, "dashboard_rows", lambda **k: calls.append(1) or real(**k))
    monkeypatch.setattr(S, "list_items", lambda *a, **k: pytest.fail("대시보드가 목록 전체를 읽었다"))
    H.build({"u-y12c-one"})
    assert len(calls) == 1
