-- schema_stage19.sql — Y12-A(오너 2026-10-17): 상품목록 「마지막 동작 최신순」·「손댈 것만」을 SQL로(무거운 extra_json을 읽지 않고).
-- 저장할 때(collect_history_store.update) attention.stamp가 채운다. 비어 있으면 last_action_at = created_at으로 본다. idempotent.
ALTER TABLE collect_history ADD COLUMN IF NOT EXISTS last_action_at timestamptz;
ALTER TABLE collect_history ADD COLUMN IF NOT EXISTS attn_n integer NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS ix_collect_history_user_action
  ON collect_history (user_id, (COALESCE(last_action_at, created_at)) DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_collect_history_attn
  ON collect_history (user_id) WHERE deleted_at IS NULL AND attn_n > 0;
