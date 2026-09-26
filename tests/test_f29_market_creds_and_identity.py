"""F29 계약 — 열거는 굳는다. 그리고 같은 값을 두 자리가 다르게 읽으면 한쪽은 거짓말이다.

## 실측 (오너 2026-09-16)

오너가 과거 입력한 쿠팡 자격이 **등록 사전검증에서 「미입력」**(누락 7필드).
같은 계정을 **대시보드는 「자격 설정됨」**이라고 표시. 한 화면이 다른 화면을 반박했다.

## 갈라 보니 원인이 둘

**① 병합 대상이 셋으로 굳어 있었다.** F19가 `MERGE_TABLES`를 셋으로 열거하고
주석에 「오너가 지목한 셋」이라 적었다. 지목은 그때의 예시였는데 **그게 목록이 되어 굳었다** —
그 뒤에 늘어난 표(소싱 원칙·번역 작업·이미지 번역 사용량·채점·번역본 바이트…)는
아무도 안 옮겼고, **마켓 자격(`market_links`)은 「세기만」 하는 쪽**에 있었다.

  → 이제 목록은 **스키마를 따라간다.** 이 계약이 `src/db/schema_stage*.sql`을 순회해
    사용자 스코프 컬럼을 가진 표가 목록에 없으면 빨개진다.

**② 등록 경로가 계정 없이 업로더를 만들었다.** `CoupangUploader()` — 계정이 없으면
배송·자격을 **무접두 이름으로만** 읽는다. 오너는 `COUPANG_GOGANE_*`로 넣어 뒀다.
그래서 이 경로에선 **자격이 아예 안 보였다**(대시보드는 접두를 읽으니 보였다).

  → 순서가 중요하다: **무접두가 먼저**다(셀러가 연동 화면에 넣은 자기 키).
    뒤집으면 **다른 셀러의 등록이 오너 계정 자격으로 나간다.**

라이브 호출 0 · 마켓 호출 0 · 자격 값 노출 0.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# ① 표 목록 — 스키마가 정본이다
# ---------------------------------------------------------------------------

def _schema_user_scoped() -> dict:
    """스키마 파일에서 **사용자 스코프 컬럼을 가진 표**를 직접 읽는다."""
    out = {}
    files = sorted(ROOT.glob("src/db/schema_stage*.sql"),
                   key=lambda p: int(re.search(r"\d+", p.name).group()))
    for p in files:
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);",
                             p.read_text(encoding="utf-8"), re.S):
            name, body = m.group(1), m.group(2)
            for col in ("user_id", "seller_id"):
                if re.search(rf"^\s*{col}\s+\w", body, re.M):
                    out[name] = col
                    break
    return out


def test_every_user_scoped_table_is_listed():
    """★ **F29의 판정 지점** — 스키마에 있는 사용자 스코프 표가 목록에 다 있다.

    새 stage가 늘면 이 계약이 먼저 빨개진다. 「지목한 셋」이 다시 굳지 않게.
    """
    from src.auth import identity
    listed = {t for t, *_ in identity.USER_SCOPED_TABLES} | set(identity.NEVER_MERGE)
    missing = sorted(set(_schema_user_scoped()) - listed)
    assert not missing, f"스키마에 있는데 목록에 없다: {missing}"


def test_scope_column_matches_the_schema():
    """스코프 칸 이름도 스키마와 같아야 한다 — `seller_id`인 표가 하나 있다."""
    from src.auth import identity
    schema = _schema_user_scoped()
    for table, col, *_ in identity.USER_SCOPED_TABLES:
        assert schema.get(table) == col, f"{table}: 목록 {col} · 스키마 {schema.get(table)}"


def test_market_links_is_merged_now_not_merely_counted():
    """마켓 자격이 **옮겨지는** 목록에 있다 — 이게 오너 증상의 뿌리였다."""
    from src.auth import identity
    names = {t for t, *_ in identity.USER_SCOPED_TABLES}
    assert "market_links" in names
    assert identity.MERGE_TABLES, "빈 목록이면 아무것도 안 옮긴다"
    assert "market_links" in {t for t, _c, _l in identity.MERGE_TABLES}


def test_identity_tables_are_never_merged():
    """정체성 표 자신은 안 옮긴다 — 옮기면 **무엇이 고아였는지** 알 수 없게 된다."""
    from src.auth import identity
    assert "user_identities" in identity.NEVER_MERGE
    assert "identity_merge_backup" in identity.NEVER_MERGE
    merged = {t for t, *_ in identity.USER_SCOPED_TABLES}
    assert not (merged & set(identity.NEVER_MERGE))


def test_conflict_policy_defaults_to_keeping_rows():
    """충돌 시 **기본은 남기는 것**. 지우는 쪽이 기본이면 한 번의 충돌이 데이터를 먹는다."""
    from src.auth import identity
    folds = {t for t, _c, _l, _pk, _s, pol in identity.USER_SCOPED_TABLES if pol == "fold"}
    # 접기가 허용된 표는 「같은 것이 양쪽에 있는 게 확실한」 것뿐이다.
    assert folds <= {"collect_history", "telegram_links"}, folds
    for risky in ("orders", "market_links", "user_tokens", "image_translate_usage"):
        pol = [p for t, _c, _l, _pk, _s, p in identity.USER_SCOPED_TABLES if t == risky]
        assert pol == ["keep"], f"{risky}: 충돌 시 지우면 되돌릴 수 없다"


def test_tables_without_soft_delete_are_marked():
    """`deleted_at`이 없는 표를 있다고 적어 두면 **쿼리가 통째로 터진다**."""
    from src.auth import identity
    schema_body = {}
    for p in ROOT.glob("src/db/schema_stage*.sql"):
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);",
                             p.read_text(encoding="utf-8"), re.S):
            schema_body[m.group(1)] = m.group(2)
    for table, _c, _l, _pk, soft, _pol in identity.USER_SCOPED_TABLES:
        real = "deleted_at" in schema_body.get(table, "")
        assert soft == real, f"{table}: 목록 soft={soft} · 스키마 {real}"


def test_dry_run_reports_without_moving_anything():
    """드라이런은 **옮기지 않는다**. PG가 없으면 그 사실을 말한다(0건이라고 하지 않는다)."""
    from src.auth import identity
    with patch.object(identity, "_pg_ok", return_value=False):
        out = identity.dry_run()
    assert out["canonical"] == identity.OWNER_USER_ID
    assert "PG 미설정" in out["reason"]
    assert out["orphans"] == []
    assert len(out["tables"]) == len(identity.USER_SCOPED_TABLES)


def test_restore_exists_and_refuses_unknown_tables():
    """되돌림이 **있다**. 없으면 백업은 백업이 아니라 기록일 뿐이다."""
    from src.auth import identity
    assert callable(getattr(identity, "restore_batch", None))
    with patch.object(identity, "_pg_ok", return_value=False):
        out = identity.restore_batch("batch-x")
    assert "PG 미설정" in out["reason"]


# ---------------------------------------------------------------------------
# ② 자격 판정 — 한 자리에서, 업로더가 읽을 그 자리를
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("COUPANG_"):
            monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_unprefixed_credentials_win(clean_env):
    """★ 무접두가 있으면 **계정 없음**(빈 문자열) — 셀러가 넣은 자기 키다.

    뒤집으면 다른 셀러의 등록이 오너 계정 자격으로 나간다.
    """
    from src.seller_console import market_cred_view as V
    clean_env.setenv("COUPANG_ACCESS_KEY", "seller-a")
    clean_env.setenv("COUPANG_SECRET_KEY", "seller-s")
    clean_env.setenv("COUPANG_VENDOR_ID", "A09999999")
    clean_env.setenv("COUPANG_GOGANE_ACCESS_KEY", "owner-a")
    clean_env.setenv("COUPANG_GOGANE_SECRET_KEY", "owner-s")
    clean_env.setenv("COUPANG_GOGANE_VENDOR_ID", "A01381223")
    assert V.resolve_upload_account() == ""


def test_account_prefixed_credentials_are_found_when_unprefixed_is_absent(clean_env):
    """★ 오너의 실제 상태 — 무접두가 없고 접두만 있으면 그 계정을 쓴다."""
    from src.seller_console import market_cred_view as V
    clean_env.setenv("COUPANG_GOGANE_ACCESS_KEY", "owner-a")
    clean_env.setenv("COUPANG_GOGANE_SECRET_KEY", "owner-s")
    clean_env.setenv("COUPANG_GOGANE_VENDOR_ID", "A01381223")
    assert V.resolve_upload_account() == "gogane"
    state = V.coupang_api_state()
    assert state["missing"] == [], state
    assert "gogane" in state["source"]


def test_prevalidate_sees_prefixed_shipping_fields(clean_env):
    """★★ **오너 증상 그대로** — 접두로 넣은 배송 7필드를 사전검증이 본다.

    예전엔 여기만 무접두를 봐서 「미입력 7필드」였다.
    """
    from src.seller_console.upload_dispatcher import UploadDispatcher
    for k, v in (("ACCESS_KEY", "a"), ("SECRET_KEY", "s"), ("VENDOR_ID", "A01381223"),
                 ("VENDOR_USER_ID", "shanks8"), ("RETURN_CENTER_CODE", "1000274592"),
                 ("OUTBOUND_SHIPPING_PLACE_CODE", "7437895"), ("RETURN_ZIP_CODE", "06000"),
                 ("RETURN_ADDRESS", "서울시 강남구 1"), ("RETURN_CHARGE_NAME", "반품담당"),
                 ("COMPANY_CONTACT_NUMBER", "02-1234-5678")):
        clean_env.setenv(f"COUPANG_GOGANE_{k}", v)
    res = UploadDispatcher().prevalidate({"title": "수행방패", "price": 9900}, ["coupang"])
    assert res[0].ok is True, res[0].hint


def test_missing_message_names_the_store_and_the_fields(clean_env):
    """F29-5: 「미입력」만 말하면 **이미 넣은 값을 또 넣게 된다**(오너가 그랬다)."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    res = UploadDispatcher().prevalidate({"title": "수행방패", "price": 9900}, ["coupang"])
    assert res[0].ok is False
    hint = res[0].hint
    assert "확인한 곳:" in hint, hint
    assert "비어 있는 값:" in hint
    # M1-1: 빈 칸은 **칸 이름**으로 말한다 — env 이름은 화면에 싣지 않는다(missing_envs에만).
    assert "반품지센터코드" in hint and "COUPANG_" not in hint, hint
    assert "COUPANG_RETURN_CENTER_CODE" in res[0].missing_envs


def test_unknown_is_not_reported_as_missing(clean_env):
    """조회 자체가 실패하면 **「없다」고 하지 않는다** — 정직 데이터의 같은 규칙."""
    from src.seller_console import market_cred_view as V
    with patch.object(V, "_uploader_reader", side_effect=RuntimeError("boom")):
        state = V.coupang_shipping_state("gogane")
    assert state["unknown"] is True
    assert state["missing"] == []
    assert "확인하지 못했습니다" in state["source"]


def test_upload_path_uses_the_same_account_as_the_check(clean_env):
    """★ 사전검증이 통과했는데 업로더가 다른 자리를 읽으면 **가짜 그린**이다."""
    src = (ROOT / "src/channel_sync/coupang_uploader.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "resolve_upload_account" in body, "등록 경로가 계정을 해석하지 않는다"
    assert "CoupangUploader(account=account)" in body


def test_credential_values_never_leave(clean_env):
    """자격 **값**은 어떤 응답에도 안 나간다 — 있는지 없는지와 어디서 왔는지만."""
    from src.seller_console import market_cred_view as V
    clean_env.setenv("COUPANG_GOGANE_ACCESS_KEY", "SUPER-SECRET-VALUE")
    clean_env.setenv("COUPANG_GOGANE_SECRET_KEY", "ANOTHER-SECRET")
    clean_env.setenv("COUPANG_GOGANE_VENDOR_ID", "A01381223")
    blob = json.dumps([V.coupang_api_state(), V.coupang_shipping_state()],
                      ensure_ascii=False)
    assert "SUPER-SECRET-VALUE" not in blob
    assert "ANOTHER-SECRET" not in blob


# ---------------------------------------------------------------------------
# ③ Wing 로그인 ID — 미리 채우되 덮지 않는다
# ---------------------------------------------------------------------------

def test_wing_id_is_suggested_per_business(clean_env):
    """오너 실값 — 고가네 shanks8 · 우주대행 chrisvaud."""
    from src.seller_console import market_cred_view as V
    assert V.WING_USER_IDS["gogane"] == "shanks8"
    assert V.WING_USER_IDS["woojoo"] == "chrisvaud"


def test_a_saved_wing_id_is_not_overwritten(clean_env):
    """사람이 고친 값을 **상수가 덮지 않는다** — 그건 도움이 아니다."""
    from src.seller_console import market_cred_view as V
    clean_env.setenv("COUPANG_GOGANE_ACCESS_KEY", "a")
    clean_env.setenv("COUPANG_GOGANE_SECRET_KEY", "s")
    clean_env.setenv("COUPANG_GOGANE_VENDOR_ID", "A01381223")
    clean_env.setenv("COUPANG_GOGANE_VENDOR_USER_ID", "somebody-else")
    assert V.coupang_wing_user_id() == "somebody-else"


def test_no_suggestion_for_another_seller(clean_env):
    """다른 셀러(무접두 자기 키)에겐 **아무것도 제안하지 않는다** — 남의 아이디다."""
    from src.seller_console import market_credentials as mc
    clean_env.setenv("COUPANG_ACCESS_KEY", "seller-a")
    clean_env.setenv("COUPANG_SECRET_KEY", "seller-s")
    clean_env.setenv("COUPANG_VENDOR_ID", "A09999999")
    assert mc._suggest_value("COUPANG_VENDOR_USER_ID") == ""


def test_secrets_are_never_suggested(clean_env):
    """비밀값 칸엔 제안이 붙지 않는다."""
    from src.seller_console import market_credentials as mc
    st = mc.status("u1", "coupang")
    for f in st["fields"]:
        if f["secret"]:
            assert not f.get("suggest"), f["env"]


def test_the_screen_says_it_prefilled(clean_env):
    """말없이 채우면 사람은 **자기가 넣은 값인 줄 안다**."""
    tpl = (ROOT / "src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")
    assert "f.suggest" in tpl
    assert "미리 채워 뒀어요" in tpl


# ---------------------------------------------------------------------------
# ④ 감사 화면 — 오너가 Shell을 열지 않는다
# ---------------------------------------------------------------------------

def _admin_client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
        s["user_role"] = "admin"
    return c


def test_audit_screen_renders_and_lists_every_table():
    from src.auth import identity
    r = _admin_client().get("/seller/admin/identity-audit")
    assert r.status_code == 200, r.status_code
    html = r.get_data(as_text=True)
    for table, *_ in identity.USER_SCOPED_TABLES:
        assert table in html, table


def test_audit_screen_is_admin_only():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u2"
        s["user_email"] = "x@y.z"
    r = c.get("/seller/admin/identity-audit")
    assert r.status_code in (302, 403), r.status_code


def test_image_storage_screen_is_admin_only_too():
    """★ F27에서 내가 낸 구멍 — 이름이 `require_admin`인 가드가 **로그인만** 봤다.

    관리자 화면 둘 다 진짜 관리자만. 남의 저장소 상태·UUID가 보이는 화면이다.
    """
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u2"
        s["user_email"] = "x@y.z"
    for path in ("/seller/admin/image-storage", "/seller/admin/identity-audit"):
        assert c.get(path).status_code in (302, 403), path
    assert c.post("/seller/admin/image-storage/backfill").status_code in (302, 403)
    assert c.post("/seller/admin/identity-audit/restore",
                  json={"batch_id": "x"}).status_code in (302, 403)
