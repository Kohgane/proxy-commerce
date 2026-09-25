"""F44-p·F44-b 계약 — 택배사 판별을 **키가 있는 곳에서** 돌린다.

## 원칙 (오너 2026-09-21, 볼트 규칙으로 승격)

> **외부 키가 필요한 측정은 키가 있는 곳(프로덕션 관리자 화면)에서 오너가 버튼으로 돌린다.**
> CC 환경으로 키를 옮기지 않는다. 로컬은 **계약(목)까지**, 실측은 관리자 화면.

그래서 이 파일은 **라이브 호출 0**이다. 공급사는 목이고, 여기서 재는 것은
**판정 규칙·사유 전달·쿼터 표기·권한·화면**이다.

## F44-b — 공급사가 갈렸다

TrackingMore 무료 쿼터 **소진**(`4190`, 오너 실측) → **17TRACK 교체**(병존 금지).
화면은 그대로, 속만 갈아 끼웠다. 갈리면서 **성질이 하나 바뀌었다**:

★ **17TRACK엔 공짜 판별 자리가 없다.** 판별은 **등록의 부산물**(`accepted[].carrier`)이라
**한 줄 = 쿼터 한 칸**이다. 그래서 화면이 **전후 잔량**을 적는다.

## 재는 것

| # | 계약 |
|---|---|
| 1 | 판정이 갈린다 — `판별`/`후보`/`못함`, 기대값 없으면 `참고` |
| 2 | **부분 통과를 통과로 읽지 않는다** — 안 잰 곳이 있으면 `ready`가 아니다 |
| 3 | 빈 후보의 **사유**가 갈린다(키 없음 · 캐리어 미감지 · HTTP 오류) |
| 4 | 공급사 **원문**이 화면까지 온다 · 키는 마스킹된다 |
| 5 | **남은 쿼터**가 화면에 적힌다 · 못 읽으면 못 읽었다고 적는다 |
| 6 | **관리자만** — 셀러에게 진단 도구를 보이지 않는다 |
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.seller_console.orders import courier_detect as D
from tests._ast_probe import names_in, string_constants_in

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "src" / "seller_console" / "templates" / "orders.html"

KEY = "T17-SECRET-KEY-123456"


class _Resp:
    def __init__(self, status=200, payload=None, text=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload) if text is None else text

    def json(self):
        return self._payload


def _accepted(*carriers):
    """`register` 성공 — **`accepted` 배열이 증거다**(볼트 「17TRACK 등록 조용한 실패」)."""
    return _Resp(200, {"code": 0, "data": {
        "accepted": [{"origin": 1, "number": "N", "carrier": c} for c in carriers],
        "rejected": []}})


def _rejected(code=-18019903, message="Carrier cannot be detected."):
    return _Resp(200, {"code": 0, "data": {
        "accepted": [],
        "rejected": [{"number": "N", "error": {"code": code, "message": message}}]}})


def _quota(remain=1098, total=1100, used=2, today=0, max_daily=0):
    return _Resp(200, {"code": 0, "data": {
        "quota_total": total, "quota_used": used, "quota_remain": remain,
        "today_used": today, "max_track_daily": max_daily}})


def _router(*register_responses, quota=None):
    """URL로 갈라 답하는 목 — `getquota`와 `register`가 **섞이지 않게**.

    프로브는 판별 **전후로 쿼터를 한 번씩** 읽는다. 순서 목(`side_effect`)으로 짜면
    그 두 번이 판별 응답을 먹어 계약이 헛것을 잰다.
    """
    seq = list(register_responses)
    qs = list(quota or [_quota(), _quota()])

    def _post(url, *a, **kw):
        if url.endswith("/getquota"):
            return qs.pop(0) if qs else _quota()
        return seq.pop(0) if seq else _accepted(3011)

    return _post


def _strip_jinja_comments(html: str) -> str:
    """`{# ... #}`를 걷어 낸다 — **주석은 화면이 아니다.**

    계약이 주석을 읽으면 헛것을 잰다: 이 파일의 「키 입력칸이 없다」가 처음에
    **설명문에 적힌 env 이름**에 걸려 터졌다.
    """
    import re
    return re.sub(r"\{#.*?#\}", "", html, flags=re.S)


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("SEVENTEENTRACK_API_KEY", KEY)
    return monkeypatch


@pytest.fixture
def our_code(monkeypatch):
    """우리 코드표가 **있다고 가정**한 판 — 캐리어 목록 문서가 오면 이 상태가 된다.

    지금은 전부 빈칸이라(`seventeentrack_code: ""`) 실제로는 `참고`로 떨어진다.
    그 규칙은 따로 재고, 여기서는 **맞다/틀리다 판정 자체**를 잰다.
    """
    real = D._catalog_index

    def _idx():
        out = dict(real())
        for term, row in out.items():
            if row.get("name") == "CJ대한통운":
                out[term] = {**row, D.OUR_CODE_FIELD: "3011"}
        return out

    monkeypatch.setattr(D, "_catalog_index", _idx)
    return monkeypatch


# ---------------------------------------------------------------------------
# 1) 판정이 갈린다
# ---------------------------------------------------------------------------

def test_a_first_place_match_is_a_hit(keyed, our_code):
    with patch("requests.post", side_effect=_router(_accepted(3011))):
        out = D.probe("CJ대한통운\t123")
    assert out["rows"][0]["verdict"] == "판별", out["rows"][0]


def test_a_lower_candidate_is_not_a_hit(keyed, our_code):
    """★ 1순위가 아니면 **판별이 아니다** — 자동으로 채워 넣을 수 없다."""
    with patch("requests.post", side_effect=_router(_accepted(100003, 3011))):
        out = D.probe("CJ대한통운\t123")
    r = out["rows"][0]
    assert r["verdict"] == "후보" and "3011" in r["note"]


def test_a_wrong_answer_is_a_miss(keyed, our_code):
    with patch("requests.post", side_effect=_router(_accepted(100003))):
        out = D.probe("CJ대한통운\t123")
    assert out["rows"][0]["verdict"] == "못함"


def test_without_our_code_it_reports_instead_of_judging(keyed):
    """★★★ **지금이 이 상태다.** 17TRACK 캐리어 목록 문서가 없어 우리 코드가 빈칸이다.

    그럴 때 「맞다/틀리다」를 말하면 **없는 기준으로 채점하는 것**이다 —
    되돌아온 코드만 적고, 왜 판정 못 하는지 함께 적는다(F44-a 「규격 미지정」과 같은 규율).
    """
    with patch("requests.post", side_effect=_router(_accepted(3011))):
        out = D.probe("CJ대한통운\t123")
    r = out["rows"][0]
    assert r["verdict"] == "참고"
    assert "3011" in r["note"] and "우리 코드표 없음" in r["note"]


def test_a_number_without_a_name_is_reported_not_judged(keyed):
    """★★ 기대값이 없으면 **맞다/틀리다를 말하지 않는다** — 무엇이 나왔는지만 적는다."""
    with patch("requests.post", side_effect=_router(_accepted(100003))):
        out = D.probe("1234567890")
    r = out["rows"][0]
    assert r["verdict"] == "참고" and r["name"] == ""


# ---------------------------------------------------------------------------
# 2) 부분 통과를 통과로 읽지 않는다
# ---------------------------------------------------------------------------

def test_one_row_is_not_a_pass(keyed):
    """★★★ **판정 지점** — 9곳 중 하나만 재고 「다 된다」고 하지 않는다."""
    with patch("requests.post", side_effect=_router(_accepted(3011))):
        out = D.probe("CJ대한통운\t123")
    assert out["verdict"] == "gap"
    assert out["untested"], out
    assert "안 잰 곳이 있으면" in D.verdict_sentence(out)


def test_all_nine_measured_is_a_pass(keyed):
    lines = [f"{name}\t100{i}" for i, (name, _k) in enumerate(D.TARGETS)]
    with patch("requests.post",
               side_effect=_router(*[_accepted(3011) for _ in lines])):
        out = D.probe("\n".join(lines))
    assert out["verdict"] == "ready", out
    assert not out["misses"] and not out["untested"]


def test_a_rejected_row_keeps_it_from_passing(keyed):
    """★★ 아홉 줄을 다 넣어도 **하나가 거절되면 통과가 아니다.**"""
    lines = [f"{name}\t100{i}" for i, (name, _k) in enumerate(D.TARGETS)]
    seq = [_accepted(3011)] * (len(lines) - 1) + [_rejected()]
    with patch("requests.post", side_effect=_router(*seq)):
        out = D.probe("\n".join(lines))
    assert out["verdict"] == "gap" and out["misses"]


def test_nothing_measured_is_unknown_not_pass(keyed):
    with patch("requests.post", side_effect=_router(_accepted(100003))):
        out = D.probe("9999")            # 이름 없는 줄만 → 잰 게 없다
    assert out["verdict"] == "unknown"


# ---------------------------------------------------------------------------
# 3·4) 사유가 갈린다 · 원문이 온다 · 키는 가린다
# ---------------------------------------------------------------------------

def test_a_missing_key_is_its_own_answer(monkeypatch):
    """★★ 빈 목록은 「못 찾음」·「키 없음」·「쿼터 소진」을 **한 값으로 뭉갠다**."""
    monkeypatch.delenv("SEVENTEENTRACK_API_KEY", raising=False)
    out = D.probe("CJ대한통운\t123")
    assert out["ok"] is False and out["verdict"] == "unknown"
    assert "SEVENTEENTRACK_API_KEY" in out["error"]


def test_carrier_not_detected_says_what_to_do(keyed):
    """★★★ 볼트 지뢰 — 캐리어 자동감지 실패는 **코드를 지정하면 풀린다.**

    그 사실이 사유에 없으면 다음 사람이 「이 택배사는 안 되는구나」로 잘못 읽는다.
    """
    with patch("requests.post", side_effect=_router(_rejected())):
        out = D.probe("CJ대한통운\t123")
    r = out["rows"][0]
    assert r["verdict"] == "못함"
    assert "코드를 지정" in r["note"], r


def test_a_429_carries_the_status_and_body(keyed):
    with patch("requests.post",
               side_effect=_router(_Resp(429, {}, text="rate limit exceeded"))):
        out = D.probe("CJ대한통운\t123")
    r = out["rows"][0]
    assert r["verdict"] == "못함"
    assert r["http_status"] == 429
    assert "rate limit" in r["raw"]


def test_an_empty_body_says_it_was_empty(keyed):
    with patch("requests.post", side_effect=_router(_Resp(500, {}, text=""))):
        out = D.probe("CJ대한통운\t123")
    assert "빈 응답" in out["rows"][0]["raw"]


def test_a_200_with_a_vendor_error_code_is_not_success(keyed):
    """★★ 공급사가 **200으로 실패**를 말하는 자리 — 여기를 안 보면 조용한 실패다."""
    with patch("requests.post",
               side_effect=_router(_Resp(200, {"code": 4190, "data": None}))):
        out = D.probe("CJ대한통운\t123")
    r = out["rows"][0]
    assert r["verdict"] == "못함" and "4190" in r["note"]


def test_the_api_key_never_reaches_the_screen(keyed):
    """★★ 공급사가 요청을 되울리면 키가 섞인다 — F41이 그걸 잡았다."""
    with patch("requests.post",
               side_effect=_router(_Resp(401, {}, text=f"bad key {KEY}"))):
        out = D.probe("CJ대한통운\t123")
    assert KEY not in out["rows"][0]["raw"]


def test_a_200_with_neither_list_is_not_success(keyed):
    """★★ `accepted`도 `rejected`도 없으면 **아무도 무슨 일인지 말하지 않은 것**이다."""
    with patch("requests.post",
               side_effect=_router(_Resp(200, {"code": 0, "data": {}}))):
        out = D.probe("CJ대한통운\t123")
    assert out["rows"][0]["verdict"] == "못함"
    assert "accepted" in out["rows"][0]["note"]


# ---------------------------------------------------------------------------
# 5) 남은 쿼터 (오너 지시)
# ---------------------------------------------------------------------------

def test_the_remaining_quota_reaches_the_screen(keyed):
    """★★★ 오너 지시 — **「남은 쿼터를 화면에 적어라.」**

    TrackingMore는 다 쓴 뒤에야 `4190`으로 알려 줬다. 그건 늦다.
    """
    with patch("requests.post",
               side_effect=_router(_accepted(3011),
                                   quota=[_quota(remain=1000), _quota(remain=999)])):
        out = D.probe("CJ대한통운\t123")
    s = D.quota_sentence(out["quota"], out["spent"])
    assert "999" in s and "1100" in s
    assert out["spent"] == 1                       # 한 줄 = 한 칸


def test_the_quota_it_could_not_read_is_not_invented(keyed):
    """★★ 못 읽은 잔량을 **숫자로 채우지 않는다** — 못 읽었다고 적는다."""
    with patch("requests.post",
               side_effect=_router(_accepted(3011),
                                   quota=[_Resp(500, {}, text="boom"),
                                          _Resp(500, {}, text="boom")])):
        out = D.probe("CJ대한통운\t123")
    assert out["spent"] is None
    assert "읽지 못했습니다" in D.quota_sentence(out["quota"], out["spent"])


def test_an_unlimited_daily_cap_is_not_read_as_zero():
    """★★ 문서: `max_track_daily = 0`은 **무제한**이다. 「오늘 0칸」으로 읽으면 정반대다."""
    s = D.quota_sentence({"ok": True, "remain": 5, "total": 10, "today_used": 1,
                          "max_daily": 0})
    assert "일 한도 없음" in s


def test_the_screen_warns_before_it_spends(keyed):
    """★ 쓰고 나서 알려 주면 늦다 — **실행 전에** 화면이 말한다."""
    html = _strip_jinja_comments(TPL.read_text(encoding="utf-8"))
    i = html.index("cdRun")
    assert "쿼터를 씁니다" in html[:i]
    assert "quota_sentence" in html


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
# 6) 관리자만 · 화면
# ---------------------------------------------------------------------------

def test_the_route_is_admin_only():
    from tests._ast_probe import calls_in
    from src.seller_console import views

    got = calls_in(views.admin_courier_detect)
    assert "_is_admin_user" in got and "_check_auth" in got


def test_the_key_is_read_from_the_server_not_pasted():
    """★★★ **키를 옮기지 말고 측정을 옮긴다** — 화면이 키를 받지 않는다.

    ※ 소스 문자열이 아니라 **그 함수가 쓰는 이름·문자열 값**을 본다(메타 계약).
    """
    from src.seller_console import views

    used = names_in(views.admin_courier_detect) | string_constants_in(
        views.admin_courier_detect)
    assert not any("API_KEY" in str(u) for u in used), used
    html = _strip_jinja_comments(TPL.read_text(encoding="utf-8"))
    assert "cdInput" in html
    assert "SEVENTEENTRACK_API_KEY" not in html    # 화면에 키 입력칸이 없다


def test_the_panel_is_hidden_from_sellers():
    html = TPL.read_text(encoding="utf-8")
    i = html.index("courierDetectCard")
    assert "{% if is_admin %}" in html[:i]


def test_the_screen_shows_the_raw_response():
    html = TPL.read_text(encoding="utf-8")
    assert "응답 원문" in html and "r.raw" in html
