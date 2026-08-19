"""tests/test_v88_c_pilot.py — v88-C 파일럿 배선: 모집단 396 결정성 · 50 선정 · 하드 정지 · 검수표 · admin 트리거.

라이브 실행 없음(트리거까지만). 순수 로직·라우트 접근/게이트 검증. 난수 금지(재현성).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline import coupang_replicate as CR


# ── 합성 sourcing_map (결정성·대표선정 검증) ─────────────────────────────────────
def _sm():
    return {
        # sid=100: 두 ASIN 그룹 → 대표 1 (krw+usd 보유 우선)
        "AAA00000A1": {"name_ko": "가", "krw": 1000, "sources": [{"url": "https://x/a", "priority": 1}], "coupang_sid": 100},
        "BBB00000B1": {"name_ko": "나", "krw": 2000, "usd": 2, "sources": [{"url": "https://x/b", "ship_usd": 0, "priority": 1}], "coupang_sid": 100},
        # sid=50: 단일
        "CCC00000C1": {"name_ko": "다", "krw": 3000, "sources": [{"url": "https://s.myshopify.com/products/c", "priority": 1}], "coupang_sid": 50},
        # coupang_sid 없음 → 모집단 제외
        "DDD00000D1": {"name_ko": "라", "krw": 4000, "sources": [{"url": "https://x/d"}]},
    }


def test_population_636_to_396_shape_and_determinism():
    r1 = CR.build_pilot_population(_sm())
    r2 = CR.build_pilot_population(_sm())
    # coupang_sid truthy 3 → distinct sid 2 (sid=100 중복 1 제거).
    assert r1["reduction"] == {"truthy": 3, "distinct_sid": 2, "dropped_dup": 1}
    assert r1["count"] == 2
    # 결정성: 두 번 돌려 동일 sid 시퀀스(sid 오름차순).
    assert [p["sid"] for p in r1["population"]] == [p["sid"] for p in r2["population"]] == [50, 100]


def test_representative_priority_krw_usd_then_ship_then_asin():
    pop = {p["sid"]: p for p in CR.build_pilot_population(_sm())["population"]}
    # sid=100 대표 = BBB(krw+usd 보유) — AAA(krw만)보다 우선.
    assert pop[100]["asin"] == "BBB00000B1"
    assert "krw+usd" in pop[100]["reason"]


def test_select_pilot_deterministic_and_count():
    pop = [{"sid": i, "asin": f"A{i}"} for i in range(200)]
    a = CR.select_pilot(pop, n=50)
    b = CR.select_pilot(list(reversed(pop)), n=50)   # 입력 순서 무관(내부 sid 정렬)
    assert len(a) == 50 and [x["sid"] for x in a] == [x["sid"] for x in b]   # 재현성
    assert [x["sid"] for x in a] == sorted(x["sid"] for x in a)              # sid 오름차순 stride
    # 모집단 <= n 이면 전량.
    assert len(CR.select_pilot(pop[:30], n=50)) == 30


def test_hard_stop_gate_raises_and_env_cannot_override(monkeypatch):
    assert CR.PILOT_REGISTER_APPROVED is False
    monkeypatch.setenv("PILOT_REGISTER_APPROVED", "1")   # env로 못 뚫는다
    with pytest.raises(RuntimeError, match="하드 정지"):
        CR.pilot_register_guard()


def test_review_row_blacklist_and_price_and_no_register():
    # 금지 카테고리 → excluded + 사유(조용한 탈락 금지).
    bad = CR.build_review_row({"sid": 1, "asin": "X", "name_ko": "샤넬 향수", "krw": 10000},
                              channel="woocommerce_multishop")
    assert bad["excluded"] is True and bad["forbidden"].startswith("forbidden-category")
    assert bad["registered"] is False
    # 정상 → 원가기준 가격(멀티샵 3%·마진 27.4%) 14,400.
    ok = CR.build_review_row({"sid": 2, "asin": "Y", "name_ko": "원목 식탁", "krw": 10000},
                             channel="woocommerce_multishop")
    assert ok["excluded"] is False and ok["sale_krw"] == 14400 and ok["registered"] is False
    # 주입 blacklist85 반영.
    inj = CR.build_review_row({"sid": 3, "asin": "Z", "name_ko": "특정금지품 XYZ", "krw": 5000},
                              channel="woocommerce_multishop", blacklist=["특정금지품"])
    assert inj["excluded"] is True and inj["forbidden"].startswith("blacklist")


# ── admin 트리거 라우트 (오너 세션 인증 · 등록 하드 정지) ─────────────────────────
def _admin_client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner"
        s["user_role"] = "admin"       # is_admin_session True
    return c


def test_pilot_route_requires_admin(monkeypatch):
    from src.order_webhook import app
    c = app.test_client()
    r = c.post("/admin/coupang-pilot")   # 세션 없음 → 로그인 리다이렉트(비-200)
    assert r.status_code in (301, 302, 403)


def test_pilot_route_returns_population_selection_and_gate(monkeypatch):
    c = _admin_client(monkeypatch)
    monkeypatch.delenv("COUPANG_BLACKLIST85", raising=False)
    # blacklist 미설정 → 가드가 400 → 전체 경로 검증 위해 명시적 우회.
    r = c.post("/admin/coupang-pilot?n=50&allow_no_blacklist=1")
    assert r.status_code == 200, r.status_code
    d = r.get_json()
    assert d["ok"] is True
    assert d["registered"] is False and "PILOT_REGISTER_APPROVED=False" in d["register_gate"]
    # 레포에 data/pilot_population.json(396) 존재 → 그 모집단 사용.
    if Path("data/pilot_population.json").is_file():
        assert d["population_count"] == 396 and d["selected"] == 50
    # 제외 테이블 키 존재(조용한 탈락 금지).
    assert "excluded_table" in d and "review_table" in d
    # 라이브 미충족(샌드박스) → 현행가 아님 표기.
    assert "현행가 아님" in d["price_basis"] or d["live"] is True


def test_pilot_route_blacklist_guard_blocks_on_zero(monkeypatch):
    # 조용한 실패 금지: blacklist 0건이면 표 산출 중단·400(빈 필터 전량 통과 금지).
    c = _admin_client(monkeypatch)
    monkeypatch.delenv("COUPANG_BLACKLIST85", raising=False)
    r = c.post("/admin/coupang-pilot?n=10")   # 우회 없음
    assert r.status_code == 400, r.status_code
    d = r.get_json()
    assert d["ok"] is False and d["blacklist85_loaded"] == 0
    assert "review_table" not in d           # 표를 만들지 않았다
    assert "COUPANG_BLACKLIST85" in d["how_to_load"]


def test_build_pilot_report_live_price_flips_basis_and_recalcs():
    # 계약(task 3): relay 주입 + price_fn(현행가) → price_basis="coupang live" + 마진 재계산.
    pop = [{"sid": 7, "asin": "A7", "name_ko": "원목 선반", "krw": 10000, "source": "amazon"}]
    access = {"ready": True, "missing": [], "relay_mode": "mkt.php(MARKET_API_RELAY_URL)",
              "coupang_accounts": {"우주대행": True}}
    relay = {"ready": True, "mode": "mkt.php(MARKET_API_RELAY_URL)"}
    # 현행가 재조회 stub: sourcing krw(10000)와 다른 현행가(20000) → 재계산 결과가 달라야 한다.
    live = CR.build_pilot_report(pop, n=1, access=access, relay=relay,
                                 price_fn=lambda sid: 20000, blacklist=["__none__"])
    assert live["live"] is True and live["live_price_used"] is True
    assert live["price_basis"].startswith("coupang live")
    sale_live = live["review_table"][0]["sale_krw"]
    # price_fn 없으면 sourcing krw 기준 → 다른 판매가 + basis 표기 달라짐.
    off = CR.build_pilot_report(pop, n=1, access=access, relay=relay,
                                price_fn=None, blacklist=["__none__"])
    assert off["live_price_used"] is False and "현행가 아님" in off["price_basis"]
    assert sale_live != off["review_table"][0]["sale_krw"], "현행가 재조회가 마진 재계산에 반영 안 됨"
