# AI_SOURCING.md — AI 소싱 허브 운영 가이드 (Phase 160)

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

3. **My Sources**
   - 자주 쓰는 도메인 저장/삭제/재수집
   - 저장소: `src/seller_console/my_sources_store.py`
   - Sheets(`my_sources`) 미설정 시 인메모리 fallback

4. **확장/북마클릿 안내**
   - `/seller/me/tokens` 토큰 발급
   - `/seller/bookmarklet` 설치

---

## Discovery 연계

- 수동 수집 성공 시 신규 도메인은 Discovery 후보 등록 훅을 호출합니다.
- My Sources 추가 시에도 신규 도메인은 Discovery 후보 등록을 시도합니다.
- 제외 대상(대형 플랫폼/기존 등록 도메인)은 자동 skip 됩니다.

---

## 운영 팁

- 추천은 키 미설정/LLM 미사용 환경에서도 규칙 기반으로 안정 동작합니다.
- 후보 승인/등록 실작업은 기존 `/seller/sourcing/candidates`에서 수행합니다.
