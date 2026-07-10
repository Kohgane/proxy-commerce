# v52 STEP1 — 인스턴트 내비게이션 엔진

## 선택 근거 (자작 vs Turbo Drive)
**자작 ~2KB 채택.** Turbo Drive는 ~40KB + `data-turbo-permanent`/`data-turbo-eval` 규약 도입 + 인라인
스크립트 재평가가 우리 페이지별 무거운 인라인 스크립트(폴링·드로어·나이아 레일)와 충돌 위험. 우리는 `<main>`
단일 스왑 + 명시적 teardown 훅만 필요하므로 자작이 더 작고 통제 가능. **핵심 안전장치: 어떤 오류든 즉시
`location.assign(url)` 일반 내비로 강등 → 엔진이 죽어도 내비는 산다.**

## 엔진 (`_base.html` 인라인, 전 페이지 공통)
- **프리패치**: `mouseover`/`touchstart`/`focusin` 시 href를 `fetch`해 **메모리 캐시**(TTL 30초, 동시 2건 제한).
  `X-KGP-Nav:1` 헤더. 로그아웃·`data-no-swap`·`data-method`·`_blank`·`download`·외부·`javascript:` 제외.
- **클릭 스왑**: 동일 오리진 `<a>` 클릭 → 캐시(히트 시 네트워크 0) 또는 fetch → 새 문서의 `main.console-content`
  **innerHTML만 교체**(CSS/JS 재로드 없음) + `<title>` + `history.pushState` + 스크롤(신규 top·뒤로 복원).
- **스크립트 재실행**: 스왑된 `<main>` 내부 + `#kgp-page-js`(=`extra_js` 래퍼)의 `<script>`를 재생성해 실행 →
  드로어·나이아 레일·토스트·폴링 등 페이지 초기화가 스왑 후에도 작동. 이미 로드된 외부 스크립트는 재실행 안 함.
- **teardown 훅**: 스왑 직전 `window.__kgpTeardown` 전 함수 실행 후 비움 → 폴링 인터벌 등 정리(누수·중복 방지).
  수집이력 8초 폴링을 등록.
- **진행바 + skeleton**(기존 v51)은 스왑 생명주기에 연동. `popstate`(뒤/앞) 처리. reduced-motion 존중.

## "끝에서 끈다" 제거 (전송 최적화만 — 패밀리·색·토큰 불변)
- **Noto Serif KR 미사용 굵기 제거**: 실사 결과 콘솔 세리프(`--font-display`)는 **600만**(h1·pc-display 등
  전부 `--w-semi=600`), 랜딩은 **900**(hero·KPI·scard·sec-head) + 500(plain). 콘솔 `wght@500;600;700→600`,
  랜딩 `500;700;900→500;900`(700은 세리프 아님=Pretendard). `display=swap` 유지.
- **bootstrap JS**: body 끝 배치라 이미 렌더 비차단(뒤 인라인 스크립트가 의존 → defer는 순서 깨 미사용, 현 배치가
  defer와 동일 효과). 목록 썸네일 `loading=lazy decoding=async`(기존).

## 판정 (오너 실기기)
서울 실기기 화면녹화: 수집이력→카탈로그→드로어→대시보드 연속 이동, 각 전환 **스피너 없이 콘텐츠 즉시 교체**.
크롬 Performance 탭 전환 1회 클릭→콘텐츠 표시 ≤150ms(prefetch 히트) 캡처. 탭 스피너 1초+ 잔류 시 불합격.
⚠️ 스왑 후 **중복 폴링/리스너 누수 여부**를 콘솔·네트워크 탭에서 확인(teardown 커버 범위 밖 전역 리스너는
멱등적이나 오너 실기기 확인 권장). 문제 링크는 `data-no-swap`으로 일반 내비 강등 가능.

## 가드
test_v52_instant_nav(5): 엔진 소스계약·폴링 teardown·**node로 eligible() 링크 필터링 실증**(내부만 스왑, 로그아웃/
외부/_blank/download/js/no-swap 제외)·폰트 굵기 축소·목록 lazy. 전 페이지 렌더 200(base 변경 회귀 0).
