# v87-W3 — 수집 이력 영속성: 배포 생존 조사 + 조용한 휘발 봉인

## 오너 확정 사실 (재조사 금지)
8/8·8/9 수집 레코드 소실, 8/12 09:19(배포 09:18:30 직후)분만 생존. 컨테이너 내에선 유지·**배포마다
리셋** = 컨테이너 로컬(휘발) 저장 시그니처. 194건 정리 후보 소실도 동일 원인 — W1 무죄.

## ① 수집 이력 실저장 위치 — 특정 (코드 근거)
**`collect_history`는 코드상 이미 Supabase PG 전용**이다:
- `src/db/collect_history_pg.py` + `schema_stage1.sql`(collect_history 테이블), 런타임은 PG 위임.
- `scripts/migrate_to_supabase.py`의 이관 범위에 **포함**(migrate_collect).
- **단, `pg_enabled()`가 True일 때만** PG. False면 **조용히 in-memory(컨테이너 로컬)로 폴백** → 배포마다 소실.

`pg_enabled()` = `DATABASE_URL` 설정 + psycopg3 + **연결 성공**(1회 메모이즈). PG 경로엔 최근 회귀
없음(마지막 변경 8/12 이전) → **원인은 코드 회귀가 아니라 config**: 프로덕션에서 `pg_enabled()`가
False = **DATABASE_URL이 실제로 안 먹고** 있고, 예전 부팅 가드는 `APP_ENV=="production"`일 때만
실패해서(그 값 미설정) **조용히 휘발 운영**됐다.

→ **새 이관 불필요(이미 이관됨). 실제 수리 = ① config(DATABASE_URL) + ② '조용한 휘발' 코드 봉인.**

## 수리 (이번 PR — 조용한 휘발 봉인 + 관측성)
- **부팅 가드 확장**: 조건을 `APP_ENV==production` → **`is_deployed()`**(Render 마커 `RENDER`/
  `RENDER_SERVICE_ID` 등)로 넓힘. 배포 컨테이너에서 PG 없으면 **부팅 실패**(데이터 새는 것 원천 차단).
  의도적 휘발은 `ALLOW_VOLATILE_STORAGE=1`로만 명시 허용. CI/dev/pytest는 is_deployed=False(무영향).
- **`/health` 저장 내구성 신호**: `storage:{durable,backend,url_set,deployed,volatile_in_production}`.
  `volatile_in_production=true`면 배포마다 소실 중 = 밖에서 즉시 보임(조용한 손실 박멸).
- **운영 실증 스크립트** `scripts/persistence_check.py`: `status`(읽기전용 신호) / `seed`(QA-TEST- 1건,
  배포 전) / `verify`(배포 후 생존 확인=SURVIVED/LOST) / `cleanup`(QA-TEST-만). 실유저 데이터 불접촉.

## ③ 같은 휘발 위험 데이터 — 전수 (durability 계층)
Render 컨테이너 = 디스크·in-memory 모두 배포마다 초기화. 저장소별 내구 계층:

| 계층 | 저장소 | 배포 생존 조건 |
|---|---|---|
| **PG** (DATABASE_URL 죽으면 함께 소실) | `collect_history`, `user_tokens`(personal_tokens), `orders`, `market_credentials`(market_links) | DATABASE_URL(6543) 도달 |
| **Sheets** (DATABASE_URL와 무관) | `word_rules`·`collect_groups`·`pccc_store`·`translation_usage`·`billing_store`·`passkey_store`·`my_sources_store` | GOOGLE_SHEET_ID 설정 |
| **로컬파일/인메모리 전용** (항상 소실) | `audit_store`·`diagnostic_token` 등(PG·Sheets 백엔드 없음) | (내구 백엔드 없음 — 배포마다 소실) |
| 세션 키 | SECRET_KEY → Sheets `app_config` → /tmp 파일 | SECRET_KEY 또는 GOOGLE_SHEET_ID |

→ **collect_history만이 아니라 PG 계층 4개(수집·토큰·주문·마켓연동)가 DATABASE_URL 소실 시 함께 소실.**
   로컬전용 계층(audit·diagnostic_token)은 **env와 무관하게 배포마다 소실** — 수리는 목록 보고 후 별도 트랙.

## 완료 보고 조건 (5항 + 해시)
1. **계약 그린 + 인위회귀**: `tests/test_v87_w3_persistence.py`(7) — 로컬 강제→재시작 소실 재현(LOST) /
   내구 백엔드 생존(SURVIVED) / storage_status·/health 신호 / is_deployed 판정 / 부팅가드 확장·스크립트 안전. ✅
2. **버전/배포 해시 + /health**: 코드 해시(머지 후). `/health.storage`가 내구성 노출. Render 배포는 **오너**.
3. **운영 실증(오너 실행)**: `python scripts/persistence_check.py seed` → 배포 → `verify` = **SURVIVED** 출력 첨부.
   실유저 PG는 불가침이라 제가 직접 못 함 — DATABASE_URL 설정 후 오너가 실증.
4. **3항 전수 목록**: 위 표.

## 오너 액션 (실제 수리)
1. Render 환경변수 **DATABASE_URL(6543 풀러) + DATABASE_URL_DIRECT(5432)** 설정·연결 확인
   (부팅 로그 `DB 연결: Supabase OK`). 필요 시 `APP_ENV=production`.
2. 배포 → `/health`의 `storage.durable=true` 확인 → `persistence_check.py seed`→배포→`verify=SURVIVED`.
   (이 PR 배포 후 DATABASE_URL이 안 잡혀 있으면 **부팅이 실패**하며 사유를 로그로 명시 — 조용한 손실 대신
   즉시 드러남. 그게 이 봉인의 목적.)
3. 실유저 데이터 이관/복구는 하지 않음(휘발이면 이미 없음 — 확인만).

금지 구조 준수: 확장 디렉토리 무변경. Supabase 스키마 파괴적 변경 0(ADD만). 실유저 데이터 이관은 대상
목록 제시→오너 확인 후에만. 자동 삭제 없음(persistence_check cleanup은 QA-TEST-만).
