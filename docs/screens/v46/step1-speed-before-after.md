# v46 STEP1 — 속도 전/후 (로컬 PG 실측, 2000행·extra_json 40이미지+상세+리뷰+스펙)

> ⚠️ 로컬 PostgreSQL 16 실측. **배포서버(kohganepercentiii.com) Server-Timing 캡처는 오너 실기기 몫**
> (에이전트 프록시가 배포 도메인 CONNECT 차단 — 저는 배포 사이트 접근 불가).

## 병목 측정 (수리 전, 스토어 호출 분해)
| 호출 | 시간 | 원인 |
|---|---|---|
| list_items(50행, full) | 27ms | (경미) |
| **summary** | **438ms** | list_items(전체 2000행) → 대형 extra_json **detoast** 후 파이썬 집계 |
| **distinct_domains** | **437ms** | 동일(전체 detoast) |
| 합(=목록 엔드포인트 db) | **871ms** | summary+distinct 지배 |

EXPLAIN: 순수 count/DISTINCT SQL 자체는 1.9ms(seq scan, buffered) — 느린 건 SQL이 아니라
전체 행을 파이썬으로 끌어와 detoast한 스토어 로직.

## 수리
1. 스토어 summary/distinct → **PG SQL 집계 위임**(count(*) FILTER / SELECT DISTINCT domain) — 전체 행 detoast 폐지.
2. 목록 list_items **lean projection** — extra_json에서 목록에 필요한 소필드(title_ko/en·uploaded·price_status·
   warnings·첫 이미지 1장)만 jsonb_build_object로 축약. 대형(이미지 40장·상세·리뷰·스펙) 제외. 대표 썸네일=image_url 컬럼.

## 전/후
| 페이지 | BEFORE | AFTER | 배속 |
|---|---|---|---|
| 수집이력 목록(2000행·40img) | **871ms** | **27ms** | **32×** |
| 무한스크롤 조각 | (summary 미호출) | ~20ms | — |
| 드로어(단건 full) | 18ms(#440 speed3) | 18ms | 유지 |

목표(≤전÷3) 대폭 초과. 프로덕션 절대치는 풀러 지연이 더해지나, 이 병목(전체 detoast) 제거가 지배적.
