-- src/db/schema_stage8.sql — C-F19: 로그인 정체성(user_identities) + 되돌림 백업.
--
-- 왜 생겼나(실측 2026-09-13 16:02, 오너): PC에서 구글로 로그인했더니 「신규 셀러 가입」 알림이
-- 뜨고 **새 user_id**가 났다 — 수집 0건. 어제 hanmail 로그인은 또 다른 UUID였다.
-- 데이터를 쥔 UUID는 따로 있었다(토큰 2 · 초안 3+ · 확장 연결 · 텔레그램 매핑).
-- 즉 **로그인할 때마다 정체성이 새로 났다.** 근원은 C-F17-A1(user_store import 파손)이고,
-- 그 파손이 고쳐진 뒤에도 이미 흩어진 정체성은 저절로 모이지 않는다.
--
-- 그래서 **(provider, email) → user_id** 를 한 곳에 적어 둔다. 로그인 경로는 이 표를 먼저 본다.
-- 표에 없을 때만 새로 만든다 — 「없으면 새로 만든다」가 유일한 규칙이면, 못 찾을 때마다 사람이 는다.
--
-- 저장하는 것: provider · email(소문자) · user_id · 대표 여부 · 표시 이름.
-- **저장하지 않는 것: 비밀번호·토큰.** 여긴 "누가 누구인가"만 적는다.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS user_identities (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider     text NOT NULL,                    -- google|kakao|naver|apple|password|bootstrap
  email        text NOT NULL,                    -- 소문자 정규화
  user_id      text NOT NULL,                    -- 정본 식별자
  is_primary   boolean NOT NULL DEFAULT false,   -- 화면·회신에 쓸 대표 이메일
  display_name text NOT NULL DEFAULT '',
  deleted_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

-- 한 (provider, email)은 한 사람에게만 간다. 다시 등록하면 갈아끼운다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_identities_active
  ON user_identities (provider, email)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_user_identities_user
  ON user_identities (user_id)
  WHERE deleted_at IS NULL;

-- 이메일만으로도 찾는다(어느 프로바이더로 들어왔든 같은 사람인지 보려고).
CREATE INDEX IF NOT EXISTS ix_user_identities_email
  ON user_identities (email)
  WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_user_identities_updated_at ON user_identities;
CREATE TRIGGER trg_user_identities_updated_at
  BEFORE UPDATE ON user_identities
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- 병합 백업 — **되돌릴 수 있어야 병합해도 된다.**
-- 흩어진 UUID의 데이터를 정본으로 옮길 때, 옮기기 전 값을 여기 먼저 적는다.
-- 한 줄이 한 칸이다(어느 표의 어느 행의 어느 칸이 무엇에서 무엇으로).
CREATE TABLE IF NOT EXISTS identity_merge_backup (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id   text NOT NULL,                      -- 한 번의 병합 실행
  table_name text NOT NULL,
  row_id     text NOT NULL,
  field      text NOT NULL DEFAULT 'user_id',
  old_value  text NOT NULL DEFAULT '',
  new_value  text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_identity_merge_backup_batch
  ON identity_merge_backup (batch_id);
