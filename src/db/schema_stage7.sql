-- src/db/schema_stage7.sql — C-F17-B: 텔레그램 chat_id ↔ 셀러 바인딩(telegram_links).
-- 폰 기본 입구가 단축어 → **텔레그램 봇**으로 바뀌었다(실측: 상하이 셀룰러에서 단축어가
-- VPN on/off·서버 무관 「네트워크 연결 유실」. 서버 앞단 Cloudflare 도달성은 우리 통제 밖).
-- 봇은 chat_id밖에 모른다 — 그 chat이 **누구의 계정인지**를 서버가 기억해야
-- 담은 상품이 올바른 목록으로 간다. 바인딩은 `/link <API 토큰>` 1회로 만들어진다.
--
-- 저장하는 것: chat_id · user_id · 바인딩 시각/마지막 사용.
-- **저장하지 않는 것: 토큰 원문.** 토큰은 검증에만 쓰고 버린다(원문 저장 0 — 기존 규율).
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

-- 한 chat은 한 계정에만 묶인다(다시 /link 하면 갈아끼운다 — 두 계정에 동시에 담기지 않게).
CREATE UNIQUE INDEX IF NOT EXISTS uq_tglink_active
  ON telegram_links (chat_id)
  WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_tglink_updated_at ON telegram_links;
CREATE TRIGGER trg_tglink_updated_at
  BEFORE UPDATE ON telegram_links
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
