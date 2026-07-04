-- src/db/schema_stage1.sql — Google Sheets → Supabase Postgres 이관 1단계 스키마.
-- 버그 최다 테이블 2개: collect_history(수집이력), user_tokens(수집기 토큰).
-- 공통: 고유 PK(uuid), user_id 스코프, deleted_at(소프트삭제), created_at/updated_at.
-- idempotent(IF NOT EXISTS) — init_schema()가 매 부팅 안전 실행.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- updated_at 자동 갱신 트리거 함수
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── 수집이력 ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS collect_history (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      text NOT NULL DEFAULT '',
  product_key  text,                        -- 도메인+goods_id 정규화(중복수집 방지 겸용)
  source       text NOT NULL DEFAULT '',
  domain       text NOT NULL DEFAULT '',
  url          text NOT NULL DEFAULT '',
  title        text NOT NULL DEFAULT '',
  image_url    text NOT NULL DEFAULT '',
  price        text NOT NULL DEFAULT '',
  currency     text NOT NULL DEFAULT '',
  status       text NOT NULL DEFAULT 'ok',
  preview_url  text NOT NULL DEFAULT '',
  extra_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
  deleted_at   timestamptz,                 -- 소프트삭제(NULL=활성)
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

-- 셀러 스코프 내 product_key 유니크(활성 행만) — 같은 상품 재수집 시 중복 0.
CREATE UNIQUE INDEX IF NOT EXISTS uq_collect_history_user_key
  ON collect_history (user_id, product_key)
  WHERE product_key IS NOT NULL AND product_key <> '' AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_collect_history_user
  ON collect_history (user_id) WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_collect_history_updated ON collect_history;
CREATE TRIGGER trg_collect_history_updated BEFORE UPDATE ON collect_history
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── 수집기 토큰 ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_tokens (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       text NOT NULL,
  token_hash    text NOT NULL,               -- 해시만 저장(시크릿 원문 저장 0)
  token_prefix  text NOT NULL DEFAULT '',     -- 마스킹 표시용
  scopes        text NOT NULL DEFAULT '',
  status        text NOT NULL DEFAULT 'active',   -- active/revoked
  last_used_at  timestamptz,
  expires_at    timestamptz,
  deleted_at    timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_tokens_hash
  ON user_tokens (token_hash) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_user_tokens_user
  ON user_tokens (user_id) WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_user_tokens_updated ON user_tokens;
CREATE TRIGGER trg_user_tokens_updated BEFORE UPDATE ON user_tokens
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
