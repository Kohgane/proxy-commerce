"""Y12-A(오너 2026-10-17) — 화면 정리 계약.

결정(오너 승인):
- 상태 낱말은 마켓 표기 하나: 쿠팡 = 승인대기·승인완료·승인반려(Wing) · 네이버 = 판매중·판매대기. 「검토중」「심사 중」 변주 없음.
- 쿠팡 조회가 막히거나(400 DEFAULT · 일시 차단) 실패하면 **마지막 성공 조회 값 유지** — 승인대기로 바꾸지 않고 조회 시각도 그대로.
  (반례: VRSUK 고가네 승인완료 → 재심사 400 → 승인대기로 보이면 거짓.) 쿠팡이 실제로 「승인대기중」「심사중」을 돌려준 때만 승인대기.
- 목록 한 줄 = 썸네일 · 상품명 · 마켓 뱃지 4 · 마지막 동작 시각. 기본 정렬 = 마지막 동작 최신순 · 필터 하나 「손댈 것만」.
- 모바일 뱃지 = 약자(고·우·셰·코) — 완료 = 채움 · 대기 = 테두리만 · 반려·실패 = 약자 대신 글자(색만으로 구분하지 않는다).
- 대시보드 = 세 묶음(손댈 것 · 돌아가는 것 · 오늘 쓴 것). 0이면 「없음」 / 돌아가는 것은 묶음째 숨김. 진단 패널은 「진단」 메뉴.
- 결과줄 한 문장: 「다듬기 완료 · 24장 · 바뀐 장 N」(N = 마지막 실행에서 새 버전 생긴 장 · 누적 아님).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from src.seller_console import listing_status as MS

APPROVED_AT = "2026-10-16T16:39:18+00:00"


def _rec(state="approved", raw="승인완료", checked=APPROVED_AT, market="coupang:gogane"):
    return {"market": market, "chip": "쿠팡·고가네", "label": "쿠팡 — 고가네", "product_id": "16415921785",
            "channel_product_no": "", "at": "2026-10-15T15:38:55+00:00", "account": "gogane", "external_url": "",
            "review": {"state": state, "label": "승인", "status_raw": raw, "checked_at": checked, "link": ""},
            "price": {}, "sent": {}, "name_fix": {}}


@pytest.fixture(autouse=True)
def _clean():
    MS.reset_cache()
    yield
    MS.reset_cache()


# ── 1. 상태 낱말 · 막힌 조회 ─────────────────────────────────────────────────────────────────────────────
def test_coupang_400_keeps_last_success_and_check_time(monkeypatch):
    """VRSUK 반례: 마지막 성공 = 승인완료 → 재심사 중 조회 400(reviewing) → 승인완료 그대로 · 조회 시각 갱신 안 함."""
    monkeypatch.setattr(MS, "_coupang", lambda rec: {"sid": rec["product_id"], "state": "reviewing", "label": "조회 잠시 막힘",
                                                    "status_raw": "", "comment": "", "link": "", "error": ""})
    row = MS.query(_rec())
    assert row["label"] == "승인완료" and row["state"] == "approved"
    assert row["checked_at"] == APPROVED_AT
    assert row.get("stale") is True and row.get("stale_note")
    # 막힌 조회는 기록을 덮지 않는다
    ex = {"uploaded": [{"market": "coupang:gogane", "product_id": "16415921785", "review": {"state": "approved", "checked_at": APPROVED_AT}}]}
    assert MS.remember(ex, row) is False
    assert ex["uploaded"][0]["review"]["checked_at"] == APPROVED_AT


def test_coupang_error_keeps_last_success(monkeypatch):
    monkeypatch.setattr(MS, "_coupang", lambda rec: (_ for _ in ()).throw(RuntimeError("연결 끊김")))
    row = MS.query(_rec())
    assert row["label"] == "승인완료" and row["checked_at"] == APPROVED_AT and row["stale"]


def test_coupang_real_pending_is_pending(monkeypatch):
    """쿠팡이 실제로 「승인대기중」을 돌려준 경우만 승인대기."""
    monkeypatch.setattr(MS, "_coupang", lambda rec: {"sid": rec["product_id"], "state": "pending", "label": "승인대기중",
                                                    "status_raw": "승인대기중", "comment": "", "link": "", "error": ""})
    row = MS.query(_rec())
    assert row["label"] == "승인대기" and not row.get("stale")
    assert row["checked_at"] != APPROVED_AT


def test_query_many_timeout_keeps_last_value(monkeypatch):
    import time
    monkeypatch.setattr(MS, "_coupang", lambda rec: time.sleep(1.5) or {"state": "pending"})
    rows = MS.query_many([_rec()], timeout=0.2)
    assert rows[0]["label"] == "승인완료" and rows[0]["stale"] and rows[0]["checked_at"] == APPROVED_AT


def test_state_words_one_per_market():
    assert MS.state_word("coupang:gogane", "approved") == "승인완료"
    assert MS.state_word("coupang:woojoo", "pending") == "승인대기"
    assert MS.state_word("coupang", "rejected") == "승인반려"
    assert MS.state_word("smartstore:chezgoga", "approved", "SALE") == "판매중"
    assert MS.state_word("smartstore:gocosmos", "pending") == "판매대기"
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    for bad in ("검토중", "심사 중", "검토상태보기"):
        assert bad not in CU.REVIEW_LABELS.values()
    assert CU.REVIEW_LABELS["approved"] == "승인완료" and CU.REVIEW_LABELS["pending"] == "승인대기"


def test_badge_kind_shape_not_color_only():
    assert MS.badge_kind("approved") == "done"
    assert MS.badge_kind("pending") == "wait" and MS.badge_kind("") == "wait"
    assert MS.badge_kind("rejected") == "bad"
    assert MS.badge_kind("approved", send_fail=True) == "fail"


# ── 2. 마지막 동작 · 손댈 것 ────────────────────────────────────────────────────────────────────────────
def test_last_action_picks_latest_and_kst_line():
    from src.seller_console.attention import last_action
    ex = {"uploaded": [{"market": "coupang:gogane", "at": "2026-10-15T15:38:55+00:00"},
                       {"market": "smartstore:chezgoga", "at": "2026-10-15T19:19:41+00:00",
                        "detail_sync": {"at": "2026-10-17T05:10:17+00:00", "ok": True, "same": False}}],
          "coupang_detail_sync": {"coupang:gogane": {"at": "2026-10-17T05:10:21+00:00", "ok": True}}}
    la = last_action(ex, "2026-09-27T11:05:20+00:00")
    assert la["line"] == "10-17 14:10 쿠팡 상세 보냄"
    assert la["at"].startswith("2026-10-17T05:10:21")


def test_short_when_today_vs_other_day():
    from src.seller_console.attention import short_when
    now = datetime(2026, 10, 17, 6, 0, tzinfo=timezone.utc)
    assert short_when(datetime(2026, 10, 17, 5, 10, tzinfo=timezone.utc), now) == "14:10"
    assert short_when(datetime(2026, 10, 15, 5, 10, tzinfo=timezone.utc), now) == "10-15"


def test_attention_items_three_kinds():
    from src.seller_console.attention import items
    ex = {"uploaded": [{"market": "coupang:gogane", "market_label": "쿠팡 — 고가네", "product_id": "1",
                        "review": {"state": "rejected", "status_raw": "승인반려"}},
                       {"market": "smartstore:chezgoga", "market_label": "스마트스토어 — 셰고가", "product_id": "2",
                        "detail_sync": {"at": "2026-10-17T05:10:17+00:00", "ok": False}}],
          "detail_images_ko": [{"idx": 3, "polish": {"suggest_erase": 4, "at": "x"}}],
          "risk_skip": {"reason": "상표/디자인 Zaha Hadid"}}
    got = items(ex, "제목", fresh=True)
    kinds = [i["kind"] for i in got]
    assert kinds.count("rejected") == 1 and kinds.count("send_fail") == 1 and kinds.count("owner") == 2
    texts = " / ".join(i["text"] for i in got)
    assert "승인반려" in texts and "본문 보내기 실패" in texts and "지우기 제안 사진 1장" in texts and "등록 보류" in texts


def test_update_stamps_columns_and_list_sorts_by_action(monkeypatch):
    from src.seller_console import collect_history_store as S
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    S._in_memory.clear()
    # Y12-B: 가격·사진을 실제로 담은 수집(둘 다 비면 「수집 실패」로 손댈 것이 된다)
    old = S.append(source="share", url="https://item.taobao.com/item.htm?id=1", seller_id="u-y12", title="먼저 수집",
                   price="1", currency="CNY", extra={"title_ko": "먼저 수집", "price": "1", "images": ["https://img.alicdn.com/1.jpg"]})
    new = S.append(source="share", url="https://item.taobao.com/item.htm?id=2", seller_id="u-y12", title="나중 수집",
                   price="1", currency="CNY", extra={"title_ko": "나중 수집", "price": "1", "images": ["https://img.alicdn.com/2.jpg"]})
    # 먼저 수집한 상품에 오늘 쿠팡 반려 — 마지막 동작이 가장 최근 + 손댈 것 1
    ex = {"title_ko": "먼저 수집", "uploaded": [{"market": "coupang:gogane", "market_label": "쿠팡 — 고가네", "product_id": "9",
                                                  "at": "2099-01-01T00:00:00+00:00", "review": {"state": "rejected"}}]}
    assert S.update(old, seller_ids={"u-y12"}, extra_json=json.dumps(ex, ensure_ascii=False))
    rows = S.list_items(days=3650, seller_ids={"u-y12"}, order="action")
    assert [r["id"] for r in rows][:2] == [old, new]
    only = S.list_items(days=3650, seller_ids={"u-y12"}, order="action", attn_only=True)
    assert [r["id"] for r in only] == [old]
    assert S.count_items(days=3650, seller_ids={"u-y12"}, attn_only=True) == 1
    saved = json.loads(S.get(old, seller_ids={"u-y12"})["extra_json"])
    assert "attn" not in saved                                    # 남길 게 없으면 빈 요약을 쓰지 않는다
    S._in_memory.clear()


# ── 3. 결과줄 한 문장 ──────────────────────────────────────────────────────────────────────────────────
def test_changed_last_run_counts_only_last_batch():
    """VRSUK 운영 실측: 10-16 묶음 뒤 10-17 05:00 상세 13번 한 장만 새 버전 → 「바뀐 장 1」."""
    from src.services.image_polish import changed_last_run
    pls = [{"at": "2026-10-16T16:39:%02d+00:00" % i, "version": "edit:1"} for i in range(20)]
    pls.append({"at": "2026-10-17T05:00:35+00:00", "version": "edit:1"})
    pls.append({"at": "2026-10-16T16:40:00+00:00"})                # 버전 없는 장(바뀐 것 없음)
    assert changed_last_run(pls) == 1
    # 실행 기록(started_at)이 있으면 그 뒤만
    assert changed_last_run(pls, {"started_at": "2026-10-16T16:39:10+00:00"}) == 11


def test_ocr_line_one_sentence_kst():
    from src.services import ocr_compare_diag as D
    res = {"at": "2026-10-17T05:00:42+00:00", "count": {"han": 1, "send": 2, "none": 3, "unknown": 0}, "pages": [{}] * 6}
    ln = D.line(res)
    assert ln.startswith("OCR 판정 완료 · 6장 · 다시 번역할 장 3 · 10-17 14:00")
    assert "UTC" not in ln and "+00:00" not in ln


def test_coupang_sync_line_short():
    from src.services import coupang_detail_refresh as CDR
    ex = {"coupang_detail_sync": {"coupang:gogane": {"at": "2026-10-17T05:10:21+00:00", "ok": True, "state": "승인완료"}}}
    ln = CDR.sync_line(ex, "coupang:gogane", "it-none")
    assert ln == "10-17 14:10 쿠팡 상세 보냄"


# ── 4. 화면 ──────────────────────────────────────────────────────────────────────────────────────────
def _client(uid="u-y12a"):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=f"{uid}@example.com", user_role="seller")
    return c


def _seed(uid, uploaded, sync=None):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "VRSUK 비즈니스 시리즈 리클라이너 의자", "images": ["https://img.alicdn.com/a.jpg"], "uploaded": uploaded}
    if sync:
        ex["coupang_detail_sync"] = sync
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=748639898871", seller_id=uid,
                   title=ex["title_ko"], price="6995", currency="CNY", extra=ex)
    for r in S._in_memory:                                       # 수집은 9월 — 마지막 동작은 등록 기록 쪽
        if r.get("id") == iid:
            r["collected_at"] = "2026-09-27T11:05:20+00:00"
    return iid


UP4 = [{"market": "coupang:gogane", "market_label": "쿠팡 — 고가네", "product_id": "16415921785", "account": "gogane",
        "at": "2026-10-15T15:38:55+00:00", "review": {"state": "approved", "status_raw": "승인완료"}},
       {"market": "coupang:woojoo", "market_label": "쿠팡 — 우주대행", "product_id": "16415921921", "account": "woojoo",
        "at": "2026-10-15T15:38:55+00:00", "review": {"state": "pending", "status_raw": "승인대기중"}},
       {"market": "smartstore:chezgoga", "market_label": "스마트스토어 — 셰고가", "product_id": "1", "channel_product_no": "13813465384",
        "at": "2026-10-15T19:19:41+00:00", "review": {"state": "rejected", "status_raw": "PROHIBITION"}},
       {"market": "smartstore:gocosmos", "market_label": "스마트스토어 — 고코스모스", "product_id": "2", "channel_product_no": "13813465493",
        "at": "2026-10-15T19:19:41+00:00", "review": {"state": "approved", "status_raw": "SALE"},
        "detail_sync": {"at": "2026-10-17T05:10:25+00:00", "ok": False}}]


def test_list_row_one_line_badges_and_time(monkeypatch):
    monkeypatch.setattr(MS, "query", lambda *a, **k: pytest.fail("목록 렌더가 마켓에 물었다"))
    uid = "u-y12a-row"
    iid = _seed(uid, UP4)
    html = _client(uid).get("/seller/collect/history").get_data(as_text=True)
    row = html[html.index(f'data-item-id="{iid}"'):]
    row = row[:row.index("</tr>")]
    kinds = re.findall(r'data-role="mk-chip" data-kind="(\w+)"', row)
    assert kinds == ["done", "wait", "bad", "fail"]
    shorts = re.findall(r'<span class="mk-short">([^<]*)</span>', row)
    assert shorts == ["고", "우", "반려", "실패"]                     # 반려·실패는 약자 대신 글자
    fulls = re.findall(r'<span class="mk-full">([^<]*)</span>', row)
    assert fulls == ["고가네 승인완료", "우주대행 승인대기", "셰고가 판매금지", "고코스모스 실패"]
    assert 'data-role="last-action-time"' in row and "10-17 14:10" in row
    # 줄에서 뺀 것: 도메인·가격·수집 시각·ID
    for gone in ("item.taobao.com", "6995", "it-", "수집 시각", "검토중", "심사 중"):
        assert gone not in re.sub(r'data-[\w-]+="[^"]*"|href="[^"]*"', "", row), gone


def test_list_default_sort_action_and_attn_filter(monkeypatch):
    monkeypatch.setattr(MS, "query", lambda *a, **k: pytest.fail("목록 렌더가 마켓에 물었다"))
    uid = "u-y12a-filter"
    calm = _seed(uid, [UP4[0]])
    hot = _seed(uid, UP4)
    c = _client(uid)
    html = c.get("/seller/collect/history").get_data(as_text=True)
    assert 'data-role="attn-filter"' in html and "손댈 것만" in html
    only = c.get("/seller/collect/history?attn=1").get_data(as_text=True)
    assert f'data-item-id="{hot}"' in only and f'data-item-id="{calm}"' not in only


def test_dashboard_three_bundles_empty_and_hidden():
    html = _client("u-y12a-empty").get("/seller/").get_data(as_text=True)
    assert 'data-role="hb-attention-none"' in html and "없음" in html
    assert 'data-role="hb-running"' not in html                    # 돌아가는 것 0 → 묶음째 숨김
    assert 'data-role="hb-today"' in html and "이미지 번역" in html
    assert 'data-role="hb-last-check"' in html
    for gone in ("5분 시작 가이드", "처음이신가요", "ocr-compare", "image-polish", "naver-recent"):
        assert gone not in html, gone
    # 온보딩은 지운 게 아니라 사이드바 「시작 가이드」로 · 진단 패널은 「진단」 메뉴로
    assert 'href="/seller/start"' in html and "시작 가이드" in html
    assert 'href="/seller/diagnostics"' in html


def test_dashboard_attention_counts_product(monkeypatch):
    uid = "u-y12a-attn"
    _seed(uid, UP4)
    html = _client(uid).get("/seller/").get_data(as_text=True)
    assert 'data-role="hb-attention-n">1<' in html
    assert "셰고가 판매금지" in html and "본문 보내기 실패" in html


def test_closed_drawer_sheet_hidden():
    css = open("src/static/app.css", encoding="utf-8").read()
    i = css.index(".kgp-drawer {")
    block = css[i:css.index("}", i)]
    assert "visibility: hidden" in block
    assert ".kgp-drawer.show { transform: translateX(0); visibility: visible;" in css


# ── 5. 오너 23:31 추가 ───────────────────────────────────────────────────────────────────────────────
def test_diagnostics_cards_flow_not_viewport_locked():
    """a. 「진단」은 옛 대시보드 카드를 흐르는 높이로 — `.op-shell`(뷰포트 고정 + main overflow hidden)을 쓰면 본문이 잘린다."""
    t = open("src/seller_console/templates/diagnostics_home.html", encoding="utf-8").read()
    assert "op-shell" not in t and 'class="diag-grid"' in t
    css = open("src/static/app.css", encoding="utf-8").read()
    assert ".diag-grid > .op-card { overflow: visible; }" in css


def test_ledger_rejection_words_never_show_keys_and_saved_comment_is_stale():
    """b. 실측 Fellow Stagg(쿠팡 고가네 16359486080): status=rejected · kind=unknown · 사유 「판매자(…) 임시저장」 ·
    마지막 조회 08-29 17:03 UTC — 09-05 수리 전 판정(사유가 있다 ≠ 반려다). 손댈 것에 안 올리고 화면에 키 0."""
    from src.pipeline.ops_snapshot import _reject_words
    stagg = {"reject_kind": "unknown", "reject_comment": "판매자(A01381223) 임시저장",
             "checked_at": "2026-08-29T17:03:13+00:00"}
    w = _reject_words(stagg)
    assert w == {"phase": "stale", "state_word": "임시저장", "kind_word": "", "checked_kst": "08-30 02:03"}
    live = _reject_words({"reject_kind": "image_spec", "reject_comment": "대표이미지는 최대 10M",
                          "checked_at": "2026-10-17T05:00:00+00:00"})
    assert live["phase"] == "rejected" and live["state_word"] == "승인반려" and live["kind_word"] == "이미지 규격"
    assert _reject_words({"reject_kind": "unknown", "reject_comment": "x"})["kind_word"] == ""   # 키 「unknown」은 안 보인다


def test_home_attention_counts_only_live_ledger_rejections(monkeypatch):
    from src.db import market_registrations_pg as L
    from src.seller_console import home_bundles as H
    monkeypatch.setattr(L, "enabled", lambda: True)
    monkeypatch.setattr(L, "recent_rejected", lambda **k: [
        {"account": "gogane", "title": "Fellow Stagg EKG Pro", "product_id": "16359486080", "reject_kind": "unknown",
         "reject_comment": "판매자(A01381223) 임시저장", "checked_at": "2026-08-29T17:03:13+00:00"},
        {"account": "woojoo", "title": "살아 있는 반려", "product_id": "1", "reject_kind": "image_spec",
         "reject_comment": "대표이미지 규격", "checked_at": "2026-10-17T05:00:00+00:00"}])
    a = H._attention({"u-y12a-ledger"})
    assert a["n"] == 1 and [g["label"] for g in a["groups"]] == ["쿠팡 — 우주대행 승인반려"]
    assert "Stagg" not in json.dumps(a, ensure_ascii=False) and "unknown" not in json.dumps(a, ensure_ascii=False)


def test_oneshot_review_status_reads_once_and_keeps_success_only(monkeypatch):
    """Y11W-1: 한 상품·한 마켓 상태 1회 조회(쿠팡 GET) → 성공 값만 기록 · 막힌 조회는 덮지 않음."""
    from src.services import oneshot_ops as O
    uid = "u-y12a-op"
    iid = _seed(uid, UP4)
    monkeypatch.setattr(MS, "_coupang", lambda rec: {"sid": rec["product_id"], "state": "approved", "label": "승인완료",
                                                    "status_raw": "승인완료", "comment": "", "link": "", "error": ""})
    res = O._run({"op": "review_status", "item_id": iid, "market": "coupang:woojoo"})
    assert res["ok"] and res["label"] == "승인완료" and res["saved"] and not res["stale"]
    from src.seller_console import collect_history_store as S
    ex = json.loads(S.get(iid, seller_ids={uid})["extra_json"])
    woo = next(u for u in ex["uploaded"] if u["market"] == "coupang:woojoo")
    assert woo["review"]["state"] == "approved" and woo["review"]["checked_at"]
    monkeypatch.setattr(MS, "_coupang", lambda rec: {"sid": rec["product_id"], "state": "reviewing", "label": "조회 잠시 막힘",
                                                    "status_raw": "", "comment": "", "link": "", "error": ""})
    before = woo["review"]["checked_at"]
    res2 = O._run({"op": "review_status", "item_id": iid, "market": "coupang:woojoo"})
    assert res2["stale"] and res2["label"] == "승인완료" and not res2["saved"]
    ex2 = json.loads(S.get(iid, seller_ids={uid})["extra_json"])
    assert next(u for u in ex2["uploaded"] if u["market"] == "coupang:woojoo")["review"]["checked_at"] == before


# ── 6. 오너 추가 2(d·e·f) ───────────────────────────────────────────────────────────────────────────
def test_rejected_rows_stay_in_watch_queue_but_saved_comment_rows_wait_for_owner(monkeypatch):
    """e: 반려 판정이 재조회를 끊지 않는다(다른 상태와 같은 주기). f: 사유가 「임시저장」인 반려 줄(Stagg)은 오너 승인 전엔 큐 밖."""
    from src.db import market_registrations_pg as L
    monkeypatch.setattr(L, "enabled", lambda: False)
    L._MEM.clear()
    for pid, st, cmt in (("R1", "rejected", "대표이미지는 최대 10M"), ("S1", "rejected", "판매자(A01381223) 임시저장"),
                         ("W1", "submitted", ""), ("A1", "approved", "")):
        L.record(pid, account="gogane", title=pid)
        L.mark_checked(pid, status=st, reject_comment=cmt)
    sids = {r["sid"] for r in L.watch_queue(limit=50)}
    assert sids == {"R1", "W1"}
    assert "rejected" in L._WATCH_STATUSES and "임시" in L._HELD_SQL and "COALESCE(reject_comment" in L._HELD_SQL
    L._MEM.clear()


def test_attention_rejections_never_hidden_and_stale_check_is_marked():
    """e 반례: 진짜 반려인데 사흘 전 조회 → 손댈 것에서 사라지면 안 된다. 숨기지 않고 「조회 낡음」."""
    from datetime import timedelta
    from src.seller_console.attention import check_note, items
    now = datetime(2026, 10, 17, 14, 0, tzinfo=timezone.utc)
    assert check_note("2026-10-17T05:10:00+00:00", now) == "마지막 조회 10-17 14:10"
    assert check_note((now - timedelta(days=3)).isoformat(), now) == "마지막 조회 10-14 23:00 · 조회 낡음"
    assert check_note("", now) == "조회 기록 없음 · 조회 낡음"
    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    ex = {"uploaded": [{"market": "coupang:gogane", "market_label": "쿠팡 — 고가네", "product_id": "1",
                        "review": {"state": "rejected", "status_raw": "승인반려", "checked_at": old}}]}
    got = items(ex, "t")
    assert got and got[0]["kind"] == "rejected" and got[0]["note"].endswith("조회 낡음")


def test_ledger_rejection_three_days_old_still_in_attention_with_marker(monkeypatch):
    from datetime import timedelta
    from src.db import market_registrations_pg as L
    from src.seller_console import home_bundles as H
    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    monkeypatch.setattr(L, "enabled", lambda: True)
    monkeypatch.setattr(L, "recent_rejected", lambda **k: [
        {"account": "gogane", "title": "사흘 전 반려", "product_id": "9", "reject_kind": "image_spec",
         "reject_comment": "대표이미지 규격", "checked_at": old}])
    a = H._attention({"u-y12a-ledger3"})
    assert a["n"] == 1 and a["products"][0]["lines"][0].endswith("조회 낡음")
    assert "쿠팡 — 고가네 승인반려 · 이미지 규격 · 마지막 조회" in a["products"][0]["lines"][0]


def test_no_floating_beginners_button_anywhere_sidebar_only():
    """d: 떠 있는 「처음이신가요?」는 모든 페이지에서 뺐다 — 사이드바 「시작 가이드」 한 곳."""
    for path in ("/seller/", "/seller/collect/history", "/seller/orders", "/seller/diagnostics", "/seller/markets"):
        html = _client("u-y12a-fb").get(path).get_data(as_text=True)
        assert 'id="fbWrap"' not in html and 'id="fbReopen"' not in html, path
        assert 'data-role="nav-start-guide"' in html, path
