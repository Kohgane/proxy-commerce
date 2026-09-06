"""tests/test_seller_language.py — 셀러 화면은 사람 말로 (오너 계약 6-f-3).

**화면은 사람의 것, 원문은 로그의 것.**
부검용 원문 직출력(HTTP status·JSON 응답)은 **부검 단계의 스펙**이었다.
단계가 끝나면 스펙도 은퇴시켜야 한다 — 안 그러면 운영자 언어가 셀러 화면에 남는다
([[운영자 언어 누출]]).

원문을 지우자는 게 아니다: `<details>` 접힘 안에 두고 전문은 서버 로그가 갖는다.
부검 가치는 지키되 **기본 화면에선 사람 말 한 줄**이 먼저다.
"""
from __future__ import annotations

import re
from pathlib import Path

TPL = Path("src/seller_console/templates")
RW = TPL / "reject_watch.html"

# 응답 원문·상태코드를 **화면에 그리는** 지점. (요청 body의 JSON.stringify는 보내는 것이라 무관.)
_RAW_DISPLAY = re.compile(
    r"(?:textContent|innerHTML)\s*=[^;\n]*(?:'HTTP '|\"HTTP \"|HTTP \$\{|r\.text\(\)|resp\.text\(\))"
    r"|pcToast\(\s*[`'\"][^`'\"]*HTTP\s*\$?\{?\d*")


def _js(p: Path) -> str:
    """<script> 안만 — 주석은 걷어낸다(근거를 적은 문장이 잔재로 잡히지 않게)."""
    s = p.read_text(encoding="utf-8")
    js = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", s, re.S))
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"^\s*//.*$", "", js, flags=re.M)


# ── L1 용어 ──────────────────────────────────────────────────────────────────
def test_operator_jargon_is_gone_from_the_screen():
    """★ '재무장'은 우리 말이지 셀러 말이 아니다 — 화면 문구만 바꾼다."""
    s = RW.read_text(encoding="utf-8")
    body = re.sub(r"<script.*?</script>", "", s, flags=re.S)      # 화면에 보이는 부분만
    body = re.sub(r"\{#.*?#\}|<!--.*?-->", "", body, flags=re.S)
    assert "재무장" not in body, "화면에 '재무장'이 남았다"
    assert "다시 지켜보기" in body
    assert "심사 결과를 다시 확인하고 싶은 상품" in body


def test_internal_identifiers_are_untouched():
    """★ 코드 내부 식별자(rearm)는 **불변** — 개명은 로직 변경이다(오너 지시)."""
    s = RW.read_text(encoding="utf-8")
    for hook in ('id="rearmBtn"', 'id="rearmSids"', 'id="rearmResult"',
                 "/admin/reject-watch/rearm"):
        assert hook in s, f"내부 식별자가 바뀌었다: {hook}"
    admin = Path("src/dashboard/admin_views.py").read_text(encoding="utf-8")
    assert "def _reject_watch_rearm" in admin


# ── L2 결과 표시 ─────────────────────────────────────────────────────────────
def test_no_raw_response_on_screen():
    """★ HTTP 상태·응답 원문을 **기본 화면에 그리지 않는다.**"""
    hits = _RAW_DISPLAY.findall(_js(RW))
    assert not hits, f"원문 직출력 잔존: {hits[:3]}"


def test_success_says_what_happened():
    """성공은 '성공'이 아니라 **무엇을 했는지**를 말한다.

    ※ 체크 표시는 문자(✔)가 아니라 아이콘이다 — 사용자 화면 이모지 0(v33 스윕).
      tone이 이미 성패를 아니 호출부가 문자를 붙일 이유도 없다.
    """
    js = _js(RW)
    assert "RW_TONE_ICON" in js and "bi-check-lg" in js
    assert "다시 지켜봅니다 — 다음 자동 점검(최대 2시간 내)부터 반영돼요" in js
    assert "승인 요청을 보냈어요 — 쿠팡 심사가 시작됩니다" in js
    # 조치별로 다른 문장 — 삭제해 놓고 '승인 요청'이라 하면 그게 거짓말이다.
    for action in ("request_approval", "resubmit", "reissue", "reupload", "delete"):
        assert action in js.split("RW_ACTION_KO")[1][:600], action


def test_partial_success_is_not_rounded_up():
    """일부만 된 것을 성공으로 뭉뚱그리지 않는다(가짜 성공 0)."""
    js = _js(RW)
    assert "나머지 " in js and "목록에 없는 번호예요" in js
    assert "failed ? 'warn' : 'ok'" in js


def test_raw_survives_but_folded():
    """★ 원문을 **지우는 게 아니라 접는다** — 부검 가치는 그대로 둔다."""
    js = _js(RW)
    block = js.split("function rwRender")[1].split("\n}")[0]
    assert "details" in block and "'자세히'" in block
    assert "pre.textContent = raw" in block, "원문을 innerHTML로 넣으면 실행 위험"
    # 실패 경로도 원문을 넘긴다(에러일수록 부검이 필요하다).
    assert js.count("'bad', body") >= 2


def test_details_styling_exists():
    css = Path("src/static/app.css").read_text(encoding="utf-8")
    for cls in (".rw-line", ".rw-ok", ".rw-warn", ".rw-bad", ".rw-raw"):
        assert cls in css, cls


# ── L4 전수: 원문 노출은 접힘 안에서만 ───────────────────────────────────────
def test_seller_screens_do_not_dump_raw_outside_details():
    """★ 셀러 템플릿 전수 — 원문 노출은 `<details>` 접힘 안에서만 허용한다.

    지금 통과하는 화면을 고정하고, **새로 생기는 누출을 막는다.**
    남은 부채(collect_history의 `요청 실패 (HTTP nnn)` 9곳)는 6-j에서 갚는다 —
    거긴 한국어 문장이라 이 화면만큼 급하진 않지만, 상태코드는 셀러의 말이 아니다.
    """
    known_debt = {"collect_history.html"}          # 6-j 부채 — 늘어나면 잡힌다
    offenders = {}
    for p in sorted(TPL.glob("*.html")):
        hits = _RAW_DISPLAY.findall(_js(p))
        if hits:
            offenders[p.name] = len(hits)
    unexpected = {k: v for k, v in offenders.items() if k not in known_debt}
    assert not unexpected, f"새 원문 누출: {unexpected}"
    # 부채가 줄면 이 숫자를 낮춘다 — 늘면 실패한다.
    assert offenders.get("collect_history.html", 0) <= 9, offenders


def test_screen_renders():
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    assert app.test_client().get("/seller/sourcing/reject-watch").status_code == 200
