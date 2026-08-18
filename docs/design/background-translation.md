# 백그라운드 번역 — 설계 문서 (v88-B)

> 상태: **구현 완료**(오너 "전부 가라" 승인). 설계=이 문서, 구현=아래 §8 배선. feature flag `TRANSLATE_BACKGROUND=1` + PG 가동 시 활성, 아니면 기존 동기 경로(무회귀).
> 구현 파일: `src/db/schema_stage5.sql`(translation_jobs) · `src/db/translation_jobs_pg.py`(enqueue/lease/complete/fail/get_by_ids) · `src/seller_console/translate_worker.py`(drain_once) · 라우트 `/collect/translate/{enqueue,status}` + cron `/cron/translate-drain`. 계약 `test_v88_b_impl_*`(PG 7 + 라우트 8).
> 오너 결정: "전부 가라" — 설계 트랙 개시. **W10 요청 예산 캡은 유지**(안전망 이중화).
> 불변 원칙(금지): **번역 체인 로직·요청 예산 캡·무료 쿼터 회계 무손대.** 이 설계는 번역을 *어디서 실행하는지*(요청 경로 → 백그라운드 워커)만 바꾼다.

---

## 0. 문제와 목표
- **문제(W10 계보)**: 동기 번역 체인이 요청 워커를 오래 점유(최악 항목당 8초 캡×벌크 → 워커 8슬롯 고갈). W10은 요청 예산 캡으로 *증상*을 봉인했으나, 대량 번역은 여전히 요청 경로에서 돈다.
- **목표**: 번역 실행을 **요청 경로에서 완전 분리** → 요청은 "작업 등록"만 하고 즉시 반환(수십 ms). 실제 체인 호출은 백그라운드 워커가 수행. 클라이언트는 폴링으로 진행/결과 수신.
- **비목표**: 체인 프로바이더 순서·폴백·쿼터 회계·W10 캡 변경. (그대로 재사용.)

## 1. 재사용 자산 (신규 발명 최소)
| 관례 | 출처 | 이 설계에서의 역할 |
|---|---|---|
| Supabase 스키마 패턴 | `src/db/schema_stage1~4.sql` (W3 계보) | 작업 테이블 = uuid PK·user_id 스코프·status·soft-delete·created/updated_at 트리거·jsonb·부분 유니크·idempotent DDL |
| 분산 잡 큐 | `src/jobs/queue_manager.py` (Phase 147) | `SELECT … FOR UPDATE SKIP LOCKED` 드레인·idempotency key·재시도·dead-letter·카테고리별 동시성 |
| pg 트랜잭션 | `src/db/pg.py::tx()` | 커밋 후에만 durable(W3 P2 계보) |
| 번역 체인·캡 | `ai/translator.py` (W7·W10) | 워커가 **그대로** 호출(`translate_product`), 요청 예산 캡은 워커 내부 안전망으로 유지 |
| 원인 4분 | W7a (`classify` budget/quota/rate_limit/auth) | 재시도 여부 판정(auth/quota=재시도 무의미, rate_limit/transient=재시도) |
| 필드별 상태 | W9 (`title_translated`/`desc_translated`) | 폴링 응답·뱃지 |
| 판정 재계산 | `collect_status` 조회 시 재계산(W11 item②) | 스테일 봉인 |
| 무료 쿼터 미터 | `translation_usage` | **실제 번역 성공 시에만 차감**(워커가 성공 커밋 시 increment — 회계 규칙 불변) |
| 원문 소스 | #617·W11 item① | 워커도 원본(title_en/description)에서 번역 |

## 2. 작업 저장소 (Supabase `translation_jobs`) — 스키마 초안
```sql
-- schema_stage5.sql (구현 트랙에서 추가). stage1 관례 그대로.
CREATE TABLE IF NOT EXISTS translation_jobs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        text NOT NULL DEFAULT '',
  item_id        text NOT NULL,                    -- collect_history 항목
  status         text NOT NULL DEFAULT 'pending',  -- pending|running|success|failed
  attempts       int  NOT NULL DEFAULT 0,
  max_attempts   int  NOT NULL DEFAULT 3,          -- queue_manager _MAX_RETRIES 재사용
  priority       int  NOT NULL DEFAULT 0,          -- 드로어 단건 > 벌크
  provider       text NOT NULL DEFAULT '',         -- 성공 프로바이더(계측)
  cause          text NOT NULL DEFAULT '',         -- 실패 원인 4분(W7a)
  error          text NOT NULL DEFAULT '',
  result_json    jsonb NOT NULL DEFAULT '{}'::jsonb,-- title_ko/desc_ko/attempts/detected_lang/필드상태
  idem_key       text NOT NULL,                    -- user_id|item_id (활성 중복 방지)
  locked_by      text,                             -- 워커 리스(SKIP LOCKED 보조)
  locked_at      timestamptz,
  started_at     timestamptz,
  finished_at    timestamptz,
  deleted_at     timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
-- 활성 idempotency: 같은 항목의 미완 작업 중복 금지(재클릭 폭주 방어).
CREATE UNIQUE INDEX IF NOT EXISTS uq_txjob_active_idem ON translation_jobs (idem_key)
  WHERE status IN ('pending','running') AND deleted_at IS NULL;
-- 드레인 커버링(대기 작업 우선순위·오래된 순).
CREATE INDEX IF NOT EXISTS ix_txjob_drain ON translation_jobs (status, priority DESC, created_at)
  WHERE status = 'pending' AND deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_txjob_user ON translation_jobs (user_id) WHERE deleted_at IS NULL;
-- updated_at 트리거(set_updated_at 재사용).
```
> **정직/폴백**: `pg_enabled()` 아니면(로컬/개발) 작업 테이블 없음 → 백그라운드 미가동. 그때는 **기존 동기 경로(W10 캡)** 그대로 사용(무회귀). 즉 백그라운드는 PG 있는 프로덕션의 *가속 경로*, 동기+캡은 *기본 경로*.

## 3. 상태 전이
```
                 enqueue                worker lease            체인 성공
   (없음) ─────────────▶ pending ───────────────▶ running ───────────────▶ success  (터미널)
                            ▲                         │
                            │ 재시도(backoff)          │ 체인 실패
              rate_limit/transient & attempts<max     ▼
                            └──────────────────────  failed?
                                                       │ attempts>=max  또는  cause∈{auth,quota}
                                                       ▼
                                                     failed  (터미널 → dead-letter 집계)
```
- **pending**: 요청 경로가 등록만. (idem 유니크로 재클릭 중복 0.)
- **running**: 워커가 `FOR UPDATE SKIP LOCKED`로 리스(locked_by/at). 크래시 시 `locked_at` 만료(예: 90s) 회수.
- **success**: `result_json` 커밋 + 표시 필드 갱신(원문 없으면 기존 보존 #617) + 쿼터 increment(성공분만).
- **failed**: 원인 4분 기록. auth/quota=즉시 터미널(재시도 무의미), rate_limit/transient=backoff 후 pending(attempts<max).

## 4. 폴링 계약
- **등록**: `POST /seller/collect/translate/enqueue {item_ids:[…]}` → `{ok, jobs:[{item_id, job_id, status:"pending"|"running"|"success"(이미완료 idem 재사용)}]}`. 요청 경로는 **체인 미호출**(등록만) → 수십 ms.
- **폴링**: `GET /seller/collect/translate/status?ids=job1,job2` → `{jobs:{job_id:{status, provider, cause, error, title_ok, desc_ok}}}`. 드로어/목록이 2~4초 간격 폴링(수집 자동반영 폴링 관례 재사용, `visibilitychange` 재조회). 터미널이면 폴링 중단.
- **표시**: 상태 뱃지 = W9 필드별(`title_ok`/`desc_ok`)·실패 원인(W7a). success면 표시 제목/상세 갱신(가짜 번역 0 — 실제 커밋된 값만).
- **정직**: 폴링은 서버 영속(작업 테이블) 상태만 반영. "진행 중"은 실제 running일 때만(가짜 진행바 0).

## 5. 벌크 처리 & 워커 드레인
- **등록**: 벌크 = item마다 1작업 등록(우선순위 낮음). 드로어 단건 = 우선순위 높음(priority DESC). 청크 불필요(등록만이라 빠름).
- **드레인**: 워커가 `SELECT … WHERE status='pending' ORDER BY priority DESC, created_at FOR UPDATE SKIP LOCKED LIMIT N` → running 마킹 → 체인 호출 → success/failed 커밋. 멀티워커 안전(SKIP LOCKED, queue_manager 관례).
- **동시성**: `CATEGORY_CONCURRENCY`에 `"translate": K`(초기 2) 추가 — 프로바이더 레이트리밋 존중. K는 env(`TRANSLATE_WORKER_CONCURRENCY`).
- **워커 기동(오너 인프라 선택지, 결정 대기)**:
  - (a) **Render Cron** `POST /cron/translate-drain`(X-Cron-Secret) 1~2분 간격 — 기존 cron 관례(`/cron/sourcing-monitor`) 재사용. 무상태·저비용. **지연 상한 = cron 간격.**
  - (b) **인프로세스 백그라운드 스레드** — 즉시성 좋으나 Render 워커 수명·재시작에 취약.
  - 권고: **(a) Cron 드레인**으로 시작(관례 재사용·정직한 지연 상한). 실시간성 필요 시 (b) 후속.

## 6. 실패·재시도 정책
- `max_attempts=3`(queue_manager 재사용). backoff 1→2→4분(cron 간격에 맞춰 `next_run_at`).
- **원인별 분기(W7a)**: `auth`(키 무효)·`quota`(월예산 소진)=재시도 안 함(터미널 failed, 사용자에 정직 안내). `rate_limit`·transient(5xx/타임아웃)=재시도. `budget`(요청 예산)=백그라운드엔 캡 완화되나 워커 내부 캡은 안전망 유지.
- **dead-letter**: attempts 소진 → status=failed 유지(별 테이블 불필요, 조회로 집계). 사용자에겐 "번역 실패(원인)" + [다시 시도] → 새 작업 등록(idem 재사용 종료됨).
- **쿼터 회계 불변**: 성공 커밋 시에만 `translation_usage.increment`. 실패·재시도는 차감 0(W7 규칙 그대로).

## 7. W10 캡과의 관계 (이중 안전망)
- 백그라운드 워커도 `translate_product` 호출 시 **요청 예산 캡을 그대로 통과**(워커 1건 처리 상한). 즉 캡은 제거하지 않는다 — 백그라운드는 *워커 점유를 요청에서 떼어낼 뿐* 캡 자체는 유효.
- PG 미가동/백그라운드 미배포 환경은 **동기 경로+캡**이 기본(무회귀). 백그라운드는 순수 가산(가속).

## 8. 마이그레이션·롤아웃 (구현 트랙 제안, 승인 후)
1. `schema_stage5.sql` + `src/db/translation_jobs_pg.py`(enqueue/lease/complete/fail, tx 커밋 durable). 로컬 PG 계약(부활0·idem중복0·재시작 durable).
2. `enqueue`/`status` 라우트 + 드로어/목록 폴링(수집 폴링 관례 재사용). **feature flag** `TRANSLATE_BACKGROUND=1`(기본 off) — off면 기존 동기 경로.
3. `/cron/translate-drain` + 워커 드레인(queue_manager 관례).
4. 실측: 벌크 등록 지연(수십 ms), 워커 점유 요청 경로서 0, 성공률·원인 계측, 쿼터 차감 성공분만.
5. flag on(프로덕션) → 관측 → 동기 경로는 폴백으로 보존.

## 9. 열린 결정(오너)
- 워커 기동 방식 (a Cron / b 스레드) — 권고 (a).
- cron 간격(지연 상한) — 권고 1분.
- `TRANSLATE_WORKER_CONCURRENCY` 초기값 — 권고 2(프로바이더 레이트리밋 보수적).
- 폴링 UX: 드로어만 vs 목록도(대량 시 부하) — 권고 드로어 우선.

> 이 문서는 **설계**다. 위 §8 구현은 **별 트랙**(오너 승인 후). 체인·캡·쿼터 회계는 이 트랙에서도 무손대.
