# v47 STEP2 — 수집 상태 가시화 (성공/부분 + 필드 로그)

> 목표: 수집이 무엇을 실제로 담았는지 정직 표기 — 가짜 성공·무음 실패 박멸.
> 서버가 **단일 판정**(`src/collectors/collect_status.py`) → 목록 상태 컬럼·드로어 수집 로그·토스트가 같은 판정을 쓴다.

## 판정 규칙 (단일 소스)
7개 필드(핵심=제목·가격·이미지 / 부가=옵션·상세설명·상세이미지·리뷰·평점):
- **성공**: 7개 전부 present → 목록 `성공 N/7`.
- **부분**: 하나라도 누락 → `부분 · {누락}`(뱃지는 핵심 누락 우선, 전체는 툴팁·로그).
- **실패**: 저장 자체가 안 되면 레코드가 없음 → 토스트/HTTP가 사유(401 재발급·502 저장실패·CSP 안내).
- 가격은 값이 있어도 `price_status=needs_check`면 present 아님(임의 확정 금지).

## 3곳 정직 표기
1. **목록 상태 컬럼**(collect_history_rows.html): `성공 7/7`(초록) 또는 `부분 · 가격·이미지`(주황). archived=보관 유지.
2. **드로어 하단 수집 로그**(collect_preview.html, 접이식): 필드별 `수집됨/없음` + **소스(JSON/DOM/서버파싱/있음/없음)**.
   확장 추출기가 필드별 소스(`field_sources`: json/dom/none)를 보내면 그대로, 없으면 있음/없음(가짜 소스 날조 금지).
3. **수집 토스트**(content_script.js): `수집 완료(N/7 필드)` 또는 `부분 수집 — 이미지·리뷰 누락 (1/7 필드)`.
   corr-id dedupe(건당 1회)는 유지. 서버 `field_status`가 단일 소스(구서버면 클라 partial 폴백).

## 데이터 흐름
- 추출기(kgp-extractor.js) → `field_sources` 포함 → 서버 `extension_api`가 `compute_collect_status(extra, sources)` →
  `extra.collect_status` 저장 + 응답 `field_status`.
- 목록/드로어는 저장된 `collect_status` 우선, 없으면(옛 레코드) 렌더 시 재판정.
- 속도: lean 목록 projection에 `collect_status`만 추가(대형 배열 제외 유지 — #442 속도 보존).

## 검증(로컬)
- 판정 로직: 완전 7/7=성공, 핵심 누락=부분+핵심 나열, needs_check 가격=present 아님.
- 서버 응답: `/api/v1/collect/extension` → `field_status.status`·`missing`·`partial`(coarse 하위호환).
- 렌더: 수집이력 목록에 `부분 ·`/`성공 ` 뱃지, 드로어에 `수집 로그` + 소스(DOM) 표시 — test_client 200 실측.
- 가드: test_v47_collect_status(8). 전체 회귀 그린.

배포 캡처(오너): kohganepercentiii.com 수집이력 목록의 성공/부분 뱃지 + 드로어 수집 로그 펼침.
