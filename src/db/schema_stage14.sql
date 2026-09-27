-- src/db/schema_stage14.sql — D3-8: 이미지 번역 **자동 큐**(수집 → 보강 완료 → 번역).
--
-- ## 왜 표가 필요한가
--
-- 셀러가 누르는 번역(F25)은 데몬 스레드 하나가 요청 밖에서 돈다 — 재시작하면 `queued`가 남고 사람이 다시 누른다.
-- 자동 큐는 **아무도 누르지 않는다.** 재배포·재시작·워커 둘에서도 한 장이 한 번만, 차례대로 나가야 한다.
-- 그래서 장 단위 행(`image_translate_queue`) + SKIP LOCKED 리스(워커 여럿이 같은 장을 두 번 잡지 않게).
--
-- `app_state`는 전역 작은 상태(일시정지·재개 시각·소싱처 토글) — 워커 여럿이 같은 값을 본다.

CREATE TABLE IF NOT EXISTS image_translate_queue (
  id          bigserial PRIMARY KEY,
  user_id     text NOT NULL,
  item_id     text NOT NULL,
  kind        text NOT NULL,                 -- gallery | detail
  idx         integer NOT NULL,
  status      text NOT NULL DEFAULT 'queued', -- queued | running | done | failed | skipped
  reason      text NOT NULL DEFAULT '',
  attempts    integer NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now(),
  started_at  timestamptz,
  finished_at timestamptz,
  UNIQUE (item_id, kind, idx)
);
CREATE INDEX IF NOT EXISTS ix_image_translate_queue_status ON image_translate_queue (status, id);

CREATE TABLE IF NOT EXISTS app_state (
  key        text PRIMARY KEY,
  value      jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);
