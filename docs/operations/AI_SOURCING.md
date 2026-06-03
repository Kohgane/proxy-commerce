# AI_SOURCING.md — AI 소싱 허브 운영 가이드 (Phase 160+162)

## 개요

`/seller/sourcing`은 키워드 트렌드, Discovery 후보, 기존 소싱 후보 큐를 결합해
소싱 우선순위를 추천하는 허브입니다.

---

## 핵심 기능

1. **키워드 기반 추천**
   - 입력 키워드 + 기간(실시간/일/주/월/년)
   - 트렌드 라이저/기존 후보/Discovery 후보를 합산한 추천 카드

2. **원클릭 범용 수집**
   - URL 붙여넣기 → `/seller/collect/preview` 즉시 호출
   - 지원 어댑터 없으면 `GenericOgCollector` 폴백
   - 수집 성공 시 **"+ 소싱처로 저장"** 버튼 → 소싱처 등록소에 직접 추가

3. **소싱처 등록소 (Source Registry — Phase 162)**
   - 셀러가 원하는 몰(자사몰·소규모 브랜드몰 등)을 도메인/URL로 직접 등록
   - 저장소: `src/seller_console/my_sources_store.py`
   - Sheets(`my_sources`) 미설정 시 인메모리 fallback
   - 자세한 내용은 [소싱처 등록소 섹션](#소싱처-등록소-source-registry) 참조

4. **확장/북마클릿 안내**
   - `/seller/me/tokens` 토큰 발급
   - `/seller/bookmarklet` 설치

---

## 소싱처 등록소 (Source Registry)

### 등록 흐름

1. 셀러가 도메인(`example.com`) 또는 상품 URL(`https://brand.com/product/1`)을 입력
2. 시스템이 **개방성 프로빙** 수행 (HEAD → GET, 최대 5초 타임아웃)
3. 판정 결과:
   - `open` — OG 메타태그 또는 JSON-LD(Product 스키마) 확인됨. 수집 가능.
   - `partial` — 페이지는 응답하나 OG/JSON-LD 미확인. 부분 수집 가능성.
   - `restricted` — 403/401 응답, 연결 차단 등. **수집 어려움 경고와 함께 등록은 허용** (차단 안 함).
4. 대형 플랫폼(쿠팡/아마존/타오바오 등)은 `large_platform` 배지 표기 (전용 어댑터 존재)

### 목록 정렬

- **표시 이름(label) 기준 알파벳순** (없으면 domain 기준)
- 한글/영문 혼재 시 `casefold()` 기반 유니코드 정렬 (합리적·안정)
- 영문 → 한글 순서 (유니코드 코드포인트 기반)

### 항목 액션

| 액션 | 설명 |
|---|---|
| **재수집(↺)** | `POST /seller/sourcing/registry/<domain>/recollect` — 동일 dispatcher/collector 체인으로 수집 |
| **삭제(✕)** | `POST /seller/sourcing/my-sources` (action=remove) |
| **상세(…)** | 등록일/마지막 수집/어댑터/메모 인라인 표시 |
| **검색/필터** | 이름·도메인 즉시 필터링(클라이언트 JS) |

### API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/seller/sourcing/registry/add` | JSON 등록 (개방성 검증 포함) |
| `POST` | `/seller/sourcing/registry/<domain>/recollect` | 재수집 트리거 |
| `POST` | `/seller/sourcing/my-sources` | 폼 기반 추가/삭제/touch |
| `GET` | `/seller/sourcing/my-sources` | 목록 조회 (JSON) |

### 소비자 요청형 추가 흐름

- 셀러가 도메인을 등록하면 시스템이 Discovery 후보 자동 등록 시도
  - `register_collected_domain_candidate()` 훅 호출
  - 기존 등록/대형 플랫폼은 자동 skip
  - 어댑터 없는 신규 도메인은 Discovery 파이프라인에서 어댑터 개발 대상으로 처리

### 저장 구조 (Sheets / 인메모리)

| 컬럼 | 설명 |
|---|---|
| `domain` | 정규화된 도메인 |
| `label` | 표시 이름 |
| `note` | 메모 |
| `created_at` | 등록일 (ISO 8601) |
| `last_used_at` | 최근 사용 |
| `openness_status` | open / partial / restricted |
| `adapter_name` | generic_og / AmazonCollector / large_platform 등 |
| `last_collect_at` | 마지막 수집 시각 |
| `last_collect_result` | 마지막 수집 결과 요약 |

---

## Discovery 연계

- 수동 수집 성공 시 신규 도메인은 Discovery 후보 등록 훅을 호출합니다.
- 소싱처 등록소 추가 시에도 신규 도메인은 Discovery 후보 등록을 시도합니다.
- 제외 대상(대형 플랫폼/기존 등록 도메인)은 자동 skip 됩니다.

---

## 운영 팁

- 추천은 키 미설정/LLM 미사용 환경에서도 규칙 기반으로 안정 동작합니다.
- 후보 승인/등록 실작업은 기존 `/seller/sourcing/candidates`에서 수행합니다.
- 프로빙 타임아웃은 5초 — 느린 사이트도 등록 흐름이 막히지 않습니다.
- `GOOGLE_SHEET_ID` 미설정 시 인메모리 fallback으로 화면이 깨지지 않습니다.
