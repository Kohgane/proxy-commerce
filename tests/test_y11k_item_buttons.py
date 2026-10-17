"""Y11-K(오너 2026-10-14) — 오너가 상품 ID를 알 길이 없다.

실측 21:30: 어드민 image-polish에 「4ebaf1b8」(앞 8자) → 「상품을 찾지 못했어요」 · ocr-compare는 그 위에 「시작했어요 — 30초쯤 뒤
새로고침하세요」가 **먼저** 찍혔다(못 찾는 일이 백그라운드 안에서 났다 — 순서 버그).
본 해결 = 드로어 「쿠팡 노출」 탭 안 「OCR 다시 판정(이 상품)」「번역 다듬기(이 상품)」(폰 한 탭, 결과는 같은 탭 결과줄).
"""
from __future__ import annotations

import json

import pytest

SID = "y11k"
EMAIL = "owner-y11k@example.com"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    monkeypatch.setenv("FAMILY_EMAILS", EMAIL)
    yield
    q.reset_for_tests()


def _item(title="VRSUK 리클라이너 오일 왁스 가죽", url="https://detail.tmall.com/item.htm?id=913382613725", extra=None):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": title, "images": ["https://img/g0.jpg", "https://img/g1.jpg"],
          "detail_images": [f"https://img/d{i}.jpg" for i in range(8)],
          "detail_images_ko": [{"idx": i, "status": "skipped", "use": True, "vendor": "tencent-ocr",
                                "reason": "중국어 글자 없음(OCR 판정 — 한자 0) — 원본 그대로"} for i in (2, 5, 6)]}
    ex.update(extra or {})
    iid = S.append(source="extension", url=url, seller_id=SID, title=title, price="1299", currency="CNY", extra=ex)
    return iid[0] if isinstance(iid, tuple) else iid


def _client(shared=True):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = SID
        s["user_email"] = EMAIL if shared else "someone@example.com"
    return c


# ── 2. 어드민 입력칸: ID(앞 8자도)·SKU·상품명 일부·수집 URL 아무거나 → 후보 ───────────────────────────────

def test_resolve_accepts_prefix_sku_name_url():
    from src.services import ocr_compare_diag as D
    iid = _item()
    for q in (iid, iid[:8], "913382613725", "리클라이너", "detail.tmall.com/item.htm?id=913382613725"):
        got = D.resolve(q)
        assert [c["id"] for c in got] == [iid], q
    c = D.resolve(iid[:8])[0]
    assert c["sku"] == "913382613725" and c["title"].startswith("VRSUK") and c["collected_at"]
    assert D.resolve("없는상품명xyz") == [] and D.resolve("a") == []
    assert D.resolve(iid[:4]) == []                                         # 너무 짧은 ID 조각은 ID로 안 찾는다


def test_start_does_not_say_started_when_item_missing(monkeypatch):
    """순서 버그: 못 찾으면 시작 메시지 없이 실패만 — 백그라운드도 안 띄운다."""
    from src.services import ocr_compare_diag as D
    runs = []
    monkeypatch.setattr(D, "run", lambda *a, **k: runs.append(a) or {})
    r = D.start("4ebaf1b8")
    assert r == {"ok": False, "why": "상품을 찾지 못했어요"} and not runs
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "admin"; s["user_role"] = "admin"
    html = c.post("/admin/diagnostics/ocr-compare", data={"item": "4ebaf1b8"}).get_data(as_text=True)
    assert "상품을 찾지 못했어요" in html and "시작했어요" not in html


def test_admin_pages_list_candidates_then_run(monkeypatch):
    from src.services import image_polish as IP
    from src.services import ocr_compare_diag as D
    iid = _item()
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "admin"; s["user_role"] = "admin"
    for path in ("/admin/diagnostics/ocr-compare", "/admin/diagnostics/image-polish"):
        html = c.get(path + "?q=" + iid[:8]).get_data(as_text=True)
        assert 'data-role="item-cands"' in html and iid in html and "913382613725" in html
        assert "맞는 상품이 없어요" in c.get(path + "?q=없는상품").get_data(as_text=True)
    started = []
    monkeypatch.setattr(D, "run", lambda item, idx=None: started.append((item, idx)) or {"item": item, "pages": [], "count": {}})
    html = c.post("/admin/diagnostics/ocr-compare", data={"item": iid}).get_data(as_text=True)
    assert "시작했어요" in html
    import time
    for _ in range(50):
        if started:
            break
        time.sleep(0.02)
    assert started == [(iid, None)]                                         # 상세 번호 비우면 이 상품 「한자 0」 장 전부
    assert "다듬을 번역본이 없어요" in c.post("/admin/diagnostics/image-polish", data={"item": iid}).get_data(as_text=True)


# ── 1. 드로어 「쿠팡 노출」 탭 안 두 버튼 — 결과는 같은 탭 결과줄 ───────────────────────────────────────

def test_item_ocr_recheck_runs_all_han0_pages_and_line(monkeypatch):
    from src.services import ocr_compare_diag as D
    iid = _item()
    calls = []

    def _measure(data):
        calls.append(1)
        n = len(calls)
        han = 12 if n == 1 else 0
        latin = 0 if n == 3 else 30
        return [{"name": nm, "ok": True, "han": han if nm == "원본·zh" else 0, "latin": latin, "text": "x"}
                for nm in ("1024·auto", "원본·auto", "1600·zh", "원본·zh")]
    from src.services import detail_image_plan as dip
    from src.services import image_translate_tencent as tc
    monkeypatch.setattr(tc, "fetch_image", lambda u: (b"raw", ""))
    monkeypatch.setattr(dip, "prepare_for_tencent", lambda raw: (b"jpg", {"w": 790, "h": 5000}))
    monkeypatch.setattr(D, "measure_page", _measure)
    monkeypatch.setattr(D, "explain_boxes", lambda raw, exempt=False: {"ok": True, "boxes": []})
    res = D.run(iid)
    assert [(p["kind"], p["no"], p["verdict"]) for p in res["pages"]] == [("detail", 3, "han"), ("detail", 6, "send"), ("detail", 7, "none")]
    # Y12-A: 결과줄 한 문장(다시 번역할 장 = 한자 + 라틴) · 판정별 수는 접힘(detail)
    assert D.line(res) == "OCR 판정 완료 · 3장 · 다시 번역할 장 2 · " + D.run_at(res).replace(" KST", "")
    assert D.detail(res) == ("OCR 다시 판정 3장: 한자 나옴 1 · 라틴 있어 번역으로 1 · 글자 거의 없음 1"
                             " — 「다시 번역」을 누르면 접수돼요 · " + D.run_at(res))       # Y11X: 끝 = 잰 시각(KST)
    assert D.line({"running": True}) == "OCR 판정 중… (1~2분)"


def test_drawer_buttons_shared_only_and_result_line(monkeypatch):
    from src.services import ocr_compare_diag as D
    iid = _item()
    assert _client(shared=False).post(f"/seller/collect/{iid}/ocr-recheck", json={}).status_code == 403
    c = _client()
    monkeypatch.setattr(D, "run", lambda item, idx=None: {"item": item, "pages": [{"verdict": "han"}], "count": {"han": 1}})
    d = c.post(f"/seller/collect/{iid}/ocr-recheck", json={}).get_json()
    assert d["ok"] and d["running"] and d["line"] == "OCR 판정 중… (1~2분)"
    import time
    for _ in range(50):
        g = c.get(f"/seller/collect/{iid}/ocr-recheck").get_json()
        if not g["running"]:
            break
        time.sleep(0.02)
    assert g["line"].startswith("OCR 판정 완료 · 1장 · 다시 번역할 장 1") and g["detail"].startswith("OCR 다시 판정 1장: 한자 나옴 1")
    p = c.post(f"/seller/collect/{iid}/image-polish", json={}).get_json()
    assert p["ok"] and not p["running"] and p["line"] == "다듬기 · 다듬을 번역본이 없어요" and p["detail"]


def test_exposure_payload_says_buttons_on_for_shared():
    iid = _item()
    assert _client().get(f"/seller/collect/{iid}/coupang-exposure").get_json()["diag_ok"] is True
    assert _client(shared=False).get(f"/seller/collect/{iid}/coupang-exposure").get_json()["diag_ok"] is False


def test_polish_line_counts(monkeypatch):
    from src.services import image_polish as IP
    ex = {"detail_images_ko": [{"idx": 12, "polish": {"changed": 2, "calls": 1, "rows": [{"why": ""}, {"why": "금지어·과장(1위)"}]}},
                               {"idx": 16, "polish": {"changed": 1, "calls": 1, "rows": []}}]}
    assert IP.item_detail("x", ex) == "번역 다듬기 2장: 바뀐 상자 3 · AI 2회 · AI 결과 버림 1(금지어·과장 1)"   # Y11-M: 사유별(접힘)
    assert IP.item_line("x", ex) == "다듬기 완료 · 2장 · 바뀐 장 0"                                  # Y12-A: 한 문장(버전 없음 = 0)


# ── 3. 드로어 상단 SKU 옆 전체 ID + 복사 · 목록 ID 열(접기) ──────────────────────────────────────────

def test_drawer_shows_full_id_and_sku_and_list_has_id_column():
    iid = _item()
    c = _client()
    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert 'data-role="item-id-line"' in html and f'<code data-role="item-id">{iid}</code>' in html
    assert '<strong data-role="item-sku">913382613725</strong>' in html and 'data-role="item-id-copy"' in html
    lst = c.get("/seller/collect/history").get_data(as_text=True)
    # Y12-A(오너 결정): 상품 ID는 목록 줄에서 빼고 드로어로 — 드로어는 「자세히」 안에 전체 ID + 복사
    assert 'data-role="row-id"' not in lst and f'data-item-id="{iid}"' in lst
    assert 'data-role="item-id-more"' in html and html.index('data-role="item-id-more"') < html.index('data-role="item-id-line"')
