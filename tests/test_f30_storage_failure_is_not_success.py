"""F30 계약 — 저장에 실패했으면 「완료」라고 하지 않는다.

## 실측 (오너 2026-09-16)

① 번역 **「완료 5 · 실패 0」인데** 장마다 「저장된 번역본이 없습니다」
② 등록 게이트 「6장 우리 서버 주소라 못 가져감」
③ 쿠팡 계정 설정 저장·인증 → **「인터넷 연결이 불안정했어요」**
④ 사전검증: 배송 7필드는 **두 저장소 모두 비어 있음**(입력한 적 없음 확정)

## ①의 정체 — 인메모리 폴백이 성공을 위장했다

`image_ko_blobs_pg.put()`은 PG가 없으면 **인메모리에 두고 True**를 돌려줬다.
그리고 `pg.pg_enabled()`는 **첫 접속 실패를 워커 수명 내내 캐시**한다.

  → 한 번 못 붙은 워커는 그 뒤 **모든 쓰기를 조용히 메모리로** 보내고 「저장했다」고 답한다.
    같은 워커가 읽으면 보이고, **다른 워커가 읽으면 404다.**
    `build_entry`는 URL이 있으니 `status: done`. **완료 5 · 실패 0 · 이미지 0.**

v38 #1 「가짜 성공 박멸」과 **같은 모양**이다(그때도 시트 실패 → 인메모리 폴백 → 자기검증 통과).

> 폴백은 **읽기**에선 친절이고 **쓰기**에선 거짓말이다.

## ③의 정체 — 응답코드를 버렸다

`postJson`이 `{ok, data}`만 돌려주고 상태코드를 버렸다. 서버가 500을 주든 HTML을 주든
화면엔 한 줄이었고, 연결이 끊기면 「인터넷 연결이 불안정했어요」였다 —
**우리 서버가 죽은 것**과 **인터넷이 끊긴 것**을 셀러가 가릴 수 없다.

라이브 호출 0 · 마켓 호출 0 · 접속 문자열 노출 0.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
JPG = b"\xff\xd8\xff\xe0-bytes"


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_ko_blobs_pg as blobs
    blobs.reset_for_tests()
    yield
    blobs.reset_for_tests()


# ---------------------------------------------------------------------------
# ① 쓰기 폴백 — 없애고, 실패는 실패라고 말한다
# ---------------------------------------------------------------------------

def test_no_memory_fallback_when_the_db_is_configured_but_down():
    """★ **F30의 판정 지점** — 설정돼 있는데 못 붙으면 **실패**다(메모리에 두지 않는다)."""
    from src.db import image_ko_blobs_pg as blobs
    with patch.object(blobs, "_enabled", return_value=False), \
         patch.object(blobs, "_configured", return_value=True):
        assert blobs.put("i1", 0, JPG) is False
    # 메모리에도 남지 않는다 — 남으면 같은 워커에서만 보이는 유령이 된다.
    with patch.object(blobs, "_enabled", return_value=False), \
         patch.object(blobs, "_configured", return_value=True):
        assert blobs.get("i1", 0) == (b"", "")


def test_memory_is_still_fine_when_the_db_is_simply_not_configured():
    """개발·테스트(주소 자체가 없음)는 그대로 — 여기까지 막으면 아무도 못 짠다."""
    from src.db import image_ko_blobs_pg as blobs
    with patch.object(blobs, "_enabled", return_value=False), \
         patch.object(blobs, "_configured", return_value=False):
        assert blobs.put("i1", 0, JPG) is True
        assert blobs.get("i1", 0)[0] == JPG


def test_a_failed_write_becomes_a_failed_page_not_a_done_one():
    """★★ 「완료 5 · 실패 0 · 이미지 0」이 다시 나오지 않게."""
    from src.services.image_translate_store import build_entry
    result = {"ok": True, "image_b64": "aGVsbG8=", "vendor": "tencent",
              "target_text": "한국어", "lines": ["a"], "ms": 900}
    with patch("src.db.image_ko_blobs_pg.put", return_value=False):
        entry = build_entry(0, result, item_id="i1", seller_id="u1")
    assert entry["status"] == "failed", entry
    assert not entry.get("url")
    assert entry.get("use") is False, "못 저장했는데 「번역본 사용」이 켜졌다"
    assert entry["error_class"] == "NotStored"
    assert entry["error_message"]


def test_a_stored_page_is_done():
    """성공 경로는 그대로 — 막기만 하는 수리가 되지 않게."""
    from src.services.image_translate_store import build_entry
    result = {"ok": True, "image_b64": "aGVsbG8=", "vendor": "tencent",
              "target_text": "한국어", "lines": ["a"], "ms": 900}
    entry = build_entry(0, result, item_id="i1", seller_id="u1")
    assert entry["status"] == "done" and entry["url"]


def test_the_write_error_is_remembered_verbatim():
    """왜 실패했는지 **원문**을 남긴다 — 「저장 실패」로는 크기·권한·표 없음을 못 가린다."""
    from src.db import image_ko_blobs_pg as blobs

    class _Boom:
        def __enter__(self):
            raise RuntimeError('relation "image_ko_blobs" does not exist')

        def __exit__(self, *a):
            return False

    with patch.object(blobs, "_enabled", return_value=True), \
         patch("src.db.pg.tx", lambda *a, **k: _Boom()):
        assert blobs.put("i1", 0, JPG) is False
    err = blobs.last_error()
    assert err["op"] == "put"
    assert "image_ko_blobs" in err["detail"]
    assert err["at"]


def test_the_error_never_carries_the_connection_details():
    """★ 사유는 보여 주되 **접속 지도**는 아니다 — 주소·아이피·포트를 지운다."""
    from src.db import image_ko_blobs_pg as blobs
    blobs._note_error("put", 'OperationalError: connection to server at '
                             '"db.abcd.supabase.co" (1.2.3.4), port 6543 failed: timeout')
    detail = blobs.last_error()["detail"]
    assert "supabase.co" not in detail
    assert "1.2.3.4" not in detail
    assert "6543" not in detail
    assert "timeout" in detail, "사유까지 지우면 아무 쓸모가 없다"


# ---------------------------------------------------------------------------
# ② 진단 — 오너 캡처 1장이 답이 되게
# ---------------------------------------------------------------------------

def test_probe_says_configured_connected_table_and_last_error():
    from src.db import image_ko_blobs_pg as blobs
    with patch.object(blobs, "_configured", return_value=False):
        out = blobs.probe()
    assert out["configured"] is False
    assert "DATABASE_URL" in out["reason"]
    for key in ("connected", "table", "rows", "last_error"):
        assert key in out


def test_probe_names_a_missing_table_instead_of_just_failing():
    """표가 없으면(stage12 미적용) **그렇게 말한다** — 무엇을 해야 하는지 알 수 있게."""
    from src.db import image_ko_blobs_pg as blobs

    class _Cur:
        def __init__(self):
            self.n = 0

        def execute(self, sql, params=None):
            self.n += 1

        def fetchone(self):
            return [False] if self.n == 2 else [1]

    class _Q:
        def __enter__(self):
            return _Cur()

        def __exit__(self, *a):
            return False

    with patch.object(blobs, "_configured", return_value=True), \
         patch("src.db.pg.query", lambda *a, **k: _Q()):
        out = blobs.probe()
    assert out["connected"] is True and out["table"] is False
    assert "stage12" in out["reason"]


def test_diag_screen_shows_the_db_state():
    tpl = (ROOT / "src/seller_console/templates/image_storage_diag.html").read_text(encoding="utf-8")
    body = "\n".join(l for l in tpl.splitlines() if "{#" not in l)
    assert "db.configured" in body and "db.connected" in body and "db.table" in body
    assert "db.last_error" in body
    assert "마지막 쓰기 오류" in body


def test_diag_route_passes_the_probe():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
        s["user_role"] = "admin"
    r = c.get("/seller/admin/image-storage")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "데이터베이스" in html


# ---------------------------------------------------------------------------
# ③ 실패 문장 — 응답코드를 버리지 않는다
# ---------------------------------------------------------------------------

def test_post_json_keeps_the_status_code():
    tpl = (ROOT / "src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")
    fn = re.search(r"async function postJson\(url, payload\) \{.*?\n\}", tpl, re.S)
    assert fn, "postJson을 못 찾았다"
    body = "\n".join(l for l in fn.group(0).splitlines() if not l.strip().startswith("//"))
    assert "resp.status" in body, "응답코드를 버린다"
    assert "user_message" in body, "사유가 친절 처리기에 덮인다"
    assert "서버에 닿지 못했어요" in body, "「응답이 아예 없었다」를 구분하지 않는다"


def test_save_route_reports_the_real_failure_kind():
    """★ 「저장 중 오류」가 아니라 **무엇이 났는지** — 그래야 인터넷 탓을 안 한다."""
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    import src.seller_console.market_credentials as mc
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
    with patch.object(mc, "save", side_effect=RuntimeError(
            'connection to server at "db.abcd.supabase.co" (1.2.3.4), port 6543 failed')):
        r = c.post("/seller/markets/connect/coupang", json={"values": {"COUPANG_ACCESS_KEY": "x"}})
    assert r.status_code == 500
    d = r.get_json()
    assert d["user_message"] is True
    assert "RuntimeError" in d["error"]
    # 접속 지도는 나가지 않는다.
    assert "supabase.co" not in d["error"] and "1.2.3.4" not in d["error"]


def test_friendly_handler_honours_a_flagged_error_object():
    """`Error`에 표식이 붙어도 통과 — 「응답이 아예 없었다」는 이 경로로만 올라온다."""
    import subprocess
    import tempfile
    js = (ROOT / "src/seller_console/static/seller.js").read_text(encoding="utf-8")
    fn = re.search(r"function kgpFriendlyError\(raw\) \{[\s\S]*?\n\}", js).group(0)
    harness = fn + """
const e = new Error('서버에 닿지 못했어요 — 응답이 오지 않았습니다 (Failed to fetch)');
e.user_message = true;
console.log(JSON.stringify([kgpFriendlyError(e)]));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True, timeout=20)
        assert r.returncode == 0, r.stderr
        got = json.loads(r.stdout.strip().splitlines()[-1])[0]
    finally:
        Path(path).unlink(missing_ok=True)
    assert "서버에 닿지 못했어요" in got
    assert "인터넷 연결이 불안정" not in got, "우리 서버가 죽은 것을 인터넷 탓으로 돌렸다"


def test_scrubber_keeps_the_cause_and_drops_the_map():
    from src.seller_console.views import _scrub_infra
    out = _scrub_infra('OperationalError: connection to server at "db.x.supabase.co" '
                       '(10.0.0.9), port 6543 failed: timeout expired')
    assert "timeout expired" in out and "OperationalError" in out
    for leak in ("supabase.co", "10.0.0.9", "6543"):
        assert leak not in out
    assert "postgresql://" not in _scrub_infra("postgresql://u:p@h:5432/db")


# ---------------------------------------------------------------------------
# ④ 관리자 판정 — 오너는 어느 로그인으로 와도 자기 화면에 들어간다
# ---------------------------------------------------------------------------

def _sess_client(**sess):
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(sess)
    return c


def test_canonical_owner_user_id_is_admin_without_any_env():
    """★ **F30 추가의 판정 지점** — `ADMIN_EMAILS`가 없어도 정본 user_id면 관리자다.

    F29에서 게이트를 세게 잠그면서, 오너가 자기 진단 화면에서 잠길 위험을 내가 만들었다.
    """
    from src.auth.admin_resolver import is_admin_session
    from src.auth.identity import OWNER_USER_ID
    with patch.dict(os.environ, {"ADMIN_EMAILS": "", "ADMIN_USER_IDS": ""}, clear=False):
        ok, rule = is_admin_session({"user_id": OWNER_USER_ID, "user_email": "아무거나@x.y"})
    assert ok is True
    assert rule == "ADMIN_USER_IDS", rule


@pytest.mark.parametrize("email", ["shanks8@hanmail.net", "cigua7134@gmail.com"])
def test_both_owner_logins_are_admin(email):
    """hanmail이든 구글이든 **같은 사람**이다 — 로그인 경로로 권한이 갈리지 않는다."""
    from src.auth.admin_resolver import is_admin_session
    with patch.dict(os.environ, {"ADMIN_EMAILS": "", "ADMIN_USER_IDS": ""}, clear=False):
        ok, rule = is_admin_session({"user_id": "어떤-새-uuid", "user_email": email})
    assert ok is True, email
    # 이메일이 직접 준 게 아니라 **정체성이 낸 정본 id**가 준 것이다.
    assert "ADMIN_USER_IDS" in rule, rule


def test_a_plain_seller_is_still_not_admin():
    """게이트가 헐거워지지 않았는지 — 남은 아무나 들어가면 그건 수리가 아니다."""
    from src.auth.admin_resolver import is_admin_session
    with patch.dict(os.environ, {"ADMIN_EMAILS": ""}, clear=False):
        ok, _ = is_admin_session({"user_id": "u2", "user_email": "someone@else.com"})
    assert ok is False


@pytest.mark.parametrize("email", ["shanks8@hanmail.net", "cigua7134@gmail.com"])
def test_owner_sees_the_diagnostic_links_in_the_sidebar(email):
    """★ 링크가 **보여야** 한다 — 들어갈 수 있는데 길이 없으면 없는 것과 같다."""
    c = _sess_client(user_id="u-new", user_email=email)
    html = c.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/admin/image-storage" in html, email
    assert "/seller/admin/identity-audit" in html, email


def test_a_plain_seller_does_not_see_them():
    c = _sess_client(user_id="u2", user_email="someone@else.com")
    html = c.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/admin/image-storage" not in html
    assert "/seller/admin/identity-audit" not in html


@pytest.mark.parametrize("email", ["shanks8@hanmail.net", "cigua7134@gmail.com"])
def test_owner_passes_the_admin_gate_on_both_screens(email):
    """보이는 것과 들어가는 것이 같아야 한다 — 둘이 갈리면 죽은 링크다."""
    c = _sess_client(user_id="u-new", user_email=email)
    for path in ("/seller/admin/image-storage", "/seller/admin/identity-audit"):
        assert c.get(path).status_code == 200, f"{email} {path}"


def test_the_screen_asks_one_judge_not_three():
    """사이드바가 `session['user_role']`을 직접 보던 것 — 판정기가 셋이면 하나는 틀린다."""
    tpl = (ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    body = "\n".join(l for l in tpl.splitlines() if "{#" not in l)
    assert "{% if is_admin %}" in body
    assert "_user_role == 'admin'" not in body, "약한 판정기가 남아 있다"


# ---------------------------------------------------------------------------
# ④-b 판정 기준은 **정본 user_id** — 이메일 문자열이 아니다 (F30-0)
# ---------------------------------------------------------------------------

def test_admin_list_is_user_ids_not_emails():
    """★ `ADMIN_USER_IDS`(env) + 정본 오너 id. 기본값만으로도 오너가 관리자다."""
    from src.auth.admin_resolver import admin_user_ids
    from src.auth.identity import OWNER_USER_ID
    with patch.dict(os.environ, {"ADMIN_USER_IDS": ""}, clear=False):
        ids = admin_user_ids()
    assert OWNER_USER_ID.lower() in ids
    assert not any("@" in i for i in ids), "이메일이 섞이면 그건 id 판정이 아니다"


def test_extra_admin_ids_come_from_env():
    from src.auth.admin_resolver import admin_user_ids
    with patch.dict(os.environ, {"ADMIN_USER_IDS": "aaa-111, BBB-222"}, clear=False):
        ids = admin_user_ids()
    assert "aaa-111" in ids and "bbb-222" in ids


def test_email_is_only_a_key_into_the_identity_table():
    """이메일이 **직접** 권한을 주지 않는다 — 표가 정본 id를 내줘야 통과한다."""
    from src.auth import admin_resolver as A
    with patch.dict(os.environ, {"ADMIN_EMAILS": "", "ADMIN_USER_IDS": ""}, clear=False):
        # 표가 「모른다」고 하면 관리자가 아니다(이메일이 오너 것이어도 그 경로로는 안 준다)
        with patch.object(A, "_canonical_of", return_value=""):
            ok, _ = A.is_admin_session({"user_id": "u9", "user_email": "shanks8@hanmail.net"})
        assert ok is False
        # 표가 정본 id를 내주면 통과한다
        from src.auth.identity import OWNER_USER_ID
        with patch.object(A, "_canonical_of", return_value=OWNER_USER_ID):
            ok, rule = A.is_admin_session({"user_id": "u9", "user_email": "shanks8@hanmail.net"})
        assert ok is True and "ADMIN_USER_IDS" in rule


def test_the_identity_table_answers_first_then_its_seed():
    """표가 있으면 표가, 없으면 **표의 씨앗**(부팅 때 등록되는 오너 두 줄)이 답한다."""
    from src.auth import admin_resolver as A
    from src.auth.identity import OWNER_USER_ID
    with patch("src.auth.identity.resolve_user_id", return_value="정본-표에서"):
        assert A._canonical_of("shanks8@hanmail.net") == "정본-표에서"
    with patch("src.auth.identity.resolve_user_id", return_value=""):
        assert A._canonical_of("cigua7134@gmail.com") == OWNER_USER_ID
        assert A._canonical_of("남@else.com") == ""


def test_the_403_says_who_is_logged_in():
    """★ 막혔을 때 **어느 계정인지** 보여 준다 — 로그인이 갈린 게 원인일 때 그게 답이다."""
    c = _sess_client(user_id="abcdefgh-9999-0000-1111-222222222222",
                     user_email="someone@else.com")
    r = c.get("/seller/admin/image-storage")
    assert r.status_code == 403
    body = r.get_data(as_text=True)
    assert "someone@else.com" in body
    assert "abcdefgh…" in body, body
    # 전체 식별자는 내보내지 않는다.
    assert "abcdefgh-9999" not in body
