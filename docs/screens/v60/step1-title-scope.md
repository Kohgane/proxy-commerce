# v60 STEP1 — 제목 추출 오염 차단 (title-fix)

## 오너 캡처 근원
아마존 수집 제목 = **"Chat history"** — 확장 사이드패널/오버레이(또는 우리 확장)의 h1을 상품명으로 오인.
`document.querySelector("h1")`가 페이지 첫 h1(삽입 UI)을 잡음.

## 수리
- `_isInjectedUI(el)`: 우리 확장 주입 DOM(`kgp-*` id/class·data-kgp-outline) + 사이드패널/챗/어시스턴트/네비
  (`nav`·`aside`·`header`·`role=complementary/navigation/dialog`·`assistant|chat|sidebar|rufus|panel|overlay|widget`) 제외.
- `_adapterTitle()`: 디폴트 소싱처 상품명 하드매핑 — 아마존 `#productTitle`, 테무 `goods-name`, 알리·타오바오 등.
- `_cleanH1()`: 본문 h1 중 UI·비상품 영역 제외한 최장(상품명 후보).
- **우선순위**: 어댑터 셀렉터 → ld+json/state name(Tier1) → 본문 h1(UI 제외) → og:title → document.title(최후).

## 판정 (real Chromium)
페이지에 'Chat history' 사이드패널(role=complementary) + 우리 FAB(kgp-collect-fab) h1 + 상품 #productTitle 공존:
```
BEFORE: 첫 h1 = 'Chat history' → 오염
AFTER : title = 'andobil [2026 Ultra-Thin] Magnetic Phone Grip Ring Holder'
```
가드 test_v60_title_scope(삽입 UI 존재 상태 픽스처 — 오염 0). 회귀 계약 test_v58_extract_contract 3사이트 유지.
확장 manifest 1.5.58→1.5.59.

## 파급
제목 오염이 STEP4(AI 초안 키워드)의 'Chat history'류 오염어의 **근원** — 제목 정화로 키워드 소스가 함께 정화됨.

## 오너 검증 (배포 후 실기기)
아마존 동일 상품 재수집 → 제목="andobil …" 정상. 확장 1.5.59 재로딩.
