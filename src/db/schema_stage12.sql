-- src/db/schema_stage12.sql — D2: 번역 이미지 바이트를 **DB에** 둔다(image_ko_blobs).
--
-- ## 무엇을 고치나
--
-- D1에서 번역본을 **컨테이너 로컬 파일**로 뒀다:
--
--     src/services/image_translate_store.py:35   IMAGES_KO_DIR = Path(os.getenv("IMAGES_KO_DIR", "data/images_ko"))
--     src/services/image_translate_store.py:78   (d / f"{idx}.jpg").write_bytes(raw)
--
-- **Render는 배포할 때마다 그 디스크를 버린다.** 볼트에 [[Render tmp 휘발]]로 이미 적혀 있는
-- 지뢰인데, 「CDN 붙기 전 임시」라는 이유로 다시 밟았다. 장당 과금으로 만든 결과물이
-- 다음 배포에 사라지면 그 돈을 다시 쓴다.
--
-- ## 왜 bytea인가
--
-- 번역본은 JPG 한 장이다. `extra_json`에 base64로 넣으면 **행이 수백 KB로 붓고**
-- 그 행은 목록·서랍·폴러가 매번 통째로 읽는다. 그래서 바이트는 **별도 표**에 두고,
-- `extra_json`에는 가리키는 URL만 남긴다(D1 규칙 그대로).
--
-- ## 저장소 갈래는 셋뿐이다
--
--   cdn   — Cloudinary가 붙어 있다(영속·외부 URL). 등록에 그대로 쓴다.
--   db    — 여기(영속·우리 라우트로 서빙). CDN 붙기 전의 기본값.
--   ""    — 못 뒀다. **가짜 URL을 만들지 않는다.**
--
-- **local(파일)은 없앴다.** 배포에 사라지는 자리를 「저장했다」고 부르지 않는다.

CREATE TABLE IF NOT EXISTS image_ko_blobs (
  item_id      text NOT NULL,
  idx          integer NOT NULL,
  seller_id    text NOT NULL DEFAULT '',   -- 서빙 스코프 교차 확인용(라우트도 따로 검사한다)
  kind         text NOT NULL DEFAULT 'gallery',  -- gallery | detail (D2-4: 상세 이미지도 같은 구조)
  content_type text NOT NULL DEFAULT 'image/jpeg',
  bytes        bytea NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (item_id, kind, idx)
);

CREATE INDEX IF NOT EXISTS ix_image_ko_blobs_item ON image_ko_blobs (item_id);
