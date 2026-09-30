-- src/db/schema_stage16.sql — J1(오너 2026-09-30-J): 옵션 값·상품명 **번역기 큐**(수집하면 자동, 퍼센티처럼).
--
-- 규칙표(ko_polish)로 풀리는 값은 수집 때 바로 옮긴다(비용 0). 한자가 남은 값만 여기 들어와 번역기로 간다.
-- 상품 단위 행 — 같은 상품이 다시 보강되면 행을 다시 `queued`로 돌린다(새 옵션 값이 생겼을 수 있다).
-- 일일 상한·일시정지 상태는 `app_state`(stage14)에 둔다(이미지 번역 큐와 같은 틀).

CREATE TABLE IF NOT EXISTS option_translate_queue (
  id          bigserial PRIMARY KEY,
  user_id     text NOT NULL,
  item_id     text NOT NULL UNIQUE,
  status      text NOT NULL DEFAULT 'queued', -- queued | running | done | failed | skipped
  reason      text NOT NULL DEFAULT '',
  attempts    integer NOT NULL DEFAULT 0,
  values_sent integer NOT NULL DEFAULT 0,     -- 마지막 실행에서 번역기에 보낸 값 수(상한에서 뺀 수)
  created_at  timestamptz NOT NULL DEFAULT now(),
  started_at  timestamptz,
  finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_option_translate_queue_status ON option_translate_queue (status, id);
