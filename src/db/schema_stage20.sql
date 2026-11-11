-- src/db/schema_stage20.sql — 오너 긴급 2026-11-12(Supabase 무료 전송량 402): 순차 스캔 줄이기.
--
-- ## 무엇을
-- - app_state `key LIKE 'prefix%'`(state_scan · 11k회 · 순차 스캔): PK(btree, 기본 정렬)는 LIKE 앞부분 일치를 못 쓴다
--   (C 로케일이 아니면). `text_pattern_ops` 인덱스가 앞부분 일치를 받는다.
-- - 부팅 정체성 병합(`identity._counts_for`)이 표마다 `count(*) WHERE user_id=$1`을 부른다(배포마다 · 표당 ~14k회 누적).
--   번역 큐 3종·벤치 표엔 user_id 인덱스가 없어 매번 표 전체를 훑었다(800만·420만·65만 행).
-- 표가 작아(수백~수천 행) 일반 CREATE INDEX(짧은 잠금)로 둔다.
CREATE INDEX IF NOT EXISTS ix_app_state_key_pattern ON app_state (key text_pattern_ops);
CREATE INDEX IF NOT EXISTS ix_image_translate_queue_user ON image_translate_queue (user_id);
CREATE INDEX IF NOT EXISTS ix_image_translate_usage_user ON image_translate_usage (user_id);
CREATE INDEX IF NOT EXISTS ix_option_translate_queue_user ON option_translate_queue (user_id);
CREATE INDEX IF NOT EXISTS ix_image_bench_runs_user ON image_bench_runs (user_id);
CREATE INDEX IF NOT EXISTS ix_image_ko_blobs_seller ON image_ko_blobs (seller_id);
