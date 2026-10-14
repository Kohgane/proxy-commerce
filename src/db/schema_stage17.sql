-- Y11-D(오너 2026-10-14): 수집 주소가 광고 클릭 링크(click.simba.taobao.com — 타오바오 직통차)였다.
--   「원본 보기」가 열 때마다 과금 클릭이고 리다이렉트가 언제 깨질지 모른다 → url은 상품 정규 주소,
--   원래 링크는 raw_url에 보존. 앞으로 들어오는 것은 collect_history_store.append가 바꾼다(canonical_source_url).
ALTER TABLE collect_history ADD COLUMN IF NOT EXISTS raw_url text NOT NULL DEFAULT '';

-- 기존 행 마이그레이션(몇 번 돌아도 같은 결과 — raw_url이 비어 있는 click.simba 행만).
--   skuId는 쿼리 또는 인코딩된 꼬리(`e` 안 `skuId%3D…`)에 있다. 상품번호(id)를 못 뽑는 행은 건드리지 않는다.
--   extra_json.raw_url에도 같은 값을 둔다(화면은 extra에서 읽는다).
UPDATE collect_history
   SET raw_url = url,
       extra_json = jsonb_set(extra_json, '{raw_url}', to_jsonb(url), true),
       url = 'https://item.taobao.com/item.htm?id=' || substring(url from '[?&]id=([0-9]+)')
             || coalesce('&skuId=' || substring(url from '(?i)sku_?id(?:=|%3D|%253D)([0-9]+)'), '')
 WHERE url LIKE 'https://click.simba.taobao.com/%'
   AND raw_url = ''
   AND url ~ '[?&]id=[0-9]+';
