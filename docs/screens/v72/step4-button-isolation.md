# v72 STEP4 — 버튼 스펙 격리 완성

## 증상 (오너 캡처)
- 알리에서 버튼 과대 — **사이트 상속 오염**(html/body의 큰 font-size·line-height·letter-spacing이 우리 버튼으로 상속).

## 수리 (`content_script.js`)
- **`_KGP_RESET = "all:initial !important;box-sizing:border-box !important;"`** 를 **모든 오버레이 버튼 cssText 최선두**에 부착:
  - 중앙 벌크바(`kgpBuildToolbar` `bar.style`) + 내부 버튼(`btnBase`)
  - 우측 단건 FAB(`injectCollectButton` `btn.style`) + 라벨 스팬(font-size !important)
  - 호버 수집 알약(`kgpQuickBtnStyle`) · 카드 선택 배지(`kgpCardBadgeStyle`)
- `all:initial`이 모든 상속/비상속 속성을 초기값으로 리셋(shadow DOM 동급 격리) → 이후 우리 인라인 **고정 px `!important`** 스펙만 적용. 자식 스팬은 리셋된 버튼에서 상속받아 정상(상속 오염 완전 차단). 알리·테무·아마존 픽셀 동일.

## 판정
- 가드 `tests/test_v72_button_isolation.py` (5):
  - 소스계약(_KGP_RESET 정의 + 4곳 전부 적용: 카드배지·호버알약·단건 FAB·벌크바·내부버튼).
  - **Playwright 3사이트 파라미터라이즈(알리·테무·아마존)**: 적대적 상속 CSS(`html,body{font-size:64px !important;line-height:4}`) 하에서 벌크바 폰트 = **우리 스펙 16px**(사이트 64px 상속 무력) + 바 높이 부풀지 않음(<120px). 3사이트 동일.
- 회귀: `test_v71_infinite_rescan`(node 하네스 _KGP_RESET 주입)·`test_v45_p3p4p5`(FAB 오프셋 창) 갱신. manifest 1.5.88.
- **실기기(오너 몫)**: 알리·테무·아마존 버튼 나란히 캡처(크기 동일). (개발 프록시 라이브 차단.)

## 금지 준수
- 사이트 상속 오염 0(all:initial) · 가짜 성공 0.

적용 스킬: (확장 오버레이 스타일 — 확장 인라인 스타일 관행 유지(먹/금/청록 토큰 색). gogabridj-design 토큰은 앱 CSS 전용. impeccable/humanizer CLI 미설치.)
