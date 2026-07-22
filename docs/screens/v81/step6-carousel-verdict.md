# v81 STEP6 — 알리 캐러셀 판정 회수 (v80 STEP2 배포 확인)

## 대상
v80 STEP2(#538) — 알리 카드 호버 시 자동 슬라이드로 img 부모(swiper-slide)가 교체돼 우리 수집버튼이 증발하던
문제를, **최외곽 캐러셀 컨테이너(안정, 교체 안 됨) 앵커** + **z-index 상향(2147483644, 호버 오버레이 …643 위)**
으로 수리한 커밋.

## 배포 감사
- **머지 확인**: `git log origin/main` — `7be9918 v80 STEP2: 알리 캐러셀 안정 앵커 …(#538)` 반영.
- **코드 실존(main)**: `content_script.js`에
  - `const _carRe = /(carousel|swiper|slider|slick|gallery|magnifier)/i;`
  - `if (_carRe.test(tok)) carousel = cur;`(계속 올라가며 **최외곽** 갱신)
  - `host = carousel || imgEl.parentElement;`(캐러셀 없으면 정밀 앵커 — 일반 사이트 회귀 0)
  - `"z-index:2147483644 !important"`
- **가드 모듈 존재**: `tests/test_v80_carousel_anchor.py`.

## 판정 (라이브 회수)
가드 `tests/test_v81_ali_carousel_verdict.py`(2):
- `test_v80_step2_carousel_anchor_deployed`: 위 소스계약 present + v80 가드 모듈 존재(배포 감사).
- `test_verdict_button_survives_slide_swap`(Playwright): 알리식 swiper 목록 주입 → 첫 카드 버튼이 **캐러셀
  컨테이너 앵커** · **슬라이드 innerHTML 교체 후에도 버튼 생존·캐러셀 잔류** · **z ≥ 2147483644**.
- 실측: `{anchor:true, z:2147483644, survived:true, stillCarousel:true}`.

**verdict = 채택·배포 확인(deployed & green).** 회귀 없음. 코드 변경 없음(감사 전용, manifest bump 없음).

## 캡처
`docs/screens/v81/step6-carousel-verdict.png` — 실 content_script 주입 결과 배너: 컨테이너 앵커 ✓ · z-index
2147483644(오버레이 위 ✓) · 슬라이드 교체 후 버튼 생존 ✓ · 캐러셀 잔류 ✓.

※ 오너 최종 라이브 확인은 확장 1.5.116+ 재로딩 후 실제 알리 목록에서(v80 STEP2 캡처와 동일 흐름).

적용 스킬: (배포 감사·판정 회수 — 코드 무변경. impeccable/humanizer CLI 미설치.)
