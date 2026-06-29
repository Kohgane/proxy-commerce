"""tests/test_v38_global_audit.py — v38 #7: 전역 회귀·동일유형 버그 전수 점검(CI 게이트).

언급한 것만이 아니라 같은 결함 패턴을 전 화면/코드에서 잡는다:
 (a) 가짜 성공  (b) 스코프 누락  (c) 죽은 버튼  (d) 표기 잔재  (e) 아이콘/이모지/지구본 잔재
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# (a) 가짜 성공 — 수집 성공은 서버 영속 저장 확인 후에만 ok(가짜 성공 금지)
# ---------------------------------------------------------------------------
def test_a_collect_endpoint_durable_gated():
    ext = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    # 단일 수집: durable 아니면 502 정직 실패
    assert "return_durable=True" in ext
    assert "not durable" in ext and "502" in ext
    # 벌크 수집도 이력 저장 + durable 확인(이전엔 catalog만 써서 누락)
    assert "history_append" in ext


def test_a_append_reports_durability():
    from src.seller_console.collect_history_store import append
    # 시트 미설정(개발) = 영속 간주, 튜플 반환
    item_id, durable = append(return_durable=True, source="extension", url="https://x.com",
                              title="t", seller_id="u1")
    assert item_id and durable is True


# ---------------------------------------------------------------------------
# (b) 스코프 누락 — 목록/상세/삭제가 본인 user 스코프(타인/공용 더미 노출 0)
# ---------------------------------------------------------------------------
def test_b_collect_history_is_user_scoped():
    views = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    # 목록/상세/삭제가 관용 식별자 스코프 사용
    assert "_seller_identities()" in views
    store = Path("src/seller_console/collect_history_store.py").read_text(encoding="utf-8")
    assert "seller_ids" in store          # list/get/delete가 seller_ids로 격리


def test_b_collected_detail_scope_isolation():
    # 타 셀러 항목은 404(누출 0) — 본인 스코프만
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    import src.api.extension_api as ext
    ext._require_token = lambda scopes=None: {"user_id": "owner1", "scopes": ["collect.write"]}
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    c = app.test_client()
    r = c.post("/api/v1/collect/extension", json={"url": "https://x.com/p", "title": "내 상품"})
    item_id = r.get_json().get("item_id")
    # v39 F: 다른 셀러 세션으로 상세 접근 → 404 대신 '수집 실패' 빈 상태(200)지만 데이터 누출 0
    with c.session_transaction() as s:
        s["user_id"] = "intruder9"
    rr = c.get(f"/seller/collect/preview/{item_id}")
    body = rr.get_data(as_text=True)
    assert rr.status_code == 200 and "수집 실패" in body
    assert "수집 상품 편집" not in body   # 타인 항목 편집폼 미노출(데이터 누출 0)


# ---------------------------------------------------------------------------
# (c) 죽은 버튼 — 내부 링크 404/500 = 0 (기존 no_dead_buttons 가드와 함께 CI 게이트)
# ---------------------------------------------------------------------------
def test_c_core_pages_render_ok():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"; s["user_role"] = "admin"
    for path in ("/seller/dashboard", "/seller/collect/history", "/seller/orders",
                 "/seller/markets", "/seller/catalog", "/seller/me/tokens",
                 "/seller/bookmarklet", "/seller/sourcing", "/seller/analytics"):
        assert c.get(path, follow_redirects=True).status_code == 200, path


# ---------------------------------------------------------------------------
# (d) 표기 잔재 — 'Goga Bridj'/'GOGA BRIDJ'/'고가 브릿지'(공백) 전수 0
# ---------------------------------------------------------------------------
def test_d_no_legacy_brand_spellings_in_source():
    res = subprocess.run(
        ["grep", "-rIn", "-e", "Goga Bridj", "-e", "GOGA BRIDJ", "-e", "고가 브릿지", "src/", "extensions/"],
        capture_output=True, text=True,
    )
    assert res.stdout.strip() == "", f"옛 표기 잔존:\n{res.stdout}"


# ---------------------------------------------------------------------------
# (e) 아이콘/이모지/지구본 잔재 — favicon/확장 chrome = 브릿지 마크, 지구본·픽토 이모지 0
# ---------------------------------------------------------------------------
def test_e_no_globe_in_icons_and_chrome():
    favicon = Path("src/seller_console/static/favicon.svg").read_text(encoding="utf-8")
    assert "globe" not in favicon.lower()
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "globe" not in cs.lower() and "지구본" not in cs
    # 확장 인페이지 픽토그래픽 이모지 0
    emo = [ch for ch in cs if ord(ch) >= 0x1F000 or ord(ch) in (0x2705, 0x274C)]
    assert emo == [], f"확장 이모지 잔존: {sorted(set(emo))}"
