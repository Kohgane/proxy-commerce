-- src/db/schema_stage2.sql — 이관 2단계: market_links(연동정보·암호화 컬럼).
-- 마켓 API 자격증명을 셀러×마켓별로 저장. 값은 Fernet 암호문(enc_blob) — 앱이 암호화/복호화.
-- 기존 data/<seller>.json(Render ephemeral, 재배포 시 소실) → PG(영속). idempotent.

CREATE TABLE IF NOT EXISTS market_links (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       text NOT NULL,
  market        text NOT NULL,
  enc_blob      text NOT NULL DEFAULT '',    -- Fernet 암호문(키 없으면 평문 JSON, is_encrypted=false)
  is_encrypted  boolean NOT NULL DEFAULT true,
  deleted_at    timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_market_links_user_market
  ON market_links (user_id, market) WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_market_links_updated ON market_links;
CREATE TRIGGER trg_market_links_updated BEFORE UPDATE ON market_links
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
