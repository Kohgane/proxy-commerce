# v53 STEP3 — 반응 초가속 (v52 내비 위에 적층)

## 선택: prerender vs prefetch
**Speculation Rules `prefetch`** 채택(브리프 "prerender/prefetch" 허용 범위). prerender는 백그라운드에서
페이지 JS를 실행(폴링·나이아 레일 중복 실행) + JS 스왑 엔진의 클릭 인터셉트와 경합. prefetch는 **문서만
받아 크롬 캐시에 저장(JS 미실행)** → 스왑 엔진의 `fetch()`가 그 캐시를 히트해 사실상 즉시, 충돌 0.

- `<script type="speculationrules">` prefetch, `where`: `/seller/*`, **로그아웃·sign-out·delete·bulk-delete 제외**,
  eagerness **moderate**(hover/pointerdown).
- **View Transitions**: 스왑 엔진 DOM 교체를 `document.startViewTransition(_apply)`로 감쌈(미지원/RM이면 즉시
  교체) + `@view-transition { navigation: auto }`(MPA 폴백 전환). reduced-motion이면 전환 애니메이션 정지.
- **드로어 데이터 hover 선행 로드**: 목록 행(`.kgp-open-drawer`)에 마우스 올리면 상품 상세를 `fetch`(동시 1건,
  중복 제거)로 **서버 렌더 경로(DB 풀·템플릿) 워밍** → 클릭 시 iframe 로드 체감 단축. 저장 스테일 방지 위해
  iframe의 `?t=` 캐시버스트는 유지(hover fetch는 워밍 전용, 응답 버림).

## 판정 (오너)
서울 실기기 녹화 — 주요 4페이지(수집이력·카탈로그·대시보드·드로어) 왕복이 스피너 없이 즉시 + View
Transitions 크로스페이드, Performance 탭 전환 구간 캡처.

## 가드
test_v53_prerender_bookmarklet(STEP3 4): speculation rules(prefetch·moderate·로그아웃/삭제 제외)·View
Transitions 배선·드로어 hover 동시1·warm 엔드포인트 200.
