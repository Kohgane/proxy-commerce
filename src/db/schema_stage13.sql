-- src/db/schema_stage13.sql — D2b: 번역본의 **외부 주소**(cdn_url).
--
-- ## 왜 필요한가
--
-- D2는 번역본 바이트를 DB에 두고 `/seller/collect/image-ko/<item>/<idx>`로 서빙했다.
-- 그 주소는 **로그인 게이트 뒤**다 — 우리 화면에선 보이지만 **마켓 서버는 못 가져간다.**
-- 쿠팡이 그 URL로 이미지를 받으러 오면 404를 본다(우리 세션 쿠키가 없으니까).
--
-- 그래서 등록에 나가는 주소는 **외부에서 열리는 것**이어야 한다 → Cloudinary URL.
-- 이 컬럼은 그 주소를 기억한다(멱등 백필: 이미 있으면 다시 올리지 않는다).
--
-- `bytes`는 그대로 둔다 — CDN이 죽거나 계정을 바꿀 때 **다시 올릴 원본**이 있어야 한다.

ALTER TABLE image_ko_blobs ADD COLUMN IF NOT EXISTS cdn_url    text NOT NULL DEFAULT '';
ALTER TABLE image_ko_blobs ADD COLUMN IF NOT EXISTS cdn_at     timestamptz;
ALTER TABLE image_ko_blobs ADD COLUMN IF NOT EXISTS cdn_error  text NOT NULL DEFAULT '';

-- 아직 못 올린 것만 빠르게 찾는다(백필이 매번 전수를 훑지 않게).
CREATE INDEX IF NOT EXISTS ix_image_ko_blobs_pending
  ON image_ko_blobs (item_id) WHERE cdn_url = '';
