-- src/db/schema_stage6.sql — 등록 파이프 P4: 마켓 등록 대장(market_registrations).
-- 등록 파이프가 관통(카나리 10차)하면서 실제 등록이 나가기 시작했다. **무엇을 등록했는지 서버가
-- 기억해야** 반려감시(rej_watch)가 감시 대상을 스스로 안다 — 그 전엔 오너가 sid를 손으로 넣어야 했다.
-- stage1 관례 그대로(uuid·soft-delete·updated_at 트리거). PG 미가동이면 인메모리 폴백(개발/테스트).

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS market_registrations (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  marketplace    text NOT NULL DEFAULT 'coupang',
  account        text NOT NULL DEFAULT '',         -- gogane|woojoo (계정 라우팅)
  product_id     text NOT NULL,                    -- 마켓 상품 id(쿠팡 sellerProductId = 반려조회 sid)
  vendor_sku     text NOT NULL DEFAULT '',         -- 아마존 ASIN 등(#663 식별자)
  title          text NOT NULL DEFAULT '',
  source_url     text NOT NULL DEFAULT '',
  market_url     text NOT NULL DEFAULT '',
  status         text NOT NULL DEFAULT 'submitted',-- submitted|approved|rejected|deleted|unknown
  reject_kind    text NOT NULL DEFAULT '',         -- reject_watch 분류(image_spec/trademark/...)
  reject_comment text NOT NULL DEFAULT '',         -- 반려 사유 원문(comment — 상태 문구 아님)
  prescription   text NOT NULL DEFAULT '',         -- 처방(reupload/delete/replace_option/...)
  notified_at    timestamptz,                      -- 알림 발송 시각(중복 알림 방지)
  checked_at     timestamptz,                      -- 마지막 상태 조회 시각(감시 주기)
  deleted_at     timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

-- 같은 마켓의 같은 상품 id는 활성 1행(재등록 시 갱신).
CREATE UNIQUE INDEX IF NOT EXISTS uq_mktreg_active
  ON market_registrations (marketplace, product_id)
  WHERE deleted_at IS NULL;

-- 감시 큐 조회: 미확정(submitted) 우선 + 오래 안 본 것 먼저.
CREATE INDEX IF NOT EXISTS ix_mktreg_watch
  ON market_registrations (marketplace, status, checked_at)
  WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_mktreg_updated_at ON market_registrations;
CREATE TRIGGER trg_mktreg_updated_at
  BEFORE UPDATE ON market_registrations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
