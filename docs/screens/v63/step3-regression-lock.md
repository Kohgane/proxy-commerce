# v63 STEP3 — 회귀 자물쇠 (CI 게이트)

STEP1(감지 역전)·STEP2(필드 손실 지도)의 결과를 계약으로 고정 → 무단 변경 시 CI가 막는다.

## `tests/test_v63_detection_contract.py` (5)
### 필드 계약 (파이썬 — 필드 세트 드리프트 방지)
- `collect_status.FIELDS` == `[price, images, options, detail, reviews]`, TOTAL==5.
- `field_loss_matrix.GATE_FIELDS` == `[title, price, images3, options, detail]`, threshold 0.90, 디폴트 마켓에 amazon·temu 포함.

### 셀렉터 계약 (소스 핀 — **어댑터 셀렉터 변경 시 이 테스트 필수 갱신**)
- 아마존 어댑터 셀렉터 `[data-component-type="s-search-result"], div[data-asin]:not([data-asin=""])`.
- 제네릭 앵커 폴백 컨테이너 `[class*='card' i],[class*='item' i],[class*='product' i],[class*='goods' i]`.
- `_kgpIsDetailHref` 존재 + dp/goods/product 커버.
- 감지 역전 순서: `_kgpGenericCards()`가 `_kgpAmazonCards()`보다 먼저 + `_kgpMergeCards(generic, adapter)`.

### 카드 감지 스냅샷 (node — 실 detection 파이프라인)
- `kgpFindCards`를 mock DOM에 실행:
  - 카드1 = **테무식**(이미지가 `<a>` 미포함 → 카드 컨테이너 상세앵커로 폴백).
  - 카드2 = **요시다식**(정상, 이미지가 앵커에 감싸임).
- 스냅샷 고정: **2건 감지**(테무식 앵커폴백 URL + 요시다 URL), 통화 KRW·JPY, 제네릭 경로(어댑터 미스) — STEP1 앵커 폴백 + 제네릭-first가 실제로 동작함을 못박음.

## 판정
- 어댑터/제네릭 셀렉터나 필드 세트가 바뀌면 계약 테스트가 깨져 CI(python-guard) 게이트가 막음 = 회귀 자물쇠 작동.
- CI 게이트 작동 로그: PR 체크 python-guard(계약 테스트 포함) 그린.

적용 스킬: (테스트 계약 — 런타임 변경 없음. impeccable/humanizer CLI 미설치.)
