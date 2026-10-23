"""Y15(오너 2026-10-22) — 요금표 단일화(billing_store.PLANS 정본) + 월 한도 집행 + 공유 사용자 면제 핀."""
import uuid

import pytest


@pytest.fixture(autouse=True)
def _limits_on(monkeypatch):
    monkeypatch.setenv("USAGE_LIMITS", "1")                      # conftest는 끈다 — 이 파일은 한도 자체를 본다
    monkeypatch.setenv("FAMILY_EMAILS", "fam@example.com")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    from src.seller_console import collect_history_store as S, usage_meter as M
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    monkeypatch.setattr(S, "_in_memory", [])
    M._plan_cache.clear()
    yield
    M._plan_cache.clear()


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _sid():
    return "u-" + uuid.uuid4().hex[:10]


def _collect(sid, n, **kw):
    from src.seller_console import collect_history_store as S
    for i in range(n):
        S.append(source="t", url=f"https://shop.example.com/p/{sid}/{i}", title=f"t{i}", seller_id=sid, **kw)


# ── C. 요금표 정본 ──────────────────────────────────────────────────────────────

def test_plans_table_is_the_owner_table():
    from src.seller_console.billing_store import PLANS
    assert [PLANS[p]["price_krw"] for p in ("free", "plus", "pro")] == [0, 19000, 49000]
    assert PLANS["free"]["limits"] == {"collect": 30, "translate": 20, "precheck": 10}
    assert PLANS["plus"]["limits"] == {"collect": 500, "translate": None, "precheck": None}
    assert PLANS["pro"]["limits"] == {"collect": None, "translate": None, "precheck": None}
    assert [PLANS[p]["features"]["auto_register"] for p in ("free", "plus", "pro")] == [False, True, True]
    assert PLANS["pro"]["features"]["sourcing_monitor"] and PLANS["pro"]["features"]["priority_support"]
    from src.seller_console import translation_usage
    assert translation_usage.free_limit() == 20                  # 번역 무료 횟수도 같은 표에서


def test_legacy_tenancy_plans_are_not_read_by_seller_screens():
    """옛 테넌시 FREE/BASIC/PRO/ENTERPRISE는 테넌시 API만 쓴다 — 화면·한도는 billing_store만."""
    from tests._ast_probe import importers_of
    assert importers_of("subscription_plan") == ["src/api/tenancy_api.py", "src/tenancy/__init__.py"]


# ── D. 수집 월 한도 ─────────────────────────────────────────────────────────────

def test_free_collect_stops_at_30_with_honest_message():
    from src.seller_console.usage_meter import UsageLimitReached
    sid = _sid()
    _collect(sid, 30)
    with pytest.raises(UsageLimitReached) as e:
        _collect(sid, 1)
    assert e.value.message == "이번 달 Free 한도(수집 30개)를 다 썼어요 — Plus로 올리거나 다음 달 1일에 풀려요"
    p = e.value.payload()
    assert p["ok"] is False and p["billing_url"] == "/seller/billing" and (p["used"], p["limit"]) == (30, 30)


def test_last_month_rows_do_not_count(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from src.seller_console import collect_history_store as S, usage_meter as M
    sid = _sid()
    old = (M.month_start_utc() - timedelta(seconds=1)).isoformat()
    S._in_memory.extend({"id": f"o{i}", "seller_id": sid, "collected_at": old} for i in range(40))
    _collect(sid, 30)                                            # 지난달 40개는 이번 달 한도와 무관
    assert M.used(sid, "collect") == 30
    assert M.month_start_utc(datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)).isoformat().startswith("2026-10-31T15:00")


def test_plus_allows_500_and_pro_unlimited(monkeypatch):
    from src.seller_console import billing_store, collect_history_store as S, usage_meter as M
    plus, pro = _sid(), _sid()
    monkeypatch.setattr(billing_store, "get_account",
                        lambda s: {"plan": {plus: "plus", pro: "pro"}.get(s, "free"), "token_balance": 0})
    monkeypatch.setattr(S, "count_created_since", lambda since, ids: 499)
    M.ensure("collect", plus)                                    # 499 → 통과
    monkeypatch.setattr(S, "count_created_since", lambda since, ids: 500)
    with pytest.raises(M.UsageLimitReached) as e:
        M.ensure("collect", plus)
    assert "Plus 한도(수집 500개)" in e.value.message and "Pro로 올리거나" in e.value.message
    monkeypatch.setattr(S, "count_created_since", lambda since, ids: 10 ** 6)
    M.ensure("collect", pro)                                     # 무제한


def test_duplicate_copy_is_not_a_collect():
    sid = _sid()
    _collect(sid, 30)
    _collect(sid, 3, meter=False)                                # 내가 만든 복제본은 안 센다


# ── 공유 사용자 면제 — 지금 운영 흐름 영향 0(핀) ──────────────────────────────────

def test_shared_users_are_never_metered(monkeypatch):
    from src.auth.identity import OWNER_USER_ID
    from src.db import user_identities_pg
    from src.seller_console import usage_meter as M
    fam = _sid()
    monkeypatch.setattr(user_identities_pg, "emails_for", lambda uid: ["fam@example.com"] if uid == fam else [])
    monkeypatch.setenv("ADMIN_USER_IDS", "admin-uid-1")
    for who in (OWNER_USER_ID, fam, "admin-uid-1", "fam@example.com", "default", ""):
        assert M.is_exempt(who), who
        _collect(who or "x-never", 0)
    _collect(OWNER_USER_ID, 45)                                  # 오너는 한 달 30개를 넘겨도 그대로
    _collect(fam, 45)
    for _ in range(15):
        M.take_precheck(fam)                                     # 사전검증 10회 상한도 없다
    assert M.translate_unlimited(fam) and M.translate_unlimited(OWNER_USER_ID)
    assert not M.is_exempt(_sid()) and not M.translate_unlimited(_sid())


def test_session_admin_role_alone_is_not_exempt(client, monkeypatch):
    """Y15 P0-2(오너 2026-10-23): 한도 면제도 마켓 키 격리와 같은 판정 — 세션 role=admin만으론 아니고 user_id 목록이어야 한다."""
    from src.seller_console import usage_meter as M
    with client.application.test_request_context():
        from flask import session
        session.update({"user_id": "sess-admin", "user_email": "boss@example.com", "user_role": "admin"})
        assert not M.is_exempt("sess-admin")
        monkeypatch.setenv("ADMIN_USER_IDS", "sess-admin")
        assert M.is_exempt("sess-admin")


def test_meter_failure_never_blocks(monkeypatch):
    from src.seller_console import collect_history_store as S
    sid = _sid()
    monkeypatch.setattr(S, "count_created_since", lambda since, ids: (_ for _ in ()).throw(RuntimeError("db down")))
    _collect(sid, 35)                                            # 잴 수 없으면 막지 않는다(가짜 차단 금지)


# ── 사전검증 월 한도 ────────────────────────────────────────────────────────────

def test_free_precheck_10_per_month_then_402(client, monkeypatch):
    from src.seller_console import views as V
    sid = _sid()
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: object())
    monkeypatch.setattr(V, "_pv_start_job", lambda data, mk, d: (V.jsonify({"ok": True, "job_id": "j"}), 202))
    with client.session_transaction() as s:
        s["user_id"], s["user_email"], s["user_role"] = sid, f"{sid}@example.com", "seller"
    body = {"product": {"title": "x"}, "markets": ["coupang"]}
    codes = [client.post("/seller/collect/prevalidate", json=body).status_code for _ in range(11)]
    assert codes == [202] * 10 + [402]
    r = client.post("/seller/collect/prevalidate", json=body).get_json()
    assert r["error"] == "이번 달 Free 한도(사전검증 10회)를 다 썼어요 — Plus로 올리거나 다음 달 1일에 풀려요"
    assert r["billing_url"] == "/seller/billing"


# ── 입구별 정직 응답 ────────────────────────────────────────────────────────────

def test_bulk_core_reports_limit_per_item(monkeypatch):
    from types import SimpleNamespace
    from src.api import extension_api as E
    sid = _sid()
    _collect(sid, 30)
    monkeypatch.setattr(E, "_dispatcher_collect",
                        lambda: (lambda url: SimpleNamespace(title="상품", images=["https://i/x.jpg"], price="10",
                                                             currency="CNY", price_original="")))
    monkeypatch.setattr(E, "_upsert_catalog", lambda *a, **k: None)
    r = E.collect_one_url("https://shop.example.com/p/new", seller_id=sid)
    assert r["ok"] is False and r["limit_reached"] and "수집 30개" in r["error"]


def test_billing_page_shows_table_and_usage(client):
    sid = _sid()
    _collect(sid, 7)
    with client.session_transaction() as s:
        s["user_id"], s["user_email"], s["user_role"] = sid, f"{sid}@example.com", "seller"
    html = client.get("/seller/billing").get_data(as_text=True)
    assert "data-plan-table" in html and "data-usage" in html
    for cell in ("30개", "500개", "10회", "20회", "무제한", "자동 등록", "소싱 모니터링", "우선 지원"):
        assert cell in html, cell
    assert "<strong>7</strong>" in html                           # 이번 달 실제로 센 수
