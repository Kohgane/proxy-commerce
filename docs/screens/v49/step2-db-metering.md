# v49 STEP2 — DB 왕복 계측·다이어트

## 계측 (측정 먼저)
스택은 **psycopg3**(SQLAlchemy 아님) → pg 레이어(`query()`/`tx()`)에서 쿼리별로 계측:
- **요청당 총 쿼리 수** → `Server-Timing: dbq;desc="N queries"` + 로그 `perf_count.db_query`.
- **개별 쿼리 ms** → 로그 `perf_ms.db_ms_each`(느린 순 상위 10) — 어떤 쿼리가 왕복을 먹는지.
- **연결(핸드셰이크) 수** → `dbconn;desc=N`(요청범위 재사용 시 1).
- **db 합계** → `db;dur=` (뷰 레벨 `perf_block("db")` 이중계상 제거 → 정확).

### 로컬 PG 실측 (수집이력 `/seller/collect/history`)
```
Server-Timing: db;dur=8.32, render;dur=111.56, dbconn;desc=1, dbq;desc="3 queries", app;dur=35.56, total;dur=155.44
perf_ms: {db: 8.32, db_ms_each: [5.59, 2.24, 0.49]}   perf_count: {db_read: 3, db_query: 3, db_conn: 1}
```
→ **3 쿼리(list+summary+distinct), 연결 1개**(요청범위 재사용). 목표 페이지당 ≤3 충족.
배포(버지니아↔싱가포르)에선 각 쿼리에 ~220ms 왕복이 얹혀 db 합계가 커진다 → 오너가 네트워크 탭
`db;dur`·`dbq`로 확인. SG 이관(STEP1) 후엔 이 왕복이 사라져 db 합계 급감.

## 다이어트
1. **대형 컬럼 제외**: 목록은 `lean=True`(이미지 40장·상세·리뷰·스펙 SELECT 제외) — 기존 유지.
2. **뷰 레벨 이중계상 제거**: collect_history의 `perf_block("db")` 제거 → pg 레이어가 쿼리별 정확 계측.
3. **요청범위 연결 재사용**: query()가 요청당 연결 1개를 flask.g에 캐시(핸드셰이크 N→1) — 기존 유지.
4. **상시 커넥션 풀(opt-in)**: `PG_PERSISTENT_POOL=1` → psycopg_pool(size=5, pre_ping, recycle=300,
   prepared 비활성=풀러 호환)로 **요청마다의 TCP+TLS 핸드셰이크(대륙 간 ~220ms) 제거**.
   - **기본 OFF** → 기존 요청범위 1회용 연결(무회귀). 풀 미설치/생성 실패 시 자동 폴백(정직).
   - 로컬 실측(PG_PERSISTENT_POOL=1): 재요청 Server-Timing에 **`dbconn` 없음**(핸드셰이크 0, 풀 대여).
   - ⚠️ 실 Supabase 풀러 효과는 오너가 SG 서비스에서 켜고 위 계측으로 검증(측정 없는 확정 금지 →
     기본 OFF·opt-in). 켜는 법: 환경변수 `PG_PERSISTENT_POOL=1`(+선택 `PG_POOL_SIZE`).

## 세션·유저 조회
현재 세션은 **서명 쿠키**(Flask session)만 사용 — 요청당 유저 DB 조회 없음(`_seller_identities`도 쿠키
세션에서만 읽음). 별도 캐시 불요(이미 DB 왕복 0). billing_store(플랜 뱃지)는 PG 아님(별도).

## 판정 (배포 캡처는 오너)
`/seller/collect/history`·카탈로그·드로어 3곳의 이관 전/후 [쿼리 수·db 합계·total] 표 + 네트워크 탭.
로컬 계측으로 도구·쿼리 수(≤3)·연결 수(1)·풀 효과(dbconn 0)는 실증. 배포 절대치·이관 전후 배가는 오너 캡처.

## 가드
test_v49_db_metering(4): 소스 계약(계측·풀 게이트) + 로컬 PG 실측(쿼리 수·연결 1·풀 핸드셰이크 0).
requirements: `psycopg[binary,pool]`(pool extra — 플래그 ON일 때만 사용).
