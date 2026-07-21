# v79 STEP2 — sku 정제 (빈 항목 제거 + 동일 spec dedupe)

## 증상(오너 실기기 1.5.108)
테무·라쿠텐 sku가 2~3배 반복 + 빈 sku(`{spec:[], price:''}`)가 진단 로그에 저장.

## 근본 원인
`_fromJson`의 `_walk`가 같은 sku 배열을 여러 상태(라이브 전역 + 인라인 `<script>` 텍스트)에서 재방문 →
동일 sku 엔트리가 2~3회 `res.skus.push`. 옵션(axisMap 파생)은 `a.set`으로 dedup되지만 `res.skus` 배열은
누적. 빈 sku(스펙 추출 실패·가격 없음)도 그대로 저장.

## 수리
`_skusToOptions` **직전**에 `res.skus` 정제:
- **빈 항목 제거**: `spec`도 없고 `price`도 없는 항목 드롭(정직 — 쓸모 없는 노이즈).
- **동일 spec dedupe**: spec 값 집합 서명(정렬·제어문자 join)으로 유일화. 동일 spec 재등장 시 기존이
  무가격이고 새 것이 유가격이면 교체(정보 우위).
- 옵션은 axisMap 파생이라 **무영향**(이미 dedup).

## 계약(브리프)
> STEP 2 — 빈 sku({spec:[],price:''}) 제거 + 동일 spec 중복 dedupe. 계약: sku에 빈 항목 0·중복 0.

## 판정
- 가드 `tests/test_v79_sku_sanitize.py`(3): source-contract(빈 제거·무가격→유가격 교체·정제 후 옵션 변환) +
  **Playwright**: 테무식 상태(동일 spec 3+2회 반복 + 빈 sku 1) → **skus 2건**(빈 0·중복 0), 옵션 색상[2]·사이즈[2] 유지.
- **판정 캡처**: `step2-sku-sanitize.png`(BEFORE skus 6 오염 → AFTER skus 2 정직).
- 전체 **11444 passed / 22 skipped**. manifest 1.5.109→**1.5.110**.

## 금지 준수
- 추출기 변경 = 하네스 계약 동반(dedicated sku 정제 가드 + 기존 실페이지 하네스 그린) · 가짜 데이터 0.

적용 스킬: (확장 추출기 순수 함수 — UI 없음. impeccable/humanizer CLI 미설치.)
