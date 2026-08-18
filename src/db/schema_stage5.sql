-- src/db/schema_stage5.sql — v88-B: 백그라운드 번역 작업 큐(translation_jobs).
-- 설계 = docs/design/background-translation.md §2. stage1 관례 그대로(uuid·user_id·status·soft-delete·트리거).
-- 번역을 요청 경로에서 워커로 분리: 요청은 등록만(pending), 워커가 SKIP LOCKED로 드레인해 체인 호출.
-- 불변: 체인·요청예산 캡·쿼터 회계 무손대. PG 미가동이면 이 테이블 없음 → 기존 동기 경로+캡(무회귀).

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS translation_jobs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        text NOT NULL DEFAULT '',
  item_id        text NOT NULL,                    -- collect_history 항목
  status         text NOT NULL DEFAULT 'pending',  -- pending|running|success|failed
  attempts       int  NOT NULL DEFAULT 0,
  max_attempts   int  NOT NULL DEFAULT 3,          -- queue_manager _MAX_RETRIES 재사용
  priority       int  NOT NULL DEFAULT 0,          -- 드로어 단건 > 벌크
  provider       text NOT NULL DEFAULT '',         -- 성공 프로바이더(계측)
  cause          text NOT NULL DEFAULT '',         -- 실패 원인 4분(W7a: budget/quota/rate_limit/auth)
  error          text NOT NULL DEFAULT '',
  result_json    jsonb NOT NULL DEFAULT '{}'::jsonb,-- title_ko/desc_ko/attempts/detected_lang/필드상태
  idem_key       text NOT NULL,                    -- user_id|item_id (활성 중복 방지)
  locked_by      text NOT NULL DEFAULT '',
  locked_at      timestamptz,
  started_at     timestamptz,
  finished_at    timestamptz,
  deleted_at     timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

-- 활성 idempotency: 같은 항목의 미완 작업 중복 금지(재클릭 폭주 방어).
CREATE UNIQUE INDEX IF NOT EXISTS uq_txjob_active_idem ON translation_jobs (idem_key)
  WHERE status IN ('pending','running') AND deleted_at IS NULL;

-- 드레인 커버링(대기 작업 우선순위·오래된 순).
CREATE INDEX IF NOT EXISTS ix_txjob_drain ON translation_jobs (status, priority DESC, created_at)
  WHERE status = 'pending' AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_txjob_user ON translation_jobs (user_id) WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_txjob_updated ON translation_jobs;
CREATE TRIGGER trg_txjob_updated BEFORE UPDATE ON translation_jobs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
