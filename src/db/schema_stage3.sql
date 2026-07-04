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

-- upsert 키: (order_id, marketplace) 활성 행 유니크.
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_key
  ON orders (order_id, marketplace) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_orders_placed ON orders (placed_at) WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_orders_updated ON orders;
CREATE TRIGGER trg_orders_updated BEFORE UPDATE ON orders
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
