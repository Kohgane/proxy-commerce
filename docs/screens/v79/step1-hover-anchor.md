# v79 STEP1 — hover 버튼 소멸 루프 수리 (오너 1순위)

## 증상(오너 실기기 1.5.108)
아마존·테무 목록에서 [수집] 버튼이 커서 위치(이미지 중앙)에 나타나며 타일 mouseleave를 유발 → 숨김 →
재hover 반복(깜빡임). 버튼을 얹고 클릭할 수가 없다.

## 근본 원인
hover 판정이 **타일(`c.el`)만** 기준이고 mouseleave 시 **즉시** `opacity:0`(유예 0). 버튼이 이미지 중앙에
absolute로 뜨는데 타일 경계 밖으로 삐져나오는 순간 mouseleave가 발화 → 버튼 숨김 → 커서는 다시 이미지
위 → mouseenter → 재등장 → 무한 깜빡임. 버튼 자체는 hover 유지 대상이 아니었다.

## 수리
- hover 판정을 **[타일 ∪ 버튼] 공통**으로: `mouseenter`/`mouseleave`를 `c.el`뿐 아니라 **버튼(`q`)에도** 바인딩
  (버튼 위로 옮기면 `_show` → 유지).
- 숨김에 **200ms 유예**: `mouseleave` 시 즉시 숨기지 않고 `setTimeout(…, 200)`; 그 안에 어느 쪽이든
  `mouseenter`가 오면 타이머 취소(`_show`) → 깜빡임 루프 차단.

## 계약(브리프)
> STEP 1 — hover 판정을 [타일 ∪ 버튼]의 공통 컨테이너 기준으로(버튼도 hover 유지 대상), 숨김에 200ms 유예.
> 판정: 아마존·테무 목록에서 버튼에 마우스 얹고 클릭 가능.

## 판정
- 가드 `tests/test_v79_hover_anchor.py`(3): source-contract(200ms 유예·`_show` clear·타일+버튼 리스너) +
  **Playwright**: 타일 hover→버튼 등장(op>0.9) / 타일 leave 직후 버튼 위로 옮기면 **유지**(op>0.9, 루프 차단) /
  버튼도 이탈 후 200ms 유예 경과 뒤 숨김(op<0.1).
- **판정 캡처**: `step1-hover-anchor.png`(BEFORE 깜빡임 루프 → AFTER 버튼 유지·클릭 가능).
- 전체 **11441 passed / 22 skipped**. manifest 1.5.108→**1.5.109**.
- 오너 최종 판정: 확장 재로딩 후 아마존·테무 목록에서 버튼에 마우스 얹고 클릭되는지 녹화.

## 금지 준수
- 상시 노출 0(호버 전용) 유지 · 단일 버튼 시스템(타일당 1개) 무회귀 · 추출기 무변경.

적용 스킬: (확장 오버레이 hover 로직 — 인라인 스타일 관행, 앱 CSS 토큰 무관. impeccable/humanizer CLI 미설치.)
