# DB 이사: Supabase → 오라클 A1 (오너 긴급 2026-11-12 · 「무료로 간다」)

Supabase 무료 조직 전송량 402(이번 주기 15.9GB/5GB) — 같은 조직의 LinkLynk·아난시까지 막힌다. 이 DB만 A1(오라클 Always Free ·
아웃바운드 10TB/월)로 옮겨 Supabase 조직에서 뺀다. **아난시·옆 마이크로(instance-20260824-1457)는 손대지 않는다.**

| 파일 | 하는 일 | 어디서 |
|---|---|---|
| `setup_pg16.sh` | PostgreSQL 16 · 자체 서명 TLS(`ssl=on`, TLS1.2+) · `hostssl`+scram만 · 5432는 Render CIDR만(pg_hba + 호스트 방화벽) · 앱 계정/DB | A1 (root) |
| `migrate_from_supabase.sh` | `MODE=schema` 스키마 리허설 · `MODE=data` 덤프→복원→**표별 건수 대조**(다르면 exit 2) | A1 |
| `backup_daily.sh` + `kgp-backup.{service,timer}` | 매일 03:30 KST pg_dump · 로컬 7일 · **외부 암호화 사본 1곳**(GitHub 비공개 저장소 또는 HF 비공개 데이터셋) | A1 |

비밀번호·연결 문자열은 **파일**(600)에만 — 명령줄·채팅·로그에 붙이지 않는다.

## 순서

1. **OCI 콘솔(오너):** A1에 예약 공인 IP(Reserved Public IP) 붙이기 → VCN › 보안 목록(또는 NSG) 수신: TCP 5432, 원본 = Render
   아웃바운드 CIDR 각각(`0.0.0.0/0` 금지). Render 값: 대시보드 › 이 서비스 › **Connect › Outbound**(싱가포르) 목록.
2. **A1:** `sudo RENDER_CIDRS="<위 목록, 쉼표>" bash setup_pg16.sh` → 비밀번호는 `/root/.kgp_db_pass`에 생긴다.
   - **확정값(감독 11-14 · Render Outbound 싱가포르):** `74.220.52.0/24`, `74.220.60.0/24` — 그대로:
     `sudo RENDER_CIDRS="74.220.52.0/24,74.220.60.0/24" bash setup_pg16.sh`
   - OCI 보안 규칙(TCP 5432 · 원본 위 두 대역)은 감독이 콘솔에서 넣는다.
   - CC 클라우드 세션은 A1에 SSH로 닿지 못한다(샌드박스 밖 TCP 막힘 · Remote Control 폴더 없음) — A1 실행은 SSH 되는 쪽에서.
3. **A1 — 스키마 리허설(지금 가능):** `SRC_URL_FILE`(Supabase `DATABASE_URL_DIRECT` 한 줄) · `DST_URL_FILE`(A1 문자열 한 줄) 만들고
   `MODE=schema bash migrate_from_supabase.sh`. Supabase가 402로 연결을 막으면 대신 앱 스키마로: 배포된 앱이 부팅 때 같은 파일
   (`src/db/schema_stage1~20.sql`)을 적용한다 — 로컬 PG16 리허설에서 운영 public 스키마와 표·칸·타입 일치 확인(아래 기록).
4. **11/19 풀리는 즉시:** `MODE=data bash migrate_from_supabase.sh` → 「건수 전부 같음 ✔」 확인. 다르면 전환하지 않는다.
5. **백업 켜기:** 스크립트를 `/opt/kgp/`에 두고 `/etc/kgp-backup.env`(600) 작성 → `systemctl enable --now kgp-backup.timer` →
   `systemctl start kgp-backup.service`로 한 번 돌려 로컬·외부 둘 다 생겼는지 본다. 백업 키 `/root/.kgp_backup_key`는 **오프라인 사본
   하나**(키를 잃으면 외부 사본은 못 연다).
6. **Render env 교체 — 오너 확인 필수(CC는 하지 않는다):** 아래 「전환」.

## 전환 (오너가 Render에서)

바꿀 값 이름(서비스 env, 이 순서로 저장 후 한 번 재배포):

| 순서 | 이름 | 새 값 |
|---|---|---|
| 1 | `DATABASE_URL` | `postgresql://kgp_app:<비밀번호>@<A1 예약 IP>:5432/gogadb?sslmode=require` |
| 2 | `DATABASE_URL_DIRECT` | 같은 값(A1은 풀러가 없다 — 스키마 적용도 같은 곳) |
| 3 | `SUPABASE_DB_URL` | 있으면 **지운다**(앱은 `DATABASE_URL`을 먼저 읽지만, 남겨 두면 헷갈린다) |

- 전환 직전 `MODE=data`를 한 번 더(마지막 쓰기까지) → 건수 같음 확인 → env 저장 → 재배포.
- 확인: `/health/deep` 200 · `rss:restart` boot 줄 · 수집 목록이 보이는지 · 새 수집 1건이 A1에 들어가는지.
- **되돌리기:** 위 세 값을 예전 Supabase 값으로 되돌려 저장 → 재배포. 단 전환 뒤 A1에 쓴 데이터는 Supabase에 없다 — 되돌릴 땐
  `SRC=A1 · DST=Supabase`로 `MODE=data`를 한 번 돌려 옮긴 뒤 env를 바꾼다(Supabase가 열려 있을 때만).
- 앱 쪽 연결 설정은 그대로 맞는다: psycopg3 · prepared statement 끔 · 요청 풀 5 + 백그라운드 풀 2(워커당) — A1 `max_connections=60`.

## 로컬 리허설 기록 (2026-11-12 · CC)

- PG16 빈 DB에 `init_schema()`(stage1~20) → 운영 public **22개 표의 칸·타입이 전부 같음**. 차이 1: 운영에만 `checklist` 표
  (이 저장소 코드가 만들지 않는다 — `pg_dump`가 그대로 옮긴다).
- `migrate_from_supabase.sh`: schema 모드 인덱스 60=60 · data 모드 표별 건수 같음 ✔ (로컬 두 DB로).
- `backup_daily.sh`: 덤프 → 로컬 보관 → 암호화본 git push → 받아서 복호화 → `pg_restore --list` 표 데이터 21개 확인.
- 운영 확장: pgcrypto · uuid-ossp · pg_stat_statements(+ Supabase 전용 supabase_vault — 앱은 안 씀).
