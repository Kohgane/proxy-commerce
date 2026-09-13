"""tests/test_f21_logout_and_timing.py — F21: 모바일 로그아웃 + 속도 계측.

## A. 로그아웃 — 폰에서 나갈 길이 없었다

실측(오너 2026-09-13): 모바일에 로그아웃이 **없다**. 유일한 출구가 `console-topbar`의
계정 드롭다운인데, 그 탑바는 모바일에서 **CSS로 숨는다**(v36 PART A 「모바일 단일 헤더」).
즉 기능이 지워진 게 아니라 **닿을 수 없는 곳에 있었다** — HTML에 있느냐만 보면 안 보이는 결함이다.

> 그래서 계약은 「HTML에 로그아웃이 있나」가 아니라
> **「모바일에서 열리는 자리(햄버거 드로어) 안에 있나」**를 잰다.

## B. 속도 — 측정이 먼저다

F21-4 선조사에서 **짐작한 원인 셋이 다 아니었다**:
  ① 대시보드 「마켓 진단」 → env만 읽는다(외부 호출 0)
  ② F19 부팅 훅 → 모듈 최상위(프로세스당 1회). 요청 경로에 없다
  ③ F18 상한 카운터 → 텔레그램 웹훅 전용. 콘솔 요청 경로에 없다

원인을 모르니 **경계에서 전부** 잰다(`requests` 어댑터 한 겹). 아는 자리만 재면
모르는 자리는 영영 안 보인다.
"""
from __future__ import annotations

import os

import pytest

MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


@pytest.fixture()
def client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-f21"
            s["user_email"] = "shanks8@hanmail.net"
            s["user_role"] = "seller"
        yield c


def _drawer(html: str) -> str:
    """햄버거로 열리는 사이드바 드로어 안쪽만 — 모바일에서 **닿을 수 있는** 영역."""
    i = html.find('id="sidebarDrawer"')
    assert i != -1, "사이드바 드로어를 못 찾았다"
    j = html.find("</nav>", i)
    return html[i:j]


# ── A. 로그아웃 ───────────────────────────────────────────────────────────────

def test_mobile_can_log_out_from_the_drawer(client):
    """★★ 모바일 UA로 렌더한 HTML의 **드로어 안에** 로그아웃이 있다."""
    html = client.get("/seller/dashboard", headers={"User-Agent": MOBILE_UA}).get_data(as_text=True)
    drawer = _drawer(html)
    assert "/auth/logout" in drawer, "폰에서 열리는 자리에 로그아웃이 없다"
    assert "로그아웃" in drawer


def test_logout_is_a_post_not_a_link(client):
    """로그아웃은 **POST**다 — 링크(GET)면 프리페치가 눌러 사람을 로그아웃시킨다.

    이 파일의 speculationrules가 로그아웃 경로를 일부러 제외하는 것과 같은 이유다.
    """
    html = client.get("/seller/dashboard", headers={"User-Agent": MOBILE_UA}).get_data(as_text=True)
    drawer = _drawer(html)
    i = drawer.find("/auth/logout")
    seg = drawer[max(0, i - 200):i + 200]
    assert 'method="post"' in seg, seg
    assert '<a ' not in seg[seg.find("<form"):i] if "<form" in seg else True


def test_avatar_destination_also_offers_logout(client):
    """「고」 아바타가 가는 곳(`/seller/me`)에도 로그아웃이 있다 — 두 길 다 열려 있어야 한다."""
    html = client.get("/seller/dashboard", headers={"User-Agent": MOBILE_UA}).get_data(as_text=True)
    assert "/seller/me" in html
    me = client.get("/seller/me", headers={"User-Agent": MOBILE_UA}).get_data(as_text=True)
    assert "/auth/logout" in me and "로그아웃" in me


def test_desktop_dropdown_still_has_logout(client):
    """데스크톱 계정 드롭다운의 로그아웃은 그대로다(회귀 0)."""
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert html.count("/auth/logout") >= 2, "드로어·드롭다운 둘 다 있어야 한다"


# ── B. 속도 계측 ──────────────────────────────────────────────────────────────

def test_server_timing_carries_the_segments_owner_asked_for(client):
    """★ 인증 페이지 응답에 구간이 실린다 — 오너가 네트워크 탭에서 바로 읽는다.

    `db`·`dbq`는 **실제로 쿼리가 있을 때만** 실린다(인메모리 개발 모드엔 0건이라 안 붙는다).
    없는 구간을 0으로 찍지 않는 게 이 프로젝트 규율이라, 여기서는 **늘 있는 것**만 잰다.
    쿼리 수 계약은 PG 레인의 `test_query_count_and_timing_measured`가 따로 지킨다.
    """
    r = client.get("/seller/collect/history")
    st = r.headers.get("Server-Timing", "")
    assert st, "Server-Timing이 없다"
    assert "total;dur=" in st and "app;dur=" in st and "render;dur=" in st, st


def test_auth_segment_is_measured_when_the_gate_actually_runs(monkeypatch):
    """인증 구간도 잰다 — 여기는 세션 dict만 읽으므로 **0에 가까운 게 정상**이고,
    그 0이 곧 「인증은 느림의 원인이 아니다」라는 답이다."""
    from src.seller_console import views as v
    from src.utils import perf

    monkeypatch.setattr(v, "_AUTH_ENABLED", True, raising=False)
    from src.order_webhook import app
    with app.test_request_context("/seller/dashboard"):
        from flask import session
        session["user_id"] = "u-f21"
        assert v._check_auth() is True
        assert "auth" in perf.perf_snapshot(), "인증 구간이 안 잡힌다"


def test_app_segment_excludes_external_and_auth():
    """`app`은 **나머지**라는 뜻이다 — 외부 호출·인증을 안 빼면 「앱이 느리다」는 오진이 된다."""
    from pathlib import Path
    src = Path("src/middleware/request_logger.py").read_text(encoding="utf-8")
    i = src.find("_app = round(")
    seg = src[i:i + 200]
    for token in ("_db", "_render", "_ext", "_auth"):
        assert token in seg, f"app 계산에서 {token}를 안 뺀다: {seg}"


def test_external_calls_are_counted_at_the_boundary(monkeypatch):
    """★ **모르는 자리도 잡힌다** — `requests` 어댑터 한 겹에서 전부 센다.

    호출부마다 심는 방식이면 심지 않은 자리가 빠지고, 이번 판은 바로 그 상황
    (짐작한 원인 셋이 다 아니었다)에서 출발했다.
    """
    from src.order_webhook import app
    from src.utils import perf

    assert perf.install_external_probe() is True

    seen = {}

    with app.test_request_context("/"):
        class _Req:
            url = "https://api.telegram.org/botX/sendMessage"

        # 어댑터 겹이 실제로 시간을 적는지 — 밖으로 나가지 않고 확인한다.
        perf.perf_note_external("api.telegram.org", 12.5)
        seen["snapshot"] = perf.perf_snapshot()
        seen["counts"] = perf.perf_counts()
        seen["hosts"] = perf.perf_external_hosts()

    assert seen["snapshot"].get("external") == 12.5
    assert seen["counts"].get("external_call") == 1
    assert seen["hosts"] == ["api.telegram.org"]


def test_slow_requests_get_their_own_warning_line():
    """1초 초과는 **경고로 따로** 남긴다 — 평시 INFO에 섞이면 찾는 데만 시간이 든다."""
    from pathlib import Path
    src = Path("src/middleware/request_logger.py").read_text(encoding="utf-8")
    assert "_SLOW_MS" in src
    i = src.find('"event": "slow_request"')
    assert i != -1, "느린 요청 전용 줄이 없다"
    seg = src[i:i + 900]
    for key in ("route", "db_queries", "external_calls", "external_hosts", "segments_ms"):
        assert f'"{key}"' in seg, f"느린 요청 줄에 {key}가 없다"


def test_the_probe_never_changes_the_call():
    """계측 겹은 **재기만** 한다 — 막지도, 바꾸지도, 재시도하지도 않는다."""
    from src.utils import perf
    perf.install_external_probe()
    from requests.adapters import HTTPAdapter

    calls = {"n": 0}

    class _Fake(HTTPAdapter):
        def send(self, request, *a, **kw):      # noqa: D102
            calls["n"] += 1
            return "SENTINEL"

    # 하위 클래스가 자기 send를 가지면 겹은 끼지 않는다(원래 동작 그대로).
    assert _Fake().send(object()) == "SENTINEL" and calls["n"] == 1


# ── 선조사 결과를 계약으로 못박는다 (F21-4) ──────────────────────────────────

def test_dashboard_snapshot_makes_no_outbound_calls():
    """★ ①의 답: 대시보드 「마켓 진단」은 **env만 읽는다**(외부 호출 0).

    그래서 F21-5(백그라운드 진단+캐시)는 **하지 않았다** — 없는 병을 고치는 코드가 된다.
    이 계약은 나중에 누가 여기에 API 호출을 넣으면 빨개진다.
    """
    from pathlib import Path
    src = Path("src/pipeline/ops_snapshot.py").read_text(encoding="utf-8")
    for banned in ("requests.", "urlopen(", "httpx."):
        assert banned not in src, f"대시보드 스냅샷에 외부 호출이 생겼다: {banned}"


def test_identity_bootstrap_is_not_on_the_request_path():
    """★ ②의 답: F19 부팅 훅은 **모듈 최상위**(프로세스당 1회)다 — 요청 핸들러 안이 아니다."""
    from pathlib import Path
    src = Path("src/order_webhook.py").read_text(encoding="utf-8")
    i = src.find("_identity_bootstrap()")
    assert i != -1
    head = src[:i]
    # 가장 가까운 함수 정의보다 앞서 있어야 모듈 최상위다.
    assert "def " not in head.split("try:")[-1], "부팅 훅이 함수 안으로 들어갔다(요청마다 돈다)"


def test_telegram_rate_counters_stay_out_of_console_requests():
    """★ ③의 답: F18 상한 카운터는 **텔레그램 웹훅 전용**이다."""
    from pathlib import Path
    hits = sorted(str(p) for p in Path("src").rglob("*.py")
                  if "__pycache__" not in str(p)
                  and any(k in p.read_text(encoding="utf-8", errors="replace")
                          for k in ("_rate_block", "_link_locked")))
    assert hits == ["src/api/telegram_collect.py"], f"콘솔 경로로 샜다: {hits}"


def test_logging_out_then_back_in_lands_on_the_same_user_id():
    """★ A-2: 로그아웃 뒤 재로그인해도 **같은 user_id**(F19 정체성 표 재사용).

    로그아웃이 생긴 뒤 가장 위험한 것은 「나갔다 들어오니 내 상품이 없다」다 —
    F19 이전이라면 재로그인이 곧 새 사람이었다. 그 회귀를 여기서 막는다.
    """
    from src.auth import identity as idmod
    from src.db import user_identities_pg as store

    store.reset_for_tests()
    try:
        idmod.bootstrap(merge=False)
        first = idmod.resolve_user_id("google", "cigua7134@gmail.com")
        # 로그아웃은 세션만 버린다 — 표는 그대로다.
        again = idmod.resolve_user_id("password", "shanks8@hanmail.net")
        assert first and first == again == idmod.OWNER_USER_ID
    finally:
        store.reset_for_tests()
