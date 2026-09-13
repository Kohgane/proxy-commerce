-- src/db/schema_stage7.sql — C-F17/F18: 텔레그램 (봇, chat_id) ↔ 셀러 바인딩(telegram_links).
-- 폰 기본 입구가 단축어 → **텔레그램 봇**으로 바뀌었다(실측: 상하이 셀룰러에서 단축어가
-- VPN on/off·서버 무관 「네트워크 연결 유실」. 서버 앞단 Cloudflare 도달성은 우리 통제 밖).
-- 봇은 chat_id밖에 모른다 — 그 chat이 **누구의 계정인지**를 서버가 기억해야
-- 담은 상품이 올바른 목록으로 간다. 바인딩은 `/link <API 토큰>` 1회로 만들어진다.
--
-- **키가 (bot_slug, chat_id)인 이유**(F18): 한 사람이 봇 둘로 콘솔 로그인 둘(고가네/우주대행)을
-- 따로 쓴다. 같은 텔레그램 계정이라 chat_id는 같은데 담길 계정이 다르다 —
-- chat_id만으로 키를 잡으면 둘 중 하나가 다른 하나를 덮는다.
--
-- 저장하는 것: bot_slug · chat_id · user_id · **토큰 해시** · 시각.
-- **저장하지 않는 것: 토큰 원문.** 해시만 둔다(기존 규율 그대로). 해시를 두는 이유는
-- 콘솔에서 그 토큰을 폐기하면 **매핑도 따라 무효**가 되어야 하기 때문이다 —
-- 토큰을 지웠는데 봇은 계속 담기면, 지운 사람이 지웠다고 믿는 것이 사실이 아니게 된다.
-- stage1 관례 그대로(uuid·soft-delete·updated_at 트리거). PG 미가동이면 인메모리 폴백(개발/테스트).

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS telegram_links (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_id     text NOT NULL,
  user_id     text NOT NULL,                    -- 수집 저장 스코프(seller_id)
  linked_at   timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz,
  deleted_at  timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- F18: 이미 만들어진 테이블(F17판)에도 붙는다 — 재적용해도 안전하다.
ALTER TABLE telegram_links ADD COLUMN IF NOT EXISTS bot_slug   text NOT NULL DEFAULT 'default';
ALTER TABLE telegram_links ADD COLUMN IF NOT EXISTS token_hash text NOT NULL DEFAULT '';

-- 한 봇의 한 chat은 한 계정에만 묶인다(다시 /link 하면 갈아끼운다).
-- 봇이 다르면 **다른 행**이다 — 그게 F18의 요점이다.
DROP INDEX IF EXISTS uq_tglink_active;
CREATE UNIQUE INDEX IF NOT EXISTS uq_tglink_active_bot
  ON telegram_links (bot_slug, chat_id)
  WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_tglink_updated_at ON telegram_links;
CREATE TRIGGER trg_tglink_updated_at
  BEFORE UPDATE ON telegram_links
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
