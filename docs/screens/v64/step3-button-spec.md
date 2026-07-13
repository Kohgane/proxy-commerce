# v64 STEP3 — 수집 버튼 스펙 확정

## 증상
- 호버 [수집] 버튼: 원 과대·글자 과소, 카드 밖 부유(요시다 '수집됨✓' 스타일과 불일치).

## 수리 (`kgpQuickBtnStyle` / `_kgpAnchorCss`)
- **지름 절반**: `min-height` 66→**34px**, 패딩 축소, 아이콘 21→**14px** — 텍스트 위주 필.
- **글자 위계 ↑**: 아이콘을 줄이고 라벨(수집/수집됨 ✓)이 주가 되는 알약.
- **앵커(이미지 영역 오버레이)**: 기본 **가운데**, 설정에서 **좌하(7시 bl)** / **우하(5시 br)** 선택. 터치기기는 우상단 상시 소형. 수집됨 배지도 동일 앵커(같은 버튼).
- **토큰 준수**: 먹(#1A1714) 배경 · 금(#C9A24B) 테 · 수집됨=청록(#119A8E). 임의 색 0.

## 설정 (사이트 무관 공유)
- `KGP_HOVER_ANCHOR` = `chrome.storage.local`의 `kgp_hover_anchor`(center/bl/br). 팝업 `수집 버튼 위치` 셀렉트가 설정 → `onChanged`로 열린 탭 즉시 재적용(page localStorage 아님 = 모든 사이트 공유).

## 판정
- 가드 `tests/test_v64_button_spec.py` (4):
  - `min-height:34px`·66px 제거·먹/금/청록 토큰·아이콘 14px.
  - 앵커 배선(KGP_HOVER_ANCHOR·팝업 셀렉트·center/bl/br 옵션).
  - **node**: `_kgpAnchorCss` — center=translate, bl=bottom+left, br=bottom+right.
  - manifest 1.5.66.
- 실기기(요시다·아마존·테무 3사이트 호버 버튼 위치·크기 통일) 캡처는 오너 환경 — 프록시 라이브 차단.

적용 스킬: **gogabridj-design**(먹/금/청록 토큰·알약·이모지0·요시다 '수집됨✓' 스타일 유지). impeccable/humanizer CLI 미설치→의도 수동.
