"""F35 계약 — 「얼마나 기다렸나」와 「닿긴 했나」를 말한다.

## 실측 (2026-09-19 06:3x UTC — 채팅이 직접 curl)

| 대상 | 결과 |
|---|---|
| relay **정적** 파일 | 0.4s 즉답 |
| `mkt.php` | **45s · 0바이트** |
| `kohganemultishop.org` | **45s · 0바이트** |

정적은 살아 있고 **PHP만 전면 정지** = Bluehost 호스팅 장애. **코드 결함이 아니다.**
복구는 오너(cPanel). 코드가 할 일은 둘이다.

## ① 기다린 시간을 문장에 적는다

릴레이 호출은 `throttled_request`가 감싸고 그건 **예외도 재시도한다**(3회 재시도 = 총 4회,
백오프 1→2→4s). 릴레이 타임아웃 35s면 최악 **4×35+7 = 147초**다.
그런데 gunicorn은 `--timeout 120`이다 → **147초짜리 요청은 문장을 내기 전에 워커가 죽는다.**

> ★ **기다리는 시간은 워커가 살아 있는 시간 안에 들어와야 한다.**
> 안 그러면 재시도는 사용자에게 「느림」이 아니라 **「아무 말 없음」**이다.

→ 시도 횟수를 상수로 박지 않고 **워커 타임아웃에서 역산**하고, 그 숫자를 문장에 싣는다.

## ② 사전검증이 「닿나」를 잰다

멀티샵 사전검증은 **「통과」**였다. 같은 시각 그 사이트는 45초 0바이트였다.
사전검증이 잰 건 **자격이 입력돼 있나**였지 **살아 있나**가 아니었다.

> ★ **「키가 있다」는 「닿는다」가 아니다.**

라이브 호출 0 — 모든 네트워크는 목이다.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
import requests


@pytest.fixture
def clean_env(monkeypatch):
    for k in ("MARKET_RELAY_TIMEOUT_SEC", "GUNICORN_TIMEOUT",
              "MARKET_RELAY_BUDGET_MARGIN_SEC", "MARKET_API_RELAY_URL",
              "MARKET_API_RELAY_KEY", "MARKET_RELAY_TOKEN", "MARKET_RELAY_URL",
              "WC_URL", "WOO_BASE_URL", "SHOPIFY_SHOP"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# ① 대기 계획 — 워커가 죽기 전에 문장이 나와야 한다
# ---------------------------------------------------------------------------

def test_the_wait_plan_fits_inside_the_worker_timeout(clean_env):
    """★★ **F35-①의 판정 지점** — 기본값(35s 타임아웃 · 워커 120s)에서 예산 안에 든다."""
    from src.market_relay import relay_wait_plan
    plan = relay_wait_plan()
    assert plan["timeout_sec"] == 35
    assert plan["total_sec"] <= 120 - 20, plan
    assert plan["attempts"] >= 1


def test_the_old_shape_would_not_have_fit():
    """예전 모양(4회 × 35s + 백오프 7s = 147s)은 워커 타임아웃 120s를 **넘는다**.

    이 숫자를 계약에 박아 둔다 — 「재시도가 있다」는 말만으론 왜 문장이 안 왔는지 모른다.
    """
    assert 4 * 35 + (1 + 2 + 4) == 147
    assert 147 > 120


def test_the_sentence_carries_the_numbers(clean_env):
    """★ 「1회, 35s」든 「35초씩 2번, 총 71초」든 — **숫자가 문장에 있다**."""
    from src.market_relay import relay_wait_plan
    s = relay_wait_plan()["sentence"]
    assert "35" in s and "초" in s, s


def test_one_attempt_says_so(clean_env):
    """재시도가 없으면 오너 지시대로 **「1회, Ns」**라고 적는다."""
    from src.market_relay import relay_wait_plan
    clean_env.setenv("MARKET_RELAY_TIMEOUT_SEC", "90")     # 예산(100s)에 한 번만 들어간다
    plan = relay_wait_plan()
    assert plan["attempts"] == 1
    assert plan["sentence"] == "1회, 90초 기다렸습니다"


def test_a_bigger_worker_budget_buys_more_attempts(clean_env):
    """예산이 커지면 시도가 늘되 **상한 4회**를 넘지 않는다(스로틀 기본과 같은 상한)."""
    from src.market_relay import relay_wait_plan
    clean_env.setenv("GUNICORN_TIMEOUT", "600")
    plan = relay_wait_plan()
    assert plan["attempts"] == 4
    assert plan["total_sec"] == 4 * 35 + (1 + 2 + 4)


def test_a_tiny_budget_still_tries_once(clean_env):
    """예산이 타임아웃보다 작아도 **한 번은 시도한다** — 0회는 측정이 아니다."""
    from src.market_relay import relay_wait_plan
    clean_env.setenv("GUNICORN_TIMEOUT", "10")
    assert relay_wait_plan()["attempts"] == 1


def test_a_dead_relay_reports_how_long_it_waited(clean_env):
    """★★ 릴레이 무응답 → 사유 **+ 기다린 시간**이 한 문장에 온다."""
    from src import market_relay as R
    clean_env.setenv("MARKET_API_RELAY_URL", "https://relay.example/mkt.php")
    clean_env.setenv("MARKET_API_RELAY_KEY", "k")
    calls = []

    def _boom(*a, **kw):
        calls.append(1)
        raise requests.exceptions.ReadTimeout("timed out")

    with patch.object(R.requests, "post", side_effect=_boom), \
         patch("src.market_throttle.time.sleep"):
        with pytest.raises(R.RelayError) as err:
            R.relay_request("POST", "https://api-gateway.coupang.com/v2/x",
                            json={}, market="coupang")
    plan = R.relay_wait_plan()
    assert len(calls) == plan["attempts"], f"계획({plan['attempts']})과 실제 시도가 다르다"
    assert plan["sentence"] in str(err.value), str(err.value)
    assert "릴레이" in str(err.value)


def test_a_direct_market_is_untouched(clean_env):
    """릴레이를 안 타는 마켓(11번가 등)은 기존 경로 그대로다 — 무회귀."""
    from src import market_relay as R

    class _Resp:
        status_code = 200
        headers: dict = {}

    with patch.object(R.requests, "request", return_value=_Resp()) as req:
        out = R.relay_request("GET", "https://api.11st.co.kr/rest", market="elevenst")
    assert out.status_code == 200 and req.call_count == 1


# ---------------------------------------------------------------------------
# ② 사전검증이 「닿나」를 잰다
# ---------------------------------------------------------------------------

def test_an_unreachable_site_is_not_a_pass(clean_env):
    """★★ **F35-②의 판정 지점** — 사이트가 죽었으면 「통과」가 아니다.

    오너 실측 그대로: 키는 다 있고 사이트만 0바이트였다.
    """
    from src.seller_console import upload_dispatcher as UD
    clean_env.setenv("WC_URL", "https://kohganemultishop.org")
    clean_env.setenv("WC_KEY", "ck")
    clean_env.setenv("WC_SECRET", "cs")
    with patch.object(UD, "market_reach",
                      return_value={"ok": False, "ms": 5000, "detail": "ReadTimeout"}):
        res = UD.UploadDispatcher().prevalidate({"title": "수행방패", "price": 9900},
                                                ["woocommerce"])[0]
    assert res.ok is False
    assert res.error_code == "market_unreachable"
    assert "ReadTimeout" in res.message, res.message
    assert "5000ms" in res.hint, res.hint
    assert res.reach_ok is False and res.reach_ms == 5000


def test_a_reachable_site_passes_and_reports_the_time(clean_env):
    """닿으면 통과하되 **걸린 시간을 들고 온다** — 화면이 ms를 적는다."""
    from src.seller_console import upload_dispatcher as UD
    clean_env.setenv("WC_URL", "https://kohganemultishop.org")
    clean_env.setenv("WC_KEY", "ck")
    clean_env.setenv("WC_SECRET", "cs")
    with patch.object(UD, "market_reach",
                      return_value={"ok": True, "ms": 412, "detail": "HTTP 200"}):
        res = UD.UploadDispatcher().prevalidate({"title": "수행방패", "price": 9900},
                                                ["woocommerce"])[0]
    assert res.ok is True and res.reach_ok is True and res.reach_ms == 412


def test_any_http_answer_counts_as_reachable(clean_env):
    """401·403·404도 **서버가 살아 있다**는 뜻이다 — 도달로 본다."""
    from src.seller_console import upload_dispatcher as UD
    clean_env.setenv("SHOPIFY_SHOP", "x.myshopify.com")

    class _R:
        status_code = 403

    with patch("requests.get", return_value=_R()):
        out = UD.market_reach("shopify")
    assert out["ok"] is True and out["detail"] == "HTTP 403"
    assert isinstance(out["ms"], int)


def test_a_connection_failure_is_unreachable(clean_env):
    from src.seller_console import upload_dispatcher as UD
    clean_env.setenv("WC_URL", "kohganemultishop.org")          # scheme 없어도 보정한다
    with patch("requests.get", side_effect=requests.exceptions.ConnectTimeout("x")):
        out = UD.market_reach("woocommerce")
    assert out["ok"] is False and out["detail"] == "ConnectTimeout"


def test_no_address_means_not_measured_not_failed(clean_env):
    """★ 주소가 없으면 **못 쟀다**(None)다 — 「도달 불가」로 단정하지 않는다."""
    from src.seller_console import upload_dispatcher as UD
    assert UD.market_reach("woocommerce")["ok"] is None


def test_the_probe_sends_no_credentials(clean_env):
    """도달 측정은 **자격을 보내지 않는다** — 「닿나」만 묻는다."""
    from src.seller_console import upload_dispatcher as UD
    clean_env.setenv("WC_URL", "https://kohganemultishop.org")
    clean_env.setenv("WC_KEY", "ck-secret")
    clean_env.setenv("WC_SECRET", "cs-secret")

    class _R:
        status_code = 200

    with patch("requests.get", return_value=_R()) as g:
        UD.market_reach("woocommerce")
    url, kw = g.call_args[0][0], g.call_args[1]
    blob = url + repr(kw)
    assert "ck-secret" not in blob and "cs-secret" not in blob, blob
    assert kw["timeout"] == 5, "오너 지시는 5초다"


def test_the_probe_does_not_retry(clean_env):
    """사람이 기다리는 화면이다 — 백오프를 돌면 5초 예산이 30초가 된다."""
    from src.seller_console import upload_dispatcher as UD
    clean_env.setenv("SHOPIFY_SHOP", "x.myshopify.com")
    with patch("requests.get", side_effect=requests.exceptions.ReadTimeout("x")) as g:
        UD.market_reach("shopify")
    assert g.call_count == 1


def test_gated_markets_are_not_probed():
    """쿠팡·스마트스토어는 IP 화이트리스트라 무자격 GET이 의미가 없다 — 안 잰다."""
    from src.seller_console import upload_dispatcher as UD
    for m in ("coupang", "smartstore"):
        assert UD.market_reach(m)["ok"] is None


def test_the_route_carries_reach_to_the_screen():
    """라우트가 `reach_ms`를 실어 보낸다 — 함수만 맞고 화면이 비면 소용없다."""
    import inspect
    from src.seller_console import views
    src = inspect.getsource(views.collect_prevalidate)
    assert '"reach_ms"' in src and '"reach_ok"' in src


def test_the_screen_prints_the_reach_time():
    """화면이 ms를 **그린다**. 안 잰 마켓엔 아무것도 안 붙인다(빠른 척 금지)."""
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1]
           / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "reach_ok === true" in tpl and "도달 ${r.reach_ms}ms" in tpl
    assert "도달 불가" in tpl
