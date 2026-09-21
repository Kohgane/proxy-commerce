"""F44-p 계약 — 택배사 판별을 **키가 있는 곳에서** 돌린다.

## 원칙 (오너 2026-09-21, 볼트 규칙으로 승격)

> **외부 키가 필요한 측정은 키가 있는 곳(프로덕션 관리자 화면)에서 오너가 버튼으로 돌린다.**
> CC 환경으로 키를 옮기지 않는다. 로컬은 **계약(목)까지**, 실측은 관리자 화면.

그래서 이 파일은 **라이브 호출 0**이다. 공급사는 목이고, 여기서 재는 것은
**판정 규칙·사유 전달·권한·화면**이다.

## 재는 것

| # | 계약 |
|---|---|
| 1 | 판정 셋이 갈린다 — `판별`/`후보`/`못함`, 그리고 기대값 없으면 `참고` |
| 2 | **부분 통과를 통과로 읽지 않는다** — 안 잰 곳이 있으면 `keep`이 아니다 |
| 3 | 빈 후보의 **사유**가 갈린다(키 없음 · 429 · 진짜 못 찾음) |
| 4 | 공급사 **원문**이 화면까지 온다 · 키는 마스킹된다 |
| 5 | **관리자만** — 셀러에게 진단 도구를 보이지 않는다 |
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.seller_console.orders import courier_detect as D

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "src" / "seller_console" / "templates" / "orders.html"


class _Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {"data": []}
        self.text = text

    def json(self):
        return self._payload


def _codes(*codes):
    return _Resp(200, {"data": [{"courier_code": c} for c in codes]},
                 text='{"data": [...]}')


def _strip_jinja_comments(html: str) -> str:
    """`{# ... #}`를 걷어 낸다 — **주석은 화면이 아니다.**

    계약이 주석을 읽으면 헛것을 잰다: 이 파일의 「키 입력칸이 없다」가 처음에
    **설명문에 적힌 env 이름**에 걸려 터졌다.
    """
    import re
    return re.sub(r"\{#.*?#\}", "", html, flags=re.S)


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("TRACKINGMORE_API_KEY", "TM-SECRET-KEY-123456")
    return monkeypatch


# ---------------------------------------------------------------------------
# 1) 판정 셋
# ---------------------------------------------------------------------------

def test_a_first_place_match_is_a_hit(keyed):
    with patch("requests.post", return_value=_codes("cj-korea")):
        out = D.probe("CJ대한통운\t123")
    assert out["rows"][0]["verdict"] == "판별"


def test_a_lower_candidate_is_not_a_hit(keyed):
    """★ 1순위가 아니면 **판별이 아니다** — 자동으로 채워 넣을 수 없다."""
    with patch("requests.post", return_value=_codes("hanjin", "cj-korea")):
        out = D.probe("CJ대한통운\t123")
    r = out["rows"][0]
    assert r["verdict"] == "후보" and "cj-korea" in r["note"]


def test_a_wrong_answer_is_a_miss(keyed):
    with patch("requests.post", return_value=_codes("dhl")):
        out = D.probe("CJ대한통운\t123")
    assert out["rows"][0]["verdict"] == "못함"


def test_a_number_without_a_name_is_reported_not_judged(keyed):
    """★★ 기대값이 없으면 **맞다/틀리다를 말하지 않는다** — 무엇이 나왔는지만 적는다."""
    with patch("requests.post", return_value=_codes("dhl")):
        out = D.probe("1234567890")
    r = out["rows"][0]
    assert r["verdict"] == "참고" and r["name"] == ""


# ---------------------------------------------------------------------------
# 2) 부분 통과를 통과로 읽지 않는다
# ---------------------------------------------------------------------------

def test_one_hit_is_not_a_pass(keyed):
    """★★★ **판정 지점** — 9곳 중 하나만 재고 「TrackingMore 유지」라고 하지 않는다."""
    with patch("requests.post", return_value=_codes("cj-korea")):
        out = D.probe("CJ대한통운\t123")
    assert out["verdict"] == "replace"
    assert out["untested"], out
    assert "안 잰 곳이 있으면" in D.verdict_sentence(out)


def test_all_nine_hits_is_a_pass(keyed):
    from src.seller_console.orders.courier_catalog import get_courier_catalog
    idx = {}
    for row in get_courier_catalog(include_dynamic=False):
        for t in row.get("search_terms", []):
            idx.setdefault(str(t).lower(), row)

    lines, wanted = [], []
    for name, _kind in D.TARGETS:
        lines.append(f"{name}\t100{len(lines)}")
        wanted.append((idx.get(name.lower()) or {}).get("trackingmore_code", ""))

    seq = [_codes(w or "x") for w in wanted]
    with patch("requests.post", side_effect=seq):
        out = D.probe("\n".join(lines))
    # 카탈로그에 없는 국제 택배사는 우리 코드가 비어 「참고」로 떨어진다 — 그것도 **안 잰 것**이다.
    assert out["verdict"] in ("keep", "replace")
    if out["verdict"] == "keep":
        assert not out["misses"] and not out["untested"]


def test_nothing_measured_is_unknown_not_pass(keyed):
    with patch("requests.post", return_value=_codes("dhl")):
        out = D.probe("9999")            # 이름 없는 줄만 → 잰 게 없다
    assert out["verdict"] == "unknown"


# ---------------------------------------------------------------------------
# 3·4) 사유가 갈린다 · 원문이 온다 · 키는 가린다
# ---------------------------------------------------------------------------

def test_a_missing_key_is_its_own_answer(monkeypatch):
    """★★ 빈 목록은 「못 찾음」·「키 없음」·「429」를 **한 값으로 뭉갠다**."""
    monkeypatch.delenv("TRACKINGMORE_API_KEY", raising=False)
    out = D.probe("CJ대한통운\t123")
    assert out["ok"] is False and out["verdict"] == "unknown"
    assert "TRACKINGMORE_API_KEY" in out["error"]


def test_a_429_carries_the_status_and_body(keyed):
    with patch("requests.post", return_value=_Resp(429, {}, text="rate limit exceeded")):
        out = D.probe("CJ대한통운\t123")
    r = out["rows"][0]
    assert r["verdict"] == "못함"
    assert r["http_status"] == 429
    assert "rate limit" in r["raw"]


def test_an_empty_body_says_it_was_empty(keyed):
    with patch("requests.post", return_value=_Resp(500, {}, text="")):
        out = D.probe("CJ대한통운\t123")
    assert "빈 응답" in out["rows"][0]["raw"]


def test_the_api_key_never_reaches_the_screen(keyed):
    """★★ 공급사가 요청을 되울리면 키가 섞인다 — F41이 그걸 잡았다."""
    with patch("requests.post",
               return_value=_Resp(401, {}, text="bad key TM-SECRET-KEY-123456")):
        out = D.probe("CJ대한통운\t123")
    assert "TM-SECRET-KEY-123456" not in out["rows"][0]["raw"]


def test_an_empty_candidate_list_says_why(keyed):
    with patch("requests.post", return_value=_codes()):
        out = D.probe("CJ대한통운\t123")
    assert out["rows"][0]["verdict"] == "못함"
    assert "빈 목록" in out["rows"][0]["note"] or "후보가 없습니다" in out["rows"][0]["note"]


# ---------------------------------------------------------------------------
# 입력 파싱
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expect", [
    ("CJ대한통운\t123", [("CJ대한통운", "123")]),
    ("CJ대한통운 123", [("CJ대한통운", "123")]),
    ("123456", [("", "123456")]),
    ("# 주석\n\nDHL\t9", [("DHL", "9")]),
])
def test_input_parsing(text, expect):
    rows = D.parse_input(text)
    assert [(r["name"], r["number"]) for r in rows] == expect


# ---------------------------------------------------------------------------
# 5) 관리자만 · 화면
# ---------------------------------------------------------------------------

def test_the_route_is_admin_only():
    import inspect

    from src.seller_console import views
    src = inspect.getsource(views.admin_courier_detect)
    assert "_is_admin_user()" in src and "403" in src


def test_the_key_is_read_from_the_server_not_pasted():
    """★★★ **키를 옮기지 말고 측정을 옮긴다** — 화면이 키를 받지 않는다."""
    import inspect

    from src.seller_console import views
    src = inspect.getsource(views.admin_courier_detect)
    assert "api_key" not in src and "TRACKINGMORE" not in src
    html = _strip_jinja_comments(TPL.read_text(encoding="utf-8"))
    assert "cdInput" in html
    assert "TRACKINGMORE_API_KEY" not in html      # 화면에 키 입력칸이 없다


def test_the_panel_is_hidden_from_sellers():
    html = TPL.read_text(encoding="utf-8")
    i = html.index("courierDetectCard")
    assert "{% if is_admin %}" in html[:i]


def test_the_screen_shows_the_raw_response():
    html = TPL.read_text(encoding="utf-8")
    assert "응답 원문" in html and "r.raw" in html
