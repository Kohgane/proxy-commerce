"""tests/test_v87_w3_persistence.py — v87-W3 수집 이력 영속성 계약.

배포마다 수집 이력이 소실되던 원인 = pg_enabled()=False 시 조용한 in-memory(컨테이너 로컬)
폴백. 이 계약이 못박는 것:
- 인위회귀: 저장 경로를 로컬(in-memory)로 강제 → '재시작' 후 소실 재현(LOST). 내구 백엔드면 생존(SURVIVED).
- 저장 내구성 신호(storage_status)와 /health 노출 — 조용한 휘발을 밖에서 볼 수 있어야 한다.
- 부팅 가드: 배포 컨테이너(is_deployed)에서 PG 없으면 부팅 실패(ALLOW_VOLATILE_STORAGE로만 허용).
"""
from __future__ import annotations

import pytest

from src.db import pg as pgmod
from src.seller_console import collect_history_store as store


def _clear():
    store._in_memory.clear()


# ── 인위회귀: 로컬 강제 → 재시작 소실 재현 / 내구 백엔드 생존 ──────────────
def test_local_storage_loses_records_on_restart(monkeypatch):
    _clear()
    monkeypatch.setattr(store, "_pg_backend", lambda: None)   # 로컬(in-memory) 강제
    iid = store.append(source="qa", url="https://QA-TEST-w3/a", title="QA-TEST- 마커", seller_id="QA-TEST-s")
    if isinstance(iid, tuple):
        iid = iid[0]
    assert store.list_items(seller_ids={"QA-TEST-s"}, days=3650)   # 같은 컨테이너선 보임
    # '재배포/재시작' 시뮬 = 컨테이너 로컬 in-memory 소멸.
    store._in_memory.clear()
    assert store.list_items(seller_ids={"QA-TEST-s"}, days=3650) == []   # LOST(재현)


def test_durable_backend_survives_restart(monkeypatch):
    _clear()
    # 내구 백엔드(PG) 시뮬 — in-memory 소멸과 무관하게 살아있는 저장소.
    _durable = {}

    class _FakePG:
        @staticmethod
        def append(**kw):
            import secrets
            iid = secrets.token_hex(4)
            _durable[iid] = dict(kw, id=iid)
            return (iid, True) if kw.get("return_durable") else iid

        @staticmethod
        def list_items(**kw):
            sids = kw.get("seller_ids")
            return [dict(r, url=r.get("url"), title=r.get("title"))
                    for r in _durable.values()
                    if sids is None or str(r.get("seller_id")) in sids]

    monkeypatch.setattr(store, "_pg_backend", lambda: _FakePG)
    store.append(source="qa", url="https://QA-TEST-w3/b", title="QA-TEST- 마커", seller_id="QA-TEST-s", return_durable=True)
    store._in_memory.clear()   # '재시작' — 로컬은 비어도
    assert store.list_items(seller_ids={"QA-TEST-s"}, days=3650)   # SURVIVED(내구 저장)


# ── 저장 내구성 신호 ─────────────────────────────────────────────
def test_storage_status_shape_and_volatile_flag(monkeypatch):
    monkeypatch.setattr(pgmod, "pg_enabled", lambda: False)
    monkeypatch.setattr(pgmod, "is_deployed", lambda: True)
    monkeypatch.setattr(pgmod, "db_url", lambda: "")
    s = pgmod.storage_status()
    assert s["durable"] is False and s["backend"] == "in-memory"
    assert s["volatile_in_production"] is True     # 배포+무DB → 휘발 경고

    monkeypatch.setattr(pgmod, "pg_enabled", lambda: True)
    s2 = pgmod.storage_status()
    assert s2["durable"] is True and s2["backend"] == "postgres"
    assert s2["volatile_in_production"] is False


def test_is_deployed_detection(monkeypatch):
    # pytest 중엔 항상 False(PYTEST_CURRENT_TEST 존재) — 테스트가 부팅가드에 안 걸리게.
    assert pgmod.is_deployed() is False
    # 함수 로직 자체 검증(플래그 제거 시).
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("APP_ENV", "ci")
    assert pgmod.is_deployed() is False
    monkeypatch.setenv("APP_ENV", "")
    monkeypatch.setenv("RENDER", "true")
    assert pgmod.is_deployed() is True


def test_health_exposes_storage_signal(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as c:
        j = c.get("/health").get_json()
    assert "storage" in j
    for k in ("durable", "backend", "deployed", "volatile_in_production"):
        assert k in j["storage"]


# ── 부팅 가드 결정 로직(조용한 휘발 봉인) ─────────────────────────
def test_boot_guard_source_widened_beyond_production():
    # 부팅 가드가 APP_ENV==production 뿐 아니라 is_deployed()로 판정하는지(조용한 휘발 봉인).
    from pathlib import Path
    src = Path("src/order_webhook.py").read_text(encoding="utf-8")
    assert "is_deployed()" in src
    assert "ALLOW_VOLATILE_STORAGE" in src
    assert "배포마다 소실" in src


def test_persistence_check_script_qa_prefix_and_read_only():
    from pathlib import Path
    src = Path("scripts/persistence_check.py").read_text(encoding="utf-8")
    assert "QA-TEST-" in src
    # status/verify는 읽기 전용 — cleanup만 삭제(그것도 QA-TEST-만).
    assert "delete_ids" in src and "QA-TEST-persistence" in src
