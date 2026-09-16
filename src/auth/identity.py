"""src/auth/identity.py — 로그인 정체성 한 곳 (C-F19).

## 실측 (오너 2026-09-13 16:02)

PC에서 구글(`cigua7134@gmail.com`)로 로그인했더니 **「신규 셀러 가입」 알림**이 뜨고
새 `user_id`가 났다 — 「수집한 상품」 0건. 어제 hanmail(`shanks8@hanmail.net`) 로그인은
**또 다른 UUID**였다. 정작 데이터를 쥔 UUID는 세 번째였다:
활성 토큰 2 · 초안 3+ · 확장 연결 · 텔레그램 `(gogaBridz_bot, chat)` 매핑.

즉 **로그인할 때마다 정체성이 새로 났다.** 근원은 C-F17-A1(`user_store`가 없는 이름을
import해 늘 실패 → `find_by_email`이 언제나 None → 매번 `User.new()`)이고, 그 파손을
고친 뒤에도 **이미 흩어진 정체성은 저절로 모이지 않는다.**

> ★★★ 「없으면 새로 만든다」가 유일한 규칙이면, **못 찾을 때마다 사람이 는다.**
> 찾기가 실패할 수 있는 한, 만들기 앞에 **기억해 둔 표**가 있어야 한다.

## 무엇을 고정하나

정본 `user_id`는 **데이터를 쥔 쪽**이다(빈 쪽으로 맞추면 데이터가 고아가 된다).
`(provider, email) → user_id` 표를 두고, 로그인 경로는 **이 표를 먼저** 본다.

## 병합 규칙 — 증명 없이는 옮기지 않는다

F18로 이 서비스는 **여러 사람이 쓴다.** 그러니 「고아 UUID를 정본으로 합친다」를
무조건 돌리면 **남의 데이터를 내 계정으로 옮기는 코드**가 된다.
그래서 옮기는 조건은 하나다 — 그 UUID의 이메일이 **정체성 표에서 정본으로 매핑될 때만.**
확인할 수 없으면 **세지만 하고 옮기지 않는다**(표로 보고).
"""
from __future__ import annotations

import logging
import os
import uuid as _uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 오너 정본(실측으로 확정). env로 덮을 수 있으나 **기본값이 정답**이라
#   배포만 하면 오너가 Shell을 열 일이 없다(F19-8).
OWNER_USER_ID = os.getenv("OWNER_CANONICAL_USER_ID", "f275b60d-9728-4349-9f44-00cedb037516").strip()
OWNER_PRIMARY_EMAIL = os.getenv("OWNER_PRIMARY_EMAIL", "shanks8@hanmail.net").strip().lower()
OWNER_DISPLAY_NAME = os.getenv("OWNER_DISPLAY_NAME", "고가").strip()

# 오너가 실제로 쓰는 로그인 둘 — 실측(2026-09-13).
OWNER_LOGINS = (
    ("password", OWNER_PRIMARY_EMAIL),      # 이메일+비밀번호
    ("google", os.getenv("OWNER_GOOGLE_EMAIL", "cigua7134@gmail.com").strip().lower()),
)

# ---------------------------------------------------------------------------
# 사용자 단위 데이터를 가진 표 — **전수**
# ---------------------------------------------------------------------------
# F29 실측(2026-09-16): 오너가 과거 입력한 쿠팡 자격이 등록 사전검증에서 「미입력」인데
#   대시보드는 같은 계정을 「자격 설정됨」이라고 했다. 자격 행이 **고아 UUID**에 남아 있었다.
#
#   F19는 병합 대상을 **셋으로 열거**했고 주석에 「오너가 지목한 셋」이라고 적었다.
#   지목은 그때의 예시였는데 그게 **목록이 되어 굳었다** — 그 뒤에 늘어난 표
#   (소싱 원칙·번역 작업·이미지 번역 사용량·채점·번역본 바이트…)는 아무도 안 옮겼다.
#
# > 열거는 굳는다. **스키마가 정본이고, 목록은 스키마를 따라간다** —
# > 계약이 `src/db/schema_stage*.sql`을 순회해 여기 빠진 표가 있으면 빨개진다.
#
#   (테이블, 스코프 컬럼, 사람이 읽는 이름, PK 컬럼, 소프트삭제 있음, 충돌 정책)
#
#   충돌 정책 — 유일 제약에 걸렸을 때 고아 쪽을 어떻게 할지:
#     "fold" : 고아 행을 소프트삭제한다. **같은 것이 양쪽에 있는 게 확실한 표만.**
#     "keep" : 그대로 둔다(보고만). 지우면 되돌릴 수 없는 것 — 주문·자격·과금 기록.
#   기본은 **keep**이다. 지우는 쪽을 기본값으로 두면 한 번의 충돌이 데이터를 먹는다.
USER_SCOPED_TABLES = (
    ("collect_history", "user_id", "초안", "id", True, "fold"),
    ("user_tokens", "user_id", "토큰", "id", True, "keep"),
    ("telegram_links", "user_id", "텔레그램 매핑", "id", True, "fold"),
    ("market_links", "user_id", "마켓 자격", "id", True, "keep"),
    ("sourcing_rules", "user_id", "소싱 원칙", "id", True, "keep"),
    ("translation_jobs", "user_id", "번역 작업", "id", True, "keep"),
    ("settings", "user_id", "가격 정책", "user_id", False, "keep"),
    ("settings_history", "user_id", "설정 이력", "id", False, "keep"),
    ("image_translate_usage", "user_id", "이미지 번역 사용량", "id", False, "keep"),
    ("image_bench_runs", "user_id", "이미지 번역 채점", "id", False, "keep"),
    ("image_ko_blobs", "seller_id", "번역본 이미지", "", False, "keep"),
    ("orders", "user_id", "주문", "id", True, "keep"),
)

# `user_identities`는 **스코프 컬럼이 있어도 옮기지 않는다** — 이 표가 「어느 로그인이 누구인가」의
#   정본이다. 여기의 user_id를 정본으로 덮으면 고아를 가리키던 줄까지 정본을 가리켜,
#   **무엇이 고아였는지 알 수 없게 된다**(되돌림도 같이 죽는다).
NEVER_MERGE = ("user_identities", "identity_merge_backup")

# 하위 호환 — 옛 이름으로 부르는 자리가 남아 있다. 이제 **전수**를 가리킨다.
MERGE_TABLES = tuple((t, c, label) for t, c, label, _pk, _soft, _pol in USER_SCOPED_TABLES)
REPORT_TABLES = ()


def _table_meta(table: str) -> tuple:
    for row in USER_SCOPED_TABLES:
        if row[0] == table:
            return row
    return (table, "user_id", table, "id", True, "keep")


def _pg_ok() -> bool:
    try:
        from src.db import pg
        return bool(pg.pg_enabled())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 조회 — 로그인 경로가 쓰는 얼굴
# ---------------------------------------------------------------------------

def resolve_user_id(provider: str, email: str) -> str:
    """이 로그인이 **이미 아는 사람**인가 → 정본 user_id, 모르면 빈 문자열.

    ① `(provider, email)` 정확 일치 → ② 같은 이메일의 **다른 프로바이더** 등록
    (구글로 처음 들어와도 hanmail로 등록된 사람이면 같은 사람이다 —
    이메일 소유 증명은 프로바이더가 한다) → ③ 토큰 저장소의 별칭(이메일로 발급된 토큰).
    """
    try:
        from src.db import user_identities_pg as store
        hit = store.resolve(provider, email) or store.resolve_any_provider(email)
        if hit:
            return hit
    except Exception as exc:
        logger.warning("정체성 조회 실패: %s", exc)
    return user_id_from_tokens(email)


def user_id_from_tokens(email: str) -> str:
    """토큰 저장소에 **이 이메일로 발급된** 토큰이 있으면 그 user_id를 재사용한다.

    옛 경로가 user_id 대신 이메일을 스코프로 쓴 적이 있다(관용 식별자, v9).
    새로 만들기 **전에** 한 번 더 찾아보는 자리다 — 만들면 되돌리기 어렵다.
    """
    mail = str(email or "").strip().lower()
    if not mail:
        return ""
    try:
        from src.auth.personal_tokens import list_tokens
        for row in list_tokens(mail, user_ids={mail}) or []:
            if not row.get("revoked"):
                return mail
    except Exception as exc:
        logger.warning("토큰 저장소 별칭 조회 실패: %s", exc)
    return ""


def register_login(provider: str, email: str, user_id: str, *,
                   primary: bool = False, display_name: str = "") -> bool:
    """이 로그인을 이 사람 것으로 적어 둔다(다음부터는 새로 만들지 않는다)."""
    try:
        from src.db import user_identities_pg as store
        return store.register(provider, email, user_id,
                              is_primary=primary, display_name=display_name)
    except Exception as exc:
        logger.warning("정체성 등록 실패: %s", exc)
        return False


def known_email(email: str) -> bool:
    """이미 아는 이메일인가 — 「신규 셀러 가입」 알림을 **처음 한 번만** 보내기 위한 판단."""
    try:
        from src.db import user_identities_pg as store
        return bool(store.resolve_any_provider(email))
    except Exception:
        return False


def profile(user_id: str) -> dict:
    """`{email, display_name}` — 화면·회신에 쓸 대표값. 없으면 빈 dict."""
    try:
        from src.db import user_identities_pg as store
        return store.profile(user_id)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# 부팅 시 1회 — 정본 고정 · 흡수 · 병합
# ---------------------------------------------------------------------------

def _counts_for(user_id: str) -> dict:
    """이 user_id에 붙은 데이터 건수(병합 대상 + 보고 전용)."""
    out = {}
    if not _pg_ok():
        return out
    from src.db import pg
    for table, col, label, _pk, soft, _pol in USER_SCOPED_TABLES:
        # 표마다 소프트삭제 칸이 있기도 없기도 하다(`settings`엔 없다) — 있으면 살아 있는 행만,
        #   없으면 전부 센다. 없다고 **-1(못 셌다)로 두면 빈 고아가 영영 흡수되지 못한다.**
        wheres = ((f"{col} = %s AND deleted_at IS NULL", f"{col} = %s") if soft
                  else (f"{col} = %s",))
        for where in wheres:
            try:
                with pg.query() as cur:
                    cur.execute(f"SELECT count(*) FROM {table} WHERE {where}", (user_id,))
                    out[label] = int((cur.fetchone() or [0])[0])
                break
            except Exception:
                out[label] = -1    # 못 셌다 — 0으로 적지 않는다(정직)
    return out


def _orphan_user_ids() -> set:
    """병합 대상 표들에 있는 **정본이 아닌** user_id 전부."""
    found = set()
    if not _pg_ok():
        return found
    from src.db import pg
    for table, col, _label, _pk, soft, _pol in USER_SCOPED_TABLES:
        if table in NEVER_MERGE:
            continue
        where = " WHERE deleted_at IS NULL" if soft else ""
        try:
            with pg.query() as cur:
                cur.execute(f"SELECT DISTINCT {col} FROM {table}{where}")
                found |= {str(r[0]) for r in cur.fetchall() if r[0]}
        except Exception as exc:
            logger.warning("[정체성] %s 스캔 실패: %s", table, exc)
    found.discard(OWNER_USER_ID)
    found.discard("")
    return found


def _email_of(user_id: str) -> str:
    """이 user_id의 이메일 — 정체성 표 우선, 없으면 사용자 저장소(시트)."""
    prof = profile(user_id)
    if prof.get("email"):
        return prof["email"]
    try:
        from src.auth.user_store import get_store
        u = get_store().find_by_id(user_id)
        return str(getattr(u, "email", "") or "").strip().lower() if u else ""
    except Exception:
        return ""


def _merge_into_canonical(orphan_id: str, batch_id: str) -> dict:
    """고아 UUID의 데이터를 정본으로 옮긴다. **옮기기 전 값을 백업표에 먼저 적는다.**

    텔레그램 매핑은 `(bot_slug, chat_id)`가 유일하다 — 정본이 이미 같은 자리를 쓰고 있으면
    옮기지 않고 **고아 쪽을 소프트삭제**한다(유일성 충돌로 실패하느니).
    수집 초안도 `(user_id, product_key)`가 유일하다 — 같은 상품이 양쪽에 있으면 같은 처리.
    """
    from src.db import pg, user_identities_pg as idstore
    moved = {}
    for table, col, label, pk, soft, policy in USER_SCOPED_TABLES:
        if table in NEVER_MERGE:
            continue
        live = f"{col} = %s AND deleted_at IS NULL" if soft else f"{col} = %s"
        try:
            # 되돌릴 수 있게 **먼저 적는다.** PK가 없는 표(`image_ko_blobs`)는 스코프 컬럼을
            #   행 키로 쓴다 — 되돌림은 「이 표에서 정본인 행을 고아로」 되돌리는 단위면 충분하다.
            with pg.query() as cur:
                cur.execute(f"SELECT {pk or col} FROM {table} WHERE {live}", (orphan_id,))
                ids = [str(r[0]) for r in cur.fetchall()]
            if not ids:
                moved[label] = 0
                continue
            idstore.backup_rows(batch_id, [(table, rid, col, orphan_id, OWNER_USER_ID)
                                           for rid in ids])
            with pg.tx() as cur:
                cur.execute(f"UPDATE {table} SET {col} = %s WHERE {live}",
                            (OWNER_USER_ID, orphan_id))
                moved[label] = int(cur.rowcount or 0)
        except Exception as exc:
            # 유일성 충돌 등. **기본은 그대로 두는 것**이다 — 지우는 쪽을 기본값으로 두면
            #   한 번의 충돌이 주문·자격·과금 기록을 먹는다(되돌릴 수 없다).
            if policy != "fold" or not soft:
                logger.warning("[정체성] %s 병합 충돌 — **남겨 둔다**(정책 %s): %s",
                               table, policy, exc)
                moved[label] = -2          # -2 = 충돌로 남겨 둠(0건과 다른 뜻)
                continue
            logger.warning("[정체성] %s 병합 충돌 — 겹치는 행을 접는다: %s", table, exc)
            try:
                with pg.tx() as cur:
                    cur.execute(f"UPDATE {table} SET deleted_at = now() "
                                f"WHERE {col} = %s AND deleted_at IS NULL", (orphan_id,))
                moved[label] = 0
            except Exception as exc2:
                logger.warning("[정체성] %s 접기도 실패: %s", table, exc2)
                moved[label] = -1
    return moved


def restore_batch(batch_id: str) -> dict:
    """병합을 **되돌린다**. 백업표에 적힌 그대로 스코프 컬럼을 옛 값으로 돌려놓는다.

    F29 실측: 백업 코드는 있고 「되돌릴 수 있어야 병합해도 된다」고 적혀 있는데
    **되돌리는 코드가 없었다.** 되돌릴 수 없는 백업은 백업이 아니라 기록이다.
    """
    out = {"batch": batch_id, "restored": {}, "failed": {}}
    if not _pg_ok():
        out["reason"] = "PG 미설정 — 되돌릴 대상이 없습니다"
        return out
    from src.db import pg
    try:
        with pg.query() as cur:
            cur.execute("SELECT table_name, row_id, field, old_value FROM identity_merge_backup "
                        "WHERE batch_id = %s", (batch_id,))
            rows = cur.fetchall()
    except Exception as exc:
        out["reason"] = f"백업 조회 실패: {type(exc).__name__}"
        return out
    if not rows:
        out["reason"] = "그 배치의 백업이 없습니다"
        return out
    for table_name, row_id, field, old_value in rows:
        table = str(table_name)
        if table in NEVER_MERGE or not any(t == table for t, *_ in USER_SCOPED_TABLES):
            out["failed"][table] = "알 수 없는 표 — 건드리지 않음"
            continue
        _t, _c, _label, pk, _soft, _pol = _table_meta(table)
        key = pk or str(field)
        try:
            with pg.tx() as cur:
                cur.execute(f"UPDATE {table} SET {field} = %s WHERE {key} = %s",
                            (str(old_value), str(row_id)))
                out["restored"][table] = out["restored"].get(table, 0) + int(cur.rowcount or 0)
        except Exception as exc:
            out["failed"][table] = f"{type(exc).__name__}"
    return out


def dry_run() -> dict:
    """**옮기지 않고** 보여 준다 — 고아 UUID마다 표별 행 수.

    오너 Shell 없이 화면에서 보게 하려고 따로 뺐다. 「어느 UUID에 마켓 자격이 있나」는
    여기서 답이 나온다. 숫자는 전부 실측이고, 못 센 표는 **-1(못 셌다)**로 둔다(0이 아니다).
    """
    out = {"canonical": OWNER_USER_ID, "orphans": [], "tables": [], "reason": ""}
    out["tables"] = [{"table": t, "label": label, "scope": c}
                     for t, c, label, _pk, _soft, _pol in USER_SCOPED_TABLES]
    if not _pg_ok():
        out["reason"] = "PG 미설정 — 셀 수 있는 표가 없습니다"
        return out
    out["canonical_counts"] = _counts_for(OWNER_USER_ID)
    for uid in sorted(_orphan_user_ids()):
        counts = _counts_for(uid)
        out["orphans"].append({"user_id": uid, "email": _email_of(uid),
                               "counts": counts,
                               "total": sum(v for v in counts.values() if v > 0)})
    return out


def _deactivate_user_record(user_id: str) -> bool:
    """빈 고아 레코드를 **폐기**(active=0) — 조회에서 사라진다. 시트가 닿지 않으면 False."""
    try:
        from src.auth.user_store import get_store
        store = get_store()
        u = store.find_by_id(user_id)
        if u is None:
            return False
        u.active = False
        store.update(u)
        return True
    except Exception as exc:
        logger.warning("[정체성] 고아 레코드 폐기 실패: %s", exc)
        return False


def bootstrap(*, merge: bool = True) -> dict:
    """배포와 함께 자동으로 도는 **멱등** 정리. 오너 Shell 불필요(F19-8).

    ① 정본 사용자 레코드 보장(이름 「고가」) ② 로그인 두 줄 등록
    ③ 고아 UUID 표를 로그에 남기고, **같은 사람임이 증명된 것만** 병합.

    반환은 보고용 dict — 부팅을 막지 않는다(어떤 단계가 실패해도 예외를 삼키고 사유를 남긴다).
    """
    report = {"canonical": OWNER_USER_ID, "registered": [], "orphans": [],
              "merged": [], "absorbed": [], "skipped": []}

    # ① 정본 사용자 레코드 — 있으면 갱신, 없으면 생성.
    try:
        from src.auth.models import User
        from src.auth.user_store import get_store
        store = get_store()
        u = store.find_by_id(OWNER_USER_ID)
        if u is None:
            u = User(user_id=OWNER_USER_ID, email=OWNER_PRIMARY_EMAIL, name=OWNER_DISPLAY_NAME,
                     role="admin", email_verified=True, active=True,
                     created_at=datetime.now(timezone.utc).isoformat())
            store.create(u)
            report["user_record"] = "created"
        else:
            changed = False
            if not u.name:
                u.name, changed = OWNER_DISPLAY_NAME, True
            if not u.email:
                u.email, changed = OWNER_PRIMARY_EMAIL, True
            if changed:
                store.update(u)
            report["user_record"] = "updated" if changed else "ok"
    except Exception as exc:
        # 시트가 닿지 않아도 정체성 표(PG)만으로 이름을 말할 수 있다 — 부팅은 계속한다.
        logger.warning("[정체성] 정본 사용자 레코드 처리 실패(계속): %s", exc)
        report["user_record"] = "unavailable"

    # ② 로그인 두 줄.
    for prov, mail in OWNER_LOGINS:
        if not mail:
            continue
        if register_login(prov, mail, OWNER_USER_ID,
                          primary=(mail == OWNER_PRIMARY_EMAIL),
                          display_name=OWNER_DISPLAY_NAME):
            report["registered"].append(f"{prov}:{mail}")

    # ③ 고아 UUID.
    if not _pg_ok():
        report["skipped"].append("PG 미설정 — 고아 스캔·병합 없음")
        return report

    batch_id = f"f19-{_uuid.uuid4().hex[:12]}"
    for orphan in sorted(_orphan_user_ids()):
        counts = _counts_for(orphan)
        mail = _email_of(orphan)
        same_person = bool(mail) and resolve_user_id("", mail) == OWNER_USER_ID
        # 세 갈래다 — **「못 셌다」를 「비었다」로 읽지 않는다.** 그렇게 읽으면
        #   세는 데 실패한 계정을 빈 계정으로 보고 **폐기**하게 된다(계약이 이걸 잡았다).
        unknown = any(v < 0 for v in counts.values() if isinstance(v, int)) or not counts
        has_data = any(v > 0 for v in counts.values() if isinstance(v, int))
        report["orphans"].append({"user_id": orphan, "email": mail or "(모름)",
                                  "counts": counts, "same_person": same_person})
        if not same_person:
            # **증명 없이는 옮기지 않는다** — 여긴 여러 사람이 쓰는 서비스다.
            report["skipped"].append(f"{orphan}: 같은 사람임을 확인 못 함")
            continue
        if unknown and not has_data:
            report["skipped"].append(f"{orphan}: 건수를 세지 못함 — 손대지 않음")
            continue
        if has_data and merge:
            report["merged"].append({"user_id": orphan, "moved": _merge_into_canonical(orphan, batch_id)})
            _deactivate_user_record(orphan)
        elif not has_data:
            # 데이터 0 — 옮길 게 없다. 정체성만 흡수하고 레코드를 폐기한다.
            if mail:
                register_login("google" if "@gmail" in mail else "password", mail, OWNER_USER_ID,
                               display_name=OWNER_DISPLAY_NAME)
            report["absorbed"].append({"user_id": orphan, "email": mail or "(모름)",
                                       "record_discarded": _deactivate_user_record(orphan)})

    logger.info("[정체성] 정본=%s 등록=%s 고아=%d 병합=%d 흡수=%d 보류=%d (배치 %s)",
                OWNER_USER_ID, report["registered"], len(report["orphans"]),
                len(report["merged"]), len(report["absorbed"]), len(report["skipped"]), batch_id)
    for row in report["orphans"]:
        logger.info("[정체성] 고아 %s · 이메일 %s · %s · 같은사람=%s",
                    row["user_id"], row["email"], row["counts"], row["same_person"])
    return report
