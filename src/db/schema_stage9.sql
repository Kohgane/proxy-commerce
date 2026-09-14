-- src/db/schema_stage9.sql — D1: 이미지 번역 사용량·벤치 채점.
--
-- 장당 과금이라 **쓴 만큼이 곧 원가**다. 그래서 호출을 행으로 남기고, 집계는 더해서 낸다 —
-- **별도 카운터를 두지 않는다**(카운터와 실제가 갈리면 어느 쪽이 맞는지 알 수 없게 된다, D0-6).
--
-- 벤치 채점은 **오너가 손으로 채우는 값**이라 파일보다 여기가 맞다 —
-- Render 디스크는 배포마다 사라지고, 사람이 매긴 점수를 다시 매기게 할 수는 없다.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS image_translate_usage (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    text NOT NULL DEFAULT '',
  vendor     text NOT NULL DEFAULT 'tencent',
  pages      integer NOT NULL DEFAULT 0,      -- 이 호출에서 보낸 장수
  ok_pages   integer NOT NULL DEFAULT 0,      -- 그중 번역본이 실제로 놓인 장수
  ms         integer NOT NULL DEFAULT 0,      -- 합계 소요
  created_at timestamptz NOT NULL DEFAULT now()
);

-- 관리자 일 합계: (날짜, 사용자)로 긁는다.
CREATE INDEX IF NOT EXISTS ix_img_tr_usage_day
  ON image_translate_usage (created_at DESC, user_id);

-- 벤치 실행 1회 = 1행. 결과 메타와 **오너 채점**이 같이 산다.
CREATE TABLE IF NOT EXISTS image_bench_runs (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id     text NOT NULL,                   -- 화면·파일과 맞추는 이름표
  user_id    text NOT NULL DEFAULT '',
  vendor     text NOT NULL DEFAULT 'tencent',
  results    jsonb NOT NULL DEFAULT '[]'::jsonb,   -- 장별 메타(이미지 바이트는 파일에)
  scores     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- 5축 채점(오너 입력)
  note       text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_image_bench_run ON image_bench_runs (run_id);

DROP TRIGGER IF EXISTS trg_image_bench_updated_at ON image_bench_runs;
CREATE TRIGGER trg_image_bench_updated_at
  BEFORE UPDATE ON image_bench_runs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
