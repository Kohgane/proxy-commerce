# v72 STEP3 — 아마존 가격 "-" 감사

## 증상 (오너 캡처)
- 아마존 2건 가격 "-".

## 감사 (수집 로그 분기)
- 아마존 목록 카드 가격 추출은 **작동**: `_kgpAmazonCards`가 `.a-price .a-offscreen`("$29.99")에서 추출.
- 호버 단건 수집(`kgpQuickCollect`)은 카드의 가격·제목을 **1차로 담아 저장**(meta). 그러나 **보강 큐에 자동 등록을 안 함** — 벌크 경로(`kgpRunBulk`)는 `enrichStart(resp.enrichTargets)`를 호출하는데 호버 경로는 누락.
- ⇒ **목록가가 없는 카드**('See options' 변형·딜 카드)는 호버 수집 후 "-"로 남고 보강도 안 됨. **그게 수리 지점**.

## 수리 (`content_script.js` `kgpQuickCollect`)
- 성공 시 `resp.enrichTargets`(서버 회신 item_id+url)로 **보강 큐 자동 등록**(`enrichStart`) — 벌크 경로와 동일. 목록가 없는 카드도 상세 페이지 방문(보강 창)으로 가격·옵션·상세·이미지 fill-only 채움.
- 목록 카드 가격/제목은 이미 1차로 담겨 즉시 저장(meta) → 있으면 즉시 표기, 없으면 보강으로 채움.

## 판정
- 가드 `tests/test_v72_amazon_price_audit.py` (2):
  - 소스계약(호버 meta에 가격/제목 1차 + 성공 시 enrichTargets→enrichStart).
  - **amazon-search 픽스처**(`fixtures/realpages/synthetic-amazon-search.html`) Playwright: `kgpFindCards` → `.a-price` 카드 **$29.99·$14.50 추출** + 'See options' 카드는 **빈 가격**(카드 인식·보강 대상).
- `test_v42_e3_hover_collect`·`test_v64_bulk_enrich` 그린. manifest 1.5.87.
- **실기기(오너 몫)**: 아마존 호버 수집 1건 → 즉시 가격 채움(목록가 있으면) + 보강 후 전 필드. (개발 프록시 라이브 아마존 차단.)

## 금지 준수
- 가짜 성공 0(목록가 없으면 빈값·보강으로 채움) · 서버측 직접 크롤 0(보강 창 DOM).

적용 스킬: (확장 오케스트레이션 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
