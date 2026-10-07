"""오너 지시(2026-10-07) — 온바운드 4013(已超量) = 키 일일 한도 소진.

- 사유 코드 `provider_quota`로 분리 · 카드 「상품정보 서비스 일일 한도 — 내일 다시 또는 충전 후」.
- 한도 소진 뒤엔 자동 수집이 **부르지 않는다**(건당 과금 방지) — 오늘(베이징 날짜) 동안. 사람이 누른 「새로 받기」만 1회 시도(충전 확인용).
- `ONEBOUND_DAILY_CAP`이 응답 `api_info`의 max보다 크면 max로 자동 하향(실측: CAP 60 > max 10이라 우리 가드가 먼저 못 막았다).
"""
from __future__ import annotations

import json

import pytest

QUOTA_BODY = {"error_code": "4013", "reason": "已超量", "error": "已超量", "api_info": "today:10 max:10 all[10=10+0+0];expires:2026-10-08"}


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setenv("ONEBOUND_KEY", "kkk_test_key_1234")
    monkeypatch.setenv("ONEBOUND_SECRET", "sss_test_secret_5678")
    monkeypatch.setenv("ONEBOUND_DAILY_CAP", "60")


def _ok_body(iid, api_info="today:3 max:10 all[3=3+0+0];expires:2099-12-31"):
    from pathlib import Path
    raw = json.loads((Path(__file__).parent.parent / "fixtures" / "providers" / "onebound_item_get_reconstructed.json")
                     .read_text(encoding="utf-8"))
    raw["item"]["num_iid"] = iid
    raw["api_info"] = api_info
    raw["cache"] = 0
    return raw


class _Tr:
    def __init__(self, *bodies):
        self.bodies, self.calls = list(bodies), []

    def __call__(self, url, params):
        self.calls.append(dict(params))
        b = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        return 200, json.dumps(b, ensure_ascii=False)


def test_4013_is_provider_quota_and_blocks_auto_calls_today():
    from src.collectors import taobao_provider_onebound as O
    tr = _Tr(QUOTA_BODY)
    r = O.call("9001", transport=tr)
    assert r["ok"] is False and r["kind"] == "provider_quota" and r["why"].startswith(O.QUOTA_LINE)
    assert "4013" in r["why"] and "已超量" in r["why"] and O.quota_block()["code"] == "4013"
    before = O.used_today()
    r2 = O.fetch_detail("9002", transport=tr)                                 # 다른 상품 자동 수집
    assert len(tr.calls) == 1 and O.used_today() == before                       # 부르지도, 한도를 쓰지도 않는다
    assert r2["state"] == "manual" and r2["kind"] == "provider_quota" and O.QUOTA_LINE in r2["reason"]


def test_quota_text_variant_without_code():
    from src.collectors import taobao_provider_onebound as O
    r = O.call("9003", transport=_Tr({"error_code": "4099", "reason": "当日调用已超量"}))
    assert r["kind"] == "provider_quota"
    assert O.is_quota_error("4013", "") and O.is_quota_error("", "已超量") and not O.is_quota_error("4005", "签名错误")


def test_manual_refresh_tries_once_and_clears_block_on_success():
    from src.collectors import taobao_provider_onebound as O
    O.call("9004", transport=_Tr(QUOTA_BODY))
    tr = _Tr(_ok_body("9004"))
    r = O.call("9004", refresh=True, no_cache=True, transport=tr)              # 충전 뒤 진단 「새로 받기」
    assert r["ok"] and len(tr.calls) == 1 and tr.calls[0]["cache"] == "no"
    assert not O.quota_block().get("code")                                       # 막음 풀림
    assert O.call("9005", transport=_Tr(_ok_body("9005")))["ok"]                # 자동 경로 다시 열림


def test_cap_auto_lowered_to_api_max():
    from src.collectors import taobao_provider_onebound as O
    assert O.daily_cap() == 60                                                   # 아직 모름 → env
    assert O.call("9006", transport=_Tr(_ok_body("9006")))["ok"]
    assert O.api_limits()["max"] == 10 and O.daily_cap() == 10                   # 60 > max 10 → 10
    from src.db import image_translate_queue_pg as st
    st.state_set(O._LIMITS, {"max": 10, "expires": "2020-01-01"})
    assert O.daily_cap() == 60                                                   # 만료된 키의 max는 쓰지 않는다


def test_env_cap_smaller_than_max_wins(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    monkeypatch.setenv("ONEBOUND_DAILY_CAP", "5")
    O.call("9007", transport=_Tr(_ok_body("9007")))
    assert O.daily_cap() == 5


def test_learned_cap_blocks_before_vendor_but_manual_uses_env_cap(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    from src.db import image_translate_queue_pg as st
    st.state_set(O._LIMITS, {"max": 2, "expires": "2099-12-31"})
    m2 = "today:{} max:2 all[];expires:2099-12-31"
    tr = _Tr(_ok_body("9100", m2.format(1)))
    for i in range(2):
        tr.bodies = [_ok_body(f"91{i:02d}", m2.format(i + 1))]
        assert O.call(f"91{i:02d}", transport=tr)["ok"]
    tr.bodies = [_ok_body("9199", m2.format(3))]
    r = O.call("9199", transport=tr)
    assert r["kind"] == "provider_cap" and len(tr.calls) == 2                    # 우리 가드가 먼저 막음(과금 0)
    r = O.call("9199", refresh=True, no_cache=True, transport=tr)
    assert r["ok"] and len(tr.calls) == 3                                        # 사람이 누른 새로 받기는 env 상한으로


def test_card_line_and_auto_run(monkeypatch):
    import src.seller_console.views as V
    assert "상품정보 서비스 일일 한도 — 내일 다시 또는 충전 후" in V._m5_auto(
        {"auto_enrich": {"state": "manual", "kind": "provider_quota", "reason": "x"}})["line"]
    from src.collectors import taobao_provider_onebound as O
    from src.seller_console import collect_history_store as S
    from src.services import taobao_auto as A
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    real = O.call
    monkeypatch.setattr(O, "call", lambda iid, refresh=False, no_cache=False, transport=None:
                        real(iid, refresh=refresh, no_cache=no_cache, transport=_Tr(QUOTA_BODY)))
    iid = S.append(source="share_text", url="https://item.taobao.com/item.htm?id=9300", seller_id="q-seller",
                   title="x", price="", currency="",
                   extra={"title": "x", "item_id_taobao": "9300", "enrich_state": "pending", "images": []})
    rec = A.run("q-seller", iid)
    assert rec["state"] == "manual" and rec["kind"] == "provider_quota"
    ex = json.loads(S.get(iid, seller_ids={"q-seller"})["extra_json"])
    assert "상품정보 서비스 일일 한도" in V._m5_auto(ex)["line"]


def test_diag_shows_quota_and_lowered_cap(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    O.call("9400", transport=_Tr(_ok_body("9400")))
    O.call("9401", transport=_Tr(QUOTA_BODY))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-provider").get_data(as_text=True)
    assert 'data-role="provider-quota"' in h and "4013" in h
    assert "ONEBOUND_DAILY_CAP=60 · 키 max 10" in h and "상한 10로 낮춰 씀" in h and "/10회" in h
