-- src/db/schema_stage10.sql — F24: 소싱 원칙(sourcing_rules) + 봇별 기본 등록 계정.
--
-- ## 왜 표로 두나
--
-- 지금까지 소싱 기준은 **코드 상수**였다(`DEFAULT_MARGIN_RATE = 27.4`, 배송비 `0.35 * 원가`).
-- 오너가 기준을 바꾸려면 코드를 고쳐 배포해야 했다 — 원칙은 사람이 정하는 것인데
-- 사람이 못 바꾸는 자리에 있었다.
--
-- ## 키가 (bot_slug, user_id)인 이유
--
-- 한 사람이 봇 둘로 사업 둘(고가네·우주대행)을 굴린다. **원가 하한도 마진도 사업마다 다르다.**
-- chat이 아니라 봇으로 가르는 것은 F18과 같은 이유다 — 같은 텔레그램 계정이라 chat_id가 겹친다.
-- `bot_slug=''`는 **콘솔**(검수표)이 읽는 기본 행이다.
--
-- **두 벌 금지**: 콘솔 검수표와 봇이 같은 이 표를 읽는다. 값이 없으면 옛 상수가 기본값으로 선다
-- (무회귀) — 그래서 이 표는 「덮어쓰기」이지 「이관」이 아니다.
--
-- 저장하는 것은 **숫자와 플래그뿐**이다. 판정 로직은 코드에 그대로 있다(기준만 밖으로 뺐다).

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS sourcing_rules (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bot_slug    text NOT NULL DEFAULT '',      -- '' = 콘솔(검수표) 기본 행
  user_id     text NOT NULL,
  rules       jsonb NOT NULL DEFAULT '{}'::jsonb,
  deleted_at  timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sourcing_rules_active
  ON sourcing_rules (bot_slug, user_id)
  WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_sourcing_rules_updated_at ON sourcing_rules;
CREATE TRIGGER trg_sourcing_rules_updated_at
  BEFORE UPDATE ON sourcing_rules
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- F24-1: 봇마다 **기본 등록 계정**이 다르다(KohujooBot=우주대행 · gogaBridz_bot=고가네).
-- 초안에 실어 두면 등록 화면이 그걸 미리 고른다 — 매번 사람이 고르지 않게.
-- 이미 만들어진 telegram_links에도 붙는다(재적용 안전).
ALTER TABLE telegram_links ADD COLUMN IF NOT EXISTS default_market_account text NOT NULL DEFAULT '';
