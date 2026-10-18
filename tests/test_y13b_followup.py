"""Y13-A 추가(오너 2026-10-18 16:37·16:41) — 9. 옛 4013 공유 초안 이월 재투입 · 7. 판촉 상자 · 8. 브랜드 로고 · 10. 세/셰."""
from __future__ import annotations

import json

import pytest

from src.seller_console import collect_history_store as S


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    S._in_memory.clear()
    from src.db import image_translate_queue_pg as st
    st._MEM_STATE.pop("onebound:carry", None)
    yield
    S._in_memory.clear()
    st._MEM_STATE.pop("onebound:carry", None)


def _share(uid, reason, n):
    return S.append(source="share", url=f"https://item.taobao.com/item.htm?id={n}", seller_id=uid, title="", price="",
                    currency="CNY", extra={"mode": "share", "enrich_state": "pending", "share_raw": f"https://e.tb.cn/h.x{n}",
                                           "auto_enrich": {"state": "manual", "kind": "provider_fail", "reason": reason,
                                                           "route": "onebound", "at": "2026-10-07T03:00:00+00:00"}})


# ── 9. 옛 4013 → provider_quota + 이월 대기 ─────────────────────────────────────────────────────────
def test_carry_requeue_tags_quota_and_queues(monkeypatch):
    from src.services import oneshot_ops as OO
    from src.services import onebound_carry as C
    monkeypatch.setattr(C, "_pg_on", lambda: False)
    a = _share("u-36", "온바운드 4013: Key[t_x]已超量", 998336500042)
    b = _share("u-36", "온바운드 5000: data error", 956991758741)
    done = S.append(source="share", url="https://item.taobao.com/item.htm?id=1", seller_id="u-36", title="x", price="1",
                    currency="CNY", extra={"enrich_state": "done"})
    out = OO._run({"op": "carry_requeue", "item_ids": [a, b, done]})
    assert out["queued"] == 2 and out["waiting"] == 2
    ex_a = json.loads(S.get(a, seller_ids={"u-36"})["extra_json"])
    ex_b = json.loads(S.get(b, seller_ids={"u-36"})["extra_json"])
    assert ex_a["auto_enrich"]["kind"] == "provider_quota" and ex_a["carry_requeued_at"]
    assert ex_b["auto_enrich"]["kind"] == "provider_fail"                    # 5000은 사유 그대로(한 번 더 부를 뿐)
    assert ex_a["share_raw"] == "https://e.tb.cn/h.x998336500042"           # 수집 원본 칸 그대로
    assert [r["item_id"] for r in C.items()] == [a, b]
    assert out["rows"][2]["why"].startswith("보강 대기 아님")
    assert OO._run({"op": "carry_requeue", "item_ids": [a]})["waiting"] == 2   # 두 번 넣어도 한 줄


# ── 7. 판촉 상자 = 지우기 제안 · 번역 안 함 · 사전 추가 · 나가기 전 경고 ───────────────────────────────────────
def test_promo_dictionary_has_owner_words():
    from src.collectors.ko_polish import promo_hits
    for w in ("무이자 할부", "차액 환불", "선물 증정", "운임 보험", "초강력 할인", "包邮", "分期免息", "买贵退差", "赠品", "运费险"):
        assert promo_hits(f"오늘 {w} 이벤트"), w


def test_promo_box_not_translated_and_suggested():
    from src.services.image_polish import guard_row
    r = {"id": "t3", "src": "分期免息 买贵退差", "tgt": "무이자 할부 차액 환불", "ko": "무이자 할부·차액 환불", "from": "polish"}
    got = guard_row(r, [], False, True)
    assert got == {"suggest": True, "op": {"id": "t3", "action": "restore"}}
    assert r["ko"] == "分期免息 买贵退差" and r["from"] == "restore" and r["suggest_erase"] and "판촉" in r["why"]
    r2 = {"id": "t4", "src": "运费险", "tgt": "운임 보험", "ko": "배송 보험"}
    got2 = guard_row(r2, [], False, False)                                  # 되살릴 수 없으면 텐센트 글자 + 제안만
    assert got2 == {"suggest": True} and r2["ko"] == "운임 보험" and r2["from"] == "tencent"
    assert guard_row({"id": "t5", "src": "实木", "tgt": "원목", "ko": "원목"}, [], False, True) is None


def test_promo_left_caution_before_outbound():
    from src.services.image_polish import promo_left_caution
    ex = {"detail_images_ko": [
        {"idx": 0, "status": "done", "url": "u0", "target_text": "무이자 할부\n원목 소파"},
        {"idx": 1, "status": "done", "url": "u1", "target_text": "선물 증정", "erase_skip": {"texts": ["선물 증정"]}},
        {"idx": 2, "status": "done", "url": "u2", "polish": {"rows": [{"ko": "初", "from": "restore"}, {"ko": "차액 환불", "from": "polish"}]}},
        {"idx": 3, "status": "failed", "target_text": "초강력 할인"}]}
    msg = promo_left_caution(ex)
    assert msg.startswith("나가기 전 경고: 번역본 2장에 판촉 글자") and "무이자" in msg and "차액" in msg
    assert promo_left_caution({"detail_images_ko": [{"status": "done", "url": "u", "target_text": "원목"}]}) == ""


# ── 8. 브랜드 로고 — 음차 금지 · 원문 유지 · 대표 사진이면 지우기 제안 ────────────────────────────────────────
FISH = {"brand": "", "title": "菲尚丽家单人沙发椅设计师客厅阳台休闲懒人沙发可睡可躺舒适单椅"}


def test_logo_names_from_title_prefix_confirmed_by_pinyin():
    from src.services.image_edit import logo_names
    assert logo_names(FISH, ["菲尚丽家", "FEISHANGLIJIA", "舒适单椅"]) == ["菲尚丽家", "FEISHANGLIJIA"]
    assert logo_names(FISH, ["舒适单椅"]) == []                              # 병음이 사진에 없으면 브랜드로 단정하지 않는다


def test_logo_box_restored_not_transliterated():
    from src.services.image_polish import guard_row
    logos = ["菲尚丽家", "FEISHANGLIJIA"]
    r = {"id": "t0", "src": "菲尚丽家", "tgt": "피샹리가", "ko": "피샹리가", "from": "polish"}
    got = guard_row(r, logos, False, True)
    assert got == {"suggest": False, "op": {"id": "t0", "action": "restore"}} and r["ko"] == "菲尚丽家"
    assert r["brand_logo"] and "음차 안 함" in r["why"] and not r.get("suggest_erase")
    rep = {"id": "t1", "src": "FEISHANGLIJIA", "tgt": "페이샹리자", "ko": "페이샹리자"}
    got = guard_row(rep, logos, True, True)
    assert got["suggest"] and rep["suggest_erase"] and "대표 사진" in rep["why"]


# ── 10. 「세/셰」 — 플리츠 실데이터 390px 목록 한 줄 ───────────────────────────────────────────────────────────
from tests._pw import chromium_hits, launch_opts  # noqa: E402

PLEATS = "플리츠 미니멀 여성 여름 세트, 디자인 감각이 돋보이는 언밸런스 컷팅 주름 스커트 + 반팔 상의"


@pytest.mark.skipif(not chromium_hits(), reason="Playwright/chromium 미설치")
def test_pleats_row_390_badge_is_she_and_title_cut_is_not_se():
    """운영 ae9cee70 모양(제목 「…여름 세트」 · 고·우·셰·코 4계정 등록). 390px에서 제목 말줄임이 「세」로 끊겨 뱃지 옆에 붙는지 ·
    뱃지 약자가 「셰」인지. 실측: 말줄임은 「플리츠 미니…」(세 아님) · 약자 셰 — 글자 잘림 아님(닫음)."""
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    up = [{"market": "coupang", "product_id": "16401838524", "at": "2026-10-02T03:00:00+00:00", "review": {"state": "approved"}},
          {"market": "coupang:woojoo", "account": "woojoo", "product_id": "1", "at": "2026-10-09T03:00:00+00:00",
           "review": {"state": "approved"}},
          {"market": "smartstore:chezgoga", "account": "chezgoga", "product_id": "2", "channel_product_no": "3",
           "at": "2026-10-10T12:00:00+00:00", "review": {"state": "approved"}},
          {"market": "smartstore:gocosmos", "account": "gocosmos", "product_id": "13742367344", "channel_product_no": "13803531537",
           "at": "2026-10-10T12:11:33+00:00"}]
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=1", seller_id="u-pl", title=PLEATS, price="129",
                   currency="CNY", extra={"title_ko": PLEATS, "uploaded": up, "price": "129"})
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="u-pl", user_email="u-pl@example.com", user_role="seller")
    html = c.get("/seller/collect/history?days=3650").get_data(as_text=True)
    css = Path("src/static/app.css").read_text(encoding="utf-8")
    html = html.replace("</head>", f"<style>{css}</style></head>", 1)
    with sync_playwright() as pw:
        b = pw.chromium.launch(**launch_opts())
        pg = b.new_page(viewport={"width": 390, "height": 800})
        pg.set_content(html, wait_until="domcontentloaded")
        got = pg.evaluate("""(id) => {
          const tr = document.querySelector(`tr[data-item-id='${id}']`);
          const a = tr.querySelector('.ch-title-1'), t = a.firstChild, cell = a.closest('td').getBoundingClientRect();
          const rg = document.createRange(); let last = -1;
          for (let i = 0; i < t.length; i++) { rg.setStart(t, i); rg.setEnd(t, i + 1); const r = rg.getBoundingClientRect();
            if (r.width > 0 && r.right <= cell.right - 12) last = i; }
          return {tail: t.data.slice(0, last + 1),
                  shorts: [...tr.querySelectorAll('.mk-badge .mk-short')].filter(s => getComputedStyle(s).display !== 'none').map(s => s.textContent)};
        }""", iid)
        b.close()
    assert got["shorts"] == ["고", "우", "셰", "코"]
    assert not got["tail"].rstrip().endswith("세"), got
