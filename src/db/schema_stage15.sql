-- src/db/schema_stage15.sql — AUTH-1: 이메일+비밀번호 계정(password_accounts).
--
-- ## 왜 생겼나(오너 실측 2026-09-30)
-- 이메일로 가입하면 「가입이 완료되었습니다」 → 같은 자격으로 로그인하면 「이메일 또는 비밀번호가 올바르지 않습니다」.
-- 계정 행은 Google Sheets `users`에 있었고, gspread 6 `get_all_records`가 문자열 "1"을 **숫자 1로** 바꿔 돌려준다 →
-- `active == "1"`이 늘 거짓 → 모든 시트 계정이 「비활성」으로 읽혀 **아무도 이메일로 로그인할 수 없었다.**
-- 게다가 시트 쓰기가 실패해도 경고 로그만 남고 화면은 「가입 완료」였다(쿼터 429·연결 실패 무음).
--
-- 그래서 비밀번호 계정은 **커밋이 확인되는 곳**(PG)에 둔다. 시트는 옛 계정을 읽어 오는 입구로만 남는다
-- (첫 로그인 때 이 표로 옮겨 적는다 — 해시 그대로, 새로 만들지 않는다).
--
-- 저장하는 것: 비밀번호 **해시**(bcrypt)·토큰(인증·재설정). 평문 비밀번호는 오지 않는다.
-- `email_verified`는 유지하되 로그인 조건은 env `AUTH_REQUIRE_EMAIL_VERIFY`(기본 0)가 정한다.

CREATE TABLE IF NOT EXISTS password_accounts (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          text NOT NULL,
  email            text NOT NULL,                  -- 소문자 정규화
  name             text NOT NULL DEFAULT '',
  role             text NOT NULL DEFAULT 'seller',
  password_hash    text NOT NULL,
  email_verified   boolean NOT NULL DEFAULT false,
  verify_token     text NOT NULL DEFAULT '',
  reset_token      text NOT NULL DEFAULT '',
  reset_token_exp  timestamptz,
  source           text NOT NULL DEFAULT 'signup',  -- signup | sheets(옛 시트에서 옮김)
  last_login_at    timestamptz,
  deleted_at       timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

-- 한 이메일은 한 계정 — 두 번 가입하면 두 번째가 **실패**한다(덮어쓰지 않는다).
CREATE UNIQUE INDEX IF NOT EXISTS uq_password_accounts_email
  ON password_accounts (email)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_password_accounts_user
  ON password_accounts (user_id)
  WHERE deleted_at IS NULL;
