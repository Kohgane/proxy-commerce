# CS 자동 번역 운영 가이드 (Phase 139)

## 개요
- 고객 문의 언어와 FAQ 언어가 다르면 자동 번역 답변을 생성합니다.
- 번역 결과는 FAQ의 `translations` 캐시에 저장됩니다.

## 환경변수
- `CS_AUTO_TRANSLATE=1`
- `CS_TRANSLATE_PROVIDER=deepl` (`deepl|openai|disabled`)

## 동작 순서
1. 동일 언어 FAQ가 있으면 그대로 사용
2. 없으면 원본 FAQ를 번역
3. 템플릿 변수(`{{customer_name}}` 등)는 번역 후 치환

## 안전 장치
- `BudgetGuard` 통과 시에만 외부 번역 호출
- 실패 시 원문 + `[번역 검수 필요]` 마커 반환
