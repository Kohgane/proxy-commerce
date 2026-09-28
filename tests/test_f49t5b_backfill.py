"""F49-T 5부-b — 기존 34건 백필 + 감사 화면(오너 실측 2026-09-28).

오너 계정 image-audit(30일): A 34 · B 0 · C 0 · D 14. A는 전부 `attempts 0 · enrich_state "" · mode simple` —
5부 수리(목록 타일=보강 대기) **전에** 담긴 행이라 보강 큐에 한 번도 오르지 않았다. 5부는 앞으로 담는 행만 고쳤다.

이 파일이 못박는 것:
  ① 옛 A 행(보강 축 없음)은 대기열에 없다 — 원인 재현
  ② 「상세 보강 다시 실행」 → A·C만 보강 대기로(최대 N건, B·D는 그대로), 저장된 행만 셈
  ③ 되돌린 C 행은 옛 1장이 있어도 대기로 남는다(`enrich_rerun`) — 곧장 완료로 돌아가면 큐가 못 집는다
  ④ 확장 페이로드(갤러리·상세) → D, 「다시」 표시가 내려가고 진행률이 서버에서 셈
  ⑤ 화면: 요약 4칸 + 표(제목·소스·이미지 수·상태·사유) + 버튼, JSON은 `?format=json`
"""
from __future__ import annotations

import json

URL = "https://item.taobao.com/item.htm?id={}"


def _client(monkeypatch, seller):
    import src.api.extension_api as ext
    from src.order_webhook import app
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": seller})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def _old_a_row(seller, gid):
    """5부 이전에 목록 카드로 담긴 행 — 오너 실측 모양 그대로(보강 축 없음 · 시도 0 · simple)."""
    from src.seller_console import collect_history_store as S
    iid = S.append(source="extension", seller_id=seller, url=URL.format(gid), title=f"随行盾 {gid}",
                   price="29.9", currency="CNY", image="https://img.alicdn.com/list.jpg",
                   extra={"mode": "simple", "images": ["https://img.alicdn.com/list.jpg"], "price": "29.9"})
    return iid[0] if isinstance(iid, tuple) else iid


def _extra(iid, seller):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_id=seller)["extra_json"])


def _pending_ids(c):
    return {p["item_id"] for p in c.get("/api/v1/collect/enrich/pending").get_json()["items"]}


def test_old_a_rows_are_not_in_queue_before_backfill(monkeypatch):
    seller = "u-5b-cause"
    c = _client(monkeypatch, seller)
    ids = [_old_a_row(seller, 610000000000 + i) for i in range(3)]
    assert not (set(ids) & _pending_ids(c))                              # 원인: 큐에 한 번도 안 오른다
    got = c.get("/seller/collect/image-audit?format=json").get_json()
    a = {r["item_id"]: r for r in got["samples"]["A"]}
    assert set(ids) <= set(a)
    assert all(a[i]["attempts"] == 0 and a[i]["enrich_state"] == "" and a[i]["mode"] == "simple" for i in ids)


def test_backfill_three_a_rows_to_d(monkeypatch):
    """회귀(브리프 3): A 3건 → 버튼 → 보강 대기 → 확장 페이로드 → D."""
    seller = "u-5b-a2d"
    c = _client(monkeypatch, seller)
    ids = [_old_a_row(seller, 620000000000 + i) for i in range(3)]

    r = c.post("/seller/collect/image-audit/requeue", json={"cases": ["A", "C"]})
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and set(d["requeued"]) == set(ids) and d["left"] == 0
    for i in ids:
        ex = _extra(i, seller)
        assert ex["enrich_state"] == "pending" and ex["enrich_rerun"] is True and ex["enrich_attempts"] == 0
    assert set(ids) <= _pending_ids(c)                                   # 확장 폴러가 집는 자리

    got = c.get("/seller/collect/image-audit?format=json").get_json()
    assert got["requeued"]["total"] == 3 and got["requeued"]["waiting"] == 3

    for n, i in enumerate(ids):                                          # 확장이 상세를 열어 보낸 값
        e = c.post("/api/v1/collect/enrich", json={
            "item_id": i, "gallery": [f"https://img.alicdn.com/g{n}_{k}.jpg" for k in range(3)],
            "detail_images": [f"https://img.alicdn.com/d{n}.jpg"], "gallery_expected": 3,
            "field_sources": {"images": "ice_context"}}).get_json()
        assert e["ok"], e
    got = c.get("/seller/collect/image-audit?format=json").get_json()
    d_ids = {x["item_id"] for x in got["samples"]["D"]}
    assert set(ids) <= d_ids and not ({x["item_id"] for x in got["samples"]["A"]} & set(ids))
    assert got["requeued"] == {**got["requeued"], "total": 3, "D": 3, "waiting": 0, "still_short": 0}
    for i in ids:
        ex = _extra(i, seller)
        assert "enrich_rerun" not in ex and ex["enrich_rerun_done_at"]
        assert ex["enrich_state"] == "done" and ex["image_check"]["ok"] is True
    assert not (set(ids) & _pending_ids(c))                              # 끝난 건 큐에서 빠진다


def test_c_row_stays_pending_despite_old_thumbnail(monkeypatch):
    from src.collectors.collect_status import enrich_axes
    seller = "u-5b-c"
    c = _client(monkeypatch, seller)
    iid = _old_a_row(seller, 630000000001)
    c.post("/api/v1/collect/enrich", json={"item_id": iid, "detail_images": ["https://img.alicdn.com/d.jpg"]})
    assert enrich_axes(_extra(iid, seller))["enrich_state"] == "done"    # C: 보강은 돌았는데 1장
    c.post("/seller/collect/image-audit/requeue", json={})
    ex = _extra(iid, seller)
    assert enrich_axes(ex)["enrich_state"] == "pending" and iid in _pending_ids(c)
    # 다시 돌았는데도 1장이면 「여전히 부족」으로 센다(가짜 완료 금지).
    c.post("/api/v1/collect/enrich", json={"item_id": iid, "gallery": ["https://img.alicdn.com/list.jpg"]})
    got = c.get("/seller/collect/image-audit?format=json").get_json()
    assert iid in {x["item_id"] for x in got["samples"]["C"]} and got["requeued"]["still_short"] == 1


def test_requeue_limit_and_leaves_b_d_alone(monkeypatch):
    seller = "u-5b-limit"
    c = _client(monkeypatch, seller)
    a = [_old_a_row(seller, 640000000000 + i) for i in range(5)]
    b = _old_a_row(seller, 640000000100)
    for _ in range(3):
        c.post("/api/v1/collect/enrich/blocked", json={"item_id": b, "reason": "로그인 벽"})
    d = c.post("/seller/collect/image-audit/requeue", json={"limit": 2}).get_json()
    assert len(d["requeued"]) == 2 and d["left"] == 3 and b not in d["requeued"]
    assert _extra(b, seller)["enrich_state"] == "blocked"                # B는 같은 벽 — 되돌리지 않는다
    d2 = c.post("/seller/collect/image-audit/requeue", json={"limit": 20}).get_json()
    assert set(d["requeued"]) | set(d2["requeued"]) == set(a) and d2["left"] == 0
    d3 = c.post("/seller/collect/image-audit/requeue", json={}).get_json()
    assert d3["ok"] and d3["requeued"] == [] and "되돌릴 항목이 없어요" in d3["message"]
    bad = c.post("/seller/collect/image-audit/requeue", json={"cases": ["B", "D"]})
    assert bad.status_code == 400


def test_requeue_is_seller_scoped(monkeypatch):
    other = "u-5b-other"
    _client(monkeypatch, other)
    theirs = _old_a_row(other, 650000000001)
    c = _client(monkeypatch, "u-5b-me")
    d = c.post("/seller/collect/image-audit/requeue", json={"item_ids": [theirs]}).get_json()
    assert theirs not in d["requeued"] and "enrich_rerun" not in _extra(theirs, other)


def test_requeue_needs_login():
    from src.order_webhook import app
    import os
    c = app.test_client()
    os.environ["SELLER_CONSOLE_AUTH"] = "1"
    try:
        import importlib
        import src.seller_console.views as V
        orig = V._AUTH_ENABLED
        V._AUTH_ENABLED = True
        try:
            assert c.post("/seller/collect/image-audit/requeue", json={}).status_code == 401
        finally:
            V._AUTH_ENABLED = orig
    finally:
        os.environ["SELLER_CONSOLE_AUTH"] = "0"


def test_audit_page_renders_summary_table_and_button(monkeypatch):
    seller = "u-5b-page"
    c = _client(monkeypatch, seller)
    iid = _old_a_row(seller, 660000000001)
    html = c.get("/seller/collect/image-audit").get_data(as_text=True)
    assert 'data-role="audit-summary"' in html and html.count('data-case="') >= 5   # 4칸 + 표 행
    assert 'data-role="audit-table"' in html and f'data-id="{iid}"' in html
    for col in ("상품", "이미지 출처", "이미지", "상태", "사유"):
        assert f"<th" in html and col in html
    assert 'id="auditRequeueBtn"' in html and "상세 보강 다시 실행" in html and "(1건)" in html
    assert "목록 카드로만 담김 — 상세 보강 기록 없음" in html
    assert "{" + "{" not in html and "format=json" in html                  # 화면이 JSON을 다시 불러 진행률을 센다
    c.post("/seller/collect/image-audit/requeue", json={})
    html2 = c.get("/seller/collect/image-audit").get_data(as_text=True)
    assert 'data-role="audit-progress"' in html2 and 'data-role="audit-progress" hidden' not in html2
    assert "보강 대기" in html2 and "보강 다시 실행 대기" in html2
    assert "(0건)" in html2                                                  # 대기 중인 건 다시 안 센다
    lst = c.get("/seller/collect/history").get_data(as_text=True)
    assert 'data-role="image-audit-link"' in lst and "/seller/collect/image-audit" in lst


def test_audit_page_tokens_only_no_hex_no_emoji():
    import re
    from pathlib import Path
    t = Path("src/seller_console/templates/image_audit.html").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", t.split("<script>")[0])
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", t)
    assert "btn-cta" in t and t.count("btn-cta") <= 3                      # 강조 1색(주황 CTA 하나)
