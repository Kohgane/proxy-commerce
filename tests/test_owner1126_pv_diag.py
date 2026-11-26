"""오너 11-26 오후 ② — 운영에서 **읽기 전용** 사전검증(`/seller/admin/diag/prevalidate/<id>`). 계약.

등록과 같은 몸통·같은 `UploadDispatcher.prevalidate`(실제 마켓 API 조회는 그 안에서)를 돌리되 행에 쓰지 않는다:
리드타임 정리·리스크 자동 적용·대표 자동 교체 저장·일회성 줄 세우기를 건너뛴다. 관리자만. 결과는 마켓마다 원문.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    return c


def test_diag_runs_prevalidate_without_writing(admin, monkeypatch):
    from src.seller_console import collect_history_store as S
    from src.seller_console.upload_dispatcher import PrevalidationResult, UploadDispatcher
    iid = S.append(source="share", url="https://www.amazon.com/dp/B0C38WV1F6", title="OKNIFE Otacle D1", price="36372", currency="KRW",
                   image="", seller_id="default", extra={"title_ko": "OKNIFE 오타클 D1", "images": ["https://m.media-amazon.com/images/I/61a._AC_SL1500_.jpg"],
                                                        "price": "36372", "currency": "KRW", "options": [{"name": "색상", "values": ["A", "B"]}],
                                                        "skus": [{"spec": ["A"], "price": "36372", "currency": "KRW"}]})
    seen = {}

    def fake_pv(self, pd, markets):
        seen["markets"], seen["skus"] = markets, len(pd.get("skus") or [])
        return [PrevalidationResult(market="coupang:gogane", ok=True),
                PrevalidationResult(market="coupang:woojoo", ok=False, hold=True, error_code="coupang_category",
                                    message="쿠팡 카테고리 필수 속성이 비었어요", details=["필수 속성 「색상」 값 없음"], fixes=["category"])]
    monkeypatch.setattr(UploadDispatcher, "prevalidate", fake_pv)
    writes = []
    real_update = S.update
    monkeypatch.setattr(S, "update", lambda *a, **k: writes.append((a, k)) or real_update(*a, **k))
    from src.services import oneshot_ops
    monkeypatch.setattr(oneshot_ops, "enqueue", lambda *a, **k: writes.append(("enqueue", a)))
    d = admin.get(f"/seller/admin/diag/prevalidate/{iid}?raw=1").get_json()
    assert d["ok"] and seen["markets"] == ["coupang:gogane", "coupang:woojoo"] and seen["skus"] == 1
    assert d["verdict"].startswith("통과 1/2") and "coupang_category" in d["verdict"]
    assert d["rows"][1]["details"] == ["필수 속성 「색상」 값 없음"]
    assert writes == []                                                                   # 읽기 전용
    h = admin.get(f"/seller/admin/diag/prevalidate/{iid}", headers={"Accept": "text/html"}).get_data(as_text=True)
    assert "읽기 전용" in h and 'data-role="dg-pv-row" data-ok="0"' in h and "쿠팡 카테고리 필수 속성이 비었어요" in h
    S.delete([iid], seller_id="default")


def test_diag_is_admin_only(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: False)
    assert app.test_client().get("/seller/admin/diag/prevalidate/x").status_code == 403


def test_dry_flag_off_outside_diag():
    from src.order_webhook import app
    from src.seller_console import views as V
    with app.test_request_context("/x"):
        assert V._pv_dry() is False
