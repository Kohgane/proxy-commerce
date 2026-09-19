"""F34-1 계약 — 「못 읽었다」를 「비어 있다」라고 말하지 않는다.

## 오너 실측 (2026-09-19, 카나리 1차)

마켓 연동 드로어에 **여섯 칸**을 넣고 저장했다:

| 칸 | 넣은 값 |
|---|---|
| Wing 로그인 ID | shanks8 |
| 반품지센터코드 | 1002166041 |
| 반품지 우편번호 | 14600 |
| 반품지 주소 | (주소) |
| 반품지 담당자명 | 장말로 |
| 반품지 연락처 | (번호) |

그런데 사전검증은 **일곱 칸 전부 「비어 있음」**이라고 했다.
진짜로 비어 있는 칸은 **출고지코드 하나**뿐이었다.

## 갈라 보니 — 빈 dict가 두 군데서 났다

1. **복호화 실패**(`market_links_pg._decode`) → `{}`.
   키가 바뀌었거나 없으면 저장소는 조용히 빈 dict를 냈고, 그게 화면·검증기를 지나
   「입력한 적 없음」처럼 보였다.
2. **저장소가 갈렸다**(`pg.pg_enabled()`는 워커 수명 동안 첫 접속 결과를 **캐시한다**).
   접속이 한 번 삐끗한 워커는 그 뒤로 계속 `data/<seller>.json`에 썼다 — 그 파일은
   컨테이너와 함께 사라지고 **옆 워커에는 보이지도 않는다.**
   화면엔 「저장됨」, 다음 요청엔 「비어 있음」.

> ★ **못 물어본 것과 없는 것은 다른 사건이다.**
> 섞어 말하면 셀러는 이미 넣어 둔 값을 또 넣는다 — 오너가 실제로 그랬다.

> ★ **운영에서 PG로 못 가는데 파일에 쓰는 것은 저장이 아니라 거짓말이다.**
> 같은 판정을 F30이 이미 이미지 저장소에 적용했다. 여기만 예외일 이유가 없다.

라이브 호출 0 · 마켓 호출 0 · 레포에 파일 0(`_DATA_DIR`은 **모듈 로드 시점 상수**라
env로 못 바꾼다 — 상수를 세운다).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 오너가 실제로 넣은 여섯 칸 + 등록에 필요한 API 자격 3.
#   **출고지코드는 일부러 없다** — 그게 진짜로 비어 있던 유일한 칸이다.
OWNER_SIX = {
    "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk",
    "COUPANG_VENDOR_ID": "A01381223",
    "COUPANG_VENDOR_USER_ID": "shanks8",
    "COUPANG_RETURN_CENTER_CODE": "1002166041",
    "COUPANG_RETURN_ZIP_CODE": "14600",
    "COUPANG_RETURN_ADDRESS": "경기도 김포시 통진읍 서암리",
    "COUPANG_RETURN_CHARGE_NAME": "장말로",
    "COUPANG_COMPANY_CONTACT_NUMBER": "010-0000-0000",
}

MISSING_ONE = "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE"


@pytest.fixture
def clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("COUPANG_") or k in ("DATABASE_URL", "SUPABASE_DB_URL",
                                             "MARKET_CRED_ENC_KEY"):
            monkeypatch.delenv(k, raising=False)
    return monkeypatch


@pytest.fixture
def file_store(clean_env, tmp_path):
    """파일 저장소로 고정 + 레포 바깥으로 격리."""
    from src.seller_console import market_credentials as mc
    clean_env.setattr(mc, "_DATA_DIR", str(tmp_path), raising=False)
    mc._FILE_READ_ERROR.clear()
    with patch.object(mc, "_pg_links", return_value=None):
        yield mc


def _precheck(mc, seller):
    from src.seller_console.upload_dispatcher import UploadDispatcher
    with mc.seller_market_env(seller, ["coupang"]):
        return UploadDispatcher().prevalidate({"title": "수행방패", "price": 9900},
                                              ["coupang"])[0]


# ---------------------------------------------------------------------------
# ① 오너가 말한 판정 지점 — 여섯 칸 저장 → **정확히 하나만** 비었다고 말한다
# ---------------------------------------------------------------------------

def test_six_saved_fields_leave_exactly_one_missing(file_store):
    """★★ **F34-1의 판정 지점.**

    오너가 넣은 여섯 칸이 그대로 살아 있고, 모자란 건 출고지코드 하나다.
    예전엔 여기서 일곱 개가 나왔다.
    """
    mc = file_store
    mc.save("seller-f34", "coupang", dict(OWNER_SIX))
    res = _precheck(mc, "seller-f34")

    assert res.ok is False, "출고지코드가 없으니 막는 건 맞다"
    assert MISSING_ONE in res.hint
    for env in OWNER_SIX:
        assert f"{env}(" not in res.hint, f"{env}는 넣었는데 비었다고 말한다"
    assert res.hint.count("COUPANG_") == 1, f"모자란 칸은 하나여야 한다 — {res.hint}"


def test_the_seventh_field_completes_it(file_store):
    """일곱 번째를 채우면 통과한다 — 게이트가 살아 있고, 조건도 이 일곱뿐이다."""
    mc = file_store
    mc.save("seller-f34b", "coupang", {**OWNER_SIX, MISSING_ONE: "7437895"})
    assert _precheck(mc, "seller-f34b").ok is True


def test_the_state_view_agrees_with_the_precheck(file_store):
    """화면 판정기와 검증기가 **같은 답**을 낸다 — 갈리면 한쪽이 거짓말이다."""
    from src.seller_console.market_cred_view import coupang_shipping_state
    mc = file_store
    mc.save("seller-f34c", "coupang", dict(OWNER_SIX))
    with mc.seller_market_env("seller-f34c", ["coupang"]):
        st = coupang_shipping_state("")
    assert [e for e, _ in st["missing"]] == [MISSING_ONE]
    assert len(st["present"]) == 6
    assert not st["read_failed"]


# ---------------------------------------------------------------------------
# ② 읽기 실패 — 「비어 있음」이라고 말하지 않는다
# ---------------------------------------------------------------------------

def test_a_decrypt_failure_is_reported_as_unreadable_not_empty(clean_env, tmp_path):
    """★ 키가 사라지면 **「읽지 못했습니다」**다. 「입력한 적 없음」이 아니다."""
    from src.seller_console import market_credentials as mc
    clean_env.setattr(mc, "_DATA_DIR", str(tmp_path), raising=False)
    mc._FILE_READ_ERROR.clear()
    clean_env.setenv("MARKET_CRED_ENC_KEY", "aXKQ0m3S6w7p9Vv1t2u3x4y5z6A7B8C9D0E1F2G3H4I=")

    with patch.object(mc, "_pg_links", return_value=None):
        mc.save("seller-lost", "coupang", dict(OWNER_SIX))
        clean_env.delenv("MARKET_CRED_ENC_KEY", raising=False)   # 키가 사라졌다
        assert mc.get("seller-lost", "coupang") == {}, "전제: 값이 안 읽힌다"
        state = mc.read_state("seller-lost")

    assert state["ok"] is False
    # 키가 아예 없으면 「복호화 키가 없습니다」, SECRET_KEY로 파생된 다른 키가 잡히면
    #   「복호화 실패」 — 어느 쪽이든 **읽지 못했다는 사실**이 올라와야 한다.
    assert "복호화" in state["reason"], state


def test_the_precheck_sentence_stops_saying_empty_when_it_could_not_read(file_store):
    """★★ 문장 자체가 바뀐다 — 셀러가 읽는 건 사전검증의 그 한 줄이다."""
    mc = file_store
    with patch.object(mc, "read_state",
                      return_value={"ok": False, "reason": "복호화 실패: InvalidToken"}):
        res = _precheck(mc, "seller-unreadable")

    assert res.ok is False, "못 읽었는데 통과시키면 그게 더 나쁘다(게이트 유지)"
    assert "비어 있는 값" not in res.hint, "못 읽은 걸 비었다고 말한다"
    assert "읽지 못해" in res.hint
    assert "복호화 실패: InvalidToken" in res.hint, "사유가 문장에 안 실렸다"


def test_a_successful_read_leaves_no_stale_reason(clean_env, tmp_path):
    """한 번 실패한 사유가 **들러붙지 않는다** — 그러면 멀쩡한 값을 못 읽었다고 한다."""
    from src.db import market_links_pg as ml
    ml._note_read_error("복호화 실패: InvalidToken")
    assert ml.last_read_error().get("reason")
    ml._clear_read_error()
    assert ml.last_read_error() == {}


def test_the_reason_never_carries_the_value(clean_env):
    """사유에 자격 값·접속 문자열이 실리지 않는다(F31 선례)."""
    from src.db import market_links_pg as ml
    ml._note_read_error('connection to server at "db.abcd.supabase.co" (1.2.3.4), port 6543 failed')
    reason = ml.last_read_error()["reason"]
    assert "1.2.3.4" not in reason and "supabase.co" not in reason, reason
    ml._clear_read_error()


# ---------------------------------------------------------------------------
# ③ 저장소가 갈렸다 — 폴백 저장은 성공이 아니다
# ---------------------------------------------------------------------------

def test_backend_is_not_degraded_without_a_database_url(clean_env):
    """DB를 안 쓰는 개발 환경은 정상이다 — 파일이 제 자리다(무회귀)."""
    from src.seller_console import market_credentials as mc
    assert mc.backend_state() == {"backend": "file", "degraded": False, "reason": ""}


def test_a_dead_database_is_degraded_not_silent(clean_env):
    """★ DATABASE_URL이 있는데 PG로 못 가면 **degraded**다."""
    from src.db import pg
    from src.seller_console import market_credentials as mc
    clean_env.setenv("DATABASE_URL", "postgresql://x/y")
    with patch.object(pg, "pg_enabled", return_value=False):
        st = mc.backend_state()
    assert st["degraded"] is True
    assert "연결하지 못했" in st["reason"]


def test_saving_into_the_ephemeral_fallback_raises(clean_env, tmp_path):
    """★★ 사라질 파일에 써 놓고 「저장됨」이라 하지 않는다."""
    from src.db import pg
    from src.seller_console import market_credentials as mc
    clean_env.setattr(mc, "_DATA_DIR", str(tmp_path), raising=False)
    clean_env.setenv("DATABASE_URL", "postgresql://x/y")
    with patch.object(pg, "pg_enabled", return_value=False):
        with pytest.raises(RuntimeError) as err:
            mc.save("seller-split", "coupang", dict(OWNER_SIX))
    assert "연결하지 못했" in str(err.value)
    assert not list(Path(tmp_path).glob("*.json")), "막아 놓고 파일은 썼다"


def test_a_degraded_backend_reads_as_unreadable(clean_env):
    """저장소가 갈린 상태에서 「비어 있음」이라 말하면 또 같은 병이다."""
    from src.db import pg
    from src.seller_console import market_credentials as mc
    clean_env.setenv("DATABASE_URL", "postgresql://x/y")
    with patch.object(pg, "pg_enabled", return_value=False):
        st = mc.read_state("seller-any")
    assert st["ok"] is False and st["reason"]


def test_the_save_route_answers_with_a_status_code(clean_env, tmp_path):
    """★ 「저장 실패는 실패라고 말한다(응답코드 포함)」 — 오너 계약 그대로."""
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.db import pg
    from src.order_webhook import app
    from src.seller_console import market_credentials as mc
    clean_env.setattr(mc, "_DATA_DIR", str(tmp_path), raising=False)
    clean_env.setenv("DATABASE_URL", "postgresql://x/y")
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-f34"
        s["user_email"] = "a@b.c"
    with patch.object(pg, "pg_enabled", return_value=False):
        r = c.post("/seller/markets/connect/coupang",
                   json={"values": {"COUPANG_VENDOR_USER_ID": "shanks8"}})
    assert r.status_code == 500, "폴백에 써 놓고 200을 돌려줬다"
    body = r.get_json()
    assert body["ok"] is False
    assert "연결하지 못했" in body["error"], body


# ---------------------------------------------------------------------------
# ③b 저장 라우트의 거부 조건 — 오너 확정(09-19): 「어제 저장이 조용히 버려졌다」
#
#   드로어 재오픈 실측: 여섯 칸 전부 빈칸, Wing ID만 차 있었다 — 그건 **저장값이 아니라
#   제안**이다. 그러니 어제의 「저장했어요」는 아무것도 안 쓰고 낸 말이었다.
#   → 저장은 **되읽힐 때** 저장이다. 안 읽히면 실패라고 말한다.
# ---------------------------------------------------------------------------

def test_a_save_that_does_not_read_back_is_a_failure(file_store):
    """★★ **오너 확정 갈래 a)/c)의 판정 지점** — 써 놓고 안 읽히면 실패다."""
    mc = file_store
    # 되읽으면 아무것도 없다. `return_value`를 쓰면 **같은 dict가 재사용돼** 쓰기가 그 안에
    #   남는다 — 그러면 계약이 헛것을 잰다. 매번 새 빈 dict를 낸다.
    with patch.object(mc, "_load_all", side_effect=lambda *a, **k: {}):
        with pytest.raises(RuntimeError) as err:
            mc.save("seller-drop", "coupang", dict(OWNER_SIX))
    msg = str(err.value)
    assert "다시 읽히지 않습니다" in msg
    assert "COUPANG_RETURN_CENTER_CODE" in msg, f"어느 칸인지 말하지 않는다 — {msg}"


def test_a_good_save_reads_back_and_reports_success(file_store):
    """되읽히면 조용히 통과한다 — 검증이 멀쩡한 저장을 막지 않는다(무회귀)."""
    mc = file_store
    saved = mc.save("seller-ok", "coupang", dict(OWNER_SIX))
    assert saved["COUPANG_RETURN_CENTER_CODE"] == "1002166041"
    assert mc.get("seller-ok", "coupang")["COUPANG_RETURN_ZIP_CODE"] == "14600"


def test_unknown_field_names_are_refused_not_dropped(file_store):
    """★ 이 마켓에 없는 칸만 보내면 **400**이다 — 예전엔 아무것도 안 쓰고 200이었다."""
    mc = file_store
    with pytest.raises(ValueError) as err:
        mc.save("seller-bad", "coupang", {"COUPANG_RETURN_CODE": "1002166041"})
    assert "COUPANG_RETURN_CODE" in str(err.value), "버린 칸 이름을 말하지 않는다"


def test_the_route_answers_400_for_a_refused_save(clean_env, tmp_path):
    """라우트가 그 거부를 **400 + 사유**로 낸다(성공 위장 금지)."""
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    from src.seller_console import market_credentials as mc
    clean_env.setattr(mc, "_DATA_DIR", str(tmp_path), raising=False)
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-f34b"
        s["user_email"] = "a@b.c"
    with patch.object(mc, "_pg_links", return_value=None):
        r = c.post("/seller/markets/connect/coupang",
                   json={"values": {"NOT_A_FIELD": "x"}})
    assert r.status_code == 400, r.get_json()
    body = r.get_json()
    assert body["ok"] is False and "NOT_A_FIELD" in body["error"]


def test_a_prefilled_suggestion_is_not_a_saved_value(clean_env, tmp_path):
    """★ 오너가 본 그 화면 — Wing ID가 **차 있어 보여도** 저장값이 아니다.

    화면 모델이 둘을 구분해서 내야, 재오픈 화면이 「저장됐다」는 착각을 안 준다.
    """
    from src.seller_console import market_credentials as mc
    clean_env.setattr(mc, "_DATA_DIR", str(tmp_path), raising=False)
    for k, v in (("ACCESS_KEY", "a"), ("SECRET_KEY", "s"), ("VENDOR_ID", "A01381223")):
        clean_env.setenv(f"COUPANG_{k}", v)
    with patch.object(mc, "_pg_links", return_value=None):
        st = mc.status("seller-empty", "coupang")
    wing = [f for f in st["fields"] if f["env"] == "COUPANG_VENDOR_USER_ID"][0]
    assert wing["suggest"] == "shanks8"
    assert wing["has_value"] is False, "제안을 저장값으로 보고한다 — 그게 오너가 본 착시다"


# ---------------------------------------------------------------------------
# ④ 재발 방지 — 읽기 실패를 삼키는 자리를 남겨 두지 않는다
# ---------------------------------------------------------------------------

def test_every_decode_failure_branch_records_a_reason():
    """`_decode`가 `{}`를 내는 모든 갈래가 **사유를 남긴다**(주석이 아니라 코드로 잰다)."""
    import ast
    import inspect
    from src.db import market_links_pg as ml

    tree = ast.parse(inspect.getsource(ml._decode))
    empties = [n for n in ast.walk(tree)
               if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)
               and not n.value.keys]
    assert empties, "빈 dict 반환 갈래를 못 찾았다 — 계약이 헛것을 잰다"
    notes = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_note_read_error"]
    assert len(notes) >= 2, f"사유를 남기지 않는 갈래가 있다(빈 반환 {len(empties)}, 기록 {len(notes)})"


def test_read_state_is_the_single_judge():
    """화면 판정기가 자기만의 규칙을 다시 쓰지 않는다 — 저장소에게 묻는다."""
    import ast
    import inspect
    from src.seller_console import market_cred_view as V

    src = inspect.getsource(V._read_state)
    names = {n.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Attribute)}
    assert "read_state" in src, "market_credentials.read_state를 안 부른다"
    assert "_decode" not in src and "Fernet" not in names, "판정기를 새로 썼다"
