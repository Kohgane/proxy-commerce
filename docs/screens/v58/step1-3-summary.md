# v58 — 추출 회귀 수리 + 옵션 수집 + 버전 스탬프

## STEP1 — 추출 회귀 원인 특정·수리 (결론: 확장 회귀 없음)
real Chromium(Playwright)에 kgp-extractor.js + content_script.js를 로드해 3 사이트 픽스처에서
`extractProductMeta()` 실행 → **title·price·images 전부 정상**(step1-extract-contract.json):

| 사이트 | title | price | images | source |
|---|---|---|---|---|
| generic_mall(JSON-LD) | 프리미엄 무선 이어폰 X100 | 39000 KRW | 2 | json |
| testpage(og/meta) | 데모 상품 접이식 차량용 책상 | 18900 KRW | 1 | dom |
| temu(state-json) | 미니 가습기 USB | 12900 KRW | 3 | json+dom |

→ **확장 추출은 회귀 없음.** 오너 '제목·가격·옵션 미수집'의 근원은 **북마클릿 엔티티 SyntaxError**
(`Unexpected token '&'`) — v59에서 퍼센트 인코딩으로 수리 완료(별도 PR #454, merged). 회귀 계약 테스트
`test_v58_extract_contract`로 3사이트 title·price·images를 CI 게이트에 고정(회귀 시 즉시 실패).
(FORBIDDEN 준수: 회귀가 없으므로 추출 로직을 임의 변경하지 않음 — 가짜 수정 0.)

## STEP2 — 옵션 수집 (1팩/2팩·색상·사이즈)
- `_domOptions` 확장: `<select>` 외에 **라디오·버튼 그룹**(`[role=radiogroup]`·`[class*=sku i]`·
  `[class*=option i]`·`[class*=variant i]`·`[class*=swatch i]`) 텍스트 수집 — select 없는 SPA(테무) 대응.
  추천/리뷰 영역 제외, 값 2+일 때만(확신 없으면 미수집=정직).
- 실증(button-group 픽스처): 색상[블랙,화이트]·사이즈[S,M,L]·수량[1팩,2팩] 수집.
- 드로어 옵션 탭: 옵션×값 편집 행 렌더(기존) + **누락 시 '옵션 미수집' 배지**(무음 아님, 직접 추가 유도).

## STEP3 — 버전 스탬프 (죽은 버전 혼동 차단)
- 북마클릿 토스트: `수집 중… (bm-v58)` — 서버가 파일 생성 시 `BMV` 주입. run.js 채택 시 `(bm-v58+run-v58)`.
- 확장 토스트: `수집 완료 … · ext v1.5.58` (매니페스트 버전).
- 북마클릿 페이지 최상단: **'설치 전 기존 고가수집 북마크 전부 삭제'** 경고 + 북마크 관리자 단축키(Ctrl+Shift+O).
- 확장 manifest 1.5.57→**1.5.58**.

## 판정 (배포 후 실기기 — 오너)
① testpage 초록 + `수집 중… (bm-v58)` 토스트 ② 3사이트 제목·가격 ③ 옵션 표 ④ 테무 sources=tier1 지속.
