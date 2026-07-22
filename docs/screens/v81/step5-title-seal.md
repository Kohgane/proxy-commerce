# v81 STEP5 — 제목 새니타이저 서버 봉인 (코어 폴백 포함)

## 증상(오너)
`PORTER STROLL 2WAY BAG | YOSHIDA & Co.` 접미가 그대로 저장(STROLL BAG 건). 코어 폴백 수집(북마클릿 og-meta)은
클라이언트 `_sanitizeTitle`을 **안 타고**, 클라 새니타이저조차 법인 접미(`& Co.`)는 `$` 앵커를 막혀 못 지웠다.

## 근본 원인
- 코어 폴백은 서버로 og-meta title을 그대로 보냄(클라 sanitize 우회).
- 클라/서버 어디에도 **브랜드 뒤 법인 지정 접미**(`& Co.`, `& Co., Ltd.`, `Inc.`, `株式会社`…) 제거 로직이 없어
  `| YOSHIDA & Co.`가 살아남음(브랜드 `YOSHIDA` 뒤 `& Co.`가 `$` 앞을 막음).

## 수리
- `src/collectors/collect_sanitize.py`에 **서버 `sanitize_title(title, url)`** 신설 — 클라 `_sanitizeTitle` 포팅
  (마켓 브래킷 접두 `【…市場…】`, 사이트 접두 `Amazon.com:`·`楽天市場｜`, 브랜드 접미) + **법인 접미**
  `(?:& )?(co\.?(,? ?ltd\.?)?|company|inc\.?|ltd\.?|corp\.?|gmbh|s\.?a\.?|株式会社|有限会社|カバン)*` 까지 제거.
  도메인 브랜드(SLD) 제네릭 마지막 세그먼트 제거도 포팅. **과도 제거 시 원문 보존**(빈 결과 금지).
- `sanitize_payload`(저장 직전 **단일 지점**, 모든 수집 경로가 통과 — 확장·북마클릿·수동)가 `sanitize_title` 호출
  → **코어 폴백 포함 전 경로 봉인**. 서버 순수 변경(확장 런타임 무변경, manifest bump 없음).

## 판정 (| YOSHIDA & Co. 접미 재발 0)
가드 `tests/test_v81_title_seal.py`(5):
- 단위: `| YOSHIDA & Co.`·`& Co., LTD.`·라쿠텐/아마존 접두·마켓 브래킷 → 정확 제거 · **접미 재발 0**.
- 과도제거 방지: 브랜드 없는 제목 불변 · 전부 브랜드면 원문 보존 · **멱등**.
- 소스계약: `sanitize_payload`가 `sanitize_title` 호출(단일 지점).
- **E2E**: `mode=core`로 `/api/v1/collect/extension` POST(요시다 title) → 저장 `product_data.title`에
  `YOSHIDA & Co.` 없음 · `PORTER STROLL 2WAY BAG` 유지.
- collect/sanitize/확장 회귀 39 그린 · 전체 스위트 그린.

## 캡처
`docs/screens/v81/step5-title-seal.png` — 실 `sanitize_title` 출력 before/after 표(코어 폴백·법인 접미·라쿠텐·
아마존·마켓 브래킷 제거 + 브랜드 없는 제목 불변).

## 금지 준수
빈 제목 저장 0(과도 제거 시 원문 보존) · 단일 지점 봉인(경로별 누락 0) · 정직(실 함수 출력 캡처).

적용 스킬: (백엔드 서버 새니타이즈 — UI 없음. impeccable/humanizer CLI 미설치.)
