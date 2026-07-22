# v81 STEP7 — 변경 가시성 (콘솔 배너 + 체인지로그 페이지)

## 요구(브리프)
콘솔 상단 버전 배너 '이번 업데이트: ○○·○○ (자세히)' + 체인지로그 페이지(배치 버전별 3줄 요약 자동 누적).

## 구현
1. **단일 소스** `src/seller_console/changelog.py` — `CHANGELOG`(배치별 `{version, date, title, lines[≤3]}`,
   최신이 맨 앞). 새 배치는 dict 하나 prepend = **자동 누적**. `banner_summary()`가 최신 배치의 핵심 2줄을 배너용
   축약으로 반환. 문구는 **사용자 언어**(시스템 용어·개발 표기 0, 정직).
2. **콘솔 배너**(`_base.html`, 전 콘솔 페이지 상단): 주황 **키스톤** 점 + 금 '이번 업데이트' 라벨 + 최신 2줄 축약 +
   청록 '자세히→/seller/changelog' + 닫기. **최신 버전 1회만**(localStorage `kgp_cl_seen`=버전 dismiss — 새 배치
   나오면 다시 뜸, 나머진 조용). 컨텍스트 프로세서가 `changelog_banner` 주입(실패 시 배너만 생략).
3. **체인지로그 페이지** `/seller/changelog`(`changelog.html`): CHANGELOG eyebrow(금) + 세리프 대형 헤드라인
   '이번엔 이런 걸 손봤어요' + **게이트 아치 디바이더(다리 시그니처)** + 배치 카드(최신=주황 키스톤 배지,
   과거=청록 배지) + 각 줄머리 **금 키스톤 데크 점** + hover 살짝 떠오름.

## gogabridj-design 적용
- 토큰만(먹 --ink / 한지·종이 --paper / 금 --gold·--gold-ink / 청록 --teal / 주황 --orange) — **하드코딩 hex 0**
  (test_design_tokens_v18 그린). 강조 1색/화면: CTA·키스톤=주황, 링크·배지=청록, 포인트=금.
- **시그니처(다리)**: 게이트 아치 디바이더 + 데크 키스톤 점으로 '다리를 건너는 흐름' 은은하게. 화면당 키스톤(주황)
  시선 고정점 1군.
- **이모지 0**(bi-stars·bi-check-lg·bi-arrow-right-short만) · reduced-motion 정지 · 모바일 배너 줄바꿈.

## 판정
가드 `tests/test_v81_changelog.py`(4):
- 단일 소스: 최신 v81 맨 앞·배치당 ≤3줄·banner_summary 버전+≤2줄.
- 라우트: `/seller/changelog` 200 + 헤드라인 + **전 배치(v77~v81) 3줄 전부 렌더**(HTML 이스케이프 반영).
- 배너: 대시보드에 `kgpUpdateBanner` + '이번 업데이트' + `/seller/changelog` 링크 + `kgp_cl_seen` dismiss.
- gogabridj 계약: 이모지 0 · STEP7 CSS 하드코딩 hex 0 · 키스톤(주황) present.
- 회귀: dead-buttons·emoji-sweep·global-audit·design-token 88 그린. 전체 스위트 그린.

## 캡처
- `docs/screens/v81/step7-changelog.png` — 체인지로그 페이지 전체(상단 배너 + 게이트 아치 + v81~v77 카드).
- `docs/screens/v81/step7-banner.png` — 콘솔 '이번 업데이트' 배너 클로즈업.

적용 스킬: **gogabridj-design**(먹/금/청록/주황 토큰·게이트 아치·키스톤 시그니처·이모지 0·하드코딩 hex 0).
impeccable/humanizer CLI 미설치 → 슬롭 제거·사람 톤 수동 적용(사용자 언어 3줄 요약).
