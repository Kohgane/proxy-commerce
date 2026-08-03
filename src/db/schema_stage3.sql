-- src/db/schema_stage3.sql — 이관 3단계: orders(주문·정산 파생 포함).
-- SheetsOrderAdapter의 'orders' 워크시트 → PG. 컬럼은 ORDERS_HEADERS와 동일(text)로 저장해
-- 행 dict 왕복이 시트와 동일(_row_to_order 재사용). 정산 KPI(마진 등)는 이 행에서 파생.
-- 키=(order_id, marketplace) upsert. idempotent.

CREATE TABLE IF NOT EXISTS orders (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               text NOT NULL DEFAULT '',   -- 향후 멀티테넌시(현재 단일 스코프)
  order_id              text NOT NULL,
  marketplace           text NOT NULL,
  status                text NOT NULL DEFAULT '',
  placed_at             text NOT NULL DEFAULT '',    -- ISO 문자열(시트와 동일 포맷)
  paid_at               text NOT NULL DEFAULT '',
  buyer_name_masked     text NOT NULL DEFAULT '',
  buyer_phone_masked    text NOT NULL DEFAULT '',
  buyer_address_masked  text NOT NULL DEFAULT '',
  total_krw             text NOT NULL DEFAULT '0',
  shipping_fee_krw      text NOT NULL DEFAULT '0',
  items_json            text NOT NULL DEFAULT '[]',
  courier               text NOT NULL DEFAULT '',
  tracking_no           text NOT NULL DEFAULT '',
  shipped_at            text NOT NULL DEFAULT '',
  landed_cost_krw       text NOT NULL DEFAULT '',
  margin_krw            text NOT NULL DEFAULT '',
  margin_pct            text NOT NULL DEFAULT '',
  last_synced_at        text NOT NULL DEFAULT '',
  notes                 text NOT NULL DEFAULT '',
  deleted_at            timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);

-- v87-S2 후속: 통관 축(pcc·country). 구매대행은 통관이 척추라 주문 행에 실린다.
--   기존 배포에도 붙어야 하므로 CREATE TABLE 본문이 아니라 idempotent ALTER로 둔다
--   (이미 만들어진 orders 테이블은 CREATE TABLE IF NOT EXISTS가 건드리지 않는다).
--   값을 채우는 건 마켓 주문 동기화 배선(별도 티켓) — 그 전까지는 빈 값이고,
--   화면은 빈 값을 숨기지 않고 '미수신'으로 표기한다(죽은 필드 은폐 금지).
ALTER TABLE orders ADD COLUMN IF NOT EXISTS pcc     text NOT NULL DEFAULT '';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS country text NOT NULL DEFAULT '';

-- v87-S4: 드로어 상단 3칩([수집처][판매마켓][상세페이지])의 대상 주소.
--   PCC와 똑같이 **읽는 쪽만 있고 만드는 쪽이 없어서** 세 칩이 영구 비활성이었다(실기기 무반응 확정).
--   수집처는 카탈로그 역참조(v56)로 채워질 때가 있지만 그마저 sku 미매칭이면 빈다 —
--   주문 행이 직접 들고 있게 해서 동기화가 채우면 바로 링크가 산다.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS source_url text NOT NULL DEFAULT '';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS market_url text NOT NULL DEFAULT '';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS detail_url text NOT NULL DEFAULT '';

-- upsert 키: (order_id, marketplace) 활성 행 유니크.
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_key
  ON orders (order_id, marketplace) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_orders_placed ON orders (placed_at) WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_orders_updated ON orders;
CREATE TRIGGER trg_orders_updated BEFORE UPDATE ON orders
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
