# v47 STEP1 — 속도 최종 판정 + Render 승급 게이트

> 목표: 배포 실서버 3종 측정 → 판정 프레임워크로 결론(승급 권고 vs 프론트 수리) → before/after 표.
> 정직 고지: 나(에이전트)는 kohganepercentiii.com에 접근할 수 없다(에이전트 프록시 403). **배포 실측 3종 캡처는 오너 몫**이다.
> 아래는 (1) 오너가 바로 판정할 수 있게 `Server-Timing` 헤더에 서버시간 분해(db/render/app)를 심었고,
> (2) 판정 기준(프레임워크)을 못박았으며, (3) 이미 머지된 서버측 근본 수리(#442)의 로컬 실측을 근거로 남긴다.

## 1) 측정 도구 — Server-Timing 서버시간 분해 (이번 STEP1 추가)

`src/middleware/request_logger.py`가 모든 응답에 `Server-Timing`을 붙인다. v47에서 **`app` 구간**을 추가:

```
Server-Timing: db;dur=<쿼리ms>, render;dur=<템플릿ms>, app;dur=<나머지서버ms>, total;dur=<총서버ms>
```

- `db` = PG 쿼리 누적(perf_block "db")
- `render` = 템플릿 렌더 누적(perf_block "render")
- `app` = `total − db − render` (파이썬 로직·직렬화·미들웨어 등 나머지 서버시간)
- `total` = 서버가 응답을 만드는 데 쓴 전체시간(=브라우저 TTFB의 서버측 성분)

**오너 판정 절차(크롬 개발자도구 → Network 탭):**
1. `/seller/collect`(수집이력), 카탈로그 목록, 드로어 열기 3종을 각각 로드.
2. 각 요청의 **Timing** 하위 "Server-Timing" 막대에서 `total`(서버시간)과 전체 요청시간을 본다.
3. **TTFB(≈서버 total) 비중 = server total ÷ 전체 요청시간**.

## 2) 판정 프레임워크 (게이트)

| 조건 | 결론 | 행동 |
|---|---|---|
| 서버시간(TTFB) 비중 **≥ 50%** | **Render Standard 승급 권고** | 승급은 **오너 결정**. 코드는 승급하지 않는다. `db`가 큰지 `app`이 큰지 병기 |
| 서버시간 비중 **< 50%** | 프론트 병목 | JS 번들 분할·죽은코드 제거, WOFF2 폰트 서브셋+`font-display:swap`, 이미지 lazy+썸네일 리사이즈, 정적 immutable+압축 |
| `db` 가 total의 **≥ 50%** | 쿼리 병목 | 쿼리로그 N+1 점검, 목록 SELECT서 대형컬럼 제외(lean), 커버링 인덱스 |

`app` 이 크면(=db/render 아닌데 total 큼) → 파이썬 직렬화/미들웨어 or **Render 인스턴스 CPU 한계**(Starter 0.5 CPU) → 승급 근거.

## 3) 이미 머지된 서버측 근본 수리 (#442) — 로컬 실측 근거

v46 STEP1에서 수집이력 목록의 진짜 병목을 로컬 PG로 확정·수리(머지 완료):

- **원인:** `summary()`·`distinct_domains()` 가 `list_items(full)` 로 전 행을 읽어 **큰 jsonb(extra_json, 이미지 40장)를 TOAST 디토스트** → 한 페이지에서 438ms×2.
- **수리:** `summary()`→ `count(*) FILTER` 순수 집계, `distinct_domains()`→ `SELECT DISTINCT domain`, 목록은 `_SELECT_LEAN`(대형 배열 제외 projection).
- **로컬 실측(PG 16):** 수집이력 페이지 서버시간 **871ms → 27ms (약 32×)**.

## 4) before/after 표 (배포 실측은 오너 캡처)

| 화면 | before(서버 total) | after(서버 total) | 목표 |
|---|---|---|---|
| 수집이력 `/seller/collect/history` | (오너 캡처) | (오너 캡처) | after ≤ before ÷ 3 |
| 카탈로그 목록 | (오너 캡처) | (오너 캡처) | after ≤ before ÷ 3 |
| 드로어 열기 | (오너 캡처) | (오너 캡처) | after ≤ before ÷ 3 |

> 로컬 근거(#442)로 서버측은 32× 개선됨을 실측. 배포 환경에서 남는 비중이 서버(≥50%)면 위 게이트대로 **Standard 승급**,
> 프론트(<50%)면 §2 프론트 수리로 넘어간다. 어느 쪽이든 `Server-Timing`의 `app`/`db`/`render` 분해로 한눈에 판정된다.

## 5) 현재 상태(정직)
- ✅ 서버측 근본 수리(#442) — 머지·로컬 실측 32×.
- ✅ 정적 immutable 캐시(버전드 1년) + gzip 압축 — 기존(v40-B/v8) 유지.
- ✅ `Server-Timing` db/render/**app**/total 분해 — 이번 STEP1 추가(오너 판정용).
- ⏳ 배포 실측 3종 + 승급 여부 결론 — **오너 캡처 대기**(에이전트 프록시 접근 불가, 켠 척 금지).
