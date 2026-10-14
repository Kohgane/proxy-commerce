-- schema_stage18.sql — F-PROXY-1: 구매대행 주문 대장(승인 큐 + 증빙: 주문번호 ↔ 구매영수증 ↔ 운송장). idempotent.
-- 상태: quoted -> awaiting_approval -> approved -> purchased -> shipped -> delivered | refused | cancelled
CREATE TABLE IF NOT EXISTS proxy_orders (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  draft_order_id  text NOT NULL DEFAULT '',      -- Shopify draftOrder gid
  shopify_order   text NOT NULL DEFAULT '',      -- 결제 후 주문 번호
  email           text NOT NULL DEFAULT '',
  source_url      text NOT NULL,
  title           text NOT NULL DEFAULT '',
  total_usd       numeric(10,2) NOT NULL,
  price_krw       integer NOT NULL DEFAULT 0,
  fx_krw_per_usd  numeric(10,2) NOT NULL DEFAULT 0,
  status          text NOT NULL DEFAULT 'awaiting_approval',
  purchase_ref    text NOT NULL DEFAULT '',      -- 구매 영수증/주문번호(소싱처)
  purchase_krw    integer,
  carrier         text NOT NULL DEFAULT '',
  tracking_no     text NOT NULL DEFAULT '',
  note            text NOT NULL DEFAULT '',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_proxy_orders_status ON proxy_orders (status, created_at);
