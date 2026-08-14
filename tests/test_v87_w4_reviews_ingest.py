"""tests/test_v87_w4_reviews_ingest.py — v87-W4 리뷰·평점 수신·저장·표시 계약.

## 오너 실기기 결함(재조사 금지)
확장(1.5.145)이 payload_echo reviews_n=10·rating 4.7·review_count 22 **송신 확정**. 서버 레코드는
'부분 수집 — 리뷰·평점 누락(4/5)'. 확장 무죄 — 서버 수신·저장·표시만 본다.

## 근원(1줄)
재수집(force) 덮어쓰기 병합(`extension_api._merged.update(...)`)이 reviews/rating/review_count 키를
**빠뜨려**, 최초수집(리뷰 없음) 행을 리뷰 담긴 새 수집으로 덮어써도 _merged엔 옛 빈 값이 남고 그걸로
collect_status를 재계산 → '리뷰·평점 누락(4/5)' 고정.

## 인위회귀
수신 배선을 '무력화'(옛 병합=리뷰 키 제외)하면 재수집 후에도 4/5·reviews_n=0으로 **누락 재현(red)**,
원복(리뷰 키 포함 병합)하면 5/5·reviews_n=10 **green**. 저장·표시가 실제로 리뷰를 태우는지 못박는다.
"""
from __future__ import annotations

import json

import pytest

from src.collectors.collect_status import compute_collect_status


URL = "https://www.temu.com/kr/g-601104878115983.html"
_BASE = {
    "url": URL, "title": "큐브 스피커", "price": "12730", "currency": "KRW",
    "images": ["https://img/a.jpg", "https://img/b.jpg"],
    "options": [{"name": "색", "values": ["A"]}],
    "description": "이 제품은 원목으로 만든 튼튼한 스피커입니다 좋아요",
}
_REVIEWS = [{"text": "좋아요", "rating": "5"}] * 10


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def _clear():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()


def _extra_of(item_id):
    from src.seller_console import collect_history_store as ch
    row = ch.get(item_id, seller_id="u1")
    ex = row.get("extra") or row.get("extra_json") or {}
    return json.loads(ex) if isinstance(ex, str) else ex


# ── 판정기: 리뷰·평점이 5필드에 반영되는가 ─────────────────────────────
def test_status_counts_reviews_when_present():
    ex = dict(_BASE, images=_BASE["images"], reviews=_REVIEWS, rating="4.7", review_count="22")
    st = compute_collect_status(ex, title_fallback="큐브")
    assert st["status"] == "성공" and st["filled"] == 5 and "리뷰·평점" not in st["missing"]


def test_status_reviews_missing_is_honest():
    ex = dict(_BASE, reviews=[], rating="", review_count="")
    st = compute_collect_status(ex, title_fallback="큐브")
    assert "리뷰·평점" in st["missing"] and st["filled"] == 4   # 조용한 통과 금지 — 정직 누락


# ── E2E: 재수집이 리뷰를 갱신해 5/5 (근원 수리 green) ───────────────────
def test_recollect_merges_reviews_to_full(client):
    _clear()
    # 최초수집(옛 확장 — 리뷰 없음) → 4/5
    r1 = client.post("/api/v1/collect/extension", json=dict(_BASE, reviews=[], rating="", review_count=""))
    ex1 = _extra_of(r1.get_json()["item_id"])
    assert ex1["collect_status"]["filled"] == 4 and "리뷰·평점" in ex1["collect_status"]["missing"]
    # 재수집(1.5.145 — 리뷰 10·평점 4.7·리뷰수 22) force → 5/5 + 실제 저장
    r2 = client.post("/api/v1/collect/extension",
                     json=dict(_BASE, reviews=_REVIEWS, rating="4.7", review_count="22", force=True))
    assert r2.get_json().get("updated") is True
    ex2 = _extra_of(r2.get_json()["item_id"])
    assert ex2["collect_status"]["filled"] == 5 and ex2["collect_status"]["status"] == "성공"
    assert len(ex2["reviews"]) == 10 and ex2["rating"] == "4.7" and ex2["review_count"] == "22"
    assert ex2.get("recollected_at")   # 최근 갱신 시각(참고 칩: 최초/최근 분리)


def test_recollect_is_non_destructive_on_empty(client):
    _clear()
    client.post("/api/v1/collect/extension", json=dict(_BASE, reviews=[], rating="", review_count=""))
    client.post("/api/v1/collect/extension",
                json=dict(_BASE, reviews=_REVIEWS, rating="4.7", review_count="22", force=True))
    # 리뷰가 채워진 뒤, 리뷰 없는 재수집이 와도 기존 리뷰를 지우지 않는다(비파괴).
    r3 = client.post("/api/v1/collect/extension",
                     json=dict(_BASE, reviews=[], rating="", review_count="", force=True))
    ex3 = _extra_of(r3.get_json()["item_id"])
    assert len(ex3["reviews"]) == 10 and ex3["rating"] == "4.7"


def test_fresh_collect_with_reviews_is_full(client):
    _clear()
    r = client.post("/api/v1/collect/extension",
                    json=dict(_BASE, reviews=_REVIEWS, rating="4.7", review_count="22"))
    ex = _extra_of(r.get_json()["item_id"])
    assert ex["collect_status"]["filled"] == 5 and len(ex["reviews"]) == 10


# ── 인위회귀: 수신 배선(리뷰 키 병합) 무력화 → 누락 재현 → 원복 green ──
def test_artificial_regression_merge_wire():
    # 무력화(옛 병합): 리뷰 키를 제외하고 병합하면 옛 빈 값이 남아 4/5(red 재현).
    old_extra = dict(_BASE, reviews=[], rating="", review_count="")   # 최초수집 상태
    merged_old = dict(old_extra)
    merged_old.update({"price": "12730", "images": _BASE["images"], "options": _BASE["options"]})  # 리뷰 키 없음
    st_old = compute_collect_status(merged_old, title_fallback="큐브")
    assert st_old["filled"] == 4 and "리뷰·평점" in st_old["missing"]   # red

    # 원복(현 배선): 리뷰/평점/리뷰수를 병합에 포함 → 5/5(green).
    merged_new = dict(merged_old)
    merged_new.update({"reviews": _REVIEWS, "rating": "4.7", "review_count": "22"})
    st_new = compute_collect_status(merged_new, title_fallback="큐브")
    assert st_new["filled"] == 5 and st_new["status"] == "성공"   # green


# ── 표시: 드로어·목록·PG 프로젝션 ───────────────────────────────────
def test_drawer_template_renders_reviews_and_honest_empty():
    from pathlib import Path
    t = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "리뷰 0건 수신" in t                    # 빈 리뷰 정직 표기(조용한 미렌더 금지)
    assert "리뷰 <strong>{{ _rc }}</strong>건" in t
    assert "평점 <strong>{{ _rating }}</strong>" in t


def test_list_row_exposes_review_count_and_rating():
    from pathlib import Path
    r = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    assert "it.review_count" in r and "it.rating" in r
    v = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert 'it["review_count"]' in v and 'it["rating"]' in v


def test_pg_lean_projection_includes_review_scalars():
    from pathlib import Path
    pg = Path("src/db/collect_history_pg.py").read_text(encoding="utf-8")
    assert "'rating', extra_json->'rating'" in pg
    assert "'review_count', extra_json->'review_count'" in pg
