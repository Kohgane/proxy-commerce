# v76 STEP1 — 제목 새니타이저 (전 마켓 공통)

## 배경(오너 하네 기준선)
- 요시다: 제목 꼬리 오염 `... | 吉田カバン`.
- 아마존: 제목 머리 오염 `Amazon.com: ...`.
- 라쿠텐: `【楽天市場】...` 접두 흔함.

## 구현
`kgp-extractor.js`에 **최종 제목 정화 관문** 신설 — 어댑터/티어 선택이 끝난 제목에 `_sanitizeTitle(title, location.href)`
1회 적용(전 마켓 공통).

- **`_SITE_BRAND_RE`**: 사이트 브랜드 사전(amazon·aliexpress·rakuten·楽天市場·temu·qoo10·mercari·yahoo쇼핑·
  paypaymall·吉田カバン/요시다/yoshida·iherb·dhgate·tmall·taobao·1688·shopee·ebay).
- **접두 제거**: `【…楽天/市場/store/shop/mall/ストア…】` + `(amazon|楽天市場|rakuten|aliexpress|temu|qoo10) [:：|｜-–·]`.
- **접미 제거**: 구분자(`|｜:：-–·`) 뒤 세그먼트가 브랜드 사전과 일치하면 절단(최대 3회 반복 — 다중 꼬리).
- **제네릭(사전 밖 도메인 브랜드)**: 마지막 세그먼트가 **도메인 SLD**(`_brandFromHost`, 4자↑)와 접두 일치하면 절단
  (예: `someshop.com` → `... | someshop` 꼬리 제거). 짧은/모호한 브랜드는 보존(오탐 방지).
- **본문 보존**: 상품명 내부의 정상 구분자/단어는 건드리지 않음. 깨끗한 제목은 불변.

## 판정
- 가드 `tests/test_v76_title_sanitize.py`(4): manifest 핀 + source-contract(`_sanitizeTitle`/`_brandFromHost`/
  `_SITE_BRAND_RE` + 최종 제목 적용) + **node 8종 오염 패턴 → 사이트명 0**(정규화 결과 일치 + 사이트명 잔존 0) +
  전 픽스처 `title_contains`↔`title_excludes` 짝 강제(정직 회귀 가드).
- 실페이지 하네스 `tests/test_v70_realpage_harness.py`에 **`title_excludes`** 계약 추가 → 픽스처 8종 제목에
  사이트명 0을 실 kgp-extractor로 검증. 신규 픽스처 `yoshida-detail`(오염 og/h1/ld+json → 정화 후
  "PORTER TANKER ショルダーバッグ (S)").
- **판정 캡처**: `step1-title-sanitize.png`(실 `_sanitizeTitle` 8종 전/후 — Amazon.com:·|吉田カバン·|요시다·
  【楽天市場】·-AliExpress·｜楽天市場·도메인 세그먼트(someshop) 전부 제거, 사이트명 0, 상품명 본문·깨끗한 제목 불변).
- manifest 1.5.97→**1.5.98**(재로딩) + 버전핀 갱신.

## 계약(브리프)
> STEP 1 — 제목 새니타이저 (전 마켓 공통) … 계약: 픽스처 8종 제목에 사이트명 0.

전 픽스처(amazon-dp·temu·ali·yoshida-detail)에 `title_excludes` 부여 + 실페이지 하네스 그린 → 계약 충족.

## 금지 준수
- 상품명 훼손 0(본문·정상 구분자 보존, 짧은/모호 브랜드는 보존해 오탐 방지).
- 가짜 성공 0(정화는 제거만 — 없는 제목 생성 안 함, 빈 제목이면 빈 채 유지).
- 추출기 변경 = 하네스 계약 동반(realpage title_excludes + node 8패턴).

적용 스킬: (확장 추출기 순수 함수 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
