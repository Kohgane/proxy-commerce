-- src/db/schema_stage4.sql — v87-S3 가격 정책(settings).
-- 셀러별 가격 정책 1행. 정책 본문은 jsonb(필드가 늘어도 마이그레이션 없이 확장).
-- 낙관잠금: version을 조건에 걸고 UPDATE — 두 탭에서 동시에 저장하면 뒤엣것이 조용히 덮어쓰지 않는다.
-- idempotent(IF NOT EXISTS) — init_schema()가 매 부팅 안전 실행.

CREATE TABLE IF NOT EXISTS settings (
  user_id    text PRIMARY KEY,
  policy     jsonb NOT NULL DEFAULT '{}'::jsonb,
  version    integer NOT NULL DEFAULT 1,      -- 낙관잠금 토큰(저장마다 +1)
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_settings_updated_at ON settings;
CREATE TRIGGER trg_settings_updated_at BEFORE UPDATE ON settings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 변경 이력(화면에 최근 5건 표시). 정책 전문을 스냅샷으로 남긴다 — '언제 뭐가 바뀌었나'를 되짚을 수 있게.
CREATE TABLE IF NOT EXISTS settings_history (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    text NOT NULL DEFAULT '',
  policy     jsonb NOT NULL DEFAULT '{}'::jsonb,
  version    integer NOT NULL DEFAULT 1,
  summary    text NOT NULL DEFAULT '',        -- 바뀐 항목 요약(사람이 읽는 한 줄)
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_settings_history_user
  ON settings_history (user_id, created_at DESC);
