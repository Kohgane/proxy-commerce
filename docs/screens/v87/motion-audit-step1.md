# v87 STEP1 — 모션 검수 리포트

대상: `src/dashboard/web_ui.py` (콘솔 전 화면 공용 `_BASE_HTML` 컴포넌트 킷 + `_ORDERS_STYLE` 스코프 스타일)
브랜치: `feat/v87-console-redesign`
기준: `improve-animations` 스킬 AUDIT 8개 카테고리 (Emil Kowalski 모션 철학)

> **정직 표기:** `review-animations` 스킬은 이 CLI 세션에서 모델 호출이 비활성(`disable-model-invocation`)이라
> 실행하지 못했다. `improve-animations`는 정상 로드되어 그 AUDIT 기준으로 검수했다. 켠 척 하지 않는다(v20 선례).
> 이 리포트는 정적 코드 기준이며, **체감(feel) 판정은 배포 후 실기기 확인이 필요**한 항목을 아래에 따로 표시했다.

## 요약

STEP1에서 도입한 모션은 전부 `transform`/`opacity`(+색·보더) 한정이고 `transition: all`은 0건,
`scale(0)` 0건, 커스텀 커브는 `--ease-out: cubic-bezier(.23,1,.32,1)` / `--ease-drawer: cubic-bezier(.32,.72,0,1)`
토큰 단일 소스로 통일돼 있다. 검수에서 **자체 결함 3건을 찾아 이 PR 안에서 고쳤고**, 주문 화면(STEP2 소관)
잔여 4건은 아래 이월 목록으로 넘긴다.

## 이 PR에서 수정한 것 (STEP1 자체 결함)

| # | 심각도 | 카테고리 | 위치 | 결함 | 조치 |
|---|---|---|---|---|---|
| 1 | MEDIUM | 접근성 | `.kgp-btn:hover` | 터치 기기에서 `:hover`가 탭할 때 가짜로 걸려 버튼이 **뜬 채로 남음**. AUDIT §6이 명시적으로 지목하는 ungated hover motion. | `@media (hover:hover) and (pointer:fine)` 안으로 `translateY(-2px)` 이동. |
| 2 | MEDIUM | 접근성 | `prefers-reduced-motion` 블록 | 전역 `transition-duration:.01ms!important`로 **모션을 0으로 만듦**. AUDIT §6: "모션 감소는 모션 0이 아니다 — 이해를 돕는 불투명도·색 전이는 남겨야 한다." | 위치 이동(`transform`)만 제거하고 불투명도·색 전이는 존치. |
| 3 | MEDIUM | 이징 | `.kgp-skel` | 무한 반복 셔머에 `ease` — 루프 이음매마다 **멈칫**한다. AUDIT §2: 상시 모션은 `linear`. | `animation: kgpShim 1.4s linear infinite`. |

## STEP2로 이월 (주문 화면 `.kgp-oc` 스코프 — 이번 PR 범위 밖)

| # | 심각도 | 카테고리 | 위치 | 결함 | 권고값 |
|---|---|---|---|---|---|
| 4 | MEDIUM | 이징·지속 | `.kgp-oc-drawer` | 드로어 `.42s`(420ms). AUDIT 예산(200–500ms) 안이지만 **v87 브리프가 260ms를 명시**한다. | `transition: transform 260ms var(--ease-out)` — 브리프 준수. |
| 5 | LOW | 응집 | `.kgp-oc-scrim` | 딤 `.3s`(300ms)가 드로어 420ms보다 **120ms 먼저 끝나** 짝이 어긋난다. | 드로어와 동일 260ms로 맞춤. |
| 6 | MEDIUM | 응집·토큰 | `_ORDERS_STYLE` 전반 | `.18s`/`.12s`/`.15s`/`.3s`/`.42s`를 손으로 적어 `--dur`/`--dur-slow` 토큰을 안 쓴다. AUDIT §7의 "거의 같은 값 다섯 개" 통합 대상. | 전부 토큰 참조로. STEP2에서 `.kgp-oc`를 공용 킷에 흡수하며 자연 해소. |
| 7 | LOW | 물성 | `.kgp-oc .oc-ico:active` | 누름 피드백 `scale(.94)` — AUDIT §3 권장 범위(0.95–0.98)를 살짝 벗어난다. | `scale(.96)`. |

## 카테고리별 판정

| 카테고리 | 판정 |
|---|---|
| ① 목적·빈도 | **통과.** 장식용 모션 없음. 버튼 hover lift는 `gogabridj-design` 스킬이 명시 지정한 사항이라 결함으로 보지 않음(설계 결정 존중). |
| ② 이징·지속 | **수정 후 통과.** `ease-in` 0건. 전 구간 강한 ease-out 커스텀 커브. UI 300ms 이하 준수(드로어만 예외 예산 내). |
| ③ 물성·원점 | **통과.** `scale(0)` 0건. 토스트는 `translateY(10px)`+opacity로 진입(순수 페이드 아님). 누름 `scale(.97)`/120ms — 버튼 예산(100–160ms) 내. |
| ④ 중단 가능성 | **통과.** 토스트·드로어 모두 keyframes가 아닌 transition이라 진행 중 되돌리면 현재 상태에서 재조준된다. |
| ⑤ 성능 | **통과.** `transition: all` 0건. 애니메이트 대상은 transform/opacity/색/보더/그림자뿐 — 레이아웃 유발 속성 0건. |
| ⑥ 접근성 | **수정 후 통과.** (결함 1·2 수정) |
| ⑦ 응집·토큰 | **부분.** STEP1 킷은 토큰 일원화 완료. 주문 스코프 잔여는 결함 6으로 STEP2 이월. |
| ⑧ 놓친 기회 | 아래 참조. |

## 놓친 기회 (가산 항목 — 이번 PR 미적용)

1. **필터 전환이 순간이동한다.** 상품·업로드 화면의 마켓/번역 셀렉트는 `location.search`로 **전체 페이지를 새로 로드**해
   표가 툭 바뀐다. 킷에 `.kgp-skel`(스켈레톤)을 넣어뒀지만 **아직 쓰는 화면이 없다** — 전환 중 스켈레톤을 물리면
   가장 잦은 상호작용의 체감이 크게 붙는다. STEP3 후보.
2. **토스트·체크칩이 CSS만 있고 마크업이 없다.** `.kgp-toast`, `.kgp-skel`, `.kgp-chip`은 STEP1 킷 명세(브리프)에
   따라 정의만 해둔 상태로, 현재 이 3개는 **사용처 0**이다. STEP2(주문 체크칩)·STEP3에서 소비된다.
   지금은 미사용 CSS라는 점을 정직하게 표기한다.
3. **주문 상태 탭 전환도 전체 리로드다.** 결제완료→배송중 탭 이동이 페이지 새로고침이라 맥락이 끊긴다. STEP2에서
   드로어와 함께 다룰 후보.

## 체감 확인이 필요한 항목 (배포 후 실기기)

코드만으로 판정 불가 — 오너 배포 캡처 단계에서 확인:

- 드로어 슬라이드의 실제 무게감(260ms 적용 후 너무 빠른지) — STEP2.
- 버튼 hover lift가 밀도 높은 필터 바에서 산만한지.
- 셔머 1.4s linear의 속도가 실제 로딩 시간과 어울리는지.
